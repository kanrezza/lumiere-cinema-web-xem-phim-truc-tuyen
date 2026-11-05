"""Membership entry points distinguish active members from prospective buyers."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Movie, Order, Plan


class VipMembershipExperienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.member = users.objects.create_user('vip-active-viewer', 'vip-active@example.test', vip_until=timezone.now() + timedelta(days=90))
        cls.expired = users.objects.create_user('vip-expired-viewer', 'vip-expired@example.test', vip_until=timezone.now() - timedelta(days=1))
        cls.regular = users.objects.create_user('vip-regular-viewer', 'vip-regular@example.test')
        cls.plan = Plan.objects.create(name='VIP Tháng', price=59000, days=30)
        cls.movie = Movie.objects.create(title='Ready public film', slug='vip-ready-public', published=True)
        cls.episode = Episode.objects.create(movie=cls.movie, title='Full film', status='ready', duration=600)
        draft = Movie.objects.create(title='Private film', slug='vip-ready-private', published=False)
        Episode.objects.create(movie=draft, title='Private episode', status='ready')

    def test_active_member_sees_benefits_instead_of_sales_pitch_or_plan_form(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('plans'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['member_dashboard'])
        self.assertFalse(response.context['renewing'])
        self.assertContains(response, 'VIP của bạn đang hoạt động.')
        self.assertContains(response, 'Quyền lợi đang có')
        self.assertContains(response, reverse('plans') + '?renew=1')
        self.assertContains(response, reverse('watch', args=[self.episode.pk]) + '#watch-together')
        self.assertNotContains(response, 'id="membership-form"')
        self.assertNotContains(response, 'Chọn gói của bạn')
        self.assertNotContains(response, 'Thêm phim hay.')
        self.assertNotContains(response, 'Chưa thể mua gói')
        self.assertEqual(Order.objects.count(), 0)

    def test_member_explicitly_opens_renewal_options(self):
        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse('profile')), 'href="' + reverse('plans') + '?renew=1"')
        response = self.client.get(reverse('plans'), {'renew': '1'})
        self.assertFalse(response.context['member_dashboard'])
        self.assertTrue(response.context['renewing'])
        self.assertContains(response, 'Gia hạn VIP theo nhu cầu của bạn.')
        self.assertContains(response, 'Chọn thời gian gia hạn')
        self.assertContains(response, 'id="membership-form"')
        self.assertContains(response, 'Quay lại VIP của bạn')
        self.assertNotContains(response, 'Bạn vẫn có thể xem phim miễn phí')
        self.assertEqual(Order.objects.count(), 0)

    def test_guest_regular_and_expired_members_can_still_choose_a_plan(self):
        for user in (None, self.regular, self.expired):
            with self.subTest(user=user):
                if user:
                    self.client.force_login(user)
                else:
                    self.client.logout()
                response = self.client.get(reverse('plans'))
                self.assertFalse(response.context['member_dashboard'])
                self.assertFalse(response.context['renewing'])
                self.assertContains(response, 'Chọn gói của bạn')
                self.assertContains(response, 'id="membership-form"')
                self.assertNotContains(response, 'VIP của bạn đang hoạt động.')

    def test_renew_parameter_does_not_grant_membership_or_change_status(self):
        self.client.force_login(self.regular)
        response = self.client.get(reverse('plans'), {'renew': '1'})
        self.assertFalse(response.context['renewing'])
        self.assertContains(response, 'Chọn gói của bạn')
        self.regular.refresh_from_db()
        self.assertIsNone(self.regular.vip_until)
        self.assertEqual(Order.objects.count(), 0)
        self.client.force_login(self.member)
        self.assertTrue(self.client.get(reverse('plans'), {'renew': 'true'}).context['member_dashboard'])

    def test_member_view_does_not_depend_on_payment_configuration_or_available_plans(self):
        self.client.force_login(self.member)
        Plan.objects.all().delete()
        with override_settings(VNPAY_TMN_CODE='', VNPAY_HASH_SECRET=''):
            response = self.client.get(reverse('plans'))
        self.assertTrue(response.context['member_dashboard'])
        self.assertContains(response, 'VIP của bạn đang hoạt động.')
        self.assertNotContains(response, 'Thanh toán đang được thiết lập')

    def test_watch_together_action_does_not_point_at_an_unready_or_hidden_episode(self):
        self.client.force_login(self.member)
        self.episode.status = 'processing'
        self.episode.save(update_fields=['status'])
        response = self.client.get(reverse('plans'))
        self.assertEqual(response.context['watch_together_url'], reverse('catalog'))
