"""Chat exposes only public author profiles and remains room-scoped."""

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Chat, Membership, Room, User


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RoomChatTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.host = User.objects.create_user('chat-host', 'host@example.test')
        cls.viewer = User.objects.create_user(
            'chat-viewer', 'private@example.test', first_name='Minh', last_name='Anh',
            avatar='avatars/' + 'a' * 32 + '.webp',
        )
        cls.outsider = User.objects.create_user('chat-outsider', 'outsider@example.test')
        cls.room = Room.objects.create(host=cls.host, name='Chat preview')
        Membership.objects.create(room=cls.room, user=cls.host)
        Membership.objects.create(room=cls.room, user=cls.viewer)

    def test_chat_and_seats_use_same_public_avatar_and_display_name(self):
        Chat.objects.create(room=self.room, user=self.viewer, content='Chào cả phòng 👋')
        self.client.force_login(self.host)
        response = self.client.get(reverse('room_state', args=[self.room.pk]))
        self.assertEqual(response.status_code, 200)
        message = response.json()['messages'][0]
        self.assertEqual(message['display_name'], 'Minh Anh')
        self.assertEqual(message['user'], self.viewer.username)
        self.assertTrue(message['avatar_url'].endswith('/avatars/' + 'a' * 32 + '.webp'))
        seat = next(row for row in response.json()['members'] if row['user_id'] == self.viewer.pk)
        self.assertEqual(message['avatar_url'], seat['avatar_url'])
        self.assertNotContains(response, self.viewer.email)
        self.assertNotIn('password', message)

    def test_only_joined_members_can_read_or_send_chat(self):
        self.client.force_login(self.outsider)
        endpoint = reverse('room_state', args=[self.room.pk])
        self.assertEqual(self.client.get(endpoint).status_code, 404)
        self.assertEqual(self.client.post(endpoint, {'action': 'chat', 'content': 'No access'}).status_code, 404)
        self.assertFalse(Chat.objects.exists())

    def test_chat_preserves_unicode_and_rejects_oversized_messages(self):
        self.client.force_login(self.viewer)
        endpoint = reverse('room_state', args=[self.room.pk])
        response = self.client.post(endpoint, {'action': 'chat', 'content': 'Phim hay quá! 🎬'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['messages'][0]['content'], 'Phim hay quá! 🎬')
        response = self.client.post(endpoint, {'action': 'chat', 'content': 'x' * 501})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Chat.objects.count(), 1)
