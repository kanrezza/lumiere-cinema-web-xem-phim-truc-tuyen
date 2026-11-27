"""The HTTPS smoke must resolve a rendition before decoding its MPEG-TS data."""

from email.message import Message
from pathlib import Path
import ssl
import subprocess
from unittest.mock import patch

from django.test import SimpleTestCase

from deploy.staging.smoke import BrowserSession, Reply, play_fixture


WATCH = '/watch/41/'
MASTER = '/stream/41/index.m3u8?token=fixture'
RENDITION = '/stream/41/q360.m3u8?token=fixture'
SEGMENT = '/stream/41/q360_seg00000.ts?token=fixture'
TS_DATA = b'\x47' + b'\x00' * 187
MASTER_DATA = f'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=892000,RESOLUTION=640x360\n{RENDITION}\n'
MEDIA_DATA = f'#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.000000,\n{SEGMENT}\n#EXT-X-ENDLIST\n'


def reply(body, *, status=200, private=False):
    headers = Message()
    if private:
        headers['Cache-Control'] = 'private, no-store'
    return Reply(status, headers, body.encode() if isinstance(body, str) else body)


class FixtureSession:
    def __init__(self, replies):
        self.replies = {
            '/movies/tram-anh-sang-demo/': reply(f'<a href="{WATCH}">Episode</a>'),
            WATCH: reply('<track src="/watch/41/subtitles/1.vtt"><track src="/watch/41/subtitles/2.vtt">'),
            WATCH + 'ticket/': reply('{"url": "' + MASTER + '"}'),
            '/watch/41/subtitles/1.vtt': reply('WEBVTT\n\n'),
            '/watch/41/subtitles/2.vtt': reply('WEBVTT\n\n'),
            SEGMENT: reply(TS_DATA),
            **replies,
        }
        self.requested = []

    def request(self, path, data=None):
        self.requested.append((path, data))
        return self.replies[path]


class StagingPlaybackSmokeTests(SimpleTestCase):
    def master_session(self, **changes):
        return FixtureSession({
            MASTER: reply(MASTER_DATA, private=True),
            RENDITION: reply(MEDIA_DATA, private=True),
            **changes,
        })

    def test_master_resolves_rendition_and_passes_ts_bytes_to_ffmpeg(self):
        session = self.master_session()
        decoded = []

        def decode(command, **options):
            self.assertEqual(command[:5], ['ffmpeg', '-nostdin', '-v', 'error', '-xerror'])
            self.assertTrue(options['check'])
            self.assertEqual(options['timeout'], 20)
            decoded.append(Path(command[command.index('-i') + 1]).read_bytes())

        with patch('deploy.staging.smoke.subprocess.run', side_effect=decode):
            self.assertEqual(play_fixture(session, decode=True), WATCH)
        self.assertEqual(decoded, [TS_DATA])
        self.assertEqual([path for path, _ in session.requested][3:6], [MASTER, RENDITION, SEGMENT])
        self.assertIn(('/watch/41/subtitles/1.vtt', None), session.requested)
        self.assertIn(('/watch/41/subtitles/2.vtt', None), session.requested)

    def test_legacy_media_playlist_still_fetches_and_checks_its_segment(self):
        session = FixtureSession({MASTER: reply(MEDIA_DATA, private=True)})
        with patch('deploy.staging.smoke.subprocess.run') as decode:
            self.assertEqual(play_fixture(session, decode=False), WATCH)
        decode.assert_not_called()
        self.assertNotIn((RENDITION, None), session.requested)
        self.assertIn((SEGMENT, None), session.requested)

    def test_master_with_no_rendition_fails_with_an_actionable_error(self):
        session = FixtureSession({MASTER: reply('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=892000\n', private=True)})
        with self.assertRaisesRegex(RuntimeError, 'master playlist has no rendition'):
            play_fixture(session, decode=False)

    def test_unavailable_or_non_playlist_rendition_is_rejected(self):
        for response in (reply('Forbidden', status=403), reply('<html>Error</html>', private=True)):
            with self.subTest(status=response.status, body=response.body):
                session = self.master_session(**{RENDITION: response})
                with self.assertRaisesRegex(RuntimeError, 'rendition playlist could not be fetched'):
                    play_fixture(session, decode=False)
                self.assertNotIn((SEGMENT, None), session.requested)

    def test_missing_private_cache_header_is_rejected_for_both_playlist_levels(self):
        for path, body in ((MASTER, MASTER_DATA), (RENDITION, MEDIA_DATA)):
            with self.subTest(path=path):
                session = self.master_session(**{path: reply(body)})
                with self.assertRaisesRegex(RuntimeError, 'Private HLS must not be cached'):
                    play_fixture(session, decode=False)

    def test_nested_master_or_media_without_durations_is_rejected(self):
        for body in (MASTER_DATA, '#EXTM3U\n' + SEGMENT + '\n'):
            with self.subTest(body=body):
                session = self.master_session(**{RENDITION: reply(body, private=True)})
                with self.assertRaisesRegex(RuntimeError, 'Invalid HLS media playlist'):
                    play_fixture(session, decode=False)

    def test_media_without_segment_uri_is_rejected(self):
        session = self.master_session(**{RENDITION: reply('#EXTM3U\n#EXTINF:6.000000,\n', private=True)})
        with self.assertRaisesRegex(RuntimeError, 'media playlist has no segment'):
            play_fixture(session, decode=False)

    def test_malformed_master_and_non_ts_response_still_fail(self):
        for path, response, message in (
            (MASTER, reply('<html>Error</html>'), 'Invalid HLS playlist'),
            (SEGMENT, reply(b'#EXTM3U\n' + b' ' * 188), 'media segment could not be fetched'),
            (SEGMENT, reply(TS_DATA, status=403), 'media segment could not be fetched'),
        ):
            with self.subTest(path=path, status=response.status):
                session = self.master_session(**{path: response})
                with self.assertRaisesRegex(RuntimeError, message):
                    play_fixture(session, decode=False)

    def test_decoder_failure_is_not_swallowed(self):
        session = self.master_session()
        with patch('deploy.staging.smoke.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'ffmpeg')):
            with self.assertRaises(subprocess.CalledProcessError):
                play_fixture(session, decode=True)

    def test_real_session_rejects_external_or_protocol_relative_playlist_uris(self):
        session = BrowserSession('https://localhost:8443', ssl.create_default_context())
        for path in ('https://example.invalid/video.m3u8', '//example.invalid/video.m3u8'):
            with self.subTest(path=path), self.assertRaisesRegex(RuntimeError, 'same-origin request path'):
                session.request(path)
