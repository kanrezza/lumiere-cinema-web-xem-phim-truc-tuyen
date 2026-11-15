from urllib.parse import urlencode

from django.test import TestCase
from django.urls import reverse

from .models import Episode, Movie, Room, User


class AccountNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        host = User.objects.create_user('admin', 'admin@example.test', is_staff=True)
        movie = Movie.objects.create(title='Phim thử', slug='phim-thu', published=True)
        episode = Episode.objects.create(movie=movie, title='Tập thử', status='ready')
        cls.room = Room.objects.create(host=host, episode=episode, name='Phòng được mời')

    @staticmethod
    def signup_details():
        return {
            'username': 'newmember', 'email': 'newmember@example.test',
            'password1': 'Seven-trees-raft-416!', 'password2': 'Seven-trees-raft-416!',
        }

    def test_room_invite_survives_registration_and_validation_retry(self):
        room_url = reverse('room', args=[self.room.pk])
        login_page = self.client.get(room_url, follow=True)
        register_url = reverse('register')
        registration_link = f'{register_url}?{urlencode({"next": room_url})}'
        self.assertContains(login_page, f'href="{registration_link}"')

        registration_page = self.client.get(registration_link)
        hidden_destination = f'<input type="hidden" name="next" value="{room_url}">'
        self.assertContains(registration_page, hidden_destination, html=True)
        details = self.signup_details()
        failed = self.client.post(register_url, {**details, 'password2': 'different', 'next': room_url})
        self.assertContains(failed, hidden_destination, html=True)

        registered = self.client.post(register_url, {**details, 'next': room_url})
        self.assertRedirects(registered, room_url)
        self.assertContains(self.client.get(room_url), self.room.name)

    def test_registration_ignores_external_destination_and_defaults_to_catalog(self):
        register_url = reverse('register')
        external_url = 'https://outside.example/room-invite'
        form = self.client.get(register_url, {'next': external_url})
        self.assertNotContains(form, 'name="next"')
        registered = self.client.post(register_url, {**self.signup_details(), 'next': external_url})
        self.assertRedirects(registered, reverse('catalog'))

