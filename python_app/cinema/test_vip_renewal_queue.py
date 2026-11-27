"""Paid VIP periods preserve remaining time and become current without a job."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Order, Plan
from .payments import issue_checkout_token, signature


@override_settings(VNPAY_TMN_CODE='TESTCODE', VNPAY_HASH_SECRET='queue-test-secret-only')
class VipRenewalQueueTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now().replace(microsecond=0)
        self.user = get_user_model().objects.create_user('renewal-viewer', 'renewal@example.invalid')
        self.month = Plan.objects.create(name='VIP Tháng', price=59000, days=30)
        self.year = Plan.objects.create(name='VIP Năm', price=599000, days=365)

    def order(self, plan):
        return Order.objects.create(
            user=self.user, plan=plan, amount=plan.price, days=plan.days,
            plan_name_snapshot=plan.name,
        )

    def params(self, order, **changes):
        params = {
            'vnp_TmnCode': 'TESTCODE', 'vnp_TxnRef': order.pk.hex,
            'vnp_Amount': str(order.amount * 100), 'vnp_ResponseCode': '00',
            'vnp_TransactionStatus': '00', 'vnp_TransactionNo': order.pk.hex,
        }
        params.update(changes)
        params['vnp_SecureHash'] = signature(params)
        return params

    def confirm(self, order, *, at=None, **changes):
        with patch('cinema.payments.timezone.now', return_value=at or self.now):
            response = self.client.get(reverse('ipn'), self.params(order, **changes))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def active_month(self):
        month = self.order(self.month)
        paid_at = self.now - timedelta(days=10)
        Order.objects.filter(pk=month.pk).update(created_at=paid_at)
        self.assertEqual(self.confirm(month, at=paid_at)['RspCode'], '00')
        month.refresh_from_db()
        self.user.refresh_from_db()
        return month

    def timeline(self, at=None):
        from .memberships import membership_timeline

        self.user.refresh_from_db()
        return membership_timeline(self.user, now=at or self.now)

    def test_year_purchase_starts_after_the_remaining_month_and_only_after_paid_confirmation(self):
        month = self.active_month()
        annual = self.order(self.year)
        remaining_month_end = month.period_end
        self.user.refresh_from_db()
        self.assertEqual(self.user.vip_until, remaining_month_end)
        self.assertIsNone(annual.period_start)
        self.assertIsNone(annual.period_end)

        confirmation = self.now + timedelta(hours=2)
        self.assertEqual(self.confirm(annual, at=confirmation)['RspCode'], '00')
        annual.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(annual.paid_at, confirmation)
        self.assertEqual(annual.period_start, remaining_month_end)
        self.assertEqual(annual.period_end, remaining_month_end + timedelta(days=365))
        self.assertEqual(self.user.vip_until, annual.period_end)
        self.assertEqual(month.period_end, remaining_month_end)

    def test_queued_year_becomes_current_at_the_exact_month_boundary_without_a_worker(self):
        month = self.active_month()
        annual = self.order(self.year)
        self.assertEqual(self.confirm(annual)['RspCode'], '00')
        annual.refresh_from_db()
        before = self.timeline(month.period_end - timedelta(microseconds=1))
        self.assertEqual(before['current'].pk, month.pk)
        self.assertEqual([order.pk for order in before['queued']], [annual.pk])
        self.assertEqual(before['current_until'], month.period_end)

        boundary = self.timeline(month.period_end)
        self.assertEqual(boundary['current'].pk, annual.pk)
        self.assertEqual(list(boundary['queued']), [])
        self.assertEqual(boundary['current_until'], annual.period_end)
        self.assertEqual(boundary['active_until'], annual.period_end)
        self.user.refresh_from_db()
        self.assertEqual(self.user.vip_until, annual.period_end)

    def test_new_and_expired_members_start_their_paid_period_at_confirmation(self):
        for old_expiry in (None, self.now - timedelta(days=5)):
            with self.subTest(previous_expiry=old_expiry):
                get_user_model().objects.filter(pk=self.user.pk).update(vip_until=old_expiry)
                order = self.order(self.year)
                self.assertEqual(self.confirm(order)['RspCode'], '00')
                order.refresh_from_db()
                self.user.refresh_from_db()
                self.assertEqual(order.period_start, self.now)
                self.assertEqual(order.period_end, self.now + timedelta(days=365))
                self.assertEqual(self.user.vip_until, order.period_end)

    def test_order_created_while_vip_was_active_is_not_backdated_if_confirmation_arrives_after_expiry(self):
        month = self.active_month()
        annual = self.order(self.year)
        confirmation = month.period_end + timedelta(hours=3)
        self.assertEqual(self.confirm(annual, at=confirmation)['RspCode'], '00')
        annual.refresh_from_db()
        self.assertEqual(annual.period_start, confirmation)
        self.assertEqual(annual.period_end, confirmation + timedelta(days=365))

    def test_repeated_success_callback_does_not_append_the_year_twice_or_move_its_dates(self):
        self.active_month()
        annual = self.order(self.year)
        self.assertEqual(self.confirm(annual)['RspCode'], '00')
        annual.refresh_from_db()
        original_period = (annual.period_start, annual.period_end, annual.paid_at)
        self.assertEqual(self.confirm(annual, at=self.now + timedelta(hours=4))['RspCode'], '02')
        annual.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual((annual.period_start, annual.period_end, annual.paid_at), original_period)
        self.assertEqual(self.user.vip_until, original_period[1])

    def test_different_orders_append_by_confirmation_order_instead_of_creation_order(self):
        current_month = self.active_month()
        annual_created_first = self.order(self.year)
        extra_month_created_second = self.order(self.month)
        self.assertEqual(self.confirm(extra_month_created_second, at=self.now + timedelta(minutes=1))['RspCode'], '00')
        self.assertEqual(self.confirm(annual_created_first, at=self.now + timedelta(minutes=2))['RspCode'], '00')
        extra_month_created_second.refresh_from_db()
        annual_created_first.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(extra_month_created_second.period_start, current_month.period_end)
        self.assertEqual(annual_created_first.period_start, extra_month_created_second.period_end)
        self.assertEqual(self.user.vip_until, current_month.period_end + timedelta(days=395))
        self.assertEqual(
            [order.pk for order in self.timeline()['queued']],
            [extra_month_created_second.pk, annual_created_first.pk],
        )

    def test_failed_payment_does_not_queue_a_year_or_change_the_existing_expiry(self):
        current = self.active_month()
        annual = self.order(self.year)
        self.assertEqual(self.confirm(annual, vnp_ResponseCode='24', vnp_TransactionStatus='02')['RspCode'], '00')
        annual.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(annual.status, 'failed')
        self.assertIsNone(annual.period_start)
        self.assertIsNone(annual.period_end)
        self.assertEqual(self.user.vip_until, current.period_end)
        self.assertEqual(list(self.timeline()['queued']), [])

    def test_wrong_amount_and_signature_do_not_allocate_a_period(self):
        current = self.active_month()
        amount_order = self.order(self.year)
        self.assertEqual(self.confirm(amount_order, vnp_Amount='1')['RspCode'], '04')
        signature_order = self.order(self.year)
        params = self.params(signature_order)
        params['vnp_SecureHash'] = '0' * 128
        self.assertEqual(self.client.get(reverse('ipn'), params).json()['RspCode'], '97')
        for order in (amount_order, signature_order):
            order.refresh_from_db()
            self.assertEqual(order.status, 'pending')
            self.assertIsNone(order.period_start)
            self.assertIsNone(order.period_end)
        self.user.refresh_from_db()
        self.assertEqual(self.user.vip_until, current.period_end)

    def test_old_paid_orders_with_no_period_are_not_used_to_guess_current_or_queued_plans(self):
        expiry = self.now + timedelta(days=20)
        get_user_model().objects.filter(pk=self.user.pk).update(vip_until=expiry)
        legacy = self.order(self.month)
        legacy.status = 'paid'
        legacy.paid_at = self.now - timedelta(days=10)
        legacy.save(update_fields=['status', 'paid_at'])
        timeline = self.timeline()
        self.assertIsNone(timeline['current'])
        self.assertEqual(list(timeline['queued']), [])
        self.assertEqual(timeline['active_until'], expiry)
        legacy.refresh_from_db()
        self.assertIsNone(legacy.period_start)
        self.assertIsNone(legacy.period_end)

    def test_administrator_expiry_remains_authoritative_over_a_previously_queued_period(self):
        month = self.active_month()
        annual = self.order(self.year)
        self.assertEqual(self.confirm(annual)['RspCode'], '00')
        get_user_model().objects.filter(pk=self.user.pk).update(vip_until=month.period_end)
        timeline = self.timeline()
        self.assertEqual(timeline['current'].pk, month.pk)
        self.assertEqual(list(timeline['queued']), [])
        self.assertEqual(timeline['active_until'], month.period_end)

    def test_erased_account_payment_is_reconciled_without_allocating_vip(self):
        annual = self.order(self.year)
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False, erased_at=self.now, vip_until=None)
        self.assertEqual(self.confirm(annual)['RspCode'], '00')
        annual.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(annual.status, 'paid')
        self.assertIsNotNone(annual.paid_at)
        self.assertIsNone(annual.period_start)
        self.assertIsNone(annual.period_end)
        self.assertIsNone(self.user.vip_until)

    def test_checkout_snapshots_the_name_and_duration_before_the_plan_is_renamed(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('checkout_selected'), {
            'plan': self.year.pk, 'checkout_token': issue_checkout_token(self.user.pk),
        })
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.plan_name_snapshot, 'VIP Năm')
        Plan.objects.filter(pk=self.year.pk).update(name='Tên mới', days=30)
        self.assertEqual(self.confirm(order)['RspCode'], '00')
        order.refresh_from_db()
        self.assertEqual(order.membership_name, 'VIP Năm')
        self.assertEqual(order.period_end - order.period_start, timedelta(days=365))

    def test_membership_and_billing_show_the_current_and_paid_queued_periods(self):
        month = self.active_month()
        annual = self.order(self.year)
        self.assertEqual(self.confirm(annual)['RspCode'], '00')
        annual.refresh_from_db()
        self.client.force_login(self.user)
        response = self.client.get(reverse('plans'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['membership']['current'].pk, month.pk)
        self.assertEqual([order.pk for order in response.context['membership']['queued']], [annual.pk])
        self.assertContains(response, 'Chờ kích hoạt · Đã thanh toán')
        self.assertContains(response, timezone.localtime(annual.period_start).isoformat())
        self.assertContains(response, timezone.localtime(annual.period_end).isoformat())
        profile = self.client.get(reverse('profile'))
        self.assertEqual(profile.status_code, 200)
        self.assertContains(profile, 'VIP Năm')
        self.assertContains(profile, 'Chờ kích hoạt · Đã thanh toán')

    def test_renewal_form_previews_all_choices_after_already_purchased_time_without_allocating_a_period(self):
        self.active_month()
        annual = self.order(self.year)
        self.assertEqual(self.confirm(annual)['RspCode'], '00')
        annual.refresh_from_db()
        self.client.force_login(self.user)
        response = self.client.get(reverse('plans'), {'renew': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['renewing'])
        choices = {plan.pk: plan for plan in response.context['plans']}
        self.assertEqual(choices[self.month.pk].renewal_start, annual.period_end)
        self.assertEqual(choices[self.year.pk].renewal_start, annual.period_end)
        self.assertEqual(choices[self.year.pk].renewal_end, annual.period_end + timedelta(days=365))
        self.assertContains(response, 'data-start="' + timezone.localtime(annual.period_end).isoformat() + '"')
        self.assertEqual(Order.objects.count(), 2)
