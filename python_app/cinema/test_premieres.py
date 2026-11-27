"""Premieres have their own clock, access scope and editorial permission."""

from datetime import timedelta
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Movie, Premiere, PremiereMessage, User
from .premieres import can_manage_premieres, premiere_phase, premiere_state, premiere_stream_limit, require_premiere_playback


class PremiereTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = User.objects.create_user('screening-editor', 'editor@screening.test', is_staff=True)
        cls.editor.user_permissions.add(Permission.objects.get(codename='manage_premieres', content_type__app_label='cinema'))
        cls.staff = User.objects.create_user('other-editor', 'staff@screening.test', is_staff=True)
        cls.viewer = User.objects.create_user('screening-viewer', 'viewer@screening.test')
        cls.vip = User.objects.create_user('screening-vip', 'vip@screening.test', vip_until=timezone.now() + timedelta(days=1))
        cls.movie = Movie.objects.create(title='Friday premiere', slug='friday-premiere', published=True)
        cls.episode = Episode.objects.create(movie=cls.movie, title='The new episode', number=1, status='ready', duration=120)

    def setUp(self):
        cache.clear()
        self.screening = Premiere.objects.create(
            title='Friday screening', episode=self.episode, created_by=self.editor,
            scheduled_at=timezone.now() - timedelta(seconds=30),
        )
        self.client.force_login(self.viewer)
        self.editor_client = Client()
        self.editor_client.force_login(self.editor)

    def state_url(self):
        return reverse('premiere_state', args=[self.screening.pk])

    def control(self, client=None, **data):
        return (client or self.editor_client).post(reverse('premiere_control', args=[self.screening.pk]), {'state_version': self.screening.state_version, **data})

    def test_clock_starts_scheduled_screening_without_a_browser_host(self):
        start = self.screening.scheduled_at
        self.assertEqual(premiere_phase(self.screening, start - timedelta(seconds=1)), 'scheduled')
        self.assertEqual(premiere_phase(self.screening, start + timedelta(seconds=30)), 'live')
        self.assertEqual(premiere_stream_limit(self.screening, start + timedelta(seconds=30)), 30)
        self.assertEqual(premiere_phase(self.screening, start + timedelta(seconds=120)), 'ended')
        self.assertEqual(premiere_stream_limit(self.screening, start + timedelta(seconds=180)), 120)

    def test_state_is_server_authoritative_and_has_a_buffered_playback_position(self):
        state = self.client.get(self.state_url())
        self.assertEqual(state.status_code, 200)
        self.assertIn('no-store', state.headers['Cache-Control'])
        data = state.json()
        self.assertEqual(data['status'], 'live')
        self.assertTrue(data['can_watch'])
        self.assertTrue(data['can_chat'])
        self.assertAlmostEqual(data['position'] - data['playback_position'], 12)
        self.assertIn(f'premiere={self.screening.pk}', data['ticket_url'])
        denied = self.client.post(self.state_url(), {'action': 'sync', 'position': 110, 'playing': 'false'})
        self.assertEqual(denied.status_code, 400)
        self.screening.refresh_from_db()
        self.assertIsNone(self.screening.started_at)

    def test_only_active_staff_with_the_broadcast_permission_control_screenings(self):
        self.assertFalse(can_manage_premieres(self.viewer))
        self.assertEqual(self.control(self.client, action='end').status_code, 403)
        staff = Client()
        staff.force_login(self.staff)
        self.assertEqual(self.control(staff, action='end').status_code, 403)
        self.viewer.user_permissions.add(Permission.objects.get(codename='manage_premieres', content_type__app_label='cinema'))
        self.assertEqual(self.control(self.client, action='end').status_code, 403)
        self.assertEqual(self.control(action='end').status_code, 200)
        self.screening.refresh_from_db()
        self.assertEqual(self.screening.status, 'ended')
        self.assertEqual(self.screening.state_version, 2)
        self.assertTrue(LogEntry.objects.filter(user=self.editor, object_id=str(self.screening.pk)).exists())

    def test_start_cancel_and_stale_control_are_explicit_and_versioned(self):
        self.screening.scheduled_at = timezone.now() + timedelta(hours=1)
        self.screening.save(update_fields=['scheduled_at'])
        self.assertEqual(self.control(action='start').status_code, 200)
        stale = self.control(action='end')
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()['state_version'], 2)
        self.screening.refresh_from_db()
        self.assertEqual(self.control(action='cancel').status_code, 400)

    def test_cancelled_screening_does_not_resume_when_scheduled_time_arrives(self):
        self.screening.scheduled_at = timezone.now() + timedelta(minutes=10)
        self.screening.save(update_fields=['scheduled_at'])
        response = self.control(action='cancel')
        self.assertEqual(response.status_code, 200)
        self.screening.refresh_from_db()
        self.assertEqual(premiere_phase(self.screening, timezone.now() + timedelta(days=1)), 'cancelled')

    def test_vip_audience_hides_chat_and_ticket_from_regular_accounts(self):
        self.screening.audience = 'vip'
        self.screening.save(update_fields=['audience'])
        PremiereMessage.objects.create(premiere=self.screening, user=self.vip, content='Private conversation')
        response = self.client.get(self.state_url())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['can_watch'])
        self.assertEqual(response.json()['ticket_url'], '')
        self.assertEqual(response.json()['messages'], [])
        self.assertEqual(self.client.post(self.state_url(), {'action': 'chat', 'content': 'hello'}).status_code, 403)
        self.client.force_login(self.vip)
        self.assertTrue(self.client.get(self.state_url()).json()['can_watch'])
        User.objects.filter(pk=self.vip.pk).update(vip_until=timezone.now() - timedelta(seconds=1))
        self.assertFalse(self.client.get(self.state_url()).json()['can_watch'])

    def test_free_screening_never_overrides_vip_movie_access(self):
        Movie.objects.filter(pk=self.movie.pk).update(is_vip=True)
        response = self.client.get(self.state_url())
        self.assertFalse(response.json()['can_watch'])
        self.assertTrue(response.json()['requires_vip'])

    def test_scheduled_chat_works_but_unready_episode_cannot_be_watched(self):
        self.screening.scheduled_at = timezone.now() + timedelta(hours=1)
        self.screening.save(update_fields=['scheduled_at'])
        response = self.client.post(self.state_url(), {'action': 'chat', 'content': 'See you tonight'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['ticket_url'], '')
        self.assertEqual(response.json()['status'], 'scheduled')
        Episode.objects.filter(pk=self.episode.pk).update(status='processing')
        self.assertFalse(self.client.get(self.state_url()).json()['can_watch'])
        self.assertEqual(self.client.post(self.state_url(), {'action': 'chat', 'content': 'hello'}).status_code, 403)

    def test_chat_is_bounded_throttled_and_triaged_with_shared_moderation(self):
        response = self.client.post(self.state_url(), {'action': 'chat', 'content': 'Mày ngu'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('kiểm duyệt', response.json()['notice'])
        self.assertEqual(response.json()['messages'], [])
        self.assertTrue(PremiereMessage.objects.get().hidden)
        self.assertEqual(self.client.post(self.state_url(), {'action': 'chat', 'content': 'hello'}).status_code, 429)
        cache.clear()
        self.assertEqual(self.client.post(self.state_url(), {'action': 'chat', 'content': 'x' * 501}).status_code, 400)
        PremiereMessage.objects.bulk_create([PremiereMessage(premiere=self.screening, user=self.viewer, content=str(i)) for i in range(70)])
        messages = self.client.get(self.state_url()).json()['messages']
        self.assertEqual(len(messages), 60)
        self.assertEqual([row['content'] for row in messages], [str(i) for i in range(10, 70)])
        self.assertEqual(messages[0]['username'], self.viewer.username)

    def test_chat_closes_when_screening_finishes(self):
        self.screening.status = 'ended'
        self.screening.ended_at = timezone.now()
        self.screening.save(update_fields=['status', 'ended_at'])
        response = self.client.post(self.state_url(), {'action': 'chat', 'content': 'hello'})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.client.get(self.state_url()).json()['can_chat'])

    def test_scope_rejects_future_cancelled_and_wrong_episode_even_with_vip(self):
        request = RequestFactory().get('/', {'premiere': str(self.screening.pk)})
        request.user = self.viewer
        self.assertEqual(require_premiere_playback(request, self.episode), self.screening)
        self.screening.scheduled_at = timezone.now() + timedelta(hours=1)
        self.screening.save(update_fields=['scheduled_at'])
        with self.assertRaises(PermissionDenied):
            require_premiere_playback(request, self.episode)
        self.screening.status = 'cancelled'
        self.screening.save(update_fields=['status'])
        with self.assertRaises(PermissionDenied):
            require_premiere_playback(request, self.episode, allow_ended=True)
        request.GET = request.GET.copy()
        request.GET['premiere'] = 'invalid'
        with self.assertRaises(PermissionDenied):
            require_premiere_playback(request, self.episode)

    def test_existing_ended_stream_can_drain_but_no_new_ticket_is_allowed(self):
        self.screening.status = 'ended'
        self.screening.ended_at = timezone.now() - timedelta(seconds=5)
        self.screening.save(update_fields=['status', 'ended_at'])
        request = RequestFactory().get('/', {'premiere': str(self.screening.pk)})
        request.user = self.viewer
        with self.assertRaises(PermissionDenied):
            require_premiere_playback(request, self.episode)
        self.assertEqual(require_premiere_playback(request, self.episode, allow_ended=True), self.screening)
        frozen = premiere_stream_limit(self.screening)
        self.assertEqual(premiere_stream_limit(self.screening, timezone.now() + timedelta(hours=1)), frozen)

    def test_unready_and_unpublished_sources_are_invalid_for_scheduling(self):
        Episode.objects.filter(pk=self.episode.pk).update(status='pending')
        self.screening.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.screening.full_clean()

    def test_source_must_outlast_the_live_buffer_before_it_can_be_scheduled(self):
        Episode.objects.filter(pk=self.episode.pk).update(duration=12)
        self.screening.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, 'ít nhất 13 giây'):
            self.screening.full_clean()
        Episode.objects.filter(pk=self.episode.pk).update(duration=13)
        self.screening.refresh_from_db()
        self.screening.full_clean()

    def test_state_and_controls_keep_method_and_csrf_guards(self):
        self.assertEqual(self.editor_client.get(reverse('premiere_control', args=[self.screening.pk])).status_code, 405)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.editor)
        self.assertEqual(self.control(csrf, action='end').status_code, 403)
        self.assertEqual(csrf.post(self.state_url(), {'action': 'chat', 'content': 'hello'}).status_code, 403)

    def test_model_admin_requires_the_broadcast_permission_not_generic_staff(self):
        staff = Client()
        staff.force_login(self.staff)
        self.assertEqual(staff.get(reverse('admin:cinema_premiere_changelist')).status_code, 403)
        self.assertEqual(self.editor_client.get(reverse('admin:cinema_premiere_changelist')).status_code, 200)
        self.assertEqual(self.editor_client.get(reverse('admin:cinema_premiere_add')).status_code, 200)
        self.assertEqual(self.editor_client.get(reverse('admin:cinema_premieremessage_changelist')).status_code, 200)

    def test_withdrawn_sources_disappear_from_discovery_and_cannot_leak_metadata(self):
        listing = reverse('premieres')
        self.assertContains(self.client.get(listing), self.screening.title)
        Movie.objects.filter(pk=self.movie.pk).update(published=False)
        self.assertNotContains(self.client.get(listing), self.screening.title)
        self.assertEqual(self.client.get(reverse('premiere', args=[self.screening.pk])).status_code, 404)
        self.assertEqual(self.client.get(self.state_url()).status_code, 404)
        # Operators still receive state so they can cancel a withdrawn source.
        self.assertEqual(self.editor_client.get(self.state_url()).status_code, 200)
        Movie.objects.filter(pk=self.movie.pk).update(published=True)
        Episode.objects.filter(pk=self.episode.pk).update(status='processing')
        self.assertNotContains(self.client.get(listing), self.screening.title)


