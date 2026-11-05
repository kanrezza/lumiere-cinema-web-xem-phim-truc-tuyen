import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import QueryDict
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import Movie, Episode, Plan, Order, Room, Membership, History, Rating
from .payments import signature

User = get_user_model()

class ApplicationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('viewer', 'viewer@example.com', 'Long-password-123!')
        self.vip = User.objects.create_user('vip', 'vip@example.com', 'Long-password-123!', vip_until=timezone.now()+timedelta(days=30))
        self.other = User.objects.create_user('other', 'other@example.com', 'Long-password-123!')
        self.movie = Movie.objects.create(title='Test cinema', slug='test', description='A movie', published=True)
        self.episode = Episode.objects.create(movie=self.movie, title='Episode 1', source='originals/test.mp4', status='ready', duration=100)
        self.plan = Plan.objects.create(name='Month', price=59000, days=30)
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings = override_settings(PRIVATE_MEDIA_ROOT=Path(self.media.name))
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        folder = Path(self.media.name)/'hls'/str(self.episode.asset_id)
        folder.mkdir(parents=True)
        (folder/'index.m3u8').write_text('#EXTM3U\n#EXTINF:6,\nseg00000.ts\n#EXT-X-ENDLIST\n')
        (folder/'seg00000.ts').write_bytes(b'test-video-segment')

    def ticket(self, user=None):
        self.client.force_login(user or self.user)
        return self.client.post(reverse('ticket', args=[self.episode.pk])).json()['url']

    def test_public_pages(self):
        for url in ['/', '/movies/test/', '/vip/', '/accounts/login/', '/accounts/register/', '/accounts/password_reset/']:
            with self.subTest(url=url): self.assertEqual(self.client.get(url).status_code, 200)

    def test_account_pages(self):
        self.client.force_login(self.user)
        for url in ['/profile/', '/library/', '/watch/1/', '/accounts/password_change/']:
            with self.subTest(url=url): self.assertEqual(self.client.get(url).status_code, 200)

    def test_search_and_filter(self):
        self.assertContains(self.client.get(reverse('catalog'), {'q': 'Test'}), 'Test cinema')
        self.assertContains(self.client.get(reverse('catalog'), {'q': 'unfindable'}), 'Chưa có phim phù hợp')

    def test_registration_normalizes_email_and_rejects_duplicate(self):
        r = self.client.post('/accounts/register/', {'username':'new', 'email':'VIEWER@example.com','password1':'Random-long-987!', 'password2':'Random-long-987!'})
        self.assertContains(r, 'Email đã được sử dụng.')
        self.assertFalse(User.objects.filter(username='new').exists())

    def test_anonymous_cannot_watch(self):
        self.assertEqual(self.client.get(reverse('watch', args=[self.episode.pk])).status_code, 302)

    def test_nonvip_cannot_get_ticket(self):
        self.movie.is_vip = True; self.movie.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('ticket', args=[self.episode.pk])).status_code, 403)

    def test_valid_manifest_and_segment(self):
        url = self.ticket()
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        segment = next(line for line in r.content.decode().splitlines() if line.startswith('/stream/'))
        r = self.client.get(segment)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b''.join(r.streaming_content), b'test-video-segment')
        self.assertIn('no-store', r['Cache-Control'])

    def test_shared_token_is_rejected(self):
        url = self.ticket()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_tampered_token_rejected(self):
        url = self.ticket()
        self.assertEqual(self.client.get(url+'broken').status_code, 403)

    def test_token_expiration(self):
        url = self.ticket()
        import time
        with patch('django.core.signing.time.time', return_value=time.time()+settings.STREAM_TOKEN_AGE+1):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_old_session_revoked_by_new_playback(self):
        url = self.ticket()
        other = Client(); other.force_login(self.user)
        other.post(reverse('ticket', args=[self.episode.pk]))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_vip_expiry_revokes_existing_token(self):
        self.movie.is_vip = True; self.movie.save()
        url = self.ticket(self.vip)
        User.objects.filter(pk=self.vip.pk).update(vip_until=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_unpublished_movie_revokes_stream(self):
        url = self.ticket()
        self.movie.published = False; self.movie.save()
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_private_original_never_served(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/private_media/originals/test.mp4').status_code, 404)
        url = self.ticket().replace('index.m3u8', 'original.mp4')
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True); client.force_login(self.user)
        self.assertEqual(client.post(reverse('ticket', args=[self.episode.pk])).status_code, 403)
        self.assertEqual(client.post(reverse('comment', args=[self.movie.pk]), {'content':'hello'}).status_code, 403)

    def test_watchlist_toggle(self):
        self.client.force_login(self.user)
        url = reverse('save', args=[self.movie.pk])
        self.client.post(url); self.assertEqual(self.user.watchlist_set.count(), 1)
        self.client.post(url); self.assertEqual(self.user.watchlist_set.count(), 0)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_comment_escapes_html(self):
        self.client.force_login(self.user)
        self.client.post(reverse('comment', args=[self.movie.pk]), {'content':'<script>alert(1)</script>'})
        self.assertContains(self.client.get('/movies/test/'), '&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_invalid_rating_rejected(self):
        self.client.force_login(self.user)
        self.client.post(reverse('rate', args=[self.movie.pk]), {'score':'6'})
        self.assertEqual(Rating.objects.count(), 0)

    def test_progress_bounds(self):
        self.client.force_login(self.user)
        for position in ['nan', 'inf', '-1', '200', 'bad']:
            self.assertEqual(self.client.post(reverse('progress', args=[self.episode.pk]), {'position':position}).status_code, 400)
        self.client.post(reverse('progress', args=[self.episode.pk]), {'position':20})
        self.assertEqual(History.objects.get().position, 20)

    def make_room(self):
        room = Room.objects.create(host=self.vip, episode=self.episode, name='Together')
        Membership.objects.create(room=room, user=self.vip)
        return room

    def test_room_requires_login_and_explicit_join(self):
        room = self.make_room()
        self.assertEqual(self.client.get(reverse('room', args=[room.pk])).status_code, 302)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse('room', args=[room.pk])), f'action="{reverse("join_room", args=[room.pk])}"')
        self.assertFalse(Membership.objects.filter(room=room, user=self.user).exists())
        self.client.post(reverse('join_room', args=[room.pk]))
        self.assertTrue(Membership.objects.filter(room=room, user=self.user).exists())

    def test_viewer_cannot_control_room(self):
        room = self.make_room(); Membership.objects.create(room=room, user=self.user)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('room_state', args=[room.pk]), {'action':'sync','position':20, 'playing':'true'}).status_code, 403)

    def test_host_sync_and_chat(self):
        room = self.make_room(); self.client.force_login(self.vip)
        url = reverse('room_state', args=[room.pk])
        self.client.post(url, {'action':'sync', 'position':10, 'playing':'true'})
        self.client.post(url, {'action':'chat', 'content':'Hello'})
        data = self.client.get(url).json()
        self.assertTrue(data['playing']); self.assertGreaterEqual(data['position'],10)
        self.assertEqual(data['messages'][0]['content'], 'Hello')

    def test_kicked_user_cannot_rejoin(self):
        room = self.make_room(); Membership.objects.create(room=room, user=self.user, banned=True)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('join_room', args=[room.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('room_state', args=[room.pk])).status_code, 404)

    def test_vip_movie_requires_every_member_vip(self):
        self.movie.is_vip = True; self.movie.save()
        room = self.make_room(); self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('join_room', args=[room.pk])).status_code, 403)

    def test_room_capacity(self):
        room = self.make_room()
        for i in range(9): Membership.objects.create(room=room, user=User.objects.create_user(f'cap{i}', f'cap{i}@example.com'))
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('join_room', args=[room.pk])).status_code, 409)

    def test_nonvip_cannot_create_room(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('create_room', args=[self.episode.pk])).status_code, 403)

    def test_missing_vnpay_config_cannot_create_order(self):
        self.client.force_login(self.user)
        with override_settings(VNPAY_HASH_SECRET='', VNPAY_TMN_CODE=''):
            self.client.post(reverse('checkout', args=[self.plan.pk]))
        self.assertEqual(Order.objects.count(), 0)

    def test_nonstaff_admin_access_denied(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/admin/cinema/episode/add/').status_code, 302)

@override_settings(VNPAY_TMN_CODE='TESTCODE', VNPAY_HASH_SECRET='test-secret-only')
class CheckoutSelectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('buyer', 'buyer@example.com')
        cls.plan = Plan.objects.create(name='VIP Year', price=599000, days=365)

    def setUp(self):
        cache.clear()
        self.url = reverse('checkout_selected')

    def test_selection_uses_server_price_and_duration(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'plan': self.plan.pk, 'price': '1', 'amount': '1', 'days': '9999',
        })
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual((order.user_id, order.plan_id), (self.user.pk, self.plan.pk))
        self.assertEqual((order.amount, order.days), (599000, 365))
        self.assertEqual(order.status, 'pending')
        params = {key: values[0] for key, values in parse_qs(urlsplit(response.url).query).items()}
        self.assertEqual(params['vnp_Amount'], '59900000')
        self.assertEqual(params['vnp_TxnRef'], order.pk.hex)
        self.assertEqual(params['vnp_SecureHash'], signature(params))
        self.user.refresh_from_db()
        self.assertIsNone(self.user.vip_until)

    def test_invalid_or_inactive_selection_does_not_create_order(self):
        self.client.force_login(self.user)
        inactive = Plan.objects.create(name='Retired', price=10000, days=30, active=False)
        for data in [{}, {'plan': ''}, {'plan': 'invalid'}, {'plan': -1},
                     {'plan': inactive.pk + 1}, {'plan': inactive.pk}]:
            with self.subTest(data=data):
                self.assertEqual(self.client.post(self.url, data).status_code, 404)
        self.assertFalse(Order.objects.exists())

    def test_selection_requires_login(self):
        response = self.client.post(self.url, {'plan': self.plan.pk})
        self.assertRedirects(response, f'{settings.LOGIN_URL}?next={self.url}', fetch_redirect_response=False)
        self.assertFalse(Order.objects.exists())

    def test_ready_payment_prompts_guests_to_login_then_return_to_plans(self):
        response = self.client.get(reverse('plans'))
        self.assertContains(response, f'href="{settings.LOGIN_URL}?next={reverse("plans")}"')
        self.assertNotRegex(response.content.decode(), r'<button\b[^>]*\bpurchase-button\b')
        self.client.force_login(self.user)
        response = self.client.get(reverse('plans'))
        self.assertContains(response, f'action="{self.url}"')
        self.assertRegex(response.content.decode(), r'<button\b[^>]*\bpurchase-button\b[^>]*>Tiếp tục với VNPay')

    def test_selection_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url, {'plan': self.plan.pk}).status_code, 405)
        self.assertFalse(Order.objects.exists())

    def test_selection_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, {'plan': self.plan.pk}).status_code, 403)
        self.assertFalse(Order.objects.exists())

    @override_settings(VNPAY_TMN_CODE='', VNPAY_HASH_SECRET='')
    def test_unconfigured_payment_does_not_create_order(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'plan': self.plan.pk})
        self.assertRedirects(response, reverse('plans'))
        self.assertFalse(Order.objects.exists())


