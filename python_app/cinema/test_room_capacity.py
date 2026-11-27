"""Room limits follow the host's plan and always include the host's seat."""
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Membership, Movie, Room, RoomJoinRequest, RoomVoiceSignal, User


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RoomPlanCapacityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.free_host = User.objects.create_user('free-room-host', 'free-host@example.test')
        cls.vip_host = User.objects.create_user(
            'vip-room-host', 'vip-host@example.test', vip_until=timezone.now() + timedelta(days=3),
        )
        cls.staff_host = User.objects.create_user('staff-room-host', 'staff-host@example.test', is_staff=True)
        cls.guests = [User.objects.create_user(f'room-guest-{index}', f'guest-{index}@example.test') for index in range(10)]
        cls.vip_guest = User.objects.create_user(
            'vip-room-guest', 'vip-guest@example.test', vip_until=timezone.now() + timedelta(days=3),
        )
        free_movie = Movie.objects.create(title='Free room film', slug='free-room-film', published=True)
        vip_movie = Movie.objects.create(title='VIP room film', slug='vip-room-film', published=True, is_vip=True)
        cls.free_episode = Episode.objects.create(movie=free_movie, title='Free film', status='ready', duration=90)
        cls.vip_episode = Episode.objects.create(movie=vip_movie, title='VIP film', status='ready', duration=90)

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def make_room(self, host=None, **values):
        host = host or self.free_host
        room = Room.objects.create(host=host, name='Plan-limited screening', **values)
        Membership.objects.create(room=room, user=host)
        return room

    def join(self, room, user, **fields):
        return self.client_for(user).post(reverse('join_room', args=[room.pk]), fields)

    def state(self, room, user):
        return self.client_for(user).get(reverse('room_state', args=[room.pk]))

    def test_free_user_can_create_an_empty_room_with_three_seats(self):
        client = self.client_for(self.free_host)
        response = client.post(reverse('rooms'), {'name': 'Free screening'})
        room = Room.objects.get(host=self.free_host, name='Free screening')
        self.assertRedirects(response, reverse('room', args=[room.pk]))
        self.assertIsNone(room.episode_id)
        self.assertEqual(self.state(room, self.free_host).json()['capacity'], 3)
        self.assertTrue(room.members.filter(user=self.free_host, active=True).exists())
        self.assertEqual(client.get(response['Location']).context['room_capacity'], 3)

    def test_free_user_can_create_a_room_from_a_free_film(self):
        response = self.client_for(self.free_host).post(reverse('create_room', args=[self.free_episode.pk]), {
            'name': 'Start with a film',
        })
        room = Room.objects.get(host=self.free_host)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(room.episode_id, self.free_episode.pk)
        self.assertEqual(self.state(room, self.free_host).json()['capacity'], 3)

    def test_free_room_accepts_two_guests_and_rejects_the_fourth_person(self):
        room = self.make_room()
        for guest in self.guests[:2]:
            self.assertEqual(self.join(room, guest).status_code, 302)
        response = self.join(room, self.guests[2])
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, '3 người', status_code=409)
        self.assertFalse(room.members.filter(user=self.guests[2]).exists())
        for occupant in [self.free_host, *self.guests[:2]]:
            snapshot = self.state(room, occupant)
            self.assertEqual(snapshot.status_code, 200)
            self.assertEqual(snapshot.json()['capacity'], 3)
            self.assertEqual(len(snapshot.json()['members']), 3)

    def test_vip_and_staff_rooms_allow_ten_people_including_the_host(self):
        for host in [self.vip_host, self.staff_host]:
            with self.subTest(host=host.username):
                room = self.make_room(host)
                for guest in self.guests[:9]:
                    self.assertEqual(self.join(room, guest).status_code, 302)
                self.assertEqual(self.join(room, self.guests[9]).status_code, 409)
                snapshot = self.state(room, host)
                self.assertEqual(snapshot.status_code, 200)
                self.assertEqual(snapshot.json()['capacity'], 10)
                self.assertEqual(len(snapshot.json()['members']), 10)

    def test_guest_vip_does_not_increase_a_free_hosts_capacity(self):
        room = self.make_room()
        self.assertEqual(self.join(room, self.guests[0]).status_code, 302)
        self.assertEqual(self.join(room, self.vip_guest).status_code, 302)
        self.assertEqual(self.join(room, self.guests[1]).status_code, 409)
        self.assertEqual(self.state(room, self.vip_guest).json()['capacity'], 3)

    def test_host_seat_is_reserved_even_when_the_host_heartbeat_is_stale(self):
        room = self.make_room()
        room.members.filter(user=self.free_host).update(last_seen=timezone.now() - timedelta(minutes=1))
        for guest in self.guests[:2]:
            self.assertEqual(self.join(room, guest).status_code, 302)
        self.assertEqual(self.join(room, self.guests[2]).status_code, 409)
        self.assertEqual(self.state(room, self.free_host).status_code, 200)
        self.assertEqual(len(self.state(room, self.free_host).json()['members']), 3)

    def test_stale_active_membership_cannot_bypass_a_full_room(self):
        room = self.make_room()
        returning = self.guests[0]
        Membership.objects.create(room=room, user=returning, last_seen=timezone.now() - timedelta(minutes=1))
        for guest in self.guests[1:3]:
            self.assertEqual(self.join(room, guest).status_code, 302)
        self.assertEqual(self.join(room, returning).status_code, 409)
        self.assertEqual(self.state(room, returning).status_code, 409)
        voice = self.client_for(returning).post(reverse('room_voice_action', args=[room.pk]), {'action': 'join'})
        self.assertEqual(voice.status_code, 409)
        self.assertIsNone(room.members.get(user=returning).voice_session)

    def test_leaving_frees_a_guest_seat_without_changing_the_limit(self):
        room = self.make_room()
        for guest in self.guests[:2]:
            self.join(room, guest)
        self.assertEqual(self.join(room, self.guests[2]).status_code, 409)
        self.client_for(self.guests[0]).post(reverse('leave_room', args=[room.pk]))
        self.assertEqual(self.join(room, self.guests[2]).status_code, 302)
        self.assertEqual(self.state(room, self.free_host).json()['capacity'], 3)

    def test_correct_password_does_not_bypass_the_free_room_limit(self):
        room = self.make_room(password_hash=make_password('private-preview-password'))
        for guest in self.guests[:2]:
            self.assertEqual(self.join(room, guest, password='private-preview-password').status_code, 302)
        self.assertEqual(self.join(room, self.guests[2], password='private-preview-password').status_code, 409)
        self.assertFalse(room.members.filter(user=self.guests[2]).exists())

    def test_approved_guest_still_needs_a_free_seat_to_join(self):
        room = self.make_room(requires_approval=True)
        for guest in self.guests[:2]:
            Membership.objects.create(room=room, user=guest)
        entry = RoomJoinRequest.objects.create(room=room, user=self.guests[2])
        host_client = self.client_for(self.free_host)
        approved = host_client.post(reverse('room_admission', args=[room.pk]), {'action': 'approve', 'request': entry.pk})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(self.join(room, self.guests[2]).status_code, 409)
        self.assertFalse(room.members.filter(user=self.guests[2]).exists())
        entry.refresh_from_db()
        self.assertEqual(entry.status, RoomJoinRequest.Status.APPROVED)

    def test_upgrade_expands_an_existing_room_without_changing_its_identity(self):
        room = self.make_room()
        for guest in self.guests[:2]:
            self.join(room, guest)
        self.assertEqual(self.join(room, self.guests[2]).status_code, 409)
        User.objects.filter(pk=self.free_host.pk).update(vip_until=timezone.now() + timedelta(days=3))
        self.assertEqual(self.join(room, self.guests[2]).status_code, 302)
        self.assertEqual(self.state(room, self.free_host).json()['capacity'], 10)
        self.assertTrue(Room.objects.filter(pk=room.pk, closed=False).exists())

    def test_expired_vip_keeps_the_host_and_earliest_two_guests_without_banning_others(self):
        room = self.make_room(self.vip_host)
        for guest in self.guests[:4]:
            self.join(room, guest)
        dropped = room.members.get(user=self.guests[2])
        session = uuid4()
        room.members.filter(pk=dropped.pk).update(voice_session=session, voice_seen_at=timezone.now(), voice_mic_on=True)
        RoomVoiceSignal.objects.create(
            room=room, sender=self.guests[2], recipient=self.vip_host,
            sender_session=session, recipient_session=uuid4(), kind='offer',
            payload={'sdp': 'test audio'}, expires_at=timezone.now() + timedelta(seconds=30),
        )
        User.objects.filter(pk=self.vip_host.pk).update(vip_until=timezone.now() - timedelta(seconds=1))
        snapshot = self.state(room, self.vip_host)
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json()['capacity'], 3)
        self.assertEqual({entry['user_id'] for entry in snapshot.json()['members']}, {
            self.vip_host.pk, self.guests[0].pk, self.guests[1].pk,
        })
        self.assertTrue(Room.objects.filter(pk=room.pk, closed=False).exists())
        dropped.refresh_from_db()
        self.assertFalse(dropped.active)
        self.assertFalse(dropped.banned)
        self.assertIsNone(dropped.voice_session)
        self.assertFalse(dropped.voice_mic_on)
        self.assertFalse(RoomVoiceSignal.objects.filter(room=room).exists())
        self.assertEqual(self.state(room, self.guests[2]).status_code, 404)
        self.assertEqual(self.join(room, self.guests[2]).status_code, 409)
        self.client_for(self.guests[0]).post(reverse('leave_room', args=[room.pk]))
        self.assertEqual(self.join(room, self.guests[2]).status_code, 302)

    def test_inactive_host_cannot_leave_a_usable_room_for_guests(self):
        room = self.make_room()
        Membership.objects.create(room=room, user=self.guests[0])
        User.objects.filter(pk=self.free_host.pk).update(is_active=False)
        self.assertEqual(self.state(room, self.guests[0]).status_code, 403)
        self.assertEqual(self.join(room, self.guests[1]).status_code, 403)

    def test_free_room_does_not_grant_access_to_vip_films(self):
        client = self.client_for(self.free_host)
        denied = client.post(reverse('create_room', args=[self.vip_episode.pk]), {'name': 'No entitlement'})
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(Room.objects.filter(host=self.free_host).exists())
        room = self.make_room(episode=self.vip_episode)
        state = self.state(room, self.free_host).json()
        self.assertEqual(state['capacity'], 3)
        self.assertFalse(state['can_watch'])
        self.assertNotContains(client.get(reverse('room_player', args=[room.pk])), 'data-ticket=')
        self.assertEqual(client.post(reverse('ticket', args=[self.vip_episode.pk])).status_code, 403)
