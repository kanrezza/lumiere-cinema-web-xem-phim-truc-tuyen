from datetime import timedelta
from urllib.parse import urlsplit, parse_qs
from django.contrib.auth import authenticate
from django.core import signing
from django.test import override_settings, TestCase
from django.urls import reverse
from django.utils import timezone
from .tests import ApplicationTests, PaymentTests
from .models import Membership, User, History

class SecurityRegressionTests(TestCase):
    setUp = ApplicationTests.setUp
    ticket = ApplicationTests.ticket
    make_room = ApplicationTests.make_room
    def test_ticket_never_exposes_session_cookie(self):
        url = self.ticket()
        token = parse_qs(urlsplit(url).query)['token'][0]
        payload = signing.loads(token, salt='video')
        self.assertNotEqual(payload['s'], self.client.session.session_key)
        self.assertNotIn(self.client.session.session_key, str(payload))

    def test_resume_position_uses_javascript_decimal(self):
        History.objects.create(user=self.user, episode=self.episode, position=12.75)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse('watch', args=[self.episode.pk])), 'data-position="12.75"')

    def test_login_supports_email(self):
        self.assertEqual(authenticate(username='VIEWER@example.com', password='Long-password-123!'), self.user)

    def test_inactive_user_cannot_authenticate(self):
        self.user.is_active = False; self.user.save()
        self.assertIsNone(authenticate(username='viewer@example.com', password='Long-password-123!'))

    def test_leave_frees_seat_and_requires_rejoin(self):
        room = self.make_room()
        Membership.objects.create(room=room, user=self.user)
        self.client.force_login(self.user)
        self.client.post(reverse('leave_room', args=[room.pk]))
        self.assertEqual(self.client.get(reverse('room_state', args=[room.pk])).status_code, 404)
        self.client.post(reverse('join_room', args=[room.pk]))
        self.assertEqual(self.client.get(reverse('room_state', args=[room.pk])).status_code, 200)

    def test_stale_members_do_not_exhaust_room(self):
        room = self.make_room()
        for i in range(9): Membership.objects.create(room=room, user=User.objects.create_user(f'stale{i}', f'stale{i}@example.com'), last_seen=timezone.now()-timedelta(minutes=5))
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('join_room', args=[room.pk])).status_code, 302)

    def test_invalid_kick_is_bad_request(self):
        room = self.make_room(); self.client.force_login(self.vip)
        self.assertEqual(self.client.post(reverse('room_state', args=[room.pk]), {'action':'kick', 'user':'abc'}).status_code, 400)

    def test_studio_requires_staff(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/studio/').status_code, 403)
        self.user.is_staff = True; self.user.save()
        self.assertContains(self.client.get('/studio/'), 'Tổng quan hệ thống')

    def test_original_storage_has_no_url(self):
        with self.assertRaises(ValueError): _ = self.episode.source.url

    @override_settings(TRUST_PROXY=False)
    def test_untrusted_client_ip_header_ignored(self):
        response = self.client.get('/', HTTP_X_REAL_IP='not-an-ip')
        self.assertEqual(response.status_code, 200)

    @override_settings(TRUST_PROXY=True, TRUSTED_PROXY_IPS=['127.0.0.1'])
    def test_trusted_proxy_requires_valid_ip(self):
        self.assertEqual(self.client.get('/', HTTP_X_REAL_IP='not-an-ip').status_code, 400)
        self.assertEqual(self.client.get('/', HTTP_X_REAL_IP='192.0.2.1').status_code, 200)

@override_settings(VNPAY_TMN_CODE='TESTCODE', VNPAY_HASH_SECRET='test-secret-only')
class PaymentRegressionTests(TestCase):
    setUp = PaymentTests.setUp
    params = PaymentTests.params
    def test_unicode_signature_is_rejected_without_exception(self):
        params = self.params(); params['vnp_SecureHash'] = 'á'
        response = self.client.get('/payments/ipn/', params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['RspCode'], '97')
