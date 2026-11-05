"""Public trailers remain separate from full-film availability and membership."""
from datetime import timedelta
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Episode, History, Movie
from .views import catalog_movies


class TrailerMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.buttons = []
        self.iframes = []
        self.videos = []
        self.sources = []
        self.nested_anchor = False
        self._anchor_depth = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.nested_anchor |= self._anchor_depth > 0
            self._anchor_depth += 1
            self.links.append(attrs)
        elif tag == 'button':
            self.buttons.append(attrs)
        elif tag == 'iframe':
            self.iframes.append(attrs)
        elif tag == 'video':
            self.videos.append(attrs)
        elif tag == 'source':
            self.sources.append(attrs)

    def handle_endtag(self, tag):
        if tag == 'a':
            self._anchor_depth = max(0, self._anchor_depth - 1)


class TrailerExperienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.viewer = users.objects.create_user('trailer-ui-viewer', 'trailer-ui@example.test')
        cls.member = users.objects.create_user(
            'trailer-ui-member', 'trailer-ui-member@example.test',
            vip_until=timezone.now() + timedelta(days=30),
        )
        cls.future = Movie.objects.create(
            title='Upcoming cinema film', slug='trailer-ui-future', description='A future feature.',
            published=True, is_vip=True, is_cinema_release=True,
            trailer_url='https://www.youtube.com/watch?v=aqz-KE-bpKQ',
        )
        cls.ready = Movie.objects.create(
            title='Ready cinema film', slug='trailer-ui-ready', description='A complete feature.',
            published=True, is_vip=True, is_cinema_release=True,
            trailer_url='https://youtu.be/aqz-KE-bpKQ',
        )
        cls.episode = Episode.objects.create(movie=cls.ready, title='Full film', status='ready', duration=600)
        cls.plain = Movie.objects.create(title='Waiting without trailer', slug='trailer-ui-plain', published=True)
        cls.draft = Movie.objects.create(
            title='Private trailer title', slug='trailer-ui-draft', published=False,
            trailer_url='https://youtu.be/aqz-KE-bpKQ',
        )

    def card(self, film, user=None):
        return render_to_string('cinema/card.html', {
            'movie': catalog_movies().get(pk=film.pk), 'portrait': True,
            'user': user or AnonymousUser(),
        })

    def test_unready_cinema_card_exposes_trailer_without_fake_full_film_target(self):
        html = self.card(self.future)
        parsed = TrailerMarkup(html)
        trigger = next(button for button in parsed.buttons if 'quickview-trigger' in button.get('class', ''))
        self.assertIn('Đang chuẩn bị', html)
        self.assertIn('Chiếu rạp', html)
        self.assertNotIn('Đang chiếu rạp', html)
        self.assertEqual(trigger['data-movie-cinema'], '1')
        self.assertEqual(trigger['data-movie-trailer'], reverse('trailer', args=[self.future.slug]))
        self.assertEqual(trigger['data-movie-ready'], '0')
        self.assertEqual(trigger['data-movie-play'], '')
        self.assertTrue(any(link.get('href') == reverse('trailer', args=[self.future.slug]) for link in parsed.links))
        self.assertFalse(parsed.nested_anchor)

    def test_ready_vip_keeps_full_film_membership_gate_and_public_trailer(self):
        for user, target in (
            (AnonymousUser(), reverse('plans')),
            (self.viewer, reverse('plans')),
            (self.member, reverse('watch', args=[self.episode.pk])),
        ):
            with self.subTest(user=str(user)):
                parsed = TrailerMarkup(self.card(self.ready, user))
                trigger = next(button for button in parsed.buttons if 'quickview-trigger' in button.get('class', ''))
                self.assertEqual(trigger['data-movie-play'], target)
                self.assertEqual(trigger['data-movie-trailer'], reverse('trailer', args=[self.ready.slug]))
                self.assertEqual(trigger['data-movie-ready'], '1')

    def test_plain_card_clears_trailer_and_cinema_data_for_reused_quickview(self):
        html = self.card(self.plain)
        parsed = TrailerMarkup(html)
        trigger = next(button for button in parsed.buttons if 'quickview-trigger' in button.get('class', ''))
        self.assertEqual(trigger['data-movie-trailer'], '')
        self.assertEqual(trigger['data-movie-cinema'], '0')
        self.assertNotIn('card-trailer-link', html)
        self.assertNotIn('cinema-tag', html)

    def test_unready_detail_offers_trailer_and_explains_missing_full_film(self):
        response = self.client.get(reverse('movie', args=[self.future.slug]))
        self.assertContains(response, reverse('trailer', args=[self.future.slug]))
        self.assertContains(response, 'Phim đang được chuẩn bị')
        self.assertContains(response, 'Bản phim đầy đủ chưa sẵn sàng')
        self.assertContains(response, 'Phim chiếu rạp')
        self.assertNotContains(response, 'href="' + reverse('watch', args=[self.episode.pk]) + '"')

    def test_guest_can_open_vip_trailer_without_loading_youtube_before_play(self):
        response = self.client.get(reverse('trailer', args=[self.future.slug]))
        self.assertEqual(response.status_code, 200)
        parsed = TrailerMarkup(response.content.decode())
        button = next(button for button in parsed.buttons if 'data-trailer-load' in button)
        self.assertEqual(button['data-trailer-embed'], self.future.trailer_embed_url)
        self.assertEqual(parsed.iframes, [])
        self.assertEqual(parsed.videos, [])
        self.assertContains(response, 'Chưa có bản xem')
        self.assertContains(response, 'Bản phim đầy đủ đang được chuẩn bị')
        self.assertEqual(History.objects.count(), 0)

    def test_published_file_trailer_uses_native_controls_without_autoplay(self):
        film = Movie.objects.create(
            title='Uploaded trailer film', slug='trailer-ui-file', published=True,
            trailer_file='trailers/0123456789abcdef0123456789abcdef.mp4',
        )
        response = self.client.get(reverse('trailer', args=[film.slug]))
        self.assertEqual(response.status_code, 200)
        parsed = TrailerMarkup(response.content.decode())
        self.assertEqual(len(parsed.videos), 1)
        video = parsed.videos[0]
        self.assertIn('controls', video)
        self.assertIn('playsinline', video)
        self.assertNotIn('autoplay', video)
        self.assertEqual(video['preload'], 'metadata')
        self.assertEqual(parsed.sources[0]['src'], film.trailer_file.url)
        self.assertEqual(parsed.sources[0]['type'], 'video/mp4')
        self.assertEqual(parsed.iframes, [])

    def test_hidden_and_missing_trailers_do_not_expose_public_player_pages(self):
        for movie in (self.draft, self.plain):
            with self.subTest(movie=movie.slug):
                self.assertEqual(self.client.get(reverse('trailer', args=[movie.slug])).status_code, 404)

    def test_public_trailer_does_not_remove_full_film_authentication_or_vip_checks(self):
        self.assertEqual(self.client.get(reverse('trailer', args=[self.ready.slug])).status_code, 200)
        self.assertEqual(self.client.get(reverse('watch', args=[self.episode.pk])).status_code, 302)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('trailer', args=[self.ready.slug])).status_code, 200)
        self.assertEqual(self.client.get(reverse('watch', args=[self.episode.pk])).status_code, 403)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('watch', args=[self.episode.pk])).status_code, 200)

    def test_title_data_is_escaped_in_the_trailer_markup(self):
        self.future.title = 'A "quote" <script>alert(1)</script>'
        self.future.save(update_fields=['title'])
        response = self.client.get(reverse('trailer', args=[self.future.slug]))
        parsed = TrailerMarkup(response.content.decode())
        button = next(button for button in parsed.buttons if 'data-trailer-load' in button)
        self.assertEqual(button['data-trailer-title'], self.future.title)
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_trailer_credit_shows_attribution_and_links_without_executing_html(self):
        self.future.trailer_credit = '© 2008 Blender Foundation · CC BY 3.0\nhttps://creativecommons.org/licenses/by/3.0/ <script>alert(1)</script>'
        self.future.save(update_fields=['trailer_credit'])
        response = self.client.get(reverse('trailer', args=[self.future.slug]))
        self.assertContains(response, '© 2008 Blender Foundation · CC BY 3.0')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        parsed = TrailerMarkup(response.content.decode())
        self.assertTrue(any(link.get('href') == 'https://creativecommons.org/licenses/by/3.0/' for link in parsed.links))
