import json
from datetime import timedelta
from uuid import uuid4

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Membership, Movie, Room, RoomVoiceSignal, User
from .room_voice import VOICE_HEARTBEAT


class RoomVoiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.host = User.objects.create_user('voice-host', 'voice-host@example.test', is_staff=True)
        cls.guest = User.objects.create_user('voice-guest', 'voice-guest@example.test')
        cls.outsider = User.objects.create_user('voice-outsider', 'voice-outsider@example.test')
        movie = Movie.objects.create(title='Voice chat film', slug='voice-chat-film', published=True)
        cls.episode = Episode.objects.create(movie=movie, title='Part 1', status='ready', duration=100)
        cls.room = Room.objects.create(host=cls.host, episode=cls.episode, name='Voice test room')
        cls.host_member = Membership.objects.create(room=cls.room, user=cls.host)
        cls.guest_member = Membership.objects.create(room=cls.room, user=cls.guest)

    def setUp(self):
        self.host_client, self.guest_client, self.other_client = Client(), Client(), Client()
        self.host_client.force_login(self.host)
        self.guest_client.force_login(self.guest)
        self.other_client.force_login(self.outsider)
        self.voice = reverse('room_voice', args=[self.room.pk])
        self.action = reverse('room_voice_action', args=[self.room.pk])

    def command(self, client, action, **params):
        return client.post(self.action, {'action': action, **params})

    def join(self, client):
        response = self.command(client, 'join')
        self.assertEqual(response.status_code, 200)
        return response.json()['session']

    def send_sdp(self, client, session, recipient, target_session, *, media='audio'):
        return self.command(
            client, 'signal', session=session, user=recipient, target_session=target_session, type='offer',
            payload=json.dumps({'sdp': f'v=0\r\nm={media} 9 UDP/TLS/RTP/SAVPF 111\r\n', 'negotiation': str(uuid4())}),
        )

    def test_reentering_voice_refreshes_admitted_presence_and_always_resets_microphone(self):
        old_session = uuid4()
        Membership.objects.filter(pk=self.guest_member.pk).update(
            last_seen=timezone.now() - timedelta(minutes=1), voice_session=old_session,
            voice_seen_at=timezone.now(), voice_mic_on=True,
        )
        response = self.command(self.guest_client, 'join')
        self.assertEqual(response.status_code, 200)
        self.guest_member.refresh_from_db()
        self.assertNotEqual(self.guest_member.voice_session, old_session)
        self.assertFalse(self.guest_member.voice_mic_on)
        self.assertGreater(self.guest_member.last_seen, timezone.now() - timedelta(seconds=5))
        self.assertFalse(self.guest_client.get(self.voice).json()['self']['mic_on'])

    def test_voice_controls_require_admission_and_are_host_only(self):
        self.assertEqual(self.other_client.get(self.voice).status_code, 404)
        self.assertEqual(self.command(self.other_client, 'join').status_code, 404)
        self.assertEqual(self.command(self.guest_client, 'mute', user=self.host.pk, muted='true').status_code, 403)
        self.assertEqual(self.command(self.host_client, 'mute', user=self.outsider.pk, muted='true').status_code, 404)
        Membership.objects.filter(pk=self.guest_member.pk).update(banned=True, active=False)
        self.assertEqual(self.guest_client.get(self.voice).status_code, 404)

    def test_host_mute_disables_mic_and_unmute_requires_guest_to_opt_in(self):
        session = self.join(self.guest_client)
        self.assertFalse(self.guest_client.get(self.voice).json()['self']['mic_on'])
        self.assertEqual(self.command(self.guest_client, 'mic', session=session, enabled='true').status_code, 200)
        self.assertTrue(self.host_client.get(self.voice).json()['peers'][0]['mic_on'])

        self.assertEqual(self.command(self.host_client, 'mute', user=self.guest.pk, muted='true').status_code, 200)
        guest_state = self.guest_client.get(self.voice, {'session': session}).json()['self']
        self.assertTrue(guest_state['host_muted'])
        self.assertFalse(guest_state['mic_on'])
        self.assertEqual(guest_state['voice_session'], session)
        self.assertEqual(self.command(self.guest_client, 'mic', session=session, enabled='true').status_code, 403)

        self.assertEqual(self.command(self.host_client, 'mute', user=self.guest.pk, muted='false').status_code, 200)
        guest_state = self.guest_client.get(self.voice, {'session': session}).json()['self']
        self.assertFalse(guest_state['host_muted'])
        self.assertFalse(guest_state['mic_on'])
        self.assertEqual(self.command(self.guest_client, 'mic', session=session, enabled='true').status_code, 200)

    def test_signals_require_current_sessions_and_are_delivered_only_to_the_recipient(self):
        host_session = self.join(self.host_client)
        guest_session = self.join(self.guest_client)
        self.assertEqual(self.send_sdp(self.host_client, host_session, self.outsider.pk, guest_session).status_code, 409)
        self.assertEqual(self.send_sdp(self.host_client, host_session, self.guest.pk, guest_session, media='video').status_code, 400)
        self.assertEqual(self.send_sdp(self.host_client, host_session, self.guest.pk, guest_session).status_code, 200)
        self.assertEqual(self.host_client.get(self.voice, {'session': host_session}).json()['signals'], [])
        self.assertEqual(self.guest_client.get(self.voice).json()['signals'], [])
        signal, = self.guest_client.get(self.voice, {'session': guest_session}).json()['signals']
        self.assertEqual((signal['from_user_id'], signal['from_session'], signal['type']), (self.host.pk, host_session, 'offer'))
        self.assertEqual(self.guest_client.get(self.voice, {'session': guest_session, 'after': signal['id']}).json()['signals'], [])

        RoomVoiceSignal.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.guest_client.get(self.voice, {'session': guest_session}).json()['signals'], [])
        replacement = self.join(self.guest_client)
        self.assertNotEqual(replacement, guest_session)
        self.assertEqual(self.send_sdp(self.host_client, host_session, self.guest.pk, guest_session).status_code, 409)
        self.assertEqual(self.command(self.guest_client, 'mic', session=guest_session, enabled='true').status_code, 409)

    def test_voice_expiry_is_not_renewable_from_a_stale_session(self):
        guest_session = self.join(self.guest_client)
        expired = timezone.now() - VOICE_HEARTBEAT - timedelta(seconds=1)
        Membership.objects.filter(pk=self.guest_member.pk).update(voice_seen_at=expired, voice_mic_on=True)
        response = self.guest_client.get(self.voice, {'session': guest_session}).json()['self']
        self.assertIsNone(response['voice_session'])
        self.assertFalse(response['mic_on'])
        self.guest_member.refresh_from_db()
        self.assertEqual(self.guest_member.voice_seen_at, expired)

    def test_returning_member_can_load_voice_state_while_room_presence_refreshes(self):
        Membership.objects.filter(pk=self.guest_member.pk).update(last_seen=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.guest_client.get(self.voice).status_code, 200)
        self.assertEqual(self.command(self.guest_client, 'join').status_code, 200)
        self.assertFalse(self.guest_client.get(self.voice).json()['self']['mic_on'])
        room_state = reverse('room_state', args=[self.room.pk])
        self.assertEqual(self.guest_client.get(room_state).status_code, 200)
        self.join(self.guest_client)

    @override_settings(ROOM_VOICE_ICE_SERVERS=[{'urls': 'stun:voice.example.test:3478'}])
    def test_ice_config_is_scoped_and_only_the_room_page_allows_microphone(self):
        self.assertEqual(self.guest_client.get(self.voice).json()['ice_servers'], [{'urls': 'stun:voice.example.test:3478'}])
        room_page = reverse('room', args=[self.room.pk])
        self.assertIn('microphone=(self)', self.guest_client.get(room_page)['Permissions-Policy'])
        self.assertIn('microphone=()', self.other_client.get(room_page)['Permissions-Policy'])
        self.assertIn('microphone=()', self.guest_client.get(reverse('watch', args=[self.episode.pk]))['Permissions-Policy'])