class PremiereStreamScopeTests(TestCase):
    """A signed premiere URL cannot expose segments ahead of its server clock."""

    def setUp(self):
        cache.clear()
        self.now = timezone.now()
        self.viewer = User.objects.create_user('premiere-stream-viewer', 'stream@premiere.test', vip_until=self.now + timedelta(days=1))
        movie = Movie.objects.create(title='Stream source', slug='premiere-stream-source', published=True)
        self.episode = Episode.objects.create(movie=movie, title='An episode', status='ready', duration=24)
        self.screening = Premiere.objects.create(title='A live premiere', episode=self.episode, scheduled_at=self.now - timedelta(seconds=12))
        self.client.force_login(self.viewer)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.overrides = override_settings(PRIVATE_MEDIA_ROOT=Path(temporary.name))
        self.overrides.enable()
        self.addCleanup(self.overrides.disable)
        output = Path(temporary.name) / 'hls' / str(self.episode.asset_id)
        output.mkdir(parents=True)
        (output / 'quality.json').write_text(json.dumps({'version': 1, 'renditions': [{
            'height': 720, 'width': 1280, 'video_height': 720, 'playlist': 'q720.m3u8', 'bandwidth': 2692000,
        }]}))
        lines = ['#EXTM3U', '#EXT-X-TARGETDURATION:6']
        for index in range(4):
            name = f'q720_seg{index:05d}.ts'
            lines.extend(['#EXTINF:6,', name])
            (output / name).write_bytes(b'private-segment')
        lines.append('#EXT-X-ENDLIST')
        (output / 'q720.m3u8').write_text('\n'.join(lines) + '\n')
        self.clock = patch('cinema.premieres.timezone.now', return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def get_ticket(self):
        return self.client.post(reverse('ticket', args=[self.episode.pk]) + '?' + urlencode({'premiere': self.screening.pk}))

    def stream_url(self, ticket, filename):
        return reverse('stream', args=[self.episode.pk, filename]) + '?' + urlsplit(ticket['url']).query

    def test_scope_is_signed_and_only_complete_already_aired_segments_are_exposed(self):
        response = self.get_ticket()
        self.assertEqual(response.status_code, 200)
        ticket = response.json()
        manifest = self.client.get(ticket['qualities'][0]['url'])
        self.assertEqual(manifest.status_code, 200)
        text = manifest.content.decode()
        self.assertIn('#EXT-X-PLAYLIST-TYPE:EVENT', text)
        self.assertNotIn('#EXT-X-ENDLIST', text)
        self.assertIn('q720_seg00001.ts', text)
        self.assertNotIn('q720_seg00002.ts', text)
        self.assertEqual(self.client.get(self.stream_url(ticket, 'q720_seg00002.ts')).status_code, 403)
        params = parse_qs(urlsplit(ticket['url']).query)
        params.pop('premiere')
        unscoped = reverse('stream', args=[self.episode.pk, 'index.m3u8']) + '?' + urlencode(params, doseq=True)
        self.assertEqual(self.client.get(unscoped).status_code, 403)

    def test_schedule_and_audience_are_rechecked_after_token_issue(self):
        self.screening.scheduled_at = self.now + timedelta(hours=1)
        self.screening.save(update_fields=['scheduled_at'])
        self.assertEqual(self.get_ticket().status_code, 403)
        self.screening.scheduled_at = self.now - timedelta(seconds=12)
        self.screening.audience = 'vip'
        self.screening.save(update_fields=['scheduled_at', 'audience'])
        ticket = self.get_ticket().json()
        User.objects.filter(pk=self.viewer.pk).update(vip_until=self.now - timedelta(seconds=1))
        self.assertEqual(self.client.get(self.stream_url(ticket, 'q720_seg00000.ts')).status_code, 403)

    def test_manual_end_drains_only_aired_content_and_denies_new_tickets(self):
        ticket = self.get_ticket().json()
        self.screening.status = 'ended'
        self.screening.ended_at = self.now
        self.screening.save(update_fields=['status', 'ended_at'])
        self.assertEqual(self.get_ticket().status_code, 403)
        manifest = self.client.get(ticket['qualities'][0]['url'])
        self.assertEqual(manifest.status_code, 200)
        self.assertIn('#EXT-X-ENDLIST', manifest.content.decode())
        self.assertNotIn('q720_seg00002.ts', manifest.content.decode())
        self.assertEqual(self.client.get(self.stream_url(ticket, 'q720_seg00002.ts')).status_code, 403)
