"""Real FFmpeg integration tests; all media stays in isolated temporary storage."""
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from .admin import EpisodeAdmin
from .models import Episode, Movie


@skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg and ffprobe are required')
class VideoPipelineTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fixture_dir = tempfile.TemporaryDirectory(prefix='lumiere-video-fixture-')
        cls.addClassCleanup(cls.fixture_dir.cleanup)
        source = Path(cls.fixture_dir.name) / 'sample.mp4'
        # A generated 2-second clip avoids relying on user files or copyrighted media.
        subprocess.run(
            ['ffmpeg', '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i',
             'color=c=blue:s=160x90:r=12', '-f', 'lavfi', '-i',
             'sine=frequency=440:sample_rate=44100', '-t', '2', '-c:v', 'libx264',
             '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-threads', '1', str(source)],
            check=True, capture_output=True, timeout=30,
        )
        cls.video_bytes = source.read_bytes()

    def setUp(self):
        cache.clear()
        self.directory = tempfile.TemporaryDirectory(prefix='lumiere-video-test-')
        self.addCleanup(self.directory.cleanup)
        self.private_root = Path(self.directory.name) / 'private'
        self.public_root = Path(self.directory.name) / 'public'
        self.settings_override = override_settings(
            PRIVATE_MEDIA_ROOT=self.private_root,
            MEDIA_ROOT=self.public_root,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        # Episode's storage is instantiated at import time; isolate that object too.
        self.storage_patch = patch.object(
            Episode._meta.get_field('source'), 'storage',
            FileSystemStorage(location=self.private_root, base_url=None),
        )
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)
        self.admin = get_user_model().objects.create_superuser(
            'video-admin', 'video-admin@example.test', 'Test-only-password-93!',
        )
        self.movie = Movie.objects.create(
            title='Pipeline test', slug='pipeline-test', description='Generated clip',
            published=True,
        )
        self.client.force_login(self.admin)

    def upload(self, content=None, filename='clip.mp4'):
        return self.client.post(reverse('admin:cinema_episode_add'), {
            'movie': self.movie.pk,
            'number': 1,
            'title': 'Generated test clip',
            'source': SimpleUploadedFile(
                filename, self.video_bytes if content is None else content,
                content_type='video/mp4',
            ),
            '_save': 'Save',
        })

    def process(self, episode, **options):
        call_command(
            'process_videos', episode=episode.pk,
            stdout=io.StringIO(), stderr=io.StringIO(), **options,
        )
        episode.refresh_from_db()

    def test_admin_upload_transcodes_real_video_and_streams_authorized_hls(self):
        response = self.upload()
        self.assertEqual(response.status_code, 302)
        episode = Episode.objects.get()
        self.assertEqual(episode.status, 'pending')
        self.assertTrue(Path(episode.source.path).is_relative_to(self.private_root))
        self.assertNotEqual(Path(episode.source.name).name, 'clip.mp4')
        self.assertFalse(self.public_root.exists())
        # Neither a private-root URL nor the public media route exposes the original.
        self.assertEqual(self.client.get('/private_media/' + episode.source.name).status_code, 404)
        self.assertEqual(self.client.get('/media/' + episode.source.name).status_code, 404)
        self.assertEqual(self.client.post(reverse('ticket', args=[episode.pk])).status_code, 403)

        self.process(episode)
        self.assertEqual(episode.status, 'ready', episode.error)
        self.assertGreater(episode.duration, 1)
        self.assertLess(episode.duration, 3)
        folder = self.private_root / 'hls' / str(episode.asset_id)
        playlist = (folder / 'index.m3u8').read_text()
        self.assertIn('#EXT-X-ENDLIST', playlist)
        self.assertIn('#EXTINF:', playlist)
        segments = list(folder.glob('seg*.ts'))
        self.assertTrue(segments)
        self.assertTrue(all(segment.stat().st_size > 0 for segment in segments))

        ticket = self.client.post(reverse('ticket', args=[episode.pk])).json()['url']
        manifest_response = self.client.get(ticket)
        self.assertEqual(manifest_response.status_code, 200)
        protected_segment = next(
            line for line in manifest_response.content.decode().splitlines()
            if line.startswith('/stream/')
        )
        segment_response = self.client.get(protected_segment)
        self.assertEqual(segment_response.status_code, 200)
        self.assertGreater(len(b''.join(segment_response.streaming_content)), 0)
        self.assertIn('no-store', segment_response['Cache-Control'])
        self.client.logout()
        self.assertEqual(self.client.get(protected_segment).status_code, 302)

    def test_file_with_mp4_extension_but_no_video_fails_closed(self):
        self.assertEqual(self.upload(b'<html>not a video</html>').status_code, 302)
        episode = Episode.objects.get()
        folder = self.private_root / 'hls' / str(episode.asset_id)
        self.process(episode)
        self.assertEqual(episode.status, 'failed')
        self.assertTrue(episode.error)
        self.assertFalse(folder.exists())
        self.assertEqual(self.client.post(reverse('ticket', args=[episode.pk])).status_code, 403)

    def test_failed_worker_can_retry_the_original_upload(self):
        self.assertEqual(self.upload().status_code, 302)
        episode = Episode.objects.get()
        with patch('cinema.management.commands.process_videos.subprocess.run',
                   side_effect=subprocess.TimeoutExpired('ffprobe', 60)):
            self.process(episode)
        self.assertEqual(episode.status, 'failed')
        self.assertTrue(Path(episode.source.path).is_file())
        self.process(episode, retry_failed=True)
        self.assertEqual(episode.status, 'ready', episode.error)
        self.assertEqual(episode.error, '')
        self.assertTrue((self.private_root / 'hls' / str(episode.asset_id) / 'index.m3u8').is_file())

    def test_ready_episode_is_not_processed_again(self):
        self.upload()
        episode = Episode.objects.get()
        self.process(episode)
        self.assertEqual(episode.status, 'ready', episode.error)
        with patch('cinema.management.commands.process_videos.subprocess.run') as run:
            self.process(episode)
        run.assert_not_called()

    def test_interrupted_transcode_can_be_retried_without_failed_flag(self):
        self.upload()
        episode = Episode.objects.get()
        output = self.private_root / 'hls' / str(episode.asset_id)

        def interrupt(_source, staging):
            (staging / 'index.m3u8').write_text('incomplete output')
            self.assertFalse(output.exists())
            raise KeyboardInterrupt

        with patch('cinema.management.commands.process_videos.Command.encode', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.process(episode)
        episode.refresh_from_db()
        self.assertEqual(episode.status, 'pending')
        self.assertTrue(Path(episode.source.path).is_file())
        self.assertFalse(output.exists())

        self.process(episode)
        self.assertEqual(episode.status, 'ready', episode.error)
        self.assertIn('#EXT-X-ENDLIST', (output / 'index.m3u8').read_text())

    def test_worker_recovers_a_killed_workers_episode_and_partial_output(self):
        self.upload()
        episode = Episode.objects.get()
        Episode.objects.filter(pk=episode.pk).update(status='processing')
        hls = self.private_root / 'hls'
        work_root = hls / '.processing'
        stale = work_root / str(episode.asset_id) / 'previous-attempt'
        stale.mkdir(parents=True)
        (stale / 'index.m3u8').write_text('incomplete staging output')
        output = hls / str(episode.asset_id)
        output.mkdir()
        (output / 'seg99999.ts').write_bytes(b'incomplete legacy output')

        with subprocess.Popen(
            [sys.executable, '-c', 'import fcntl, sys, time; '
             'lock = open(sys.argv[1], "ab"); fcntl.flock(lock, fcntl.LOCK_EX); '
             'print("locked", flush=True); time.sleep(30)',
             str(work_root / f'{episode.asset_id}.lock')],
            stdout=subprocess.PIPE, text=True,
        ) as worker:
            try:
                self.assertEqual(worker.stdout.readline().strip(), 'locked')
                with patch('cinema.management.commands.process_videos.subprocess.run') as run:
                    self.process(episode)
                run.assert_not_called()
                self.assertEqual(episode.status, 'processing')
                self.assertTrue(stale.exists())
            finally:
                worker.kill()
                worker.wait(timeout=5)

        self.process(episode)
        self.assertEqual(episode.status, 'ready', episode.error)
        self.assertIn('#EXT-X-ENDLIST', (output / 'index.m3u8').read_text())
        self.assertFalse((output / 'seg99999.ts').exists())
        self.assertFalse(stale.exists())

    def test_metadata_save_preserves_worker_state_changed_during_request(self):
        self.upload()
        episode = Episode.objects.get()
        save_model = EpisodeAdmin.save_model

        def finish_processing(model_admin, request, obj, form, change):
            Episode.objects.filter(pk=obj.pk).update(status='ready', duration=2.2)
            save_model(model_admin, request, obj, form, change)

        with patch.object(EpisodeAdmin, 'save_model', finish_processing):
            response = self.client.post(reverse('admin:cinema_episode_change', args=[episode.pk]), {
                'movie': self.movie.pk, 'number': 1, 'title': 'Renamed episode', '_save': 'Save',
            })
        self.assertEqual(response.status_code, 302)
        episode.refresh_from_db()
        self.assertEqual((episode.title, episode.status, episode.duration), ('Renamed episode', 'ready', 2.2))

    def test_unsupported_extension_is_rejected_before_file_is_saved(self):
        response = self.upload(b'<?php echo 1; ?>', filename='payload.php')
        self.assertEqual(response.status_code, 200)
        self.assertIn('source', response.context['adminform'].form.errors)
        self.assertFalse(Episode.objects.exists())
        self.assertFalse(self.private_root.exists())

    def test_oversized_upload_is_rejected(self):
        with override_settings(MAX_VIDEO_BYTES=10):
            response = self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertIn('source', response.context['adminform'].form.errors)
        self.assertFalse(Episode.objects.exists())
        self.assertFalse(self.private_root.exists())

    def test_normal_user_cannot_upload_to_admin(self):
        viewer = get_user_model().objects.create_user('viewer', 'viewer@example.test')
        self.client.force_login(viewer)
        self.assertEqual(self.upload().status_code, 302)
        self.assertFalse(Episode.objects.exists())
        self.assertFalse(self.private_root.exists())

    def test_unauthorized_upload_never_opens_temporary_file(self):
        anonymous = Client(enforce_csrf_checks=True)
        anonymous.get('/accounts/login/')
        csrf = anonymous.cookies['csrftoken'].value
        with patch('django.core.files.uploadhandler.TemporaryFileUploadHandler.new_file') as new_file:
            response = anonymous.post('/accounts/login/', {'username':'unknown', 'password':'dummy', 'csrfmiddlewaretoken':csrf, 'source':SimpleUploadedFile('film.mp4', self.video_bytes)})
        self.assertEqual(response.status_code, 200)
        new_file.assert_not_called()
        self.assertFalse(Episode.objects.exists())
