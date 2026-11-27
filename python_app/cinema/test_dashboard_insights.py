"""Date-scoped reporting and actionable queues keep model permissions intact."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Permission
from django.db.models import DateField, Value
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .content_health import health_queryset
from .dashboard_insights import dashboard_insights
from .models import Episode, Movie, Order, Plan, Subtitle, User


class DashboardInsightsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('insight-admin', 'insight-admin@example.invalid', 'Test-password-2026!')
        cls.staff = User.objects.create_user('insight-editor', 'insight-editor@example.invalid', is_staff=True)
        cls.viewer = User.objects.create_user('insight-viewer', 'insight-viewer@example.invalid')
        cls.plan = Plan.objects.create(name='Tháng', days=30, price=59000)
        cls.now = datetime(2026, 11, 27, 15, 0, tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))
        User.objects.filter(pk__in=(cls.admin.pk, cls.staff.pk, cls.viewer.pk)).update(date_joined=cls.now - timedelta(days=180))

    def order(self, amount, at, status='paid'):
        return Order.objects.create(user=self.viewer, plan=self.plan, amount=amount, days=30, status=status, paid_at=at)

    def report(self, period='7'):
        return dashboard_insights(self.admin, period, orders=True, users=True, now=self.now)

    def test_period_only_counts_confirmed_payments_with_actual_payment_dates(self):
        self.order(59000, self.now)
        self.order(599000, self.now - timedelta(days=6))
        self.order(100000, self.now - timedelta(days=7))
        self.order(999, self.now, status='pending')
        self.order(999, self.now, status='failed')
        self.order(999, None)
        self.order(999, self.now + timedelta(days=1))
        report = self.report()
        self.assertEqual(report['revenue'], 658000)
        self.assertEqual(report['paid_count'], 2)
        self.assertEqual(report['previous_revenue'], 100000)
        self.assertEqual(report['revenue_change'], 558.0)
        self.assertEqual(sum(day['amount'] for day in report['chart']), report['revenue'])
        self.assertEqual(len(report['chart']), 7)

    def test_days_use_the_display_timezone_even_at_utc_midnight(self):
        with timezone.override('Asia/Ho_Chi_Minh'):
            self.order(59000, datetime(2026, 11, 26, 18, 0, tzinfo=ZoneInfo('UTC')))
            report = self.report()
        self.assertEqual(report['chart'][-1]['amount'], 59000)
        self.assertEqual(report['chart'][-2]['amount'], 0)

    def test_zero_baseline_is_not_reported_as_infinite_or_fabricated_growth(self):
        self.order(59000, self.now)
        report = self.report()
        self.assertIsNone(report['revenue_change'])
        self.assertEqual(report['previous_revenue'], 0)

    def test_null_database_timezone_conversion_keeps_daily_revenue_accurate(self):
        self.order(59000, self.now)
        self.order(599000, self.now - timedelta(days=1))
        with timezone.override('Asia/Ho_Chi_Minh'), patch(
            'cinema.dashboard_insights.TruncDate', return_value=Value(None, output_field=DateField()),
        ):
            report = self.report()
        self.assertEqual(report['chart'][-1]['amount'], 59000)
        self.assertEqual(report['chart'][-2]['amount'], 599000)
        self.assertEqual(sum(day['amount'] for day in report['chart']), report['revenue'])

    def test_unknown_period_defaults_to_30_and_output_is_bounded(self):
        for value, expected in [('365000', 30), ('-1', 30), ('7', 7), ('90', 90)]:
            with self.subTest(period=value):
                report = self.report(value)
                self.assertEqual(report['days'], expected)
                self.assertEqual(len(report['chart']), expected)

    def test_no_reporting_data_for_non_staff_or_unauthorized_domains(self):
        for viewer in (AnonymousUser(), self.viewer):
            with self.subTest(viewer=viewer), self.assertNumQueries(0):
                self.assertIsNone(dashboard_insights(viewer, orders=True, users=True, now=self.now))
        report = dashboard_insights(self.staff, orders=True, users=True, now=self.now)
        self.assertFalse(report['available'])
        self.assertIsNone(report['revenue'])
        self.assertIsNone(report['new_users'])
        self.assertEqual(report['health'], [])

    def test_movie_editor_cannot_see_payments_users_or_episode_checks(self):
        self.staff.user_permissions.add(Permission.objects.get(codename='view_movie'))
        staff = User.objects.get(pk=self.staff.pk)
        report = dashboard_insights(staff, orders=True, users=True, now=self.now)
        self.assertEqual([check['issue'] for check in report['health']], ['poster'])
        self.assertIsNone(report['revenue'])
        self.assertIsNone(report['new_users'])

    def test_new_member_and_expiring_vip_counts_exclude_erased_or_inactive_vips(self):
        User.objects.filter(pk=self.viewer.pk).update(date_joined=self.now, vip_until=self.now + timedelta(days=3))
        User.objects.filter(pk=self.staff.pk).update(date_joined=self.now - timedelta(days=20), vip_until=self.now + timedelta(days=1), is_active=False)
        report = self.report()
        self.assertEqual(report['new_users'], 1)
        self.assertEqual(report['expiring_vips'], 1)

    def test_both_admin_entry_points_accept_the_period_filter(self):
        self.client.force_login(self.admin)
        for name in ('studio', 'admin:index'):
            with self.subTest(name=name):
                response = self.client.get(reverse(name), {'period': '7'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['insights']['days'], 7)
                self.assertContains(response, 'Theo dõi để vận hành tốt hơn.')
                self.assertContains(response, 'viewBox="0 0 720 154"')

    def test_health_links_lead_to_matching_admin_filters(self):
        waiting = Movie.objects.create(title='Đang chuẩn bị', slug='health-waiting', description='D', published=True)
        ready = Movie.objects.create(title='Đã sẵn sàng', slug='health-ready', description='D', published=True, poster='posters/example.jpg')
        draft = Movie.objects.create(title='Bản nháp', slug='health-draft', description='D')
        ready_ep = Episode.objects.create(movie=ready, title='Ready', status='ready')
        Episode.objects.create(movie=waiting, title='Failed', status='failed')
        Episode.objects.create(movie=draft, title='Ready', status='ready')
        self.assertEqual(list(health_queryset(Movie.objects.all(), 'waiting')), [waiting])
        self.assertEqual(list(health_queryset(Movie.objects.all(), 'draft_ready')), [draft])
        self.assertEqual(list(health_queryset(Movie.objects.all(), 'subtitles')), [ready])
        Subtitle.objects.create(episode=ready_ep, language='vi', label='Tiếng Việt', content='WEBVTT\n')
        self.assertFalse(health_queryset(Movie.objects.all(), 'subtitles').exists())
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin:cinema_movie_changelist'), {'health': 'waiting'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['cl'].result_list), [waiting])
