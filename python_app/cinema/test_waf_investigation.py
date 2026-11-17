from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import SecurityEvent, User


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    WAF_MODE='monitor',
    WAF_BEHAVIOR_MITIGATION=True,
)
class WAFInvestigationTests(TestCase):
    source = '0123456789abcdef'

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('waf-investigator', 'waf-investigator@example.test')

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse('admin:waf')

    def event(self, source, reason=SecurityEvent.Reason.ROUTE_MISS_BURST, action=SecurityEvent.Action.OBSERVED):
        return SecurityEvent.objects.create(
            source=source, reason=reason, action=action,
            area=SecurityEvent.Area.CATALOG, method='GET',
        )

    def test_source_history_links_and_preserves_filters_on_next_page(self):
        reason = SecurityEvent.Reason.ROUTE_MISS_BURST
        for _ in range(26):
            self.event(self.source)
        self.event('fedcba9876543210')

        self.assertContains(self.client.get(self.url), f'href="{self.url}?source={self.source}"')
        response = self.client.get(self.url, {'source': self.source, 'reason': reason})
        self.assertEqual(response.context['waf_page'].paginator.count, 26)
        self.assertNotContains(response, 'fedcba9876543210')
        self.assertContains(response, f'?reason={reason}&amp;source={self.source}&amp;page=2')
        self.assertContains(response, f'href="{self.url}?reason={reason}">Bỏ lọc theo nguồn</a>')

    def test_source_requires_an_exact_hex_identifier(self):
        self.event('unknown')
        self.event(self.source)

        response = self.client.get(self.url, {'source': self.source.upper()})
        self.assertNotIn('source', response.context['waf_filters'])
        self.assertEqual(response.context['waf_page'].paginator.count, 2)
        self.assertNotContains(response, '?source=unknown')

    def test_behavior_counts_recent_events_and_describes_enforcement_mode(self):
        incident = SecurityEvent.Reason.BEHAVIOR_ANOMALY
        cooldown = SecurityEvent.Reason.BEHAVIOR_COOLDOWN
        recorded = self.event(self.source, incident)
        recorded.signals = [SecurityEvent.Signal.ROUTE_MISSES]
        recorded.behavior_metadata = {SecurityEvent.Signal.ROUTE_MISSES: 9}
        recorded.save(update_fields=['signals', 'behavior_metadata'])
        rejected = self.event(self.source, cooldown, SecurityEvent.Action.BLOCKED)
        rejected.risk_score = 90
        rejected.save(update_fields=['risk_score'])
        old = self.event(self.source, cooldown, SecurityEvent.Action.BLOCKED)
        SecurityEvent.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=2))

        monitoring = self.client.get(self.url)
        self.assertFalse(monitoring.context['waf_behavior_mitigation'])
        self.assertEqual(monitoring.context['waf_totals']['behavior_incidents'], 1)
        self.assertEqual(monitoring.context['waf_totals']['behavior_rejections'], 1)
        self.assertEqual(monitoring.context['waf_totals']['high_risk'], 0)
        self.assertContains(monitoring, f'<strong>{SecurityEvent.Signal.ROUTE_MISSES.label}</strong> · 9')

        with override_settings(WAF_MODE='enforce'):
            enforcing = self.client.get(self.url)
        self.assertTrue(enforcing.context['waf_behavior_mitigation'])
        self.assertContains(enforcing, 'Đang thực thi')
