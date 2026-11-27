"""Saved-library filters and batch removal must respect viewing state and ownership."""

from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Actor, Episode, History, Movie, Watchlist


class LibraryToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = get_user_model().objects.create_user('library-owner', 'library-owner@example.invalid')
        cls.other = get_user_model().objects.create_user('library-other', 'library-other@example.invalid')
        cls.preparing = cls.film('Chờ ánh sáng', 'library-preparing', ready=0)
        cls.unwatched = cls.film('Đường chân trời', 'library-unwatched', year=2025)
        cls.progressing = cls.film('Một chuyến đi', 'library-progressing', ready=2, kind='series')
        cls.completed = cls.film('Bến bình yên', 'library-completed', ready=2, year=2024)
        cls.unknown = cls.film('Thời lượng chưa rõ', 'library-unknown', duration=0)
        cls.draft = cls.film('Phim chưa công khai', 'library-draft', published=False)
        cls.foreign = cls.film('Tủ phim khác', 'library-foreign', owner=cls.other)
        cls.vip = cls.film('Phim riêng VIP', 'library-vip', is_vip=True)
        History.objects.create(user=cls.viewer, episode=cls.unwatched.episodes.first(), position=0)
        History.objects.create(user=cls.viewer, episode=cls.progressing.episodes.first(), position=99, hidden_from_continue=True)
        for episode in cls.completed.episodes.all():
            History.objects.create(user=cls.viewer, episode=episode, position=episode.duration - 1)
        History.objects.create(user=cls.viewer, episode=cls.unknown.episodes.first(), position=20)
        History.objects.create(user=cls.viewer, episode=cls.vip.episodes.first(), position=30)
        History.objects.create(user=cls.other, episode=cls.unwatched.episodes.first(), position=100)
        pending = Episode.objects.create(movie=cls.completed, number=3, title='Chưa có bản phát', status='pending', duration=100)
        History.objects.create(user=cls.viewer, episode=pending, position=0)

    @classmethod
    def film(cls, title, slug, *, owner=None, ready=1, duration=100, **values):
        movie = Movie.objects.create(title=title, slug=slug, description='Phim trong tủ.', published=values.pop('published', True), **values)
        Watchlist.objects.create(user=owner or cls.viewer, movie=movie)
        for number in range(1, ready + 1):
            Episode.objects.create(movie=movie, number=number, title=f'Tập {number}', status='ready', duration=duration)
        return movie

    def setUp(self):
        self.client.force_login(self.viewer)

    def library(self, **filters):
        response = self.client.get(reverse('library'), filters)
        self.assertEqual(response.status_code, 200)
        return response

    def test_library_only_contains_the_viewers_public_saved_films(self):
        response = self.library()
        self.assertEqual(response.context['saved_count'], 6)
        ids = {movie.pk for movie in response.context['movies']}
        self.assertNotIn(self.draft.pk, ids)
        self.assertNotIn(self.foreign.pk, ids)
        self.assertContains(response, 'Phim riêng VIP')
        self.assertContains(response, 'Xem với VIP')

    def test_watch_states_require_all_available_episodes_and_keep_preparing_separate(self):
        response = self.library()
        states = {movie.pk: movie.library_state for movie in response.context['movies']}
        self.assertEqual(states[self.preparing.pk], 'preparing')
        self.assertEqual(states[self.unwatched.pk], 'unwatched')
        self.assertEqual(states[self.progressing.pk], 'inprogress')
        self.assertEqual(states[self.unknown.pk], 'inprogress')
        self.assertEqual(states[self.completed.pk], 'completed')
        completed = next(movie for movie in response.context['movies'] if movie.pk == self.completed.pk)
        self.assertEqual((completed.library_ready_count, completed.library_completed_count), (2, 2))
        counts = {tab['key']: tab['count'] for tab in response.context['library_tabs']}
        self.assertEqual(counts, {'all': 6, 'unwatched': 1, 'inprogress': 3, 'completed': 1, 'preparing': 1})

    def test_ready_episode_added_to_a_completed_series_returns_it_to_in_progress(self):
        Episode.objects.create(movie=self.completed, number=4, title='Tập mới', duration=100, status='ready')
        response = self.library(status='completed')
        self.assertNotIn(self.completed.pk, {movie.pk for movie in response.context['movies']})
        response = self.library(status='inprogress')
        self.assertIn(self.completed.pk, {movie.pk for movie in response.context['movies']})

    def test_search_supports_unaccented_vietnamese_and_published_film_actors(self):
        response = self.library(q='DUONG CHAN TROI')
        self.assertEqual([movie.pk for movie in response.context['movies']], [self.unwatched.pk])
        performer = Actor.objects.create(name='Đặng Thành An')
        self.completed.actors.add(performer)
        response = self.library(q='dang thanh an', status='completed')
        self.assertEqual([movie.pk for movie in response.context['movies']], [self.completed.pk])

    def test_saved_title_and_year_sort_have_stable_results(self):
        response = self.library()
        self.assertEqual(response.context['movies'][0].pk, self.vip.pk)
        response = self.library(sort='title')
        titles = [movie.search_title for movie in response.context['movies']]
        self.assertEqual(titles, sorted(titles))
        response = self.library(sort='year')
        years = [movie.year for movie in response.context['movies']]
        self.assertEqual(years, sorted(years, reverse=True))

    def test_pagination_and_state_tabs_preserve_validated_search_filters(self):
        for number in range(26):
            self.film(f'Mùa hạ {number:02}', f'library-page-{number:02}')
        response = self.library(q='mua ha', status='unwatched', sort='title', page='2')
        self.assertEqual(response.context['library_page'].number, 2)
        self.assertEqual(len(response.context['movies']), 2)
        previous = urlsplit(response.context['library_previous'])
        self.assertEqual(parse_qs(previous.query), {'q': ['mua ha'], 'status': ['unwatched'], 'sort': ['title'], 'page': ['1']})
        self.assertEqual(previous.fragment, 'saved-films')
        tab = next(tab for tab in response.context['library_tabs'] if tab['key'] == 'all')
        self.assertEqual(parse_qs(urlsplit(tab['url']).query), {'q': ['mua ha'], 'sort': ['title']})
        self.assertEqual(self.library(page='not-a-page').context['library_page'].number, 1)

    def test_empty_filters_offer_reset_instead_of_claiming_the_library_is_empty(self):
        response = self.library(q='Khong co ten phim nay')
        self.assertContains(response, 'Chưa có phim phù hợp')
        self.assertContains(response, 'Xem tất cả phim đã lưu')
        self.assertNotContains(response, 'Chưa có phim đã lưu')
        Watchlist.objects.filter(user=self.viewer).delete()
        response = self.library()
        self.assertContains(response, 'Chưa có phim đã lưu')

    def test_query_and_invalid_filters_are_bounded_and_normalized(self):
        response = self.library(q='a' * 300, status='secret', sort='invalid')
        self.assertEqual(response.context['library_filters'], {'q': 'a' * 150, 'status': 'all', 'sort': 'saved'})

    def test_bulk_remove_only_deletes_owned_saves_and_retains_viewing_history(self):
        other_copy = Watchlist.objects.create(user=self.other, movie=self.completed)
        response = self.client.post(reverse('library_remove'), {'movies': [self.completed.pk, self.unwatched.pk, self.foreign.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Watchlist.objects.filter(user=self.viewer, movie__in=(self.completed, self.unwatched)).exists())
        self.assertTrue(Watchlist.objects.filter(pk=other_copy.pk).exists())
        self.assertTrue(Watchlist.objects.filter(user=self.other, movie=self.foreign).exists())
        self.assertTrue(History.objects.filter(user=self.viewer, episode__movie=self.completed).exists())

    def test_duplicate_selections_are_removed_once_and_redirects_are_same_origin(self):
        response = self.client.post(reverse('library_remove'), {
            'movies': [self.unwatched.pk, self.unwatched.pk], 'q': 'xin chào & Việt',
            'status': 'completed', 'sort': 'year', 'page': '2', 'next': 'https://example.invalid/phishing',
        })
        location = urlsplit(response['Location'])
        self.assertEqual((location.scheme, location.netloc, location.path), ('', '', reverse('library')))
        self.assertEqual(parse_qs(location.query), {'q': ['xin chào & Việt'], 'status': ['completed'], 'sort': ['year'], 'page': ['2']})
        self.assertEqual(location.fragment, 'saved-films')
        self.assertContains(self.client.get(response['Location']), 'Đã bỏ 1 phim khỏi tủ.')

    def test_bulk_remove_rejects_empty_invalid_huge_and_oversized_selections(self):
        before = Watchlist.objects.count()
        for selected in ([], ['-1'], ['NaN'], ['9223372036854775808'], [str(self.unwatched.pk)] * 101):
            with self.subTest(selected=selected[:2]):
                response = self.client.post(reverse('library_remove'), {'movies': selected})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(Watchlist.objects.count(), before)

    def test_bulk_removal_requires_post_authentication_and_csrf(self):
        endpoint = reverse('library_remove')
        self.assertEqual(self.client.get(endpoint).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.viewer)
        self.assertEqual(strict.post(endpoint, {'movies': [self.unwatched.pk]}).status_code, 403)
        strict.get(reverse('library'))
        self.assertEqual(strict.post(endpoint, {'movies': [self.unwatched.pk]}, HTTP_X_CSRFTOKEN=strict.cookies['csrftoken'].value).status_code, 302)
        anonymous = Client()
        self.assertEqual(anonymous.post(endpoint, {'movies': [self.completed.pk]}).status_code, 302)
        self.assertTrue(Watchlist.objects.filter(user=self.viewer, movie=self.completed).exists())

    def test_erased_accounts_cannot_read_or_remove_saved_films(self):
        get_user_model().objects.filter(pk=self.viewer.pk).update(erased_at=timezone.now())
        self.assertEqual(self.client.get(reverse('library')).status_code, 403)
        self.assertEqual(self.client.post(reverse('library_remove'), {'movies': [self.unwatched.pk]}).status_code, 403)
        self.assertTrue(Watchlist.objects.filter(user=self.viewer, movie=self.unwatched).exists())
