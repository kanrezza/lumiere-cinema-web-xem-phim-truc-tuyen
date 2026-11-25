"""Playlist operations preserve a watch room and enforce host/member roles."""
import json

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Chat, Episode, Membership, Movie, Room, RoomPlaylistItem, RoomSuggestion, User


TEST_CACHE = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'room-playlist-tests'},
}


@override_settings(CACHES=TEST_CACHE, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RoomPlaylistTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.host = User.objects.create_user('playlist-host', 'playlist-host@example.test', is_staff=True)
        cls.member = User.objects.create_user('playlist-member', 'playlist-member@example.test')
        cls.outsider = User.objects.create_user('playlist-outsider', 'playlist-outsider@example.test')
        cls.movie = Movie.objects.create(title='Phim cho cả nhóm', slug='phim-ca-nhom', published=True)
        cls.first = Episode.objects.create(movie=cls.movie, number=1, title='Tập đầu', status='ready', duration=100)
        cls.second = Episode.objects.create(movie=cls.movie, number=2, title='Tập kế', status='ready', duration=120)
        cls.third = Episode.objects.create(movie=cls.movie, number=3, title='Tập cuối', status='ready', duration=150)
        cls.private_movie = Movie.objects.create(title='Bản nháp', slug='ban-nhap-playlist', published=False)
        cls.private_episode = Episode.objects.create(movie=cls.private_movie, number=1, status='ready', duration=60)
        cls.pending = Episode.objects.create(movie=cls.movie, number=4, status='pending')
        cls.room = Room.objects.create(host=cls.host, name='Danh sách xem chung')
        Membership.objects.create(room=cls.room, user=cls.host)
        Membership.objects.create(room=cls.room, user=cls.member)

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.host_client, self.member_client, self.outsider_client = Client(), Client(), Client()
        self.host_client.force_login(self.host)
        self.member_client.force_login(self.member)
        self.outsider_client.force_login(self.outsider)
        self.endpoint = reverse('room_playlist', args=[self.room.pk])

    def snapshot(self, client=None):
        response = (client or self.host_client).get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def command(self, action, client=None, version=None, **data):
        if version is None:
            version = self.snapshot()['playlist_version']
        return (client or self.host_client).post(self.endpoint, {
            'action': action, 'playlist_version': version, **data,
        })

    def add(self, episode):
        response = self.command('add', episode=episode.pk)
        self.assertEqual(response.status_code, 200)
        return response.json()['items'][-1]

    def test_active_members_can_view_playlist_but_others_cannot(self):
        self.assertEqual(Client().get(self.endpoint).status_code, 302)
        self.assertEqual(self.outsider_client.get(self.endpoint).status_code, 404)
        self.assertEqual(self.command('add', client=self.outsider_client, episode=self.first.pk).status_code, 404)
        host, member = self.snapshot(), self.snapshot(self.member_client)
        self.assertTrue(host['is_host'])
        self.assertTrue(host['can_manage'])
        self.assertFalse(member['is_host'])
        self.assertFalse(member['can_manage'])
        Membership.objects.filter(room=self.room, user=self.member).update(active=False)
        self.assertEqual(self.member_client.get(self.endpoint).status_code, 404)

    def test_host_reorders_and_plays_without_resetting_chat_or_voice(self):
        first, second = self.add(self.first), self.add(self.second)
        Chat.objects.create(room=self.room, user=self.member, content='Chọn tập tiếp')
        voice = self.member_client.post(reverse('room_voice_action', args=[self.room.pk]), {'action': 'join'}).json()['session']
        version = self.snapshot()['playlist_version']
        reordered = self.command('reorder', version=version, item_ids=json.dumps([second['id'], first['id']]))
        self.assertEqual(reordered.status_code, 200)
        order = reordered.json()
        self.assertEqual([item['id'] for item in order['items']], [second['id'], first['id']])
        self.assertGreater(order['playlist_version'], version)
        self.room.refresh_from_db()
        old_media_version = self.room.media_version

        played = self.command('play', item=second['id'])
        self.assertEqual(played.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.room.episode_id, self.second.pk)
        self.assertGreater(self.room.media_version, old_media_version)
        self.assertEqual(self.room.position, 0)
        self.assertFalse(self.room.playing)
        self.assertEqual(Chat.objects.get(room=self.room).content, 'Chọn tập tiếp')
        member = Membership.objects.get(room=self.room, user=self.member)
        self.assertTrue(member.active)
        self.assertEqual(str(member.voice_session), voice)

    def test_guest_can_suggest_but_cannot_manage_the_playlist(self):
        item = self.add(self.first)
        suggested = self.command('suggest', client=self.member_client, episode=self.second.pk)
        self.assertEqual(suggested.status_code, 200)
        suggestion = suggested.json()['suggestions'][0]
        actions = (
            ('add', {'episode': self.third.pk}),
            ('remove', {'item': item['id']}),
            ('reorder', {'item_ids': json.dumps([item['id']])}),
            ('play', {'item': item['id']}),
            ('approve', {'suggestion': suggestion['id']}),
            ('reject', {'suggestion': suggestion['id']}),
        )
        for action, fields in actions:
            with self.subTest(action=action):
                response = self.command(action, client=self.member_client, **fields)
                self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self.snapshot()['items']), 1)
        self.assertEqual(len(self.snapshot()['suggestions']), 1)
        self.room.refresh_from_db()
        self.assertIsNone(self.room.episode_id)

    def test_host_approves_and_rejects_suggestions(self):
        suggested = self.command('suggest', client=self.member_client, episode=self.first.pk).json()
        first = suggested['suggestions'][0]
        accepted = self.command('approve', suggestion=first['id'])
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(len(accepted.json()['items']), 1)
        self.assertEqual(accepted.json()['suggestions'], [])
        member_history = self.snapshot(self.member_client)['suggestions']
        self.assertEqual(member_history[0]['status'], RoomSuggestion.Status.APPROVED)
        suggested = self.command('suggest', client=self.member_client, episode=self.second.pk).json()
        second = suggested['suggestions'][0]
        rejected = self.command('reject', suggestion=second['id'])
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()['suggestions'], [])
        self.assertEqual(len(rejected.json()['items']), 1)

    def test_stale_and_malformed_reorders_leave_the_queue_intact(self):
        initial = self.snapshot()['playlist_version']
        first, second = self.add(self.first), self.add(self.second)
        stale = self.command('remove', item=first['id'], version=initial)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()['code'], 'playlist_changed')
        self.assertEqual(len(stale.json()['items']), 2)
        original = self.snapshot()
        bad_orders = ('not-json', '{}', json.dumps([first['id']]), json.dumps([first['id'], first['id']]), json.dumps([first['id'], 999999]))
        for ids in bad_orders:
            with self.subTest(ids=ids):
                failed = self.command('reorder', item_ids=ids)
                self.assertEqual(failed.status_code, 400)
                current = self.snapshot()
                self.assertEqual([item['id'] for item in current['items']], [first['id'], second['id']])
                self.assertEqual(current['playlist_version'], original['playlist_version'])

    def test_private_or_unready_episodes_cannot_enter_queue_or_suggestions(self):
        for episode in (self.private_episode, self.pending):
            for action, client in (('add', self.host_client), ('suggest', self.member_client)):
                with self.subTest(episode=episode.pk, action=action):
                    self.assertEqual(self.command(action, client=client, episode=episode.pk).status_code, 404)
        snapshot = self.snapshot()
        self.assertEqual(snapshot['items'], [])
        self.assertEqual(snapshot['suggestions'], [])

    def test_playlist_writes_require_csrf_and_cannot_target_other_rooms(self):
        item = self.add(self.first)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.host)
        version = self.snapshot()['playlist_version']
        self.assertEqual(strict.post(self.endpoint, {'action': 'remove', 'item': item['id'], 'playlist_version': version}).status_code, 403)
        other = Room.objects.create(host=self.host, name='Phòng khác')
        Membership.objects.create(room=other, user=self.host)
        other_endpoint = reverse('room_playlist', args=[other.pk])
        self.assertEqual(self.host_client.post(other_endpoint, {'action': 'remove', 'item': item['id'], 'playlist_version': 1}).status_code, 404)
        self.assertEqual(len(self.snapshot()['items']), 1)

    def test_duplicate_add_and_suggestion_do_not_change_the_queue_or_version(self):
        added = self.command('add', episode=self.first.pk)
        duplicate = self.command('add', episode=self.first.pk)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json()['playlist_version'], added.json()['playlist_version'])
        self.assertEqual(len(duplicate.json()['items']), 1)
        queued_suggestion = self.command('suggest', client=self.member_client, episode=self.first.pk)
        self.assertEqual(queued_suggestion.status_code, 200)
        self.assertEqual(queued_suggestion.json()['suggestions'], [])

        proposed = self.command('suggest', client=self.member_client, episode=self.second.pk)
        repeated = self.command('suggest', client=self.member_client, episode=self.second.pk)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()['playlist_version'], proposed.json()['playlist_version'])
        self.assertEqual(len(repeated.json()['suggestions']), 1)

    def test_queue_and_per_member_suggestion_limits_preserve_existing_entries(self):
        episodes = Episode.objects.bulk_create([
            Episode(movie=self.movie, number=100 + number, title=f'Tập mẫu {number}', status='ready', duration=50)
            for number in range(51)
        ])
        RoomPlaylistItem.objects.bulk_create([
            RoomPlaylistItem(room=self.room, episode=episode, position=index)
            for index, episode in enumerate(episodes[:50], 1)
        ])
        version = self.snapshot()['playlist_version']
        full = self.command('add', episode=episodes[50].pk)
        self.assertEqual(full.status_code, 400)
        self.assertEqual(len(full.json()['items']), 50)
        self.assertEqual(full.json()['playlist_version'], version)
        blocked_suggestion = RoomSuggestion.objects.create(
            room=self.room, episode=episodes[50], proposed_by=self.member,
        )
        rejected_approval = self.command('approve', suggestion=blocked_suggestion.pk)
        self.assertEqual(rejected_approval.status_code, 400)
        blocked_suggestion.refresh_from_db()
        self.assertEqual(blocked_suggestion.status, RoomSuggestion.Status.PENDING)
        self.assertEqual(rejected_approval.json()['playlist_version'], version)
        self.assertEqual(len(rejected_approval.json()['items']), 50)

        other = Room.objects.create(host=self.host, name='Nhóm đề xuất')
        Membership.objects.create(room=other, user=self.host)
        Membership.objects.create(room=other, user=self.member)
        RoomSuggestion.objects.bulk_create([
            RoomSuggestion(room=other, episode=episode, proposed_by=self.member)
            for episode in episodes[:5]
        ])
        endpoint = reverse('room_playlist', args=[other.pk])
        capped = self.member_client.post(endpoint, {'action': 'suggest', 'episode': episodes[5].pk})
        self.assertEqual(capped.status_code, 400)
        self.assertEqual(RoomSuggestion.objects.filter(room=other, status=RoomSuggestion.Status.PENDING).count(), 5)

    def test_vip_access_is_checked_before_suggesting_and_unpublished_queue_metadata_is_hidden(self):
        vip_movie = Movie.objects.create(title='Chỉ dành VIP', slug='playlist-vip', published=True, is_vip=True)
        vip_episode = Episode.objects.create(movie=vip_movie, number=1, title='Bản VIP', status='ready', duration=80)
        self.assertEqual(self.command('suggest', client=self.member_client, episode=vip_episode.pk).status_code, 403)
        self.add(self.first)
        Movie.objects.filter(pk=self.movie.pk).update(published=False)
        snapshot = self.snapshot(self.member_client)
        self.assertFalse(snapshot['items'][0]['available'])
        self.assertNotEqual(snapshot['items'][0]['title'], self.movie.title)
        self.assertEqual(snapshot['items'][0]['poster_url'], '')
        self.room.refresh_from_db()
        old_version = self.room.media_version
        selected = self.command('play', item=snapshot['items'][0]['id'])
        self.assertEqual(selected.status_code, 403)
        self.room.refresh_from_db()
        self.assertEqual(self.room.media_version, old_version)
        self.assertIsNone(self.room.episode_id)
