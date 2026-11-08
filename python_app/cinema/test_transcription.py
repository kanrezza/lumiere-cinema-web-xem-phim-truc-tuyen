from datetime import timedelta
import json
from pathlib import Path
import tempfile
from unittest.mock import patch, MagicMock

from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Movie, Subtitle, SubtitleTranscription, User
from .transcription import TranscriptionError, local_speech_url, process_transcription, recognize, source_key


@override_settings(SPEECH_API_URL='http://127.0.0.1:5002', SPEECH_MODEL_VERSION='test-v1')
class TranscriptionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = override_settings(PRIVATE_MEDIA_ROOT=Path(self.directory.name))
        self.config.enable()
        self.addCleanup(self.config.disable)
        storage = patch.object(Episode._meta.get_field('source'), 'storage', FileSystemStorage(location=self.directory.name))
        storage.start()
        self.addCleanup(storage.stop)
        self.movie = Movie.objects.create(title='Speech feature', slug='speech-feature', published=True, is_vip=True)
        self.episode = Episode.objects.create(movie=self.movie, title='Episode', status='ready', duration=20, source='originals/speech.mp4')
        path = Path(self.episode.source.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'private-test-original')
        self.member = User.objects.create_user('speech-vip', 'speech-vip@example.test', vip_until=timezone.now() + timedelta(days=1))
        self.viewer = User.objects.create_user('speech-free', 'speech-free@example.test')
        self.client.force_login(self.member)
        self.url = reverse('caption_generate', args=[self.episode.pk])

    def job(self):
        return SubtitleTranscription.objects.create(episode=self.episode, source_key=source_key(self.episode), requested_by=self.member)

    def test_create_is_post_only_and_reuses_version_without_calling_recognizer(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        with patch('cinema.transcription.recognize') as inference:
            first = self.client.post(self.url, {'language': 'auto'})
            second = self.client.post(self.url, {'language': 'auto'})
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(SubtitleTranscription.objects.count(), 1)
        inference.assert_not_called()

    def test_anonymous_and_nonvip_do_not_queue_or_read_jobs(self):
        job = self.job()
        status_url = reverse('caption_generation_status', args=[self.episode.pk, job.pk])
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.assertEqual(self.client.get(status_url).status_code, 302)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertEqual(self.client.get(status_url).status_code, 403)

    def test_draft_or_unready_episode_cannot_be_transcribed(self):
        self.movie.published = False
        self.movie.save(update_fields=['published'])
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.movie.published = True
        self.movie.save(update_fields=['published'])
        self.episode.status = 'processing'
        self.episode.save(update_fields=['status'])
        self.assertEqual(self.client.post(self.url).status_code, 403)

    def test_requires_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.member)
        self.assertEqual(client.post(self.url, {'language': 'auto'}).status_code, 403)

    def test_failed_job_can_be_retried_with_cooldown_without_duplicate_rows(self):
        job = self.job()
        job.status = 'failed'
        job.save(update_fields=['status'])
        response = self.client.post(self.url, {'language': 'auto', 'retry': '1'})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['id'], str(job.pk))
        job.refresh_from_db()
        self.assertEqual(job.status, 'pending')
        job.status = 'failed'
        job.save(update_fields=['status'])
        self.assertEqual(self.client.post(self.url, {'language': 'auto', 'retry': '1'}).status_code, 429)
        self.assertEqual(SubtitleTranscription.objects.count(), 1)

    def test_unconfigured_and_missing_original_are_clear_errors_without_jobs(self):
        with override_settings(SPEECH_API_URL=''):
            self.assertEqual(self.client.post(self.url).status_code, 503)
        Path(self.episode.source.path).unlink()
        self.assertEqual(self.client.post(self.url).status_code, 503)
        self.assertEqual(SubtitleTranscription.objects.count(), 0)

    def test_retry_respects_full_queue_and_can_resume_after_capacity_is_available(self):
        job = self.job()
        SubtitleTranscription.objects.filter(pk=job.pk).update(status='failed')
        for index in range(10):
            SubtitleTranscription.objects.create(episode=self.episode, source_key=f'queued-{index}', requested_by=self.member)
        self.assertEqual(self.client.post(self.url, {'language': 'auto', 'retry': '1'}).status_code, 429)
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertEqual(SubtitleTranscription.objects.filter(status='pending').count(), 10)
        SubtitleTranscription.objects.filter(source_key='queued-0').update(status='failed')
        self.assertEqual(self.client.post(self.url, {'language': 'auto', 'retry': '1'}).status_code, 202)
        job.refresh_from_db()
        self.assertEqual(job.status, 'pending')
        self.assertEqual(SubtitleTranscription.objects.filter(status='pending').count(), 10)

    def test_only_loopback_service_is_allowed(self):
        for value in ('https://example.com', 'http://127.0.0.1:5002@evil.test', 'http://127.0.0.1:5002/#x'):
            with self.subTest(value=value), override_settings(SPEECH_API_URL=value):
                with self.assertRaises(TranscriptionError):
                    local_speech_url()

    def test_worker_creates_real_caption_and_does_not_replace_curated_track(self):
        job = self.job()
        with patch('cinema.transcription.recognize', return_value=('en', 'WEBVTT\n\n00:00:00.000 --> 00:00:04.000\nHello\n')):
            self.assertTrue(process_transcription(job.pk))
            self.assertFalse(process_transcription(job.pk))
        job.refresh_from_db()
        self.assertEqual(job.status, 'ready')
        self.assertEqual(job.subtitle.language, 'en')
        self.assertIn('Hello', job.subtitle.content)
        self.assertIn('tự động', job.subtitle.label)
        response = self.client.get(reverse('caption_generation_status', args=[self.episode.pk, job.pk]))
        self.assertEqual(response.json()['subtitle']['id'], job.subtitle_id)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertNotIn(self.directory.name, response.content.decode())

    def test_curated_subtitle_wins_over_generated_text(self):
        track = Subtitle.objects.create(episode=self.episode, language='en', label='Curated', content='Original captions')
        job = self.job()
        with patch('cinema.transcription.recognize', return_value=('en', 'Generated captions')):
            process_transcription(job.pk)
        job.refresh_from_db()
        track.refresh_from_db()
        self.assertEqual(job.subtitle_id, track.pk)
        self.assertEqual(track.content, 'Original captions')

    def test_silence_is_failed_not_fake_ready_and_source_changes_are_rejected(self):
        job = self.job()
        with patch('cinema.transcription.recognize', side_effect=TranscriptionError('Không nhận dạng được lời thoại.')):
            process_transcription(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertFalse(Subtitle.objects.exists())
        job.status = 'pending'
        job.source_key = 'changed'
        job.save()
        with patch('cinema.transcription.recognize') as inference:
            process_transcription(job.pk)
        inference.assert_not_called()

    def test_provider_segments_preserve_timing_and_escape_text(self):
        response = MagicMock()
        response.read.return_value = json.dumps({'language': 'en', 'segments': [{'start': 1.25, 'end': 3.5, 'text': '<b>Hello</b>'}]}).encode()
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch('cinema.transcription.build_opener', return_value=opener):
            language, content = recognize(self.episode, 'en')
        self.assertEqual(language, 'en')
        self.assertIn('00:00:01.250 --> 00:00:03.500', content)
        self.assertIn('&lt;b&gt;Hello&lt;/b&gt;', content)

    def test_empty_or_invalid_provider_segments_are_not_published(self):
        for data in ({'language': 'en', 'segments': []}, {'language': 'en', 'segments': [{'start': 0, 'end': 99, 'text': 'Overrun'}]}):
            response = MagicMock()
            response.read.return_value = json.dumps(data).encode()
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value = response
            with self.subTest(data=data), patch('cinema.transcription.build_opener', return_value=opener):
                with self.assertRaises(TranscriptionError):
                    recognize(self.episode, 'en')

    def test_source_changes_during_inference_do_not_publish_a_caption(self):
        job = self.job()
        def changed(*args):
            Movie.objects.filter(pk=self.movie.pk).update(published=False)
            return 'en', 'Generated captions'
        with patch('cinema.transcription.recognize', side_effect=changed):
            process_transcription(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertFalse(Subtitle.objects.exists())

    def test_interrupted_and_unexpected_errors_leave_a_retryable_failed_job(self):
        job = self.job()
        with patch('cinema.transcription.recognize', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                process_transcription(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        job.status = 'pending'
        job.save()
        with patch('cinema.transcription.recognize', side_effect=RuntimeError('private internal details')):
            process_transcription(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertNotIn('private internal details', job.error)

    def test_stale_processing_lease_is_recovered_and_model_changes_invalidate_status(self):
        from django.core.management import call_command
        import io
        job = self.job()
        SubtitleTranscription.objects.filter(pk=job.pk).update(status='processing', updated_at=timezone.now() - timedelta(hours=2))
        call_command('process_transcriptions', stdout=io.StringIO())
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        with override_settings(SPEECH_MODEL_VERSION='changed-model'):
            self.assertEqual(self.client.get(reverse('caption_generation_status', args=[self.episode.pk, job.pk])).status_code, 409)
