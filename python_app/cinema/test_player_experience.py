"""Watch and room pages use the same protected caption and seek controls."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Membership, Movie, Room, Subtitle, User


class PlayerPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.host = User.objects.create_user('caption-host', 'caption-host@example.test', vip_until=timezone.now() + timedelta(days=10))
        cls.guest = User.objects.create_user('caption-guest', 'caption-guest@example.test')
        cls.movie = Movie.objects.create(title='Captioned feature', slug='captioned-feature', published=True)
        cls.episode = Episode.objects.create(movie=cls.movie, title='Part 1', status='ready', duration=600)
        cls.track = Subtitle.objects.create(episode=cls.episode, language='vi', label='Tiếng Việt & English', content='WEBVTT\n\n00:00:00.000 --> 00:00:05.000\nHello\n')
        cls.other_episode = Episode.objects.create(movie=cls.movie, number=2, title='Part 2', status='ready', duration=600)
        cls.room = Room.objects.create(host=cls.host, episode=cls.episode, name='Caption room')
        Membership.objects.create(room=cls.room, user=cls.host)
        Membership.objects.create(room=cls.room, user=cls.guest)

    def test_watch_includes_scoped_track_and_caption_picker_without_autoselect(self):
        self.client.force_login(self.host)
        response = self.client.get(reverse('watch', args=[self.episode.pk]))
        self.assertContains(response, reverse('subtitle', args=[self.episode.pk, self.track.pk]))
        self.assertContains(response, 'kind="subtitles"')
        self.assertContains(response, 'srclang="vi"')
        self.assertContains(response, 'Tiếng Việt &amp; English')
        self.assertContains(response, '<option value="off">Tắt phụ đề</option>')
        self.assertContains(response, 'data-can-seek="true"')
        self.assertNotContains(response, '<track default')

    def test_episode_without_tracks_keeps_caption_button_and_explains_empty_state(self):
        self.client.force_login(self.host)
        response = self.client.get(reverse('watch', args=[self.other_episode.pk]))
        self.assertContains(response, 'data-caption-toggle')
        self.assertContains(response, 'Phim chưa có phụ đề')
        self.assertContains(response, 'class="player-subtitles" aria-label="Phụ đề" disabled')
        self.assertContains(response, 'Tạo phụ đề tự động')
        self.assertNotContains(response, reverse('subtitle', args=[self.episode.pk, self.track.pk]))

    def test_host_and_guest_share_captions_but_only_host_seeks_the_room(self):
        for user, can_seek in ((self.host, 'true'), (self.guest, 'false')):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse('room', args=[self.room.pk]))
                self.assertContains(response, f'data-can-seek="{can_seek}"')
                self.assertContains(response, reverse('subtitle', args=[self.episode.pk, self.track.pk]))
                self.assertContains(response, 'player-controls.js')
                self.assertContains(response, 'caption-panel.js')
                self.assertContains(response, 'aria-label="Phụ đề"')

    def test_guest_cannot_bypass_movie_access_through_player_or_caption_url(self):
        self.movie.is_vip = True
        self.movie.save(update_fields=['is_vip'])
        self.client.force_login(self.guest)
        self.assertEqual(self.client.get(reverse('watch', args=[self.episode.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('subtitle', args=[self.episode.pk, self.track.pk])).status_code, 403)
