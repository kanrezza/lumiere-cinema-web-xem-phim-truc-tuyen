"""Active members should use their benefits instead of seeing repeat upsells."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Movie, Plan


class VipPersonalizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.member = users.objects.create_user(
            'personalized-vip', 'personalized-vip@example.test',
            vip_until=timezone.now() + timedelta(days=30),
        )
        cls.free = users.objects.create_user('personalized-free', 'personalized-free@example.test')
        cls.expired = users.objects.create_user(
            'personalized-expired', 'personalized-expired@example.test',
            vip_until=timezone.now() - timedelta(days=1),
        )
        cls.movie = Movie.objects.create(title='A ready film', slug='personalized-ready', published=True)
        cls.episode = Episode.objects.create(movie=cls.movie, title='Complete film', status='ready', duration=600)
        Plan.objects.create(name='VIP Monthly Personalization', price=59000, days=30)
        Plan.objects.create(name='VIP Annual Personalization', price=599000, days=365)

    def membership_section(self, response):
        return response.content.decode().split('id="membership"', 1)[1].split('</section>', 1)[0]

    def together_banner(self, response):
        return response.content.decode().split('<section class="together-banner">', 1)[1].split('</section>', 1)[0]

    def test_active_member_welcome_shows_current_rights_without_plan_prices(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 200)
        section = self.membership_section(response)
        self.assertIn('VIP ĐANG HOẠT ĐỘNG', section)
        self.assertIn(timezone.localtime(self.member.vip_until).strftime('%d/%m/%Y'), section)
        self.assertIn('href="' + reverse('catalog') + '?access=vip"', section)
        self.assertIn('href="' + reverse('plans') + '"', section)
        self.assertIn('Quản lý VIP', section)
        self.assertNotIn('59.000', section)
        self.assertNotIn('599.000', section)
        self.assertNotIn('VIP Monthly Personalization', section)
        self.assertNotIn('Khám phá gói VIP', section)

    def test_active_member_welcome_ctas_start_real_watch_together_flow(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('landing'))
        self.assertContains(response, 'Tiếp tục khám phá')
        self.assertContains(response, reverse('watch', args=[self.episode.pk]) + '#watch-together')
        self.assertNotContains(response, 'Khám phá quyền lợi xem chung')
        self.assertNotContains(response, 'Tìm hiểu xem chung')

    def test_active_member_welcome_header_links_to_existing_membership(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('landing'))
        header = response.content.decode().split('<header', 1)[1].split('</header>', 1)[0]
        self.assertIn('Khám phá phim', header)
        self.assertIn('VIP của bạn', header)
        self.assertIn('href="' + reverse('plans') + '"', header)
        self.assertNotIn('Đăng nhập', header)
        self.assertNotIn('Đăng ký', header)

    def test_guest_welcome_keeps_purchase_options_and_signup(self):
        response = self.client.get(reverse('landing'))
        section = self.membership_section(response)
        self.assertIn('VIP Monthly Personalization', section)
        self.assertIn('59.000', section)
        self.assertIn('599.000', section)
        self.assertIn('Tạo tài khoản', section)
        self.assertNotIn('VIP ĐANG HOẠT ĐỘNG', section)

    def test_free_and_expired_members_can_still_discover_upgrade_options(self):
        for user in (self.free, self.expired):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse('landing'))
                section = self.membership_section(response)
                self.assertIn('VIP Monthly Personalization', section)
                self.assertIn('Khám phá gói VIP', section)
                self.assertNotIn('VIP ĐANG HOẠT ĐỘNG', section)
                banner = self.together_banner(self.client.get(reverse('catalog')))
                self.assertIn('Khám phá Lumière VIP', banner)
                self.assertIn('href="' + reverse('plans') + '"', banner)

    def test_active_member_catalog_links_to_a_ready_episode_not_an_upgrade(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('catalog'))
        banner = self.together_banner(response)
        self.assertIn('Bắt đầu xem chung', banner)
        self.assertIn('href="' + reverse('watch', args=[self.episode.pk]) + '#watch-together"', banner)
        self.assertNotIn('Khám phá Lumière VIP', banner)
        # The VIP genre-bar link is a content filter, so it remains available.
        self.assertContains(response, 'href="' + reverse('catalog') + '?access=vip"')

    def test_member_without_ready_films_gets_discovery_fallback_not_fake_watch_url(self):
        Episode.objects.filter(pk=self.episode.pk).update(status='processing')
        self.client.force_login(self.member)
        response = self.client.get(reverse('catalog'))
        banner = self.together_banner(response)
        self.assertIn('Bắt đầu xem chung', banner)
        self.assertIn('href="' + reverse('catalog') + '"', banner)
        self.assertNotIn('/watch/', banner)
        landing = self.client.get(reverse('landing'))
        self.assertNotContains(landing, reverse('watch', args=[self.episode.pk]) + '#watch-together')
