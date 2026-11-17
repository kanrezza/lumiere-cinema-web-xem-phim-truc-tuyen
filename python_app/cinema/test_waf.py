"""Verify Lumière's WAF with ordinary requests and synthetic traffic."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from redis.exceptions import RedisError

from . import waf
from .models import SecurityEvent, User


TEST_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'waf-tests'}}


@override_settings(WAF_MODE='monitor', TRUST_PROXY=False, CACHES=TEST_CACHE)
class WAFMiddlewareTests(TestCase):
    source_ip = '192.0.2.17'
    oversized_search = 'catalogmarker' * 680

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_monitor_records_metadata_without_blocking_or_retaining_query(self):
        response = self.client.get(reverse('catalog'), {'q': self.oversized_search}, REMOTE_ADDR=self.source_ip)

        self.assertEqual(response.status_code, 200)
        event = SecurityEvent.objects.get()
        self.assertEqual(event.action, SecurityEvent.Action.OBSERVED)
        self.assertEqual(event.reason, SecurityEvent.Reason.REQUEST_TARGET)
        self.assertEqual(event.area, SecurityEvent.Area.CATALOG)
        self.assertEqual(event.method, 'GET')
        self.assertTrue(event.source)
        self.assertNotIn(self.source_ip, str(event.__dict__))
        self.assertNotIn('catalogmarker', str(event.__dict__))

    @override_settings(WAF_MODE='enforce')
    def test_enforce_rejects_oversized_request_and_applies_response_headers(self):
        catalog = reverse('catalog')
        response = self.client.get(catalog, {'q': self.oversized_search}, REMOTE_ADDR=self.source_ip)

        self.assertEqual(response.status_code, 414)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn("default-src 'self'", response['Content-Security-Policy'])
        self.assertEqual(SecurityEvent.objects.get().action, SecurityEvent.Action.BLOCKED)

        form_fields = {f'field{index}': 'preview' for index in range(129)}
        response = self.client.get(catalog, form_fields, REMOTE_ADDR=self.source_ip)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SecurityEvent.objects.count(), 1)

    @override_settings(WAF_MODE='off')
    def test_off_turns_off_waf_inspection_and_recording(self):
        response = self.client.get(reverse('catalog'), {'q': self.oversized_search}, REMOTE_ADDR=self.source_ip)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SecurityEvent.objects.exists())

    @override_settings(WAF_MODE='enforce')
    def test_regular_catalog_filters_work_in_enforce_mode(self):
        response = self.client.get(reverse('catalog'), {'q': 'Phim Việt', 'year': '2025'}, REMOTE_ADDR=self.source_ip)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SecurityEvent.objects.exists())

    @override_settings(WAF_MODE='enforce')
    def test_waf_cache_failure_preserves_normal_access_and_strict_rules(self):
        catalog = reverse('catalog')
        with patch('cinema.waf.cache.add', side_effect=RedisError), patch('cinema.waf.cache.get', side_effect=RedisError):
            regular = self.client.get(catalog, {'q': 'phim'}, REMOTE_ADDR=self.source_ip)
            oversized = self.client.get(catalog, {'q': self.oversized_search}, REMOTE_ADDR=self.source_ip)

        self.assertEqual(regular.status_code, 200)
        self.assertEqual(oversized.status_code, 414)
        self.assertFalse(SecurityEvent.objects.exists())

    def test_auth_throttle_remains_active_and_records_block(self):
        for _ in range(15):
            response = self.client.post(reverse('login'), REMOTE_ADDR=self.source_ip)
            self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('login'), REMOTE_ADDR=self.source_ip)

        self.assertEqual(response.status_code, 429)
        event = SecurityEvent.objects.get()
        self.assertEqual(event.action, SecurityEvent.Action.BLOCKED)
        self.assertEqual(event.reason, SecurityEvent.Reason.RATE_LIMIT)

    @override_settings(WAF_MODE='enforce')
    def test_unusual_number_of_missing_routes_is_observed_without_blocking(self):
        with patch('cinema.waf.timezone.now', return_value=timezone.now()):
            for index in range(11):
                response = self.client.get(f'/unpublished-preview-{index}/', REMOTE_ADDR=self.source_ip)
                self.assertEqual(response.status_code, 404)
            self.assertFalse(SecurityEvent.objects.exists())

            response = self.client.get('/unpublished-preview-11/', REMOTE_ADDR=self.source_ip)
            self.assertEqual(response.status_code, 404)

        event = SecurityEvent.objects.get()
        self.assertEqual(event.action, SecurityEvent.Action.OBSERVED)
        self.assertEqual(event.reason, SecurityEvent.Reason.ROUTE_MISS_BURST)

    @override_settings(WAF_MODE='enforce')
    def test_rare_query_shape_against_learned_baseline_only_raises_alert(self):
        training_hour = timezone.now().replace(minute=1, second=0, microsecond=0)
        catalog = reverse('catalog')
        with patch('cinema.waf.timezone.now', return_value=training_hour) as waf_now:
            for hour_offset in (0, 3):
                waf_now.return_value = training_hour + timedelta(hours=hour_offset)
                for index in range(30):
                    response = self.client.get(catalog, {'q': 'phim'}, REMOTE_ADDR=f'198.51.100.{index + 1}')
                    self.assertEqual(response.status_code, 200)
            self.assertFalse(SecurityEvent.objects.exists())

            waf_now.return_value = training_hour + timedelta(hours=4)
            response = self.client.get(catalog, {'q': 'phim' * 200}, REMOTE_ADDR=self.source_ip)
            scored_baselines = [status['samples'] for status in waf.model_status() if status['ready']]
            self.assertEqual(scored_baselines, [60])

            waf_now.return_value = training_hour + timedelta(hours=7)
            expired_baselines = waf.model_status()
            self.assertEqual(sorted(status['samples'] for status in expired_baselines), [0, 30])
            self.assertFalse(any(status['ready'] for status in expired_baselines))

        self.assertEqual(response.status_code, 200)
        event = SecurityEvent.objects.get()
        self.assertEqual(event.action, SecurityEvent.Action.OBSERVED)
        self.assertEqual(event.reason, SecurityEvent.Reason.QUERY_ANOMALY)
        self.assertEqual(event.baseline_samples, 60)
        self.assertGreaterEqual(event.risk_score, 50)
        self.assertLessEqual(event.risk_score, 100)
        self.assertIn('length', event.signals)
        self.assertTrue(set(event.signals).issubset({'length', 'field_count', 'combination'}))
        self.assertNotIn(self.source_ip, str(event.__dict__))
        self.assertNotIn('phim' * 200, str(event.__dict__))

    def test_training_deduplicates_each_source_per_route_and_interval(self):
        training_hour = timezone.now().replace(minute=1, second=0, microsecond=0)
        catalog, actors = reverse('catalog'), reverse('actors')
        with patch('cinema.waf.timezone.now', return_value=training_hour) as waf_now:
            for route in (catalog, catalog, actors, actors):
                response = self.client.get(route, {'q': 'phim'}, REMOTE_ADDR=self.source_ip)
                self.assertEqual(response.status_code, 200)
            self.assertTrue(all(status['samples'] == 0 for status in waf.model_status()))

            waf_now.return_value = training_hour + timedelta(minutes=10)
            response = self.client.get(catalog, {'q': 'phim'}, REMOTE_ADDR=self.source_ip)
            self.assertEqual(response.status_code, 200)

            waf_now.return_value = training_hour + timedelta(hours=1)
            baselines = waf.model_status()

        self.assertEqual(sorted(status['samples'] for status in baselines), [1, 2])
        self.assertFalse(any(status['ready'] for status in baselines))
        self.assertFalse(SecurityEvent.objects.exists())

    def test_model_detects_a_rare_combination_of_individually_familiar_signals(self):
        training_hour = timezone.now().replace(minute=1, second=0, microsecond=0)
        catalog = reverse('catalog')
        long_query = {'q': 'phim' * 200}
        many_fields = {'year': ['2025'] * 12}
        with patch('cinema.waf.timezone.now', return_value=training_hour) as waf_now:
            for index in range(60):
                query = long_query if index < 30 else many_fields
                response = self.client.get(catalog, query, REMOTE_ADDR=f'198.51.100.{index + 1}')
                self.assertEqual(response.status_code, 200)

            waf_now.return_value = training_hour + timedelta(hours=1)
            for query in (long_query, many_fields):
                response = self.client.get(catalog, query, REMOTE_ADDR=self.source_ip)
                self.assertEqual(response.status_code, 200)
            self.assertFalse(SecurityEvent.objects.exists())

            combined = {'q': long_query['q'], 'year': many_fields['year']}
            response = self.client.get(catalog, combined, REMOTE_ADDR=self.source_ip)

        self.assertEqual(response.status_code, 200)
        event = SecurityEvent.objects.get()
        self.assertEqual(event.reason, SecurityEvent.Reason.QUERY_ANOMALY)
        self.assertEqual(event.signals, ['combination'])

    def test_model_status_reports_cache_outage(self):
        with patch('cinema.waf.cache.get_many', side_effect=RedisError):
            self.assertIsNone(waf.model_status())


@override_settings(WAF_MODE='monitor', CACHES=TEST_CACHE)
class WAFAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('waf-admin', 'waf-admin@example.test')
        cls.editor = User.objects.create_user('waf-editor', 'waf-editor@example.test', is_staff=True)

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_dashboard_and_navigation_require_superuser(self):
        url = reverse('admin:waf')
        self.assertRedirects(self.client.get(url), f'{reverse("admin:login")}?next={url}', fetch_redirect_response=False)

        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertNotContains(self.client.get(reverse('studio')), f'href="{url}"')

        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('studio')), f'href="{url}"')
        self.assertContains(self.client.get(url), 'WAF')

    def test_dashboard_filters_events_by_action_and_reason(self):
        observed = SecurityEvent.objects.create(
            action=SecurityEvent.Action.OBSERVED, reason=SecurityEvent.Reason.REQUEST_TARGET,
            area=SecurityEvent.Area.CATALOG, method='GET', source='a123456789abcdef',
        )
        blocked = SecurityEvent.objects.create(
            action=SecurityEvent.Action.BLOCKED, reason=SecurityEvent.Reason.RATE_LIMIT,
            area=SecurityEvent.Area.CATALOG, method='POST', source='b123456789abcdef',
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse('admin:waf'), {'action': blocked.action, 'reason': blocked.reason})

        self.assertContains(response, blocked.source)
        self.assertNotContains(response, observed.source)

    def test_dashboard_filters_high_risk_and_keeps_legacy_events_available(self):
        self.client.force_login(self.admin)
        high, scored, unscored = SecurityEvent.objects.bulk_create([
            SecurityEvent(
                action=SecurityEvent.Action.OBSERVED, reason=SecurityEvent.Reason.QUERY_ANOMALY,
                area=SecurityEvent.Area.CATALOG, method='GET', source=source,
                risk_score=risk, baseline_samples=83 if risk is not None else None,
                signals=['field_count'] if risk is not None else [],
            )
            for source, risk in (('high-sample', 83), ('scored-sample', 69), ('legacy-sample', None))
        ])
        url = reverse('admin:waf')
        for risk, expected in (('high', high), ('scored', scored), ('unscored', unscored)):
            with self.subTest(risk=risk):
                response = self.client.get(url, {'risk': risk})
                self.assertContains(response, expected.source)
                self.assertEqual(list(response.context['waf_page'].object_list), [expected])
                for label in expected.model_signal_labels:
                    self.assertContains(response, label)

    def test_prune_removes_only_events_older_than_30_days(self):
        events = SecurityEvent.objects.bulk_create([
            SecurityEvent(
                action=SecurityEvent.Action.OBSERVED, reason=SecurityEvent.Reason.REQUEST_TARGET,
                area=SecurityEvent.Area.CATALOG, method='GET', source=source,
            )
            for source in ('a123456789abcdef', 'b123456789abcdef')
        ])
        old, recent = events
        SecurityEvent.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=31))
        SecurityEvent.objects.filter(pk=recent.pk).update(created_at=timezone.now() - timedelta(days=29))

        call_command('prune_security_events', stdout=StringIO())

        self.assertEqual(list(SecurityEvent.objects.values_list('pk', flat=True)), [recent.pk])
