"""Subtitle text is bounded and only available to authorized full-film viewers."""
from datetime import timedelta
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import StopUpload
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone

from .models import Episode, History, Movie, Subtitle
from .subtitles import MAX_SUBTITLE_BYTES, normalize_subtitle
from .uploads import BoundedUploadHandler


SRT = '1\r\n00:00:01,250 --> 00:00:03,500\r\nXin chào.\r\nDòng thứ hai.\r\n\r\n2\r\n00:00:04,000 --> 00:00:05,000\r\nGood evening.\r\n'
VTT = 'WEBVTT\n\n00:00:01.250 --> 00:00:03.500\nXin chào.\nDòng thứ hai.\n\n00:00:04.000 --> 00:00:05.000\nGood evening.\n'


def subtitle_upload(text=SRT, name='dialogue.srt'):
    return SimpleUploadedFile(name, text.encode('utf-8') if isinstance(text, str) else text, content_type='text/plain')


class SubtitleParserTests(SimpleTestCase):
    def test_srt_bom_crlf_and_multiple_lines_become_canonical_vtt(self):
        upload = subtitle_upload(b'\xef\xbb\xbf' + SRT.encode())
        self.assertEqual(normalize_subtitle(upload), VTT)
        self.assertEqual(upload.tell(), 0)

    def test_vtt_ids_settings_and_notes_are_not_forwarded(self):
        source = ('WEBVTT\n\nNOTE Private metadata should not be delivered\nignored\n\n'
                  'cue-name\n00:01.250 --> 00:03.500 line:90% position:10%\nXin chào.\nDòng thứ hai.\n\n'
                  '00:04.000 --> 00:05.000\nGood evening.\n')
        self.assertEqual(normalize_subtitle(subtitle_upload(source, 'dialogue.vtt')), VTT)

    def test_markup_becomes_literal_text_without_styles_or_remote_references(self):
        source = 'WEBVTT\n\n00:01.000 --> 00:02.000\n<b>Hello</b> &amp; <script src="https://bad.test/x.js">x</script>\n'
        result = normalize_subtitle(subtitle_upload(source, 'dialogue.vtt'))
        self.assertIn('&lt;b&gt;Hello&lt;/b&gt; &amp;', result)
        self.assertNotIn('<script', result)
        for source in (
            'WEBVTT\n\nSTYLE\n::cue {background:url(https://bad.test/x)}\n\n00:01.000 --> 00:02.000\nHello\n',
            'WEBVTT\n\nREGION\nid:region\n\n00:01.000 --> 00:02.000\nHello\n',
            'WEBVTT\nX-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0\n\n00:01.000 --> 00:02.000\nHello\n',
        ):
            with self.subTest(source=source), self.assertRaises(ValidationError):
                normalize_subtitle(subtitle_upload(source, 'dialogue.vtt'))

    def test_malformed_or_empty_files_and_bad_encoding_are_rejected(self):
        for upload in (
            subtitle_upload('', 'empty.srt'), subtitle_upload('WEBVTT\n\n', 'empty.vtt'),
            subtitle_upload(b'\xff\xfe\x00', 'utf16.srt'), subtitle_upload('1\n00:01.000 --> 00:02.000\nHi\x00', 'null.srt'),
            subtitle_upload(VTT, 'dialogue.html'), subtitle_upload(VTT, 'wrong.srt'),
            subtitle_upload('1\n00:00:01,000 --> 00:00:02,000\nHi', 'missing-header.vtt'),
            subtitle_upload('1\n00:00:01,000 --> 00:00:02,000', 'no-cue.srt'),
        ):
            with self.subTest(name=upload.name), self.assertRaises(ValidationError):
                normalize_subtitle(upload)

    def test_timing_order_and_range_are_checked_but_overlap_is_allowed(self):
        for timing in ('00:00:02,000 --> 00:00:01,000', '00:00:01,000 --> 00:00:01,000',
                       '00:61:00,000 --> 00:62:00,000', '-1:00:01,000 --> 00:00:02,000',
                       '999999:00:00,000 --> 999999:00:02,000'):
            with self.subTest(timing=timing), self.assertRaises(ValidationError):
                normalize_subtitle(subtitle_upload(f'1\n{timing}\nHello'))
        with self.assertRaises(ValidationError):
            normalize_subtitle(subtitle_upload('1\n00:00:03,000 --> 00:00:05,000\nA\n\n2\n00:00:02,000 --> 00:00:06,000\nB'))
        result = normalize_subtitle(subtitle_upload('1\n00:00:01,000 --> 00:00:05,000\nA\n\n2\n00:00:02,000 --> 00:00:06,000\nB'))
        self.assertIn('00:00:02.000 --> 00:00:06.000', result)

    def test_file_size_cue_count_and_per_cue_text_are_bounded(self):
        oversized = subtitle_upload(b'x' * (MAX_SUBTITLE_BYTES + 1))
        with self.assertRaises(ValidationError):
            normalize_subtitle(oversized)
        with patch('cinema.subtitles.MAX_SUBTITLE_CUES', 1), self.assertRaises(ValidationError):
            normalize_subtitle(subtitle_upload(SRT))
        with self.assertRaises(ValidationError):
            normalize_subtitle(subtitle_upload('1\n00:00:01,000 --> 00:00:02,000\n' + 'x' * 16001))


class SubtitleAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('subtitle-admin', 'subtitle-admin@example.test')
        cls.movie = Movie.objects.create(title='Subtitle film', slug='subtitle-admin-film', published=True)
        cls.episode = Episode.objects.create(movie=cls.movie, title='Full film', status='ready', duration=600)

    def setUp(self):
        cache.clear()
        directory = tempfile.TemporaryDirectory(prefix='lumiere-subtitle-tests-')
        self.addCleanup(directory.cleanup)
        self.media = Path(directory.name)
        settings_override = override_settings(MEDIA_ROOT=self.media)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.client.force_login(self.admin)
        self.url = reverse('admin:cinema_subtitle_add')

    def payload(self, **kwargs):
        return {'episode': self.episode.pk, 'language': 'vi', 'label': 'Tiếng Việt', '_save': 'Save', **kwargs}

    def test_admin_upload_is_stored_as_normalized_text_without_public_file(self):
        response = self.client.post(self.url, self.payload(upload_file=subtitle_upload()))
        self.assertEqual(response.status_code, 302)
        track = Subtitle.objects.get()
        self.assertEqual(track.content, VTT)
        self.assertEqual(track.episode, self.episode)
        self.assertEqual(list(self.media.rglob('*')), [])

    def test_new_subtitle_requires_file_and_bad_extension_is_rejected(self):
        for changes in ({}, {'upload_file': subtitle_upload(VTT, 'payload.php')}):
            with self.subTest(changes=list(changes)):
                response = self.client.post(self.url, self.payload(**changes))
                self.assertEqual(response.status_code, 200)
                self.assertIn('upload_file', response.context['adminform'].form.errors)
                self.assertFalse(Subtitle.objects.exists())

    def test_metadata_edits_keep_content_and_valid_replacement_updates_it(self):
        track = Subtitle.objects.create(episode=self.episode, language='vi', label='Before', content=VTT)
        url = reverse('admin:cinema_subtitle_change', args=[track.pk])
        self.assertEqual(self.client.post(url, self.payload(label='Tiếng Việt mới')).status_code, 302)
        track.refresh_from_db()
        self.assertEqual(track.content, VTT)
        self.assertEqual(track.label, 'Tiếng Việt mới')
        replacement = 'WEBVTT\n\n00:00.000 --> 00:01.000\nNew words\n'
        self.assertEqual(self.client.post(url, self.payload(upload_file=subtitle_upload(replacement, 'new.vtt'))).status_code, 302)
        track.refresh_from_db()
        self.assertIn('New words', track.content)

    def test_invalid_or_oversize_replacement_cannot_clear_existing_content_or_save_metadata(self):
        track = Subtitle.objects.create(episode=self.episode, language='vi', label='Original', content=VTT)
        url = reverse('admin:cinema_subtitle_change', args=[track.pk])
        for upload, limit in ((subtitle_upload('<script>bad</script>'), MAX_SUBTITLE_BYTES), (subtitle_upload(), 8)):
            with self.subTest(limit=limit), patch('cinema.uploads.MAX_SUBTITLE_BYTES', limit):
                response = self.client.post(url, self.payload(label='Should not save', upload_file=upload))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['adminform'].form.errors)
                track.refresh_from_db()
                self.assertEqual(track.content, VTT)
                self.assertEqual(track.label, 'Original')

    def test_duplicate_parts_and_duplicate_episode_language_are_rejected(self):
        response = self.client.post(self.url, self.payload(upload_file=[subtitle_upload(), subtitle_upload()]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['adminform'].form.errors)
        self.assertFalse(Subtitle.objects.exists())
        self.assertEqual(self.client.post(self.url, self.payload(upload_file=subtitle_upload())).status_code, 302)
        response = self.client.post(self.url, self.payload(language='VI', upload_file=subtitle_upload()))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['adminform'].form.errors)
        self.assertEqual(Subtitle.objects.count(), 1)

    def test_language_and_label_are_validated(self):
        for changes in ({'language': 'javascript:foo'}, {'label': '<img src=x onerror=alert(1)>'}, {'label': 'Line\nBreak'}):
            with self.subTest(changes=changes):
                response = self.client.post(self.url, self.payload(upload_file=subtitle_upload(), **changes))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['adminform'].form.errors)
                self.assertFalse(Subtitle.objects.exists())
        response = self.client.post(self.url, self.payload(language='EN-us', label='English', upload_file=subtitle_upload()))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Subtitle.objects.get().language, 'en-us')

    def test_upload_permission_is_scoped_to_subtitle_admin_action(self):
        users = get_user_model()
        viewer = users.objects.create_user('subtitle-viewer', 'subtitle-viewer@example.test')
        staff = users.objects.create_user('subtitle-staff', 'subtitle-staff@example.test', is_staff=True)
        adder = users.objects.create_user('subtitle-adder', 'subtitle-adder@example.test', is_staff=True)
        adder.user_permissions.add(Permission.objects.get(codename='add_subtitle'))
        changer = users.objects.create_user('subtitle-changer', 'subtitle-changer@example.test', is_staff=True)
        changer.user_permissions.add(Permission.objects.get(codename='change_subtitle'))
        track = Subtitle.objects.create(episode=self.episode, language='vi', label='Original', content=VTT)
        change = reverse('admin:cinema_subtitle_change', args=[track.pk])
        factory = RequestFactory()
        for user, url in ((viewer, self.url), (staff, self.url), (adder, change), (changer, self.url), (self.admin, reverse('admin:cinema_movie_add'))):
            with self.subTest(user=user.username, url=url):
                request = factory.post(url)
                request.user = user
                request.resolver_match = resolve(url)
                handler = BoundedUploadHandler(request)
                with self.assertRaises(StopUpload):
                    handler.new_file('upload_file', 'captions.srt', 'text/plain', None)
        request = factory.post(change)
        request.user = changer
        request.resolver_match = resolve(change)
        handler = BoundedUploadHandler(request)
        handler.new_file('upload_file', 'captions.srt', 'text/plain', None)
        self.assertEqual(handler.limit, MAX_SUBTITLE_BYTES)

    def test_admin_upload_keeps_csrf_protection(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(self.url, self.payload(upload_file=subtitle_upload()))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Subtitle.objects.exists())


class SubtitleAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.viewer = users.objects.create_user('subtitles-free', 'subtitles-free@example.test')
        cls.member = users.objects.create_user('subtitles-vip', 'subtitles-vip@example.test', vip_until=timezone.now() + timedelta(days=1))
        cls.expired = users.objects.create_user('subtitles-expired', 'subtitles-expired@example.test', vip_until=timezone.now() - timedelta(days=1))
        cls.staff = users.objects.create_user('subtitles-staff', 'subtitles-staff@example.test', is_staff=True)
        cls.movie = Movie.objects.create(title='Subtitle access', slug='subtitle-access', published=True)
        cls.episode = Episode.objects.create(movie=cls.movie, title='Full film', status='ready', duration=600)
        cls.track = Subtitle.objects.create(episode=cls.episode, language='vi', label='Tiếng Việt', content=VTT)
        cls.other = Episode.objects.create(movie=cls.movie, number=2, title='Other episode', status='ready')

    def setUp(self):
        cache.clear()
        self.url = reverse('subtitle', args=[self.episode.pk, self.track.pk])

    def test_guest_is_redirected_and_authorized_viewer_gets_private_utf8_vtt(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.viewer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode('utf-8'), VTT)
        self.assertEqual(response['Content-Type'], 'text/vtt; charset=utf-8')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(History.objects.count(), 0)
        self.assertIsNone(cache.get(f'playback:{self.viewer.pk}'))

    def test_vip_gate_is_checked_on_every_request(self):
        Movie.objects.filter(pk=self.movie.pk).update(is_vip=True)
        for user, expected in ((self.viewer, 403), (self.expired, 403), (self.member, 200), (self.staff, 200)):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.url).status_code, expected)

    def test_drafts_and_unready_episodes_do_not_expose_subtitles_even_to_staff(self):
        self.client.force_login(self.staff)
        Movie.objects.filter(pk=self.movie.pk).update(published=False)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        Movie.objects.filter(pk=self.movie.pk).update(published=True)
        for status in ('pending', 'processing', 'failed'):
            with self.subTest(status=status):
                Episode.objects.filter(pk=self.episode.pk).update(status=status)
                self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_wrong_episode_unknown_track_and_write_methods_fail_closed(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('subtitle', args=[self.other.pk, self.track.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('subtitle', args=[self.episode.pk, self.track.pk + 1000])).status_code, 404)
        self.assertEqual(self.client.post(self.url).status_code, 405)
