from django.contrib.auth.hashers import check_password
from django.test import Client, TestCase
from django.urls import reverse

from .models import Episode, Membership, Movie, Room, RoomJoinRequest, User


class RoomAdmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.host = User.objects.create_user('party-host', 'host@example.test', is_staff=True)
        cls.guest = User.objects.create_user('party-guest', 'guest@example.test')
        cls.other = User.objects.create_user('party-other', 'other@example.test')
        movie = Movie.objects.create(title='Cùng xem phim', slug='cung-xem-phim', published=True)
        cls.episode = Episode.objects.create(movie=movie, title='Tập 1', status='ready', duration=90)

    def setUp(self):
        self.host_client = Client()
        self.host_client.force_login(self.host)
        self.client.force_login(self.guest)

    def make_room(self, password='đèn chiếu 27', approval='on'):
        response = self.host_client.post(reverse('create_room', args=[self.episode.pk]), {
            'name': 'Chiếu cùng bạn', 'password': password, 'requires_approval': approval,
        })
        room = Room.objects.get()
        self.assertRedirects(response, reverse('room', args=[room.pk]))
        return room

    def test_password_and_host_approval_both_gate_room_membership(self):
        room = self.make_room()
        self.assertNotEqual(room.password_hash, 'đèn chiếu 27')
        self.assertTrue(check_password('đèn chiếu 27', room.password_hash))
        join = reverse('join_room', args=[room.pk])
        state = reverse('room_state', args=[room.pk])
        admission = reverse('room_admission', args=[room.pk])
        page = reverse('room', args=[room.pk])
        self.assertEqual(self.client.post(join, {'password': 'sai mật khẩu'}).status_code, 400)
        self.assertFalse(room.join_requests.exists())
        self.assertRedirects(self.client.post(join, {'password': 'đèn chiếu 27'}), page)
        self.assertContains(self.client.get(page), 'Đang chờ chủ phòng duyệt')
        self.assertNotContains(self.client.get(page), 'data-voice=')
        self.assertIn('microphone=()', self.client.get(page).headers['Permissions-Policy'])
        self.assertEqual(self.client.get(state).status_code, 404)
        entry = room.join_requests.get()
        self.assertNotIn('pending', self.client.get(admission).json())
        self.assertEqual(self.client.post(admission, {'action': 'approve', 'request': entry.pk}).status_code, 403)

        queue = self.host_client.get(admission).json()
        self.assertEqual(queue['pending_count'], 1)
        self.assertEqual(queue['pending'][0]['user__username'], self.guest.username)
        self.assertEqual(self.host_client.post(admission, {'action': 'approve', 'request': entry.pk}).status_code, 200)
        self.assertEqual(self.client.get(admission).json()['status'], 'approved')
        self.assertRedirects(self.client.post(join), page)
        self.assertFalse(room.join_requests.exists())
        self.assertIn('microphone=(self)', self.client.get(page).headers['Permissions-Policy'])
        self.assertEqual(self.client.get(state).status_code, 200)

    def test_password_change_invalidates_pending_and_approved_requests(self):
        room = self.make_room(approval='on')
        RoomJoinRequest.objects.create(room=room, user=self.guest, status=RoomJoinRequest.Status.APPROVED)
        RoomJoinRequest.objects.create(room=room, user=self.other)
        endpoint = reverse('room_admission', args=[room.pk])
        response = self.host_client.post(endpoint, {'action': 'settings', 'password': 'mật khẩu mới', 'requires_approval': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(room.join_requests.exists())
        join = reverse('join_room', args=[room.pk])
        self.assertEqual(self.client.post(join, {'password': 'đèn chiếu 27'}).status_code, 400)
        self.assertFalse(room.members.filter(user=self.guest).exists())
        self.client.post(join, {'password': 'mật khẩu mới'})
        self.assertEqual(room.join_requests.get().status, RoomJoinRequest.Status.PENDING)

    def test_rejected_guest_cannot_join_or_view_other_requests(self):
        room = self.make_room(password='', approval='on')
        join = reverse('join_room', args=[room.pk])
        admission = reverse('room_admission', args=[room.pk])
        self.client.post(join)
        entry = room.join_requests.get()
        self.host_client.post(admission, {'action': 'reject', 'request': entry.pk})
        self.assertEqual(self.client.get(admission).json()['status'], 'rejected')
        self.assertEqual(self.client.post(join).status_code, 403)
        self.assertFalse(Membership.objects.filter(room=room, user=self.guest).exists())
        self.client.force_login(self.other)
        self.assertIsNone(self.client.get(admission).json()['status'])
