"""Job access, source versioning and translation output are independent of video tickets."""
from datetime import timedelta
import io
import json
from unittest.mock import patch
from urllib.error import URLError

from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Movie, Subtitle, SubtitleTranslation, User
from .translation import MAX_BATCH_CUES, MAX_SEGMENT_CHARACTERS, TranslationError, _request_json, provider_key, service_url, source_snapshot, translate_vtt


SOURCE = 'WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello &amp; welcome.\n\n00:00:04.000 --> 00:00:06.500\nGood evening.\n'


@override_settings(TRANSLATION_API_URL='http://127.0.0.1:5001', TRANSLATION_API_KEY='', TRANSLATION_TARGETS=('vi', 'en'), TRANSLATION_PROVIDER_VERSION='test-model-v1')
class TranslationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_user('translation-viewer', 'translation-viewer@example.test')
        cls.member = User.objects.create_user('translation-member', 'translation-member@example.test', vip_until=timezone.now() + timedelta(days=30))
        cls.movie = Movie.objects.create(title='Translated feature', slug='translated-feature', published=True)
        cls.episode = Episode.objects.create(movie=cls.movie, title='Full feature', status='ready', duration=600)
        cls.track = Subtitle.objects.create(episode=cls.episode, language='en', label='English', content=SOURCE)
        cls.other_episode = Episode.objects.create(movie=cls.movie, number=2, title='Other episode', status='ready', duration=600)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.viewer)

    def request_translation(self, **data):
        return self.client.post(reverse('subtitle_translate', args=[self.episode.pk, self.track.pk]), {'target': 'vi', **data})

    def new_job(self):
        response = self.request_translation()
        self.assertEqual(response.status_code, 202)
        return SubtitleTranslation.objects.get(pk=response.json()['id'])

    def status_url(self, job):
        return reverse('subtitle_translation_status', args=[self.episode.pk, job.pk])

    def track_url(self, job):
        return reverse('subtitle_translation_track', args=[self.episode.pk, job.pk])

    def provider(self, path, payload=None):
        if path == '/languages':
            return [{'code': 'en', 'targets': ['vi']}, {'code': 'vi', 'targets': ['en']}]
        return {'translatedText': ['Xin chào <b>bạn</b> & mọi người.' for _ in payload['q']]}

    def test_post_creates_snapshot_and_reuses_same_version_without_inference(self):
        with patch('cinema.translation._request_json') as remote:
            first = self.request_translation()
            second = self.request_translation()
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.json()['id'], first.json()['id'])
        self.assertEqual(SubtitleTranslation.objects.count(), 1)
        job = SubtitleTranslation.objects.get()
        self.assertEqual(job.source_content, SOURCE)
        self.assertEqual(job.source_language, 'en')
        self.assertEqual(job.target_language, 'vi')
        self.assertEqual(job.requested_by, self.viewer)
        self.assertEqual(job.source_hash, source_snapshot(self.track)[2])
        self.assertEqual(first.json()['track_url'], None)
        self.assertEqual(first.json()['status_url'], self.status_url(job))
        remote.assert_not_called()

    def test_authentication_and_csrf_required_before_a_job_can_be_queued(self):
        anonymous = Client()
        url = reverse('subtitle_translate', args=[self.episode.pk, self.track.pk])
        self.assertEqual(anonymous.post(url, {'target': 'vi'}).status_code, 302)
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.viewer)
        self.assertEqual(guarded.post(url, {'target': 'vi'}).status_code, 403)
        self.assertEqual(SubtitleTranslation.objects.count(), 0)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_missing_or_untrusted_service_never_produces_a_fake_translation(self):
        for value in ('', 'http://untrusted.example', 'https://user:password@example.test', 'javascript:alert(1)'):
            with self.subTest(value=value), override_settings(TRANSLATION_API_URL=value):
                response = self.request_translation()
                self.assertEqual(response.status_code, 503)
                self.assertEqual(SubtitleTranslation.objects.count(), 0)

    def test_only_configured_targets_and_different_source_language_are_accepted(self):
        for target in ('', 'fr', 'en', '../vi', '<script>'):
            with self.subTest(target=target):
                self.assertEqual(self.request_translation(target=target).status_code, 400)
        self.assertEqual(SubtitleTranslation.objects.count(), 0)

    def test_subtitle_cannot_be_requested_under_another_episode(self):
        url = reverse('subtitle_translate', args=[self.other_episode.pk, self.track.pk])
        self.assertEqual(self.client.post(url, {'target': 'vi'}).status_code, 404)
        self.assertEqual(SubtitleTranslation.objects.count(), 0)

    def test_movie_access_is_required_for_queue_status_and_ready_track(self):
        job = self.new_job()
        job.status, job.content = 'ready', SOURCE
        job.save(update_fields=['status', 'content'])
        self.movie.is_vip = True
        self.movie.save(update_fields=['is_vip'])
        self.assertEqual(self.request_translation().status_code, 403)
        self.assertEqual(self.client.get(self.status_url(job)).status_code, 403)
        self.assertEqual(self.client.get(self.track_url(job)).status_code, 403)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.track_url(job)).status_code, 200)
        self.episode.status = 'pending'
        self.episode.save(update_fields=['status'])
        self.assertEqual(self.client.get(self.status_url(job)).status_code, 403)
        self.episode.status = 'ready'
        self.episode.save(update_fields=['status'])
        self.movie.published = False
        self.movie.save(update_fields=['published'])
        self.assertEqual(self.client.get(self.track_url(job)).status_code, 403)

    def test_source_edits_create_new_job_and_reject_stale_result(self):
        first = self.new_job()
        self.track.content = SOURCE.replace('Good evening.', 'Different source text.')
        self.track.save(update_fields=['content'])
        second = self.new_job()
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.source_content, SOURCE)
        self.assertEqual(self.client.get(self.status_url(first)).status_code, 409)
        self.assertEqual(self.client.get(self.track_url(first)).status_code, 409)

    def test_provider_version_changes_invalidate_translation_cache(self):
        first = self.new_job()
        with override_settings(TRANSLATION_PROVIDER_VERSION='updated-model-v2'):
            second = self.new_job()
        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first.provider_key, second.provider_key)

    def test_pending_and_hourly_limits_do_not_block_a_cached_result(self):
        first = self.new_job()
        for index in range(2):
            track = Subtitle.objects.create(episode=self.episode, language=f'en-{index:02}', label=f'English {index}', content=SOURCE + '\n')
            language, content, digest = source_snapshot(track)
            SubtitleTranslation.objects.create(subtitle=track, source_hash=digest, source_language=language, source_content=content, target_language='vi', provider_key=provider_key(), requested_by=self.viewer)
        self.track.content = SOURCE.replace('Good evening.', 'Another revision.')
        self.track.save(update_fields=['content'])
        self.assertEqual(self.request_translation().status_code, 429)
        self.track.content = SOURCE
        self.track.save(update_fields=['content'])
        self.assertEqual(self.request_translation().json()['id'], str(first.pk))
        SubtitleTranslation.objects.update(status='ready', content=SOURCE)
        cache.set(f'subtitle-translation:{self.viewer.pk}', 12, 3600)
        self.track.content = SOURCE.replace('Good evening.', 'Fresh source.')
        self.track.save(update_fields=['content'])
        self.assertEqual(self.request_translation().status_code, 429)

    def test_worker_translates_plain_text_preserves_timing_and_never_overwrites_source(self):
        job = self.new_job()
        with patch('cinema.translation._request_json', side_effect=self.provider) as remote:
            call_command('process_translations', stdout=io.StringIO())
        job.refresh_from_db()
        self.track.refresh_from_db()
        self.assertEqual(job.status, 'ready')
        self.assertIn('00:00:01.000 --> 00:00:03.000', job.content)
        self.assertIn('00:00:04.000 --> 00:00:06.500', job.content)
        self.assertIn('Xin chào &lt;b&gt;bạn&lt;/b&gt; &amp; mọi người.', job.content)
        self.assertNotIn('<b>', job.content)
        self.assertEqual(self.track.content, SOURCE)
        payload = remote.call_args_list[1].args[1]
        self.assertEqual(payload['format'], 'text')
        self.assertEqual(payload['q'][0], 'Hello & welcome.')
        status = self.client.get(self.status_url(job))
        self.assertEqual(status.json()['status'], 'ready')
        self.assertEqual(status.json()['track_url'], self.track_url(job))
        response = self.client.get(self.track_url(job))
        self.assertEqual(response['Content-Type'], 'text/vtt; charset=utf-8')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_failed_inference_does_not_publish_partial_or_original_text_as_translation(self):
        job = self.new_job()
        with patch('cinema.translation._request_json', side_effect=TranslationError('Dịch vụ tạm thời không sẵn sàng.')):
            call_command('process_translations', stdout=io.StringIO())
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertEqual(job.content, '')
        self.assertEqual(self.client.get(self.track_url(job)).status_code, 409)
        self.assertEqual(self.client.get(self.status_url(job)).json()['error'], 'Dịch vụ tạm thời không sẵn sàng.')

    def test_provider_count_or_language_mismatch_fails_truthfully(self):
        for response in ({'translatedText': ['one']}, {'translatedText': None}, {'translatedText': [1, 2]}):
            with self.subTest(response=response), patch('cinema.translation._request_json', side_effect=[[{'code': 'en', 'targets': ['vi']}], response]):
                with self.assertRaises(TranslationError):
                    translate_vtt(SOURCE, 'en', 'vi')
        with patch('cinema.translation._request_json', return_value=[{'code': 'en', 'targets': ['fr']}]):
            with self.assertRaises(TranslationError):
                translate_vtt(SOURCE, 'en', 'vi')

    def test_failed_job_retry_is_explicit_rate_limited_and_preserves_version(self):
        job = self.new_job()
        job.status, job.error = 'failed', 'Temporary outage.'
        job.save(update_fields=['status', 'error', 'updated_at'])
        self.assertEqual(self.request_translation().json()['status'], 'failed')
        self.assertEqual(self.request_translation(retry='1').status_code, 429)
        SubtitleTranslation.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(seconds=31))
        response = self.request_translation(retry='1')
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['id'], str(job.pk))
        self.assertEqual(response.json()['status'], 'pending')

    def test_retrying_other_viewers_failed_jobs_uses_current_viewers_pending_quota(self):
        jobs = []
        for index in range(4):
            track = Subtitle.objects.create(episode=self.episode, language=f'en-{index:02}', label=f'English {index}', content=SOURCE)
            language, content, digest = source_snapshot(track)
            job = SubtitleTranslation.objects.create(subtitle=track, source_hash=digest, source_language=language,
                source_content=content, target_language='vi', provider_key=provider_key(),
                requested_by=self.member, status='failed', error='Temporary outage.')
            SubtitleTranslation.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(seconds=31))
            jobs.append(job)

        for job in jobs[:3]:
            response = self.client.post(reverse('subtitle_translate', args=[self.episode.pk, job.subtitle_id]),
                {'target': 'vi', 'retry': '1'})
            self.assertEqual(response.status_code, 202)
            job.refresh_from_db()
            self.assertEqual(job.status, 'pending')
            self.assertEqual(job.requested_by, self.viewer)
        self.assertEqual(SubtitleTranslation.objects.filter(requested_by=self.viewer, status='pending').count(), 3)
        fourth = jobs[3]
        response = self.client.post(reverse('subtitle_translate', args=[self.episode.pk, fourth.subtitle_id]),
            {'target': 'vi', 'retry': '1'})
        self.assertEqual(response.status_code, 429)
        fourth.refresh_from_db()
        self.assertEqual(fourth.status, 'failed')
        self.assertEqual(fourth.requested_by, self.member)

    def test_long_cues_are_segmented_without_changing_timing_or_dropping_text(self):
        content = 'WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n' + 'word ' * 500 + '\n'
        sent = []
        def provider(path, payload=None):
            if path == '/languages':
                return [{'code': 'en', 'targets': ['vi']}]
            self.assertLessEqual(len(payload['q']), MAX_BATCH_CUES)
            self.assertTrue(all(len(value) <= MAX_SEGMENT_CHARACTERS for value in payload['q']))
            sent.extend(payload['q'])
            return {'translatedText': ['bản dịch ' + str(index) for index, _ in enumerate(payload['q'])]}
        with patch('cinema.translation._request_json', side_effect=provider):
            result = translate_vtt(content, 'en', 'vi')
        self.assertGreater(len(sent), 1)
        self.assertEqual(' '.join(sent).split(), ['word'] * 500)
        self.assertEqual(result.count('-->'), 1)
        self.assertIn('00:00:01.000 --> 00:00:04.000', result)

    def test_transport_uses_only_configured_destination_and_hides_transport_secrets(self):
        for value in ('http://localhost:5001', 'http://127.0.0.1:5001', 'https://translation.example.test/api'):
            with self.subTest(value=value), override_settings(TRANSLATION_API_URL=value):
                self.assertEqual(service_url(), value)
        with patch('cinema.translation.build_opener') as factory:
            factory.return_value.open.side_effect = URLError('secret-token and private subtitle')
            with self.assertRaises(TranslationError) as error:
                _request_json('/translate', {'q': ['private subtitle']})
            self.assertNotIn('secret-token', str(error.exception))
            self.assertNotIn('private subtitle', str(error.exception))

    def test_source_changed_before_worker_does_not_call_provider(self):
        job = self.new_job()
        self.track.content = SOURCE.replace('Good evening.', 'Changed after queueing.')
        self.track.save(update_fields=['content'])
        with patch('cinema.translation._request_json') as remote:
            call_command('process_translations', stdout=io.StringIO())
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertEqual(job.content, '')
        remote.assert_not_called()

    def test_interrupted_or_stale_worker_does_not_leave_a_permanent_processing_job(self):
        job = self.new_job()
        with patch('cinema.management.commands.process_translations.process_translation', side_effect=KeyboardInterrupt):
            call_command('process_translations', stdout=io.StringIO())
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        job.status = 'processing'
        job.started_at = timezone.now() - timedelta(hours=1)
        job.save(update_fields=['status', 'started_at'])
        call_command('process_translations', stdout=io.StringIO())
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertIn('gián đoạn', job.error)