@override_settings(VNPAY_TMN_CODE='TESTCODE', VNPAY_HASH_SECRET='test-secret-only')
class PaymentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('customer', 'customer@example.com', 'Long-password-123!')
        self.plan = Plan.objects.create(name='VIP', price=59000, days=30)
        self.order = Order.objects.create(user=self.user, plan=self.plan, amount=59000, days=30)
    def params(self, **changes):
        params = {'vnp_TmnCode':'TESTCODE', 'vnp_TxnRef':self.order.pk.hex, 'vnp_Amount':'5900000', 'vnp_ResponseCode':'00', 'vnp_TransactionStatus':'00', 'vnp_TransactionNo':'12345'}
        params.update(changes); params['vnp_SecureHash'] = signature(params)
        return params
    def test_ipn_grants_vip_once(self):
        params = self.params()
        self.assertEqual(self.client.get('/payments/ipn/',params).json()['RspCode'], '00')
        self.user.refresh_from_db(); expiry = self.user.vip_until
        self.assertGreater(expiry, timezone.now()+timedelta(days=29))
        self.assertEqual(self.client.get('/payments/ipn/',params).json()['RspCode'], '02')
        self.user.refresh_from_db(); self.assertEqual(self.user.vip_until, expiry)
    def test_wrong_amount(self):
        self.assertEqual(self.client.get('/payments/ipn/', self.params(vnp_Amount='1')).json()['RspCode'], '04')
        self.order.refresh_from_db(); self.assertEqual(self.order.status,'pending')
    def test_invalid_signature(self):
        params = self.params(); params['vnp_SecureHash'] = 'bad'
        self.assertEqual(self.client.get('/payments/ipn/', params).json()['RspCode'], '97')
    def test_wrong_merchant(self):
        self.assertEqual(self.client.get('/payments/ipn/', self.params(vnp_TmnCode='OTHER')).json()['RspCode'], '97')
    def test_failed_payment_does_not_grant_vip(self):
        self.client.get('/payments/ipn/', self.params(vnp_ResponseCode='24',vnp_TransactionStatus='02'))
        self.user.refresh_from_db(); self.assertFalse(self.user.is_vip)
        self.order.refresh_from_db(); self.assertEqual(self.order.status,'failed')
    def test_browser_return_never_grants_vip(self):
        self.client.force_login(self.user)
        self.client.get('/payments/return/', self.params())
        self.user.refresh_from_db(); self.assertIsNone(self.user.vip_until)
    def test_unknown_order(self):
        self.assertEqual(self.client.get('/payments/ipn/', self.params(vnp_TxnRef='invalid')).json()['RspCode'], '01')
    def test_plan_changes_do_not_change_order(self):
        self.plan.days = 365; self.plan.save()
        self.client.get('/payments/ipn/', self.params())
        self.user.refresh_from_db()
        self.assertLess(self.user.vip_until, timezone.now()+timedelta(days=31))
    def test_duplicate_parameters_rejected(self):
        q = QueryDict(mutable=True); q.update(self.params()); q.appendlist('vnp_Amount','1')
        self.assertEqual(self.client.get('/payments/ipn/?'+q.urlencode()).json()['RspCode'], '97')
