"""Personal discovery stays explainable, scoped and limited to playable films."""

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import Actor, Category, Episode, History, Movie, Rating, User, Watchlist
from .recommendations import recommendation_shelf


class PersonalDiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_user('discovery-viewer', 'discovery-viewer@example.test')
        cls.other = User.objects.create_user('discovery-other', 'discovery-other@example.test')
        cls.comedy = Category.objects.create(name='Hài hước', slug='discovery-comedy')
        cls.adventure = Category.objects.create(name='Phiêu lưu', slug='discovery-adventure')
        cls.actor = Actor.objects.create(name='Diễn viên khám phá')
        cls.seed = cls.film('Bộ phim đã lưu', 'discovery-seed', categories=[cls.comedy], actors=[cls.actor])
        cls.genre_match = cls.film('Phim hợp thể loại', 'discovery-genre', categories=[cls.comedy], country='Nhật Bản')
        cls.actor_match = cls.film('Phim có diễn viên chung', 'discovery-actor', actors=[cls.actor], country='Hoa Kỳ')
        cls.country_match = cls.film('Phim cùng quốc gia', 'discovery-country')
        cls.unrelated = cls.film('Phim khác sở thích', 'discovery-unrelated', categories=[cls.adventure], country='Pháp')

    @classmethod
    def film(cls, title, slug, *, categories=(), actors=(), country='Việt Nam', ready=True, published=True):
        movie = Movie.objects.create(title=title, slug=slug, country=country, published=published)
        movie.categories.add(*categories)
        movie.actors.add(*actors)
        Episode.objects.create(movie=movie, number=1, title='Bản đầy đủ', status='ready' if ready else 'pending', duration=120)
        return movie

    def save_seed(self, user=None):
        return Watchlist.objects.create(user=user or self.viewer, movie=self.seed)

    def results(self, user=None):
        shelf = recommendation_shelf(user or self.viewer)
        return shelf, [movie.pk for movie in shelf['movies']] if shelf else []

    def test_guests_inactive_erased_and_cold_start_viewers_have_no_personal_shelf(self):
        with self.assertNumQueries(0):
            self.assertIsNone(recommendation_shelf(AnonymousUser()))
        self.save_seed(self.other)
        self.assertIsNone(recommendation_shelf(self.viewer))
        for overrides in ({'is_active': False}, {'erased_at': timezone.now()}):
            with self.subTest(overrides=overrides):
                user = User.objects.get(pk=self.other.pk)
                for key, value in overrides.items():
                    setattr(user, key, value)
                with self.assertNumQueries(0):
                    self.assertIsNone(recommendation_shelf(user))

    def test_saved_tastes_rank_genres_before_actors_then_country_and_explain_the_source(self):
        self.save_seed()
        shelf, ids = self.results()
        self.assertEqual(ids, [self.genre_match.pk, self.actor_match.pk, self.country_match.pk])
        self.assertNotIn(self.seed.pk, ids)
        self.assertNotIn(self.unrelated.pk, ids)
        self.assertTrue(shelf['personalized'])
        self.assertIsNone(shelf['href'])
        self.assertIn('Cùng thể loại', shelf['movies'][0].recommendation_reason)
        self.assertIn('Bộ phim đã lưu', shelf['movies'][0].recommendation_reason)
        self.assertIn('trong tủ phim của bạn', shelf['movies'][0].recommendation_reason)
        self.assertIn('Có diễn viên chung', shelf['movies'][1].recommendation_reason)
        self.assertIn('Cùng quốc gia', shelf['movies'][2].recommendation_reason)
        self.assertIsNotNone(shelf['movies'][0].ready_episode_id)
        self.assertTrue(hasattr(shelf['movies'][0], 'resume_episode_id'))

    def test_real_positive_ratings_and_viewing_progress_can_supply_seeds(self):
        Rating.objects.create(user=self.viewer, movie=self.seed, score=5)
        shelf, ids = self.results()
        self.assertIn(self.genre_match.pk, ids)
        self.assertIn('bạn đã đánh giá cao', shelf['movies'][0].recommendation_reason)
        Rating.objects.filter(user=self.viewer).delete()
        History.objects.create(user=self.viewer, episode=self.seed.episodes.get(), position=40)
        shelf, ids = self.results()
        self.assertIn(self.genre_match.pk, ids)
        self.assertIn('bạn đã xem', shelf['movies'][0].recommendation_reason)

    def test_hidden_zero_position_other_user_and_unpublished_histories_do_not_seed_taste(self):
        draft = self.film('Tên riêng chưa công bố', 'discovery-draft-seed', published=False)
        for episode, owner, position, hidden in (
            (self.seed.episodes.get(), self.viewer, 0, False),
            (self.genre_match.episodes.get(), self.viewer, 50, True),
            (self.actor_match.episodes.get(), self.other, 50, False),
            (draft.episodes.get(), self.viewer, 50, False),
        ):
            History.objects.create(user=owner, episode=episode, position=position, hidden_from_continue=hidden)
        self.assertIsNone(recommendation_shelf(self.viewer))
        Watchlist.objects.create(user=self.viewer, movie=draft)
        Rating.objects.create(user=self.viewer, movie=draft, score=5)
        self.assertIsNone(recommendation_shelf(self.viewer))

    def test_draft_unready_and_disliked_candidates_are_excluded_without_leaking_names(self):
        self.save_seed()
        draft = self.film('Tên bản nháp không công khai', 'discovery-draft', categories=[self.comedy], published=False)
        preparing = self.film('Đang chuyển mã', 'discovery-pending', categories=[self.comedy], ready=False)
        Rating.objects.create(user=self.viewer, movie=self.genre_match, score=2)
        shelf, ids = self.results()
        self.assertNotIn(draft.pk, ids)
        self.assertNotIn(preparing.pk, ids)
        self.assertNotIn(self.genre_match.pk, ids)
        self.assertNotIn('Tên bản nháp', repr(shelf))
        # Another viewer's dislike must not suppress our recommendations.
        Rating.objects.create(user=self.other, movie=self.actor_match, score=1)
        self.assertIn(self.actor_match.pk, self.results()[1])

    def test_a_disliked_saved_film_does_not_supply_taste(self):
        self.save_seed()
        Rating.objects.create(user=self.viewer, movie=self.seed, score=1)
        self.assertIsNone(recommendation_shelf(self.viewer))

    def test_fully_finished_series_is_excluded_until_another_episode_is_ready(self):
        self.save_seed()
        first = self.genre_match.episodes.get()
        second = Episode.objects.create(movie=self.genre_match, number=2, title='Tập 2', status='ready', duration=100)
        History.objects.create(user=self.viewer, episode=first, position=119, hidden_from_continue=True)
        # One completed episode is not a completed series.
        self.assertIn(self.genre_match.pk, self.results()[1])
        History.objects.create(user=self.viewer, episode=second, position=99, hidden_from_continue=True)
        self.assertNotIn(self.genre_match.pk, self.results()[1])
        Episode.objects.create(movie=self.genre_match, number=3, title='Tập 3', status='ready', duration=100)
        self.assertIn(self.genre_match.pk, self.results()[1])

    def test_unknown_duration_and_another_viewers_finished_history_do_not_hide_a_film(self):
        self.save_seed()
        episode = self.genre_match.episodes.get()
        History.objects.create(user=self.other, episode=episode, position=120)
        self.assertIn(self.genre_match.pk, self.results()[1])
        episode.duration = 0
        episode.save(update_fields=['duration'])
        History.objects.create(user=self.viewer, episode=episode, position=120, hidden_from_continue=True)
        self.assertIn(self.genre_match.pk, self.results()[1])

    def test_zero_progress_on_a_short_episode_does_not_count_as_finished(self):
        self.save_seed()
        episode = self.genre_match.episodes.get()
        entry = History.objects.create(user=self.viewer, episode=episode, position=0, hidden_from_continue=True)
        for duration in (0.5, 1):
            with self.subTest(duration=duration):
                Episode.objects.filter(pk=episode.pk).update(duration=duration)
                self.assertIn(self.genre_match.pk, self.results()[1])
        entry.position = 0.5
        entry.save(update_fields=['position'])
        self.assertNotIn(self.genre_match.pk, self.results()[1])

    def test_results_are_deterministic_and_limits_are_capped(self):
        self.save_seed()
        for number in range(20):
            self.film(f'Hài hước {number}', f'discovery-limit-{number}', categories=[self.comedy])
        first = [film.pk for film in recommendation_shelf(self.viewer, limit=999)['movies']]
        second = [film.pk for film in recommendation_shelf(self.viewer, limit=999)['movies']]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 12)
        self.assertEqual(len(recommendation_shelf(self.viewer, limit=2)['movies']), 2)

    def test_query_count_does_not_grow_per_recommended_movie_or_reason(self):
        self.save_seed()
        for number in range(15):
            self.film(f'Đề xuất {number}', f'discovery-queries-{number}', categories=[self.comedy], actors=[self.actor])
        with CaptureQueriesContext(connection) as queries:
            shelf = recommendation_shelf(self.viewer, limit=12)
            for film in shelf['movies']:
                self.assertTrue(film.recommendation_reason)
                list(film.categories.all())
                list(film.actors.all())
        self.assertLessEqual(len(queries), 9)

    def test_unfiltered_catalog_includes_the_personal_shelf_and_filtered_catalog_does_not(self):
        self.save_seed()
        self.client.force_login(self.viewer)
        page = self.client.get(reverse('catalog'))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['shelves'][0]['title'], 'Dành cho bạn')
        self.assertEqual([movie.pk for movie in page.context['shelves'][0]['movies']], self.results()[1])
        search = self.client.get(reverse('catalog'), {'q': 'Phim'})
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.context['shelves'], [])
        self.client.logout()
        guest = self.client.get(reverse('catalog'))
        self.assertNotIn('Dành cho bạn', [shelf['title'] for shelf in guest.context['shelves']])

    def test_vip_card_does_not_grant_a_free_viewer_playback(self):
        self.save_seed()
        Movie.objects.filter(pk=self.genre_match.pk).update(is_vip=True)
        shelf, ids = self.results()
        self.assertIn(self.genre_match.pk, ids)
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('watch', args=[self.genre_match.episodes.get().pk]))
        self.assertEqual(response.status_code, 403)
