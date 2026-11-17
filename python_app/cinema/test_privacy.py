import tempfile
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Chat, Comment, ErasureRequest, Episode, History, Movie, Order, Plan, Room, User, Watchlist
from .payments import signature
from .privacy import NOTICE_VERSION


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PrivacyTests(TestCase):
    password = 'test-password-for-privacy'

    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_user('viewer', 'viewer@example.test', cls.password, first_name='Test Viewer')
        cls.admin = User.objects.create_superuser('operator', 'operator@example.test', cls.password)
        cls.staff = User.objects.create_user('editor', 'editor@example.test', cls.password, is_staff=True)
        cls.movie = Movie.objects.create(title='Phim thử nghiệm', slug='phim-thu')
        cls.episode = Episode.objects.create(movie=cls.movie, number=1)
        cls.plan = Plan.objects.create(name='VIP thử', price=59000, days=30)

    def ask(self, password=None, confirmed='on'):
        return self.client.post(reverse('account_privacy'), {
            'action': 'request', 'password': self.password if password is None else password, 'confirmed': confirmed,
        })

    def test_policy_and_authenticated_entry_points(self):
        with self.settings(PRIVACY_CONTACT_EMAIL='privacy@example.test'):
            self.assertContains(self.client.get(reverse('privacy_policy')), 'privacy@example.test')
        self.assertContains(self.client.get(reverse('register')), reverse('privacy_policy'))
        self.assertEqual(self.client.get(reverse('account_privacy')).status_code, 302)
        self.client.force_login(self.viewer)
        self.assertContains(self.client.get(reverse('profile')), reverse('account_privacy'))
        self.assertContains(self.client.get(reverse('account_privacy')), 'Mật khẩu hiện tại')

    def test_password_confirmation_duplicate_request_and_cancel(self):
        self.client.force_login(self.viewer)
        self.assertContains(self.ask(password='wrong'), 'Mật khẩu hiện tại không đúng')
        self.assertEqual(self.ask(confirmed='').status_code, 200)
        self.assertFalse(ErasureRequest.objects.exists())
        for _ in range(2):
            self.assertRedirects(self.ask(), reverse('account_privacy'))
        pending = ErasureRequest.objects.get()
        self.assertEqual(pending.notice_version, NOTICE_VERSION)
        self.assertContains(self.client.get(reverse('account_privacy')), str(pending.pk))
        self.client.post(reverse('account_privacy'), {'action': 'cancel'})
        pending.refresh_from_db()
        self.assertEqual(pending.status, ErasureRequest.Status.CANCELLED)
        self.ask()
        self.assertEqual(ErasureRequest.objects.filter(status=ErasureRequest.Status.PENDING).count(), 1)

    def test_review_requires_superuser_post_confirmation_and_csrf(self):
        entry = ErasureRequest.objects.create(user=self.viewer, notice_version=NOTICE_VERSION)
        queue = reverse('admin:privacy_requests')
        action = reverse('admin:privacy_review', args=[entry.pk])
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(queue).status_code, 403)
        self.assertEqual(self.client.post(action, {'action': 'complete', 'confirmed': 'yes'}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(queue), str(entry.pk))
        self.assertEqual(self.client.get(action).status_code, 403)
        self.assertEqual(self.client.post(action, {'action': 'complete'}).status_code, 403)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.admin)
        self.assertEqual(strict.post(action, {'action': 'complete', 'confirmed': 'yes'}).status_code, 403)
        entry.refresh_from_db()
        self.assertEqual(entry.status, ErasureRequest.Status.PENDING)

    def test_password_change_and_reset_still_accept_valid_forms(self):
        self.client.force_login(self.viewer)
        new_password = 'new-linked-to-test-viewer-321!'
        response = self.client.post(reverse('password_change'), {
            'old_password': self.password, 'new_password1': new_password, 'new_password2': new_password,
        })
        self.assertRedirects(response, reverse('password_change_done'))
        self.viewer.refresh_from_db()
        self.assertTrue(self.viewer.check_password(new_password))

        guest = Client()
        uid = urlsafe_base64_encode(force_bytes(self.viewer.pk))
        token = default_token_generator.make_token(self.viewer)
        form_url = reverse('password_reset_confirm', args=[uid, 'set-password'])
        self.assertRedirects(guest.get(reverse('password_reset_confirm', args=[uid, token])), form_url)
        self.assertRedirects(guest.post(form_url, {
            'new_password1': self.password, 'new_password2': self.password,
        }), reverse('password_reset_complete'))
        self.viewer.refresh_from_db()
        self.assertTrue(self.viewer.check_password(self.password))

    def test_failed_avatar_cleanup_remains_retriable_in_studio(self):
        entry = ErasureRequest.objects.create(user=self.viewer, notice_version=NOTICE_VERSION)
        self.client.force_login(self.admin)
        action = reverse('admin:privacy_review', args=[entry.pk])
        avatar_name = 'avatars/' + 'b' * 32 + '.webp'
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            storage = self.viewer.avatar.storage
            self.viewer.avatar = storage.save(avatar_name, ContentFile(b'demo image'))
            self.viewer.save(update_fields=['avatar'])
            with patch.object(storage, 'delete', side_effect=OSError('Test storage failure')):
                with self.assertLogs('django.test', level='ERROR'):
                    with self.captureOnCommitCallbacks(execute=True):
                        response = self.client.post(action, {'action': 'complete', 'confirmed': 'yes'})
            self.assertRedirects(response, reverse('admin:privacy_requests'))
            entry.refresh_from_db()
            self.assertEqual(entry.avatar_pending, avatar_name)
            self.assertContains(self.client.get(reverse('admin:privacy_requests'), {'status': 'completed'}), 'Thử xóa ảnh lại')

            self.assertRedirects(self.client.post(action, {'action': 'retry_avatar'}), reverse('admin:privacy_requests'))
            entry.refresh_from_db()
            self.assertEqual(entry.avatar_pending, '')
            self.assertFalse(storage.exists(avatar_name))

    @override_settings(VNPAY_TMN_CODE='test-merchant', VNPAY_HASH_SECRET='test-only')
    def test_erasure_disables_access_removes_personal_data_and_preserves_transaction(self):
        entry = ErasureRequest.objects.create(user=self.viewer, notice_version=NOTICE_VERSION)
        order = Order.objects.create(user=self.viewer, plan=self.plan, amount=59000, days=30)
        Watchlist.objects.create(user=self.viewer, movie=self.movie)
        History.objects.create(user=self.viewer, episode=self.episode, position=8)
        Comment.objects.create(user=self.viewer, movie=self.movie, content='My comment')
        hosted = Room.objects.create(host=self.viewer, episode=self.episode, name='My room')
        Chat.objects.create(room=hosted, user=self.viewer, content='My message')
        viewer_client = Client()
        viewer_client.force_login(self.viewer)
        self.client.force_login(self.admin)
        action = reverse('admin:privacy_review', args=[entry.pk])
        avatar_name = 'avatars/' + 'a' * 32 + '.webp'
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            storage = self.viewer.avatar.storage
            self.viewer.avatar = storage.save(avatar_name, ContentFile(b'demo image'))
            self.viewer.save(update_fields=['avatar'])
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(action, {'action': 'complete', 'confirmed': 'yes'})
            self.assertRedirects(response, reverse('admin:privacy_requests'))
            self.assertFalse(storage.exists(avatar_name))

        entry.refresh_from_db()
        self.viewer.refresh_from_db()
        self.assertEqual(entry.status, ErasureRequest.Status.COMPLETED)
        self.assertEqual(entry.reviewed_by_id, self.admin.pk)
        self.assertEqual(entry.avatar_pending, '')
        self.assertFalse(self.viewer.is_active)
        self.assertFalse(self.viewer.has_usable_password())
        self.assertNotIn('viewer', self.viewer.email)
        self.assertEqual(self.viewer.first_name, '')
        self.assertIsNotNone(self.viewer.erased_at)
        for model in (Watchlist, History, Comment, Chat, Room):
            self.assertFalse(model.objects.exists())
        self.assertEqual(viewer_client.get(reverse('profile')).status_code, 302)
        self.assertIsNone(authenticate(username='viewer', password=self.password))

        callback = {
            'vnp_TxnRef': order.pk.hex, 'vnp_TmnCode': 'test-merchant', 'vnp_Amount': str(order.amount * 100),
            'vnp_ResponseCode': '00', 'vnp_TransactionStatus': '00', 'vnp_TransactionNo': '1234',
        }
        callback['vnp_SecureHash'] = signature(callback)
        self.assertEqual(self.client.get(reverse('ipn'), callback).json()['RspCode'], '00')
        order.refresh_from_db()
        self.viewer.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.user_id, self.viewer.pk)
        self.assertIsNone(self.viewer.vip_until)
