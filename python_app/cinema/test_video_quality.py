"""Quality entitlements are enforced on manifests AND individual media files."""

import json
import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Movie, User
from .video_quality import encoding_renditions, probe_dimensions


class VideoQualityAccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.storage = tempfile.TemporaryDirectory(prefix='lumiere-quality-access-')
        self.addCleanup(self.storage.cleanup)
        self.override = override_settings(PRIVATE_MEDIA_ROOT=Path(self.storage.name))
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.free = User.objects.create_user('quality-free', 'free@quality.invalid')
        self.vip = User.objects.create_user('quality-vip', 'vip@quality.invalid', vip_until=timezone.now() + timedelta(days=1))
        self.staff = User.objects.create_user('quality-staff', 'staff@quality.invalid', is_staff=True)
        movie = Movie.objects.create(title='Quality fixture', slug='quality-fixture', published=True)
        self.episode = Episode.objects.create(movie=movie, title='Generated fixture', status='ready', duration=12)
        self.directory = Path(self.storage.name) / 'hls' / str(self.episode.asset_id)
        self.directory.mkdir(parents=True)
        self.write_renditions((720, 1080, 1440))

    def write_renditions(self, heights):
        renditions = []
        for height in heights:
            width = height * 16 // 9
            filename = f'q{height}.m3u8'
            (self.directory / filename).write_text(
                '#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6,\n'
                f'q{height}_seg00000.ts\n#EXTINF:6,\nq{height}_seg00001.ts\n#EXT-X-ENDLIST\n'
            )
            for index in range(2):
                (self.directory / f'q{height}_seg{index:05d}.ts').write_bytes(f'{height}p segment'.encode())
            renditions.append({'height':height, 'width':width, 'video_height':height,
                               'playlist':filename, 'bandwidth':8000000})
        (self.directory / 'quality.json').write_text(json.dumps({'version':1, 'renditions':renditions}))
        (self.directory / 'index.m3u8').write_text('#EXTM3U\n')

    def ticket(self, user):
        self.client.force_login(user)
        response = self.client.post(reverse('ticket', args=[self.episode.pk]))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_free_ticket_and_master_expose_only720_but_guessed_vip_files_also_denied(self):
        ticket = self.ticket(self.free)
        self.assertEqual(ticket['max_quality'], 720)
        self.assertEqual(ticket['source_max_quality'], 1440)
        self.assertEqual([item['height'] for item in ticket['qualities']], [720])
        master = self.client.get(ticket['url'])
        self.assertContains(master, 'q720.m3u8')
        self.assertNotContains(master, '1080')
        self.assertNotContains(master, '1440')
        for name in ('q1080.m3u8', 'q1440.m3u8', 'q1080_seg00000.ts', 'q1440_seg00001.ts'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(ticket['url'].replace('index.m3u8', name)).status_code, 403)
        segment = self.client.get(ticket['url'].replace('index.m3u8', 'q720_seg00000.ts'))
        self.assertEqual(segment.status_code, 200)
        self.assertEqual(b''.join(segment.streaming_content), b'720p segment')

    def test_vip_and_staff_can_select_actual1440_rendition(self):
        for viewer in (self.vip, self.staff):
            with self.subTest(viewer=viewer.username):
                ticket = self.ticket(viewer)
                self.assertEqual(ticket['max_quality'], 1440)
                self.assertEqual([item['height'] for item in ticket['qualities']], [720,1080,1440])
                self.assertEqual(self.client.get(ticket['qualities'][-1]['url']).status_code, 200)
                response = self.client.get(ticket['url'].replace('index.m3u8', 'q1440_seg00000.ts'))
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_expiry_revokes_high_quality_even_for_free_movie_with_old_ticket(self):
        ticket = self.ticket(self.vip)
        User.objects.filter(pk=self.vip.pk).update(vip_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(ticket['url'].replace('index.m3u8', 'q1080.m3u8')).status_code, 403)
        self.assertEqual(self.client.get(ticket['url'].replace('index.m3u8', 'q1440_seg00000.ts')).status_code, 403)
        self.assertContains(self.client.get(ticket['url']), 'q720.m3u8')
        fresh = self.client.post(reverse('ticket', args=[self.episode.pk])).json()
        self.assertEqual([item['height'] for item in fresh['qualities']], [720])

    def test_low_resolution_source_does_not_advertise_unavailable1080_or1440(self):
        self.write_renditions((360,))
        ticket = self.ticket(self.vip)
        self.assertEqual([item['height'] for item in ticket['qualities']], [360])
        self.assertEqual(ticket['source_max_quality'], 360)
        self.assertEqual(ticket['max_quality'], 1440)

    def test_metadata_never_becomes_a_streamable_public_file(self):
        ticket = self.ticket(self.vip)
        for filename in ('quality.json', '..%2Fquality.json', 'q1440_seg99999.ts'):
            self.assertEqual(self.client.get(ticket['url'].replace('index.m3u8', filename)).status_code, 404)

    def legacy(self):
        (self.directory / 'quality.json').unlink()
        (self.directory / 'index.m3u8').write_text('#EXTM3U\n#EXTINF:6,\nseg00000.ts\n#EXT-X-ENDLIST\n')
        (self.directory / 'seg00000.ts').write_bytes(b'legacy video')

    def test_verified720_legacy_asset_remains_playable(self):
        self.legacy()
        with patch('cinema.video_quality.probe_dimensions', return_value=(1280,720)) as probe:
            ticket = self.ticket(self.free)
            response = self.client.get(ticket['url'])
            self.assertContains(response, 'seg00000.ts')
            self.assertEqual([item['height'] for item in ticket['qualities']], [720])
            self.assertEqual(probe.call_count, 1)

    def test_unknown_or_too_large_legacy_asset_cannot_bypass_free_quality_limit(self):
        self.legacy()
        self.client.force_login(self.free)
        with patch('cinema.video_quality.probe_dimensions', side_effect=ValueError('unverified')):
            self.assertEqual(self.client.post(reverse('ticket', args=[self.episode.pk])).status_code, 403)
        for dimensions in ((1920,1080), (720,1440), (1280,960)):
            cache.clear()
            with self.subTest(dimensions=dimensions), patch('cinema.video_quality.probe_dimensions', return_value=dimensions):
                self.assertEqual(self.client.post(reverse('ticket', args=[self.episode.pk])).status_code, 403)

    def test_invalid_private_rendition_metadata_fails_closed(self):
        document = json.loads((self.directory / 'quality.json').read_text())
        document['renditions'][0]['playlist'] = '../../original.mp4'
        (self.directory / 'quality.json').write_text(json.dumps(document))
        self.client.force_login(self.free)
        self.assertEqual(self.client.post(reverse('ticket', args=[self.episode.pk])).status_code, 403)


