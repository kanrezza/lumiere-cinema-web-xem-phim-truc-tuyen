"""Avatar uploads are private account changes and publish only normalized images."""
import io
import struct
import tempfile
import zlib
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image, PngImagePlugin

from .avatars import MAX_AVATAR_BYTES


class SavedAvatars(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.sources = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'img' and 'data-saved-avatar' in attrs:
            self.sources.append(attrs.get('src'))


def image_upload(name='portrait.png', *, size=(700, 500), color=(220, 70, 50), image_format='PNG', **save_options):
    buffer = io.BytesIO()
    image = Image.new('RGB', size, color)
    image.save(buffer, format=image_format, **save_options)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/' + image_format.lower())


def png_with_dimensions(width, height):
    data = bytearray(image_upload(size=(1, 1)).read())
    struct.pack_into('>II', data, 16, width, height)
    struct.pack_into('>I', data, 29, zlib.crc32(data[12:29]))
    return SimpleUploadedFile('large.png', bytes(data), content_type='image/png')


class AvatarUploadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.viewer = users.objects.create_user('avatar-viewer', 'avatar-viewer@example.test', first_name='Original')
        cls.other = users.objects.create_user('avatar-other', 'avatar-other@example.test')
        cls.staff = users.objects.create_user('avatar-staff', 'avatar-staff@example.test', is_staff=True)
        cls.inactive = users.objects.create_user('avatar-inactive', 'avatar-inactive@example.test', is_active=False)

    def setUp(self):
        cache.clear()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.media = Path(temporary.name)
        settings_override = override_settings(MEDIA_ROOT=self.media)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.url = reverse('profile_avatar')
        self.client.force_login(self.viewer)

    def upload(self, image=None):
        response = self.client.post(self.url, {'avatar': image or image_upload()})
        self.assertRedirects(response, reverse('profile') + '#avatar', fetch_redirect_response=False)
        self.viewer.refresh_from_db()
        return self.viewer.avatar.name

    def avatar_files(self):
        return list((self.media / 'avatars').glob('*'))

    def test_authenticated_regular_user_uploads_a_randomized_normalized_public_webp(self):
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('Comment', 'Private original metadata')
        name = self.upload(image_upload(name='../../personal-location.png', pnginfo=metadata))
        self.assertRegex(name, r'^avatars/[0-9a-f]{32}\.webp$')
        self.assertTrue((self.media / name).is_file())
        with Image.open(self.media / name) as saved:
            self.assertEqual(saved.format, 'WEBP')
            self.assertEqual(saved.size, (512, 512))
            self.assertFalse(saved.getexif())
            self.assertNotIn('Comment', saved.info)
            self.assertNotIn('exif', saved.info)
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SavedAvatars(response.content.decode()).sources, [self.viewer.avatar.url, self.viewer.avatar.url])
        self.assertEqual(SavedAvatars(self.client.get(reverse('catalog')).content.decode()).sources, [self.viewer.avatar.url])
        self.assertEqual(len(self.avatar_files()), 1)

    def test_jpeg_orientation_is_applied_before_center_crop_and_metadata_is_removed(self):
        # Rotation90deg transforms the original leftred/rightblue image into topred/bottomblue.
        image = Image.new('RGB', (100, 100), (230, 20, 20))
        image.paste((20, 20, 230), (50, 0, 100, 100))
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = 'Private description'
        data = io.BytesIO()
        image.save(data, 'JPEG', exif=exif)
        name = self.upload(SimpleUploadedFile('rotated.jpg', data.getvalue(), content_type='image/jpeg'))
        with Image.open(self.media / name) as saved:
            top = saved.convert('RGB').getpixel((256, 50))
            bottom = saved.convert('RGB').getpixel((256, 460))
            self.assertGreater(top[0], top[2] + 100)
            self.assertGreater(bottom[2], bottom[0] + 100)
            self.assertFalse(saved.getexif())

    def test_static_webp_and_transparent_png_are_supported(self):
        for image in (image_upload(name='portrait.webp', image_format='WEBP'),):
            self.upload(image)
        data = io.BytesIO()
        Image.new('RGBA', (20, 20), (20, 50, 90, 0)).save(data, 'PNG')
        name = self.upload(SimpleUploadedFile('transparent.png', data.getvalue(), content_type='image/png'))
        with Image.open(self.media / name) as saved:
            self.assertEqual(saved.size, (512, 512))
            self.assertEqual(saved.mode, 'RGBA')
            self.assertEqual(saved.getpixel((0, 0))[3], 0)

    def test_replacing_and_removing_delete_only_previous_managed_file_after_commit(self):
        first = self.upload()
        with self.captureOnCommitCallbacks(execute=True):
            second = self.upload(image_upload(color=(20, 80, 150)))
            self.assertTrue((self.media / first).exists())
        self.assertNotEqual(first, second)
        self.assertFalse((self.media / first).exists())
        self.assertTrue((self.media / second).exists())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {'remove_avatar': 'on'})
            self.assertTrue((self.media / second).exists())
        self.assertRedirects(response, reverse('profile') + '#avatar', fetch_redirect_response=False)
        self.viewer.refresh_from_db()
        self.assertFalse(self.viewer.avatar)
        self.assertFalse((self.media / second).exists())
        self.assertNotContains(self.client.get(reverse('profile')), 'data-saved-avatar')

    def test_invalid_image_or_conflicting_remove_preserves_the_saved_image_and_profile(self):
        previous = self.upload()
        for data in (
            {'avatar': SimpleUploadedFile('fake.jpg', b'<svg><script>alert(1)</script></svg>', content_type='image/jpeg')},
            {'avatar': image_upload(), 'remove_avatar': 'on'},
            {'avatar': SimpleUploadedFile('bad.png', b'broken'), 'remove_avatar': 'on'},
            {},
        ):
            with self.subTest(fields=list(data)):
                response = self.client.post(self.url, {**data, 'first_name': 'Changed without permission'})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['avatar_form'].errors)
                self.assertEqual(response.wsgi_request.user.avatar.name, previous)
                self.viewer.refresh_from_db()
                self.assertEqual(self.viewer.avatar.name, previous)
                self.assertEqual(self.viewer.first_name, 'Original')
                self.assertTrue((self.media / previous).exists())
        self.assertEqual(len(self.avatar_files()), 1)

    def test_oversize_stream_is_an_error_and_cannot_silently_remove_an_existing_photo(self):
        previous = self.upload()
        response = self.client.post(self.url, {
            'avatar': SimpleUploadedFile('too-large.png', b'x' * (MAX_AVATAR_BYTES + 1), content_type='image/png'),
            'remove_avatar': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '5 MB')
        self.assertTrue(response.context['avatar_form'].errors)
        self.viewer.refresh_from_db()
        self.assertEqual(self.viewer.avatar.name, previous)
        self.assertTrue((self.media / previous).exists())
        self.assertEqual(len(self.avatar_files()), 1)

    def test_dimension_and_pixel_budgets_are_enforced_before_decoding(self):
        for image in (png_with_dimensions(8193, 1), png_with_dimensions(5000, 5000)):
            response = self.client.post(self.url, {'avatar': image})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '20 megapixel')
            self.assertTrue(response.context['avatar_form'].errors)
        self.viewer.refresh_from_db()
        self.assertFalse(self.viewer.avatar)
        self.assertEqual(self.avatar_files(), [])

    def test_animated_images_and_non_image_payloads_are_rejected(self):
        animated = io.BytesIO()
        Image.new('RGB', (20, 20), 'red').save(animated, format='WEBP', save_all=True, append_images=[Image.new('RGB', (20, 20), 'blue')], duration=50, loop=0)
        payloads = (
            SimpleUploadedFile('animation.webp', animated.getvalue(), content_type='image/webp'),
            SimpleUploadedFile('vector.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>', content_type='image/svg+xml'),
            SimpleUploadedFile('page.png', b'<!doctype html><script>alert(1)</script>', content_type='image/png'),
        )
        for image in payloads:
            with self.subTest(name=image.name):
                response = self.client.post(self.url, {'avatar': image})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['avatar_form'].errors)
        self.assertEqual(self.avatar_files(), [])

    def test_account_ids_and_unrelated_profile_fields_cannot_target_another_user(self):
        self.client.post(self.url, {'avatar': image_upload(), 'user_id': self.other.pk, 'id': self.other.pk, 'first_name': 'Changed'})
        self.viewer.refresh_from_db()
        self.other.refresh_from_db()
        self.assertTrue(self.viewer.avatar)
        self.assertFalse(self.other.avatar)
        self.assertEqual(self.viewer.first_name, 'Original')
        self.client.post(reverse('profile'), {'first_name': 'New name', 'last_name': '', 'bio': 'A real profile edit'})
        self.viewer.refresh_from_db()
        self.assertEqual(self.viewer.first_name, 'New name')
        self.assertTrue(self.viewer.avatar)

    def test_guest_inactive_get_and_missing_csrf_are_denied(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.logout()
        response = self.client.post(self.url, {'avatar': image_upload()})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)
        self.client.force_login(self.inactive)
        self.assertEqual(self.client.post(self.url, {'avatar': image_upload()}).status_code, 302)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.viewer)
        self.assertEqual(csrf_client.post(self.url, {'avatar': image_upload()}).status_code, 403)
        self.assertEqual(self.avatar_files(), [])

    def test_duplicate_or_unexpected_file_parts_fail_closed(self):
        previous = self.upload()
        for data in ({'avatar': [image_upload(), image_upload()]}, {'source': image_upload()}, {'avatar': image_upload(), 'other': image_upload()}):
            with self.subTest(fields=list(data)):
                response = self.client.post(self.url, data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['avatar_form'].errors)
                self.viewer.refresh_from_db()
                self.assertEqual(self.viewer.avatar.name, previous)
        self.assertEqual(len(self.avatar_files()), 1)

    def test_regular_users_cannot_use_avatar_permission_on_other_upload_routes(self):
        response = self.client.post(reverse('profile'), {'avatar': image_upload(), 'first_name': 'Original', 'last_name': '', 'bio': ''})
        self.assertEqual(response.status_code, 200)
        self.viewer.refresh_from_db()
        self.assertFalse(self.viewer.avatar)
        self.assertEqual(self.avatar_files(), [])
        self.client.force_login(self.staff)
        response = self.client.post(self.url, {'source': image_upload()})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['avatar_form'].errors)

    def test_cleanup_never_deletes_shared_or_unrelated_stored_files(self):
        first = self.upload()
        self.other.avatar = first
        self.other.save(update_fields=['avatar'])
        with self.captureOnCommitCallbacks(execute=True):
            self.upload(image_upload(color=(20, 80, 150)))
        self.assertTrue((self.media / first).exists())
        unrelated = self.media / 'posters' / 'keep.png'
        unrelated.parent.mkdir()
        unrelated.write_bytes(b'not-an-avatar')
        self.viewer.avatar = 'posters/keep.png'
        self.viewer.save(update_fields=['avatar'])
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, {'remove_avatar': 'on'})
        self.assertTrue(unrelated.exists())

    def test_database_save_failure_preserves_old_avatar_and_cleans_new_file(self):
        previous = self.upload()
        with patch.object(get_user_model(), '_do_update', side_effect=DatabaseError('simulated database error')):
            with self.assertRaises(DatabaseError):
                self.client.post(self.url, {'avatar': image_upload(color=(20, 80, 150))})
        self.viewer.refresh_from_db()
        self.assertEqual(self.viewer.avatar.name, previous)
        self.assertTrue((self.media / previous).exists())
        self.assertEqual([file.name for file in self.avatar_files()], [Path(previous).name])
