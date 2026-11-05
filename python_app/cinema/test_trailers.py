"""Trailer inputs and public preview assets stay separate from protected episodes."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import StopUpload
from django.test import RequestFactory, TestCase, override_settings
from django.urls import resolve, reverse

from .models import Episode, Movie
from .trailers import MAX_TRAILER_BYTES, validate_trailer_file, validate_youtube_url, youtube_embed_url
from .uploads import BoundedUploadHandler


class YouTubeTrailerTests(TestCase):
    video_id = 'AbC_def-123'
    embed = 'https://www.youtube-nocookie.com/embed/AbC_def-123?rel=0'

    def test_credit_is_optional_plain_text_with_a_500_character_limit(self):
        movie = Movie(title='Trailer credit', slug='trailer-credit', description='Example')
        movie.full_clean()
        movie.trailer_credit = 'Blender Foundation · CC BY 3.0 · https://peach.blender.org/'
        movie.full_clean()
        movie.save()
        movie.refresh_from_db()
        self.assertIn('Blender Foundation', movie.trailer_credit)
        movie.trailer_credit = 'x' * 501
        with self.assertRaises(ValidationError) as error:
            movie.full_clean()
        self.assertIn('trailer_credit', error.exception.message_dict)

    def test_supported_links_produce_only_a_canonical_privacy_embed(self):
        for value in (
            f'https://www.youtube.com/watch?v={self.video_id}&t=30&autoplay=1',
            f'https://youtube.com/watch?v={self.video_id}',
            f'https://m.youtube.com/watch?v={self.video_id}',
            f'https://youtu.be/{self.video_id}?si=not-forwarded',
            f'https://www.youtube.com/embed/{self.video_id}',
            f'https://www.youtube.com/shorts/{self.video_id}',
            f'https://www.youtube.com/live/{self.video_id}',
            f'https://www.youtube-nocookie.com/embed/{self.video_id}?autoplay=1',
        ):
            with self.subTest(url=value):
                self.assertEqual(youtube_embed_url(value), self.embed)
                validate_youtube_url(value)

    def test_untrusted_urls_html_and_ambiguous_ids_fail_closed(self):
        for value in (
            'javascript:alert(1)', '<iframe src="https://www.youtube.com/embed/AbC_def-123"></iframe>',
            'https://youtube.com.example.test/watch?v=AbC_def-123',
            'https://youtube.com@evil.example/watch?v=AbC_def-123',
            'https://user:password@youtube.com/watch?v=AbC_def-123',
            'http://youtube.com/watch?v=AbC_def-123', 'https://youtube.com:8443/watch?v=AbC_def-123',
            'https://youtube.com/watch?v=AbC_def-123&v=Other_id123',
            'https://youtu.be/AbC_def-123/extra', 'https://youtu.be/%41bC_def-123',
            'https://youtube.com/watch?v=short', 'https://youtube.com/redirect?q=https://evil.example',
            'https://you\ntube.com/watch?v=AbC_def-123', 'https://youtube.com\\evil.test/watch?v=AbC_def-123',
            'https://www.youtube-nocookie.com/watch?v=AbC_def-123',
        ):
            with self.subTest(url=value):
                self.assertEqual(youtube_embed_url(value), '')
                with self.assertRaises(ValidationError):
                    validate_youtube_url(value)
        self.assertEqual(youtube_embed_url(None), '')
        self.assertEqual(youtube_embed_url(''), '')

    def test_model_rejects_two_sources_and_invalid_links_without_promoting_an_episode(self):
        movie = Movie(title='Trailer metadata', slug='trailer-metadata', description='Example',
                      trailer_url='https://youtu.be/AbC_def-123', trailer_file='trailers/existing.mp4')
        with self.assertRaises(ValidationError) as error:
            movie.full_clean()
        self.assertIn('trailer_url', error.exception.message_dict)
        self.assertIn('trailer_file', error.exception.message_dict)
        movie.trailer_file = ''
        movie.full_clean()
        movie.is_cinema_release = True
        movie.save()
        self.assertTrue(movie.has_trailer)
        self.assertEqual(movie.trailer_source_kind, 'youtube')
        self.assertEqual(movie.trailer_embed_url, self.embed)
        self.assertFalse(Episode.objects.filter(movie=movie).exists())
        movie.trailer_url = 'https://evil.example/embed/AbC_def-123'
        self.assertFalse(movie.has_trailer)
        self.assertEqual(movie.trailer_embed_url, '')
        with self.assertRaises(ValidationError):
            movie.full_clean()


@skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg and ffprobe are required')
class TrailerFileTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        directory = tempfile.TemporaryDirectory(prefix='lumiere-trailer-fixture-')
        cls.addClassCleanup(directory.cleanup)
        clip = Path(directory.name) / 'clip.mp4'
        subprocess.run([
            'ffmpeg', '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=12',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100', '-t', '1', '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-threads', '1', str(clip),
        ], capture_output=True, check=True, timeout=30)
        cls.clip_bytes = clip.read_bytes()

    def setUp(self):
        cache.clear()
        directory = tempfile.TemporaryDirectory(prefix='lumiere-trailer-test-')
        self.addCleanup(directory.cleanup)
        self.media = Path(directory.name)
        settings_override = override_settings(MEDIA_ROOT=self.media)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.admin = get_user_model().objects.create_superuser('trailer-admin', 'trailer-admin@example.test')
        self.client.force_login(self.admin)
        self.url = reverse('admin:cinema_movie_add')

    def upload(self, content=None, name='preview.mp4'):
        return SimpleUploadedFile(name, self.clip_bytes if content is None else content, content_type='video/mp4')

    def payload(self, **values):
        return {
            'title': 'Trailer film', 'slug': 'trailer-film', 'description': 'Example film', 'artwork': 'orbit',
            'year': '2026', 'country': 'Việt Nam', 'kind': 'movie', 'is_cinema_release': 'on',
            'published': 'on', 'trailer_url': '', '_save': 'Save', **values,
        }

    def test_real_h264_upload_has_random_name_and_no_private_episode_side_effect(self):
        response = self.client.post(self.url, self.payload(trailer_file=self.upload(name='../../trailer.mp4')))
        self.assertEqual(response.status_code, 302)
        movie = Movie.objects.get()
        self.assertTrue(movie.is_cinema_release)
        self.assertTrue(movie.has_trailer)
        self.assertEqual(movie.trailer_source_kind, 'file')
        self.assertRegex(movie.trailer_file.name, r'^trailers/[0-9a-f]{32}\.mp4$')
        self.assertEqual(Path(movie.trailer_file.path).read_bytes(), self.clip_bytes)
        self.assertTrue(movie.trailer_file.url.startswith('/media/trailers/'))
        self.assertFalse(Episode.objects.exists())

    def test_fake_mp4_and_unsupported_extension_are_rejected_before_storage(self):
        for upload in (self.upload(b'<!doctype html><script>alert(1)</script>'), self.upload(name='payload.php')):
            with self.subTest(name=upload.name):
                response = self.client.post(self.url, self.payload(trailer_file=upload))
                self.assertEqual(response.status_code, 200)
                self.assertIn('trailer_file', response.context['adminform'].form.errors)
                self.assertFalse(Movie.objects.exists())
        self.assertEqual(list(self.media.rglob('*.mp4')), [])

    def test_uploaded_file_and_youtube_link_cannot_be_saved_together(self):
        response = self.client.post(self.url, self.payload(trailer_file=self.upload(), trailer_url='https://youtu.be/AbC_def-123'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('trailer_url', response.context['adminform'].form.errors)
        self.assertFalse(Movie.objects.exists())
        self.assertEqual(list(self.media.rglob('*.mp4')), [])

    def test_duration_codec_and_dimensions_are_checked(self):
        valid = {'format': {'format_name': 'mov,mp4,m4a,3gp,3g2,mj2', 'duration': '1'},
                 'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 160, 'height': 90},
                             {'codec_type': 'audio', 'codec_name': 'aac'}]}
        variants = []
        for duration in ('0', '-1', '300.01', 'nan', 'inf'):
            data = json.loads(json.dumps(valid)); data['format']['duration'] = duration; variants.append(data)
        for field, value in (('codec_name', 'vp9'), ('width', 8192), ('height', 4320)):
            data = json.loads(json.dumps(valid)); data['streams'][0][field] = value; variants.append(data)
        data = json.loads(json.dumps(valid)); data['streams'][1]['codec_name'] = 'opus'; variants.append(data)
        data = json.loads(json.dumps(valid)); data['streams'].append({'codec_type': 'data'}); variants.append(data)
        for data in variants:
            with self.subTest(data=data), patch('cinema.trailers.subprocess.run', return_value=SimpleNamespace(stdout=json.dumps(data))):
                with self.assertRaises(ValidationError):
                    validate_trailer_file(self.upload())
        valid['format']['duration'] = '300'
        with patch('cinema.trailers.subprocess.run', return_value=SimpleNamespace(stdout=json.dumps(valid))):
            validate_trailer_file(self.upload())

    def test_timeout_missing_tool_or_invalid_probe_output_are_validation_errors(self):
        for error in (subprocess.TimeoutExpired('ffprobe', 10), FileNotFoundError('ffprobe missing'), ValueError('bad result')):
            sources = []
            def fail(command, **kwargs):
                sources.append(command[-1])
                self.assertIn('file,pipe', command)
                self.assertIn('mov', command)
                raise error
            with self.subTest(error=type(error).__name__), patch('cinema.trailers.subprocess.run', side_effect=fail):
                with self.assertRaises(ValidationError):
                    validate_trailer_file(self.upload())
            self.assertTrue(sources)
            self.assertFalse(Path(sources[0]).exists())
        with patch('cinema.trailers.subprocess.run', return_value=SimpleNamespace(stdout='not-json')):
            with self.assertRaises(ValidationError):
                validate_trailer_file(self.upload())

    def test_oversize_rejected_before_probe_and_stream_rejection_cannot_clear_saved_file(self):
        upload = self.upload()
        upload.size = MAX_TRAILER_BYTES + 1
        with patch('cinema.trailers.subprocess.run') as probe, self.assertRaises(ValidationError):
            validate_trailer_file(upload)
        probe.assert_not_called()
        self.assertEqual(self.client.post(self.url, self.payload(trailer_file=self.upload())).status_code, 302)
        movie = Movie.objects.get()
        original_name = movie.trailer_file.name
        with patch('cinema.uploads.MAX_TRAILER_BYTES', 10):
            response = self.client.post(reverse('admin:cinema_movie_change', args=[movie.pk]), self.payload(
                title='Must not save', trailer_file=self.upload(), **{'trailer_file-clear': 'on'},
            ))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['adminform'].form.errors)
        movie.refresh_from_db()
        self.assertEqual(movie.title, 'Trailer film')
        self.assertEqual(movie.trailer_file.name, original_name)
        self.assertTrue(Path(movie.trailer_file.path).exists())

    def test_metadata_edits_do_not_probe_an_already_saved_trailer(self):
        self.client.post(self.url, self.payload(trailer_file=self.upload()))
        movie = Movie.objects.get()
        with patch('cinema.trailers.subprocess.run') as probe:
            response = self.client.post(reverse('admin:cinema_movie_change', args=[movie.pk]), self.payload(title='Updated title'))
        self.assertEqual(response.status_code, 302)
        probe.assert_not_called()
        movie.refresh_from_db()
        self.assertEqual(movie.title, 'Updated title')

    def test_duplicate_trailer_file_parts_fail_closed(self):
        response = self.client.post(self.url, self.payload(trailer_file=[self.upload(), self.upload()]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['adminform'].form.errors)
        self.assertFalse(Movie.objects.exists())
        self.assertEqual(list(self.media.rglob('*.mp4')), [])

    def test_upload_permission_is_specific_to_movie_admin_action(self):
        users = get_user_model()
        viewer = users.objects.create_user('trailer-viewer', 'trailer-viewer@example.test')
        staff = users.objects.create_user('trailer-staff', 'trailer-staff@example.test', is_staff=True)
        adder = users.objects.create_user('trailer-adder', 'trailer-adder@example.test', is_staff=True)
        adder.user_permissions.add(Permission.objects.get(codename='add_movie'))
        changer = users.objects.create_user('trailer-changer', 'trailer-changer@example.test', is_staff=True)
        changer.user_permissions.add(Permission.objects.get(codename='change_movie'))
        movie = Movie.objects.create(title='Existing', slug='existing-trailer-permissions', description='Example')
        change = reverse('admin:cinema_movie_change', args=[movie.pk])
        factory = RequestFactory()
        for user, route in ((viewer, self.url), (staff, self.url), (adder, change), (changer, self.url), (self.admin, reverse('profile'))):
            with self.subTest(user=user.username, route=route):
                request = factory.post(route); request.user = user; request.resolver_match = resolve(route)
                handler = BoundedUploadHandler(request)
                with self.assertRaises(StopUpload):
                    handler.new_file('trailer_file', 'clip.mp4', 'video/mp4', None)
        request = factory.post(change); request.user = changer; request.resolver_match = resolve(change)
        handler = BoundedUploadHandler(request)
        handler.new_file('trailer_file', 'clip.mp4', 'video/mp4', None)
        self.assertEqual(handler.limit, MAX_TRAILER_BYTES)
