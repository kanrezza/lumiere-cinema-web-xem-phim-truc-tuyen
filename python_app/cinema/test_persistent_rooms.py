"""Rooms retain their identity and participants while their selected film changes."""
from datetime import timedelta

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Chat, Episode, Membership, Movie, Room, RoomJoinRequest, User


TEST_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'persistent-room-tests',
    },
}


@override_settings(CACHES=TEST_CACHE, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PersistentRoomTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.host = User.objects.create_user('room-host', 'room-host@example.test', is_staff=True)
        cls.guest = User.objects.create_user('room-guest', 'room-guest@example.test')
        cls.outsider = User.objects.create_user('room-outsider', 'room-outsider@example.test')
        cls.vip = User.objects.create_user(
            'room-vip', 'room-vip@example.test', vip_until=timezone.now() + timedelta(days=30),
        )
        cls.free_movie = Movie.objects.create(title='Buổi chiếu thứ nhất', slug='buoi-chieu-thu-nhat', published=True)
        cls.free_episode = Episode.objects.create(movie=cls.free_movie, title='Phim đầu', status='ready', duration=100)
        cls.next_movie = Movie.objects.create(title='Buổi chiếu thứ hai', slug='buoi-chieu-thu-hai', published=True)
        cls.next_episode = Episode.objects.create(movie=cls.next_movie, title='Phim kế', status='ready', duration=150)
        cls.vip_movie = Movie.objects.create(title='Phim VIP', slug='phim-vip', published=True, is_vip=True)
        cls.vip_episode = Episode.objects.create(movie=cls.vip_movie, title='Bản VIP', status='ready', duration=90)
        cls.draft = Movie.objects.create(title='Bản nháp riêng', slug='ban-nhap-rieng', published=False)
        cls.draft_episode = Episode.objects.create(movie=cls.draft, title='Chưa công khai', status='ready', duration=100)

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.host_client, self.guest_client, self.other_client = Client(), Client(), Client()
        self.host_client.force_login(self.host)
        self.guest_client.force_login(self.guest)
        self.other_client.force_login(self.outsider)

    def make_room(self, episode=None):
        room = Room.objects.create(host=self.host, name='Phòng của nhóm', episode=episode)
        Membership.objects.create(room=room, user=self.host)
        Membership.objects.create(room=room, user=self.guest)
        return room

    def select(self, room, episode, version=None, client=None):
        if version is None:
            room.refresh_from_db()
            version = room.media_version
        return (client or self.host_client).post(reverse('room_selection', args=[room.pk]), {
            'episode': episode.pk,
            'media_version': version,
        })

    def test_create_room_without_a_film_and_reuse_its_invite(self):
        page = reverse('rooms')
        self.assertEqual(Client().get(page).status_code, 302)
        self.assertEqual(self.guest_client.post(page, {'name': 'Nhóm thường'}).status_code, 302)
        response = self.host_client.post(page, {'name': 'Tối thứ bảy'})
        self.assertEqual(response.status_code, 302)
        room = Room.objects.get(name='Tối thứ bảy')
        room_url = reverse('room', args=[room.pk])
        self.assertEqual(response['Location'], room_url)
        self.assertIsNone(room.episode_id)
        self.assertTrue(room.members.filter(user=self.host, active=True).exists())
        self.assertEqual(self.other_client.post(reverse('join_room', args=[room.pk])).status_code, 302)
        self.assertContains(self.other_client.get(room_url), room.name)
        self.assertContains(self.host_client.get(page), room_url)

    def test_empty_room_supports_chat_roster_and_voice(self):
        room = self.make_room()
        state_url = reverse('room_state', args=[room.pk])
        state = self.guest_client.get(state_url)
        self.assertEqual(state.status_code, 200)
        snapshot = state.json()
        self.assertIsNone(snapshot['episode_id'])
        self.assertFalse(snapshot['can_watch'])
        self.assertEqual(snapshot['title'], '')
        self.assertEqual(snapshot['position'], 0)
        self.assertFalse(snapshot['playing'])
        self.assertEqual(len(snapshot['members']), 2)
        self.assertEqual(self.guest_client.post(state_url, {'action': 'chat', 'content': 'Chọn phim nào?'}).status_code, 200)
        self.assertEqual(Chat.objects.get(room=room).content, 'Chọn phim nào?')
        voice = self.guest_client.post(reverse('room_voice_action', args=[room.pk]), {'action': 'join'})
        self.assertEqual(voice.status_code, 200)
        self.assertTrue(voice.json()['session'])
        self.assertContains(self.host_client.get(reverse('room_player', args=[room.pk])), 'data-room-player')

    def test_seated_roster_exposes_display_avatar_without_private_account_data(self):
        room = self.make_room()
        User.objects.filter(pk=self.guest.pk).update(
            first_name='Người xem', last_name='Thử nghiệm', avatar='avatars/' + 'a' * 32 + '.webp',
        )
        RoomJoinRequest.objects.create(room=room, user=self.outsider)
        response = self.host_client.get(reverse('room_state', args=[room.pk]))
        roster = response.json()['members']
        guest = next(member for member in roster if member['user_id'] == self.guest.pk)
        self.assertEqual(guest['display_name'], 'Người xem Thử nghiệm')
        self.assertTrue(guest['avatar_url'].endswith('/avatars/' + 'a' * 32 + '.webp'))
        self.assertFalse(any(member['user_id'] == self.outsider.pk for member in roster))
        self.assertNotContains(response, self.guest.email)
        self.assertNotContains(response, 'password')

        Membership.objects.filter(room=room, user=self.guest).update(banned=True, active=False)
        roster = self.host_client.get(reverse('room_state', args=[room.pk])).json()['members']
        self.assertFalse(any(member['user_id'] == self.guest.pk for member in roster))

    def test_switching_films_preserves_members_messages_and_voice(self):
        room = self.make_room(self.free_episode)
        state_url = reverse('room_state', args=[room.pk])
        version = room.media_version
        Chat.objects.create(room=room, user=self.guest, content='Cùng xem phim kế')
        voice = self.guest_client.post(reverse('room_voice_action', args=[room.pk]), {'action': 'join'}).json()['session']
        synchronized = self.host_client.post(state_url, {
            'action': 'sync', 'position': 27, 'playing': 'true', 'media_version': version,
        })
        self.assertEqual(synchronized.status_code, 200)

        self.assertEqual(self.select(room, self.next_episode, version).status_code, 302)
        room.refresh_from_db()
        self.assertEqual(room.episode_id, self.next_episode.pk)
        self.assertGreater(room.media_version, version)
        self.assertEqual(room.position, 0)
        self.assertFalse(room.playing)
        self.assertEqual(room.members.filter(active=True, banned=False).count(), 2)
        self.assertTrue(Chat.objects.filter(room=room, content='Cùng xem phim kế').exists())
        guest = room.members.get(user=self.guest)
        self.assertEqual(str(guest.voice_session), voice)
        snapshot = self.guest_client.get(state_url).json()
        self.assertEqual(snapshot['episode_id'], self.next_episode.pk)
        self.assertEqual(snapshot['media_version'], room.media_version)
        self.assertTrue(snapshot['can_watch'])
        self.assertEqual(snapshot['title'], self.next_movie.title)

    def test_stale_sync_and_selection_cannot_overwrite_current_movie(self):
        room = self.make_room(self.free_episode)
        original_version = room.media_version
        self.assertEqual(self.select(room, self.next_episode, original_version).status_code, 302)
        room.refresh_from_db()
        next_version = room.media_version
        self.assertEqual(self.select(room, self.free_episode, original_version).status_code, 409)
        self.assertEqual(self.select(room, self.free_episode, next_version).status_code, 302)
        room.refresh_from_db()
        self.assertGreater(room.media_version, next_version)
        stale_sync = self.host_client.post(reverse('room_state', args=[room.pk]), {
            'action': 'sync', 'position': 72, 'playing': 'true', 'media_version': original_version,
        })
        self.assertEqual(stale_sync.status_code, 409)
        missing_version = self.host_client.post(reverse('room_state', args=[room.pk]), {
            'action': 'sync', 'position': 72, 'playing': 'true',
        })
        self.assertEqual(missing_version.status_code, 409)
        room.refresh_from_db()
        self.assertEqual(room.position, 0)
        self.assertFalse(room.playing)

    def test_only_host_selects_published_ready_content_they_can_watch(self):
        room = self.make_room()
        selection_url = reverse('room_selection', args=[room.pk])
        self.assertEqual(self.guest_client.get(selection_url).status_code, 200)
        self.assertEqual(self.select(room, self.free_episode, client=self.guest_client).status_code, 403)
        self.assertEqual(self.select(room, self.free_episode, client=self.other_client).status_code, 404)
        self.assertEqual(self.select(room, self.draft_episode).status_code, 404)
        pending = Episode.objects.create(movie=self.free_movie, number=2, title='Đang xử lý', status='pending')
        self.assertEqual(self.select(room, pending).status_code, 404)
        room.refresh_from_db()
        self.assertIsNone(room.episode_id)
        chooser = self.host_client.get(selection_url)
        self.assertEqual(chooser.status_code, 200)
        self.assertNotContains(chooser, self.draft.title)

    def test_movie_access_is_separate_from_room_chat_and_voice_access(self):
        room = self.make_room(self.free_episode)
        self.assertEqual(self.select(room, self.vip_episode).status_code, 302)
        room_url = reverse('room', args=[room.pk])
        state_url = reverse('room_state', args=[room.pk])
        self.assertEqual(self.guest_client.get(room_url).status_code, 200)
        state = self.guest_client.get(state_url).json()
        self.assertFalse(state['can_watch'])
        self.assertEqual(state['episode_id'], self.vip_episode.pk)
        fragment = self.guest_client.get(reverse('room_player', args=[room.pk]))
        self.assertEqual(fragment.status_code, 200)
        self.assertNotContains(fragment, 'data-ticket=')
        self.assertEqual(self.guest_client.post(reverse('ticket', args=[self.vip_episode.pk])).status_code, 403)
        self.assertEqual(self.guest_client.post(state_url, {'action': 'chat', 'content': 'Mình vẫn ở đây'}).status_code, 200)
        voice = self.guest_client.post(reverse('room_voice_action', args=[room.pk]), {'action': 'join'})
        self.assertEqual(voice.status_code, 200)
        self.assertEqual(self.other_client.get(state_url).status_code, 404)
        self.assertEqual(self.other_client.get(reverse('room_player', args=[room.pk])).status_code, 404)

    def test_access_changes_refresh_player_state_without_changing_the_movie(self):
        room = self.make_room(self.vip_episode)
        initial_version = room.media_version
        state_url = reverse('room_state', args=[room.pk])
        player_url = reverse('room_player', args=[room.pk])
        User.objects.filter(pk=self.guest.pk).update(vip_until=timezone.now() + timedelta(days=1))
        entitled = self.guest_client.get(state_url).json()
        self.assertTrue(entitled['can_watch'])
        self.assertContains(self.guest_client.get(player_url), 'data-ticket=')

        User.objects.filter(pk=self.guest.pk).update(vip_until=timezone.now() - timedelta(seconds=1))
        revoked = self.guest_client.get(state_url).json()
        self.assertFalse(revoked['can_watch'])
        self.assertEqual(revoked['media_version'], initial_version)
        self.assertNotContains(self.guest_client.get(player_url), 'data-ticket=')
        self.assertEqual(self.guest_client.post(state_url, {'action': 'chat', 'content': 'Còn trong phòng'}).status_code, 200)

    def test_deleting_selected_episode_keeps_room_and_its_history(self):
        room = self.make_room(self.free_episode)
        Chat.objects.create(room=room, user=self.guest, content='Giữ lại buổi xem')
        self.free_episode.delete()
        room.refresh_from_db()
        self.assertIsNone(room.episode_id)
        self.assertTrue(Chat.objects.filter(room=room).exists())
        state = self.guest_client.get(reverse('room_state', args=[room.pk]))
        self.assertEqual(state.status_code, 200)
        self.assertIsNone(state.json()['episode_id'])
        self.assertFalse(state.json()['can_watch'])

    def test_existing_watch_entry_still_starts_a_room_with_the_selected_episode(self):
        response = self.host_client.post(reverse('create_room', args=[self.free_episode.pk]), {'name': 'Xem ngay'})
        self.assertEqual(response.status_code, 302)
        room = Room.objects.get(name='Xem ngay')
        self.assertEqual(room.episode_id, self.free_episode.pk)
        self.assertContains(self.host_client.get(response['Location']), room.name)
        snapshot = self.host_client.get(reverse('room_state', args=[room.pk])).json()
        self.assertTrue(snapshot['can_watch'])
        self.assertEqual(snapshot['episode_id'], self.free_episode.pk)

    def test_clear_selection_retains_room_chat_and_rejects_old_sync(self):
        room = self.make_room(self.free_episode)
        original_version = room.media_version
        Chat.objects.create(room=room, user=self.guest, content='Chờ chọn phim mới')
        response = self.host_client.post(reverse('room_selection', args=[room.pk]), {
            'action': 'clear', 'media_version': original_version,
        }, HTTP_X_LUMIERE_ROOM_SELECTION='1')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['episode_id'])
        snapshot = self.guest_client.get(reverse('room_state', args=[room.pk])).json()
        self.assertFalse(snapshot['playing'])
        self.assertEqual(snapshot['messages'][0]['content'], 'Chờ chọn phim mới')
        self.assertEqual(self.host_client.post(reverse('room_state', args=[room.pk]), {
            'action': 'sync', 'media_version': original_version, 'position': 12,
        }).status_code, 409)

    def test_selection_and_creation_require_csrf_and_filters_keep_search(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.host)
        self.assertEqual(strict.post(reverse('rooms'), {'name': 'Rejected'}).status_code, 403)
        room = self.make_room()
        selection = reverse('room_selection', args=[room.pk])
        self.assertEqual(strict.post(selection, {'episode': self.free_episode.pk, 'media_version': 1}).status_code, 403)
        result = self.host_client.get(selection, {'q': 'thu hai'}, HTTP_X_LUMIERE_ROOM_SELECTION='1')
        self.assertContains(result, self.next_movie.title)
        self.assertNotContains(result, self.free_movie.title)
        self.assertNotContains(result, '<html')

    def test_unpublished_media_is_hidden_but_room_is_retained(self):
        room = self.make_room(self.free_episode)
        Movie.objects.filter(pk=self.free_movie.pk).update(published=False)
        state = self.guest_client.get(reverse('room_state', args=[room.pk])).json()
        self.assertFalse(state['can_watch'])
        self.assertEqual(state['title'], '')
        self.assertNotContains(self.guest_client.get(reverse('room', args=[room.pk])), self.free_movie.title)
        self.assertNotContains(self.guest_client.get(reverse('room_player', args=[room.pk])), 'data-ticket=')

    def test_player_revision_and_episode_ids_are_not_localized(self):
        episode = Episode.objects.create(
            pk=1234, movie=self.free_movie, number=2, title='Tập thử', status='ready', duration=90,
        )
        room = self.make_room(episode)
        Room.objects.filter(pk=room.pk).update(media_version=1234)
        response = self.host_client.get(reverse('room', args=[room.pk]))
        self.assertContains(response, 'data-episode-id="1234"')
        self.assertContains(response, 'data-media-version="1234"', count=2)
        fragment = self.guest_client.get(reverse('room_player', args=[room.pk]))
        self.assertContains(fragment, 'data-media-version="1234"')