class QualityLadderTests(TestCase):
    def test_ladder_uses_source_detail_and_fits_portrait_or_landscape_bounds_without_upscale(self):
        for source, expected in (((2560,1440), [360,480,720,1080,1440]),
                                 ((1920,1080), [360,480,720,1080]),
                                 ((720,1440), [360,480,720]), ((160,90), [90])):
            with self.subTest(source=source):
                ladder = encoding_renditions(*source)
                self.assertEqual([item.height for item in ladder], expected)
                for item in ladder:
                    self.assertLessEqual(item.width, source[0])
                    self.assertLessEqual(item.video_height, source[1])
                    self.assertEqual(item.width % 2, 0)
                    self.assertEqual(item.video_height % 2, 0)
                    self.assertLessEqual(min(item.width,item.video_height), item.height)
                    self.assertLessEqual(max(item.width,item.video_height), item.height * 16 / 9)

    @skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_real1080_source_creates_actual_variants_and_never1440(self):
        from .management.commands.process_videos import Command
        with tempfile.TemporaryDirectory(prefix='lumiere-real-quality-') as temporary:
            root = Path(temporary)
            source, output = root / 'source.mp4', root / 'hls'
            output.mkdir()
            subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-f','lavfi','-i',
                            'color=c=blue:s=1920x1080:r=4','-t','0.5','-an','-c:v','libx264',
                            '-pix_fmt','yuv420p','-threads','1',str(source)],
                           capture_output=True, check=True, timeout=30)
            Command.encode(str(source), output)
            metadata = json.loads((output / 'quality.json').read_text())
            self.assertEqual([item['height'] for item in metadata['renditions']], [360,480,720,1080])
            self.assertFalse((output / 'q1440.m3u8').exists())
            self.assertEqual(probe_dimensions(output / 'q1080_seg00000.ts'), (1920,1080))
            self.assertEqual(probe_dimensions(output / 'q720_seg00000.ts'), (1280,720))
