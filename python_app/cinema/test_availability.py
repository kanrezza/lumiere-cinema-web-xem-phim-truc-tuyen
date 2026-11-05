from datetime import timedelta
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Movie, Watchlist
from .views import catalog_movies


class CardParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.trigger = None
        self.badges = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if tag == 'button' and 'quickview-trigger' in classes:
            self.trigger = attrs
        if 'card-availability' in classes:
            self.badges.append(attrs)


class AvailabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.viewer = users.objects.create_user('availability-viewer', 'availability@example.test')
        cls.vip = users.objects.create_user(
            'availability-vip', 'availability-vip@example.test',
            vip_until=timezone.now() + timedelta(days=30),
        )
        cls.future = Movie.objects.create(title='Future public film', slug='availability-future', published=True)
        cls.ready = Movie.objects.create(title='Ready free film', slug='availability-ready', published=True)
        cls.episode = Episode.objects.create(movie=cls.ready, title='Full film', status='ready', duration=600)
        cls.paid = Movie.objects.create(title='Ready VIP film', slug='availability-paid', published=True, is_vip=True)
        cls.paid_episode = Episode.objects.create(movie=cls.paid, title='VIP film', status='ready', duration=600)

    def card(self, movie, user=None):
        movie = catalog_movies().get(pk=movie.pk)
        html = render_to_string('cinema/card.html', {'movie': movie, 'portrait': True, 'user': user or AnonymousUser()})
        return html, CardParser(html)

    def test_unready_film_has_visible_preparing_state_and_no_playback_target(self):
        for user in (AnonymousUser(), self.viewer, self.vip):
            with self.subTest(user=str(user)):
                html, parsed = self.card(self.future, user)
                self.assertIn('Đang chuẩn bị', html)
                self.assertTrue(parsed.badges)
                self.assertEqual(parsed.trigger['data-movie-ready'], '0')
                self.assertEqual(parsed.trigger['data-movie-play'], '')
                self.assertIn('chưa sẵn sàng', parsed.trigger['data-movie-status-message'])

    def test_unready_vip_never_promises_playback_after_purchase(self):
        self.future.is_vip = True
        self.future.save(update_fields=['is_vip'])
        for user in (AnonymousUser(), self.vip):
            with self.subTest(user=str(user)):
                html, parsed = self.card(self.future, user)
                self.assertIn('Đang chuẩn bị', html)
                self.assertEqual(parsed.trigger['data-movie-status'], 'Đang chuẩn bị')
                self.assertEqual(parsed.trigger['data-movie-play'], '')

    def test_ready_vip_points_a_regular_viewer_to_membership(self):
        for user in (AnonymousUser(), self.viewer):
            with self.subTest(user=str(user)):
                _, parsed = self.card(self.paid, user)
                self.assertEqual(parsed.trigger['data-movie-ready'], '1')
                self.assertEqual(parsed.trigger['data-movie-status'], 'Xem với VIP')
                self.assertEqual(parsed.trigger['data-movie-play'], reverse('plans'))
                self.assertIn('gói VIP còn hiệu lực', parsed.trigger['data-movie-status-message'])

    def test_ready_vip_points_a_member_to_the_actual_episode(self):
        html, parsed = self.card(self.paid, self.vip)
        self.assertIn('Có thể xem', html)
        self.assertEqual(parsed.trigger['data-movie-play'], reverse('watch', args=[self.paid_episode.pk]))
        self.assertEqual(parsed.trigger['data-movie-play-label'], 'Xem ngay')

    def test_ready_free_film_tells_a_guest_to_sign_in(self):
        html, parsed = self.card(self.ready)
        self.assertIn('Đã có phim', html)
        self.assertEqual(parsed.trigger['data-movie-play-label'], 'Đăng nhập để xem')
        self.assertIn('Đăng nhập', parsed.trigger['data-movie-status-message'])
        self.assertEqual(parsed.trigger['data-movie-play'], reverse('watch', args=[self.episode.pk]))

    def test_unready_badges_are_shared_by_welcome_catalog_and_library(self):
        for route in ('landing', 'catalog'):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertContains(response, 'card-availability--preparing')
                self.assertContains(response, 'data-movie-status="Đang chuẩn bị"')
        Watchlist.objects.create(user=self.viewer, movie=self.future)
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('library'))
        self.assertContains(response, 'card-availability--preparing')
        self.assertContains(response, 'data-movie-status="Đang chuẩn bị"')
