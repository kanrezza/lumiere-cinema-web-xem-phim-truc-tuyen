"""Integration tests for correlation and bounded WAF responses."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from . import waf
from .models import SecurityEvent, User


TEST_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'waf-behavior-tests'}}


@override_settings(WAF_MODE='monitor', WAF_BEHAVIOR_MITIGATION=True, TRUST_PROXY=False, CACHES=TEST_CACHE,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class BehaviorWAFTests(TestCase):
    source = '192.0.2.21'
    other_source = '192.0.2.22'
    search_text = 'Tên phim minh họa ' * 500

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.now = datetime(2026, 1, 12, 12, 0, 1, tzinfo=UTC)
        clock = patch('cinema.waf_behavior.timezone.now', side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def route_misses(self, source):
        for index in range(10):
            result = self.client.get(f'/unpublished-preview-{index}/', REMOTE_ADDR=source)
            self.assertEqual(result.status_code, 404)

    def rule_matches(self, source):
        for _ in range(3):
            self.client.get(reverse('catalog'), {'q': self.search_text}, REMOTE_ADDR=source)

    def observed_incidents(self):
        return SecurityEvent.objects.filter(action=SecurityEvent.Action.OBSERVED,
                                            reason=SecurityEvent.Reason.BEHAVIOR_ANOMALY)

    def test_observes_correlated_signals_across_bucket_boundaries(self):
        self.route_misses(self.source)
        self.assertFalse(self.observed_incidents().exists())

        self.now += timedelta(seconds=31)
        self.rule_matches(self.source)

        incident = self.observed_incidents().get()
        self.assertGreaterEqual(incident.risk_score, 70)
        self.assertIsNone(incident.baseline_samples)
        self.assertEqual(incident.behavior_metadata['route_misses'], 10)
        self.assertGreaterEqual(incident.behavior_metadata['rule_matches'], 2)
        self.assertEqual(incident.behavior_metadata['areas'], 2)
        self.assertRegex(incident.source, r'^[0-9a-f]{16}$')
        self.assertNotIn(self.source, repr(incident.behavior_metadata))
        self.assertNotIn(self.search_text, repr(incident.behavior_metadata))
        self.assertEqual(self.client.get(reverse('catalog'), REMOTE_ADDR=self.source).status_code, 200)
        self.assertFalse(SecurityEvent.objects.filter(reason=SecurityEvent.Reason.BEHAVIOR_COOLDOWN).exists())

    def test_correlates_failed_logins_without_recording_credentials(self):
        self.route_misses(self.source)
        credentials = {'username': 'sample-user-without-an-account', 'password': 'ordinary-demo-password'}
        for _ in range(6):
            response = self.client.post(reverse('login'), credentials, REMOTE_ADDR=self.source)
            self.assertEqual(response.status_code, 200)

        incident = self.observed_incidents().get()
        self.assertEqual(incident.behavior_metadata['login_failures'], 6)
        self.assertNotIn(credentials['username'], repr(incident.behavior_metadata))
        self.assertNotIn(credentials['password'], repr(incident.behavior_metadata))

    def test_correlates_permission_denials_as_a_distinct_signal(self):
        self.route_misses(self.source)
        csrf_client = Client(enforce_csrf_checks=True)
        for _ in range(5):
            response = csrf_client.post(reverse('login'), REMOTE_ADDR=self.source)
            self.assertEqual(response.status_code, 403)

        incident = self.observed_incidents().get()
        self.assertGreaterEqual(incident.behavior_metadata['denied'], 3)
        self.assertEqual(incident.behavior_metadata.get('login_failures', 0), 0)

    def test_keeps_different_sources_and_stale_windows_separate(self):
        self.route_misses(self.source)
        self.rule_matches(self.other_source)
        self.assertFalse(self.observed_incidents().exists())

        self.now += timedelta(seconds=121)
        self.rule_matches(self.source)
        self.assertFalse(self.observed_incidents().exists())

    @override_settings(WAF_MODE='enforce')
    def test_cooldown_rejects_anonymous_catalog_reads_and_expires(self):
        self.route_misses(self.source)
        self.rule_matches(self.source)
        incident = self.observed_incidents().get()
        catalog = reverse('catalog')

        limited = self.client.head(catalog, REMOTE_ADDR=self.source)
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(int(limited['Retry-After']), 90)
        self.assertIn('no-store', limited['Cache-Control'])
        self.assertEqual(limited.content, b'')
        blocked = SecurityEvent.objects.get(action=SecurityEvent.Action.BLOCKED,
                                           reason=SecurityEvent.Reason.BEHAVIOR_COOLDOWN)
        self.assertEqual(blocked.source, incident.source)
        self.assertGreaterEqual(blocked.risk_score, incident.risk_score)
        self.assertEqual(self.client.get(catalog, REMOTE_ADDR=self.other_source).status_code, 200)

        self.now += timedelta(seconds=45)
        again = self.client.get(catalog, REMOTE_ADDR=self.source)
        self.assertEqual(again.status_code, 429)
        self.assertEqual(int(again['Retry-After']), 45)

        self.now += timedelta(seconds=46)
        self.assertEqual(self.client.get(catalog, REMOTE_ADDR=self.source).status_code, 200)

    @override_settings(WAF_MODE='enforce')
    def test_cooldown_exempts_sensitive_routes_and_signed_in_viewers(self):
        self.route_misses(self.source)
        self.rule_matches(self.source)
        self.assertEqual(self.client.get(reverse('catalog'), REMOTE_ADDR=self.source).status_code, 429)
        exempt_paths = (
            reverse('login'), reverse('studio'), reverse('ipn'), reverse('watch', args=[1]),
            reverse('stream', args=[1, 'index.m3u8']), reverse('room', args=[uuid4()]),
        )
        for path in exempt_paths:
            with self.subTest(path=path):
                expected_status = self.client.get(path, REMOTE_ADDR=self.other_source).status_code
                self.assertNotEqual(expected_status, 429)
                self.assertEqual(self.client.get(path, REMOTE_ADDR=self.source).status_code, expected_status)

        viewer = User.objects.create_user(username='waf-viewer', email='waf-viewer@example.test')
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse('catalog'), REMOTE_ADDR=self.source).status_code, 200)

    @override_settings(WAF_MODE='enforce')
    def test_a_single_incidental_error_in_another_area_does_not_trigger_cooldown(self):
        for index in range(12):
            path = reverse('movie', args=[f'unpublished-film-{index}'])
            self.assertEqual(self.client.get(path, REMOTE_ADDR=self.source).status_code, 404)
        self.assertEqual(self.client.get('/unpublished-preview/', REMOTE_ADDR=self.source).status_code, 404)
        self.rule_matches(self.source)

        incident = self.observed_incidents().get()
        self.assertEqual(incident.behavior_metadata['areas'], 1)
        self.assertEqual(self.client.get(reverse('catalog'), REMOTE_ADDR=self.source).status_code, 200)
        self.assertFalse(SecurityEvent.objects.filter(reason=SecurityEvent.Reason.BEHAVIOR_COOLDOWN).exists())

    @override_settings(WAF_MODE='enforce')
    def test_learned_shape_evidence_cannot_replace_an_independent_cooldown_signal(self):
        catalog = reverse('catalog')
        model_assessment = waf.Assessment(85, (waf.Signal.LENGTH,), baseline_samples=250)
        with patch('cinema.waf.observe_response', return_value=model_assessment):
            for _ in range(2):
                self.assertEqual(self.client.get(catalog, {'q': 'Phim'}, REMOTE_ADDR=self.source).status_code, 200)
        for _ in range(3):
            response = self.client.get(reverse('login'), {'q': self.search_text}, REMOTE_ADDR=self.source)
            self.assertEqual(response.status_code, 414)

        incident = self.observed_incidents().get()
        self.assertEqual(incident.behavior_metadata['query_anomalies'], 2)
        self.assertEqual(incident.behavior_metadata['rule_matches'], 3)
        self.assertEqual(incident.behavior_metadata['areas'], 2)
        self.assertEqual(self.client.get(catalog, REMOTE_ADDR=self.source).status_code, 200)
        self.assertFalse(SecurityEvent.objects.filter(reason=SecurityEvent.Reason.BEHAVIOR_COOLDOWN).exists())

    @override_settings(WAF_MODE='enforce', WAF_BEHAVIOR_MITIGATION=False)
    def test_mitigation_opt_out_keeps_strict_waf_rules(self):
        self.route_misses(self.source)
        self.rule_matches(self.source)

        self.assertTrue(self.observed_incidents().exists())
        catalog = reverse('catalog')
        self.assertEqual(self.client.get(catalog, REMOTE_ADDR=self.source).status_code, 200)
        oversized = self.client.get(catalog, {'q': self.search_text}, REMOTE_ADDR=self.source)
        self.assertEqual(oversized.status_code, 414)
        self.assertFalse(SecurityEvent.objects.filter(reason=SecurityEvent.Reason.BEHAVIOR_COOLDOWN).exists())
