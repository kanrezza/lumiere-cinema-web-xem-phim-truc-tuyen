"""Independent acceptance cases added during the 2026-11-05 product audit.

Only isolated Django test data and a temporary private media directory are used.
Case IDs are stable references for reports/audit_backend_results.json.
Run explicitly as cinema.audit_experience_cases. This historical audit suite is
kept separately for repeatable comparisons; search regressions also belong to
the regular test_search suite after their fixes.
"""

import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Actor, Comment, Episode, History, Membership, Movie, Rating, Report, Room, Watchlist


class ExperienceAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.viewer = users.objects.create_user('audit-viewer', 'audit-viewer@example.test')
        cls.other = users.objects.create_user('audit-other', 'audit-other@example.test')
        cls.host = users.objects.create_user(
            'audit-host', 'audit-host@example.test', vip_until=timezone.now() + timedelta(days=30),
        )
        cls.movie = Movie.objects.create(
            title='Mùa hè năm ấy', slug='audit-summer', description='Một câu chuyện mùa hè.', published=True,
        )
        cls.episode = Episode.objects.create(movie=cls.movie, title='Phim đầy đủ', status='ready', duration=600)
        cls.draft = Movie.objects.create(title='Private audit title', slug='audit-draft', published=False)
        cls.draft_episode = Episode.objects.create(movie=cls.draft, title='Private episode', status='ready', duration=600)
        cls.actor = Actor.objects.create(name='Đỗ Hải Yến')
        cls.movie.actors.add(cls.actor)

    def setUp(self):
        cache.clear()

    def test_audit_01_vietnamese_movie_search_is_case_insensitive(self):
        """An uppercase accented query must find the same Vietnamese movie."""
        for query in ('Mùa hè', 'MÙA HÈ'):
            with self.subTest(query=query):
                response = self.client.get(reverse('catalog'), {'q': query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([film.pk for film in response.context['page']], [self.movie.pk])

    def test_audit_02_vietnamese_actor_search_is_case_insensitive(self):
        """The public actor directory must handle accented upper/lowercase."""
        for query in ('Đỗ Hải', 'ĐỖ HẢI'):
            with self.subTest(query=query):
                response = self.client.get(reverse('actors'), {'q': query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([actor.pk for actor in response.context['actors']], [self.actor.pk])

    def test_audit_03_users_cannot_delete_someone_elses_comment(self):
        comment = Comment.objects.create(user=self.other, movie=self.movie, content='Other viewer comment')
        self.client.force_login(self.viewer)
        response = self.client.post(reverse('delete_comment', args=[comment.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Comment.objects.filter(pk=comment.pk).exists())
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('delete_comment', args=[comment.pk])).status_code, 302)
        self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())

    def test_audit_04_clear_history_only_changes_the_current_user(self):
        History.objects.create(user=self.viewer, episode=self.episode, position=150)
        History.objects.create(user=self.other, episode=self.episode, position=300)
        Watchlist.objects.create(user=self.viewer, movie=self.movie)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('clear_history')).status_code, 405)
        self.assertEqual(History.objects.count(), 2)
        self.assertEqual(self.client.post(reverse('clear_history')).status_code, 302)
        self.assertFalse(History.objects.filter(user=self.viewer).exists())
        self.assertTrue(History.objects.filter(user=self.other, position=300).exists())
        self.assertTrue(Watchlist.objects.filter(user=self.viewer, movie=self.movie).exists())

    def test_audit_05_draft_film_ids_cannot_be_used_to_mutate_public_features(self):
        self.client.force_login(self.viewer)
        cases = (
            ('save', self.draft.pk, {}), ('comment', self.draft.pk, {'content': 'Hidden comment'}),
            ('rate', self.draft.pk, {'score': 5}),
            ('report', self.draft_episode.pk, {'description': 'Private report'}),
            ('progress', self.draft_episode.pk, {'position': 100}),
            ('ticket', self.draft_episode.pk, {}),
        )
        for route, pk, payload in cases:
            with self.subTest(route=route):
                self.assertIn(self.client.post(reverse(route, args=[pk]), payload).status_code, (403, 404))
        for model in (Watchlist, Comment, Rating, Report, History):
            self.assertEqual(model.objects.count(), 0)

    def test_audit_06_progress_accepts_boundaries_and_keeps_one_private_record(self):
        History.objects.create(user=self.other, episode=self.episode, position=50)
        self.client.force_login(self.viewer)
        for position in (0, 600, 600.5):
            with self.subTest(position=position):
                response = self.client.post(reverse('progress', args=[self.episode.pk]), {'position': position})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(History.objects.get(user=self.viewer, episode=self.episode).position, position)
                self.assertEqual(History.objects.filter(user=self.viewer).count(), 1)
        self.assertEqual(History.objects.get(user=self.other).position, 50)
        self.assertEqual(self.client.post(reverse('progress', args=[self.episode.pk]), {'position': 601.01}).status_code, 400)
        self.assertEqual(History.objects.get(user=self.viewer).position, 600.5)

    def test_audit_07_unready_episode_cannot_receive_progress_or_stream_tickets(self):
        self.episode.status = 'processing'
        self.episode.save(update_fields=['status'])
        self.client.force_login(self.viewer)
        for route in ('progress', 'ticket'):
            with self.subTest(route=route):
                response = self.client.post(reverse(route, args=[self.episode.pk]), {'position': 100})
                self.assertEqual(response.status_code, 403)
        self.assertFalse(History.objects.exists())

    def test_audit_08_logout_then_relogin_revokes_an_old_stream_ticket(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_MEDIA_ROOT=Path(directory)):
            folder = Path(directory) / 'hls' / str(self.episode.asset_id)
            folder.mkdir(parents=True)
            (folder / 'index.m3u8').write_text('#EXTM3U\n#EXT-X-ENDLIST\n')
            self.client.force_login(self.viewer)
            ticket_url = self.client.post(reverse('ticket', args=[self.episode.pk])).json()['url']
            self.assertEqual(self.client.get(ticket_url).status_code, 200)
            self.client.logout()
            self.client.force_login(self.viewer)
            self.assertEqual(self.client.get(ticket_url).status_code, 403)

    def test_audit_09_rejoining_same_room_is_idempotent(self):
        room = Room.objects.create(host=self.host, episode=self.episode, name='Audit room')
        Membership.objects.create(room=room, user=self.host)
        self.client.force_login(self.viewer)
        for _ in range(2):
            self.assertEqual(self.client.post(reverse('join_room', args=[room.pk])).status_code, 302)
        self.assertEqual(Membership.objects.filter(room=room, user=self.viewer).count(), 1)
        self.assertEqual(self.client.get(reverse('room_state', args=[room.pk])).status_code, 200)

    def test_audit_10_expired_room_denies_page_join_and_state(self):
        room = Room.objects.create(host=self.host, episode=self.episode, name='Expired room')
        Membership.objects.create(room=room, user=self.viewer)
        Room.objects.filter(pk=room.pk).update(created_at=timezone.now() - timedelta(hours=7))
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('room', args=[room.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('join_room', args=[room.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('room_state', args=[room.pk])).status_code, 404)

    def test_audit_11_repeated_rating_updates_instead_of_inflating_score(self):
        self.client.force_login(self.viewer)
        endpoint = reverse('rate', args=[self.movie.pk])
        for score in (3, 5, 5):
            self.assertEqual(self.client.post(endpoint, {'score': score}).status_code, 302)
        self.assertEqual(Rating.objects.filter(user=self.viewer, movie=self.movie).count(), 1)
        self.assertEqual(Rating.objects.get(user=self.viewer, movie=self.movie).score, 5)

    def test_audit_12_guest_protected_route_returns_to_exact_episode_after_login(self):
        endpoint = reverse('watch', args=[self.episode.pk])
        self.assertRedirects(self.client.get(endpoint), reverse('login') + '?next=' + endpoint, fetch_redirect_response=False)
        self.assertFalse(History.objects.exists())
