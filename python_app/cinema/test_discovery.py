from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Actor, Category, Episode, Movie, Rating


class DiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = get_user_model().objects.create_user(
            'discovery-viewer', 'discovery-viewer@example.test', 'Discovery-test-password-57!'
        )
        cls.drama = Category.objects.create(name='Tâm lý', slug='tam-ly')
        cls.comedy = Category.objects.create(name='Hài hước', slug='hai-huoc')
        cls.private_genre = Category.objects.create(name='Private genre', slug='private-genre')
        cls.actor = Actor.objects.create(name='An Performer', bio='An existing performer biography.')
        cls.other_actor = Actor.objects.create(name='Binh Performer')
        cls.private_actor = Actor.objects.create(name='Private Performer')
        cls.first = Movie.objects.create(
            title='Journey A', slug='discovery-first', description='A journey film',
            country='Việt Nam', published=True,
        )
        cls.second = Movie.objects.create(
            title='Journey B', slug='discovery-second', description='Another journey film',
            country=' VIỆT NAM ', published=True,
        )
        cls.foreign = Movie.objects.create(
            title='Journey Abroad', slug='discovery-foreign', description='A journey abroad',
            country='Hoa Kỳ', published=True,
        )
        cls.series = Movie.objects.create(
            title='Journey Series', slug='discovery-series', description='A journey series',
            country='Việt Nam', kind='series', published=True,
        )
        cls.blank_country = Movie.objects.create(
            title='A country-free comedy', slug='discovery-blank', description='Comedy',
            country='   ', published=True,
        )
        cls.hidden = Movie.objects.create(
            title='Private discovery film', slug='discovery-private', description='Private film',
            country='Thái Lan', published=False,
        )
        for film in (cls.first, cls.second, cls.foreign, cls.series):
            film.categories.add(cls.drama)
        cls.blank_country.categories.add(cls.comedy)
        cls.hidden.categories.add(cls.private_genre)
        for film in (cls.first, cls.second, cls.series):
            film.actors.add(cls.actor)
        cls.foreign.actors.add(cls.other_actor)
        cls.hidden.actors.add(cls.private_actor)
        cls.episode = Episode.objects.create(
            movie=cls.first, title='A playable film', status='ready', duration=596,
        )
        Episode.objects.create(movie=cls.second, title='Another film', status='ready', duration=300)
        Episode.objects.create(movie=cls.hidden, title='Private episode', status='ready', duration=600)
        Rating.objects.create(movie=cls.first, user=cls.viewer, score=5)
        Rating.objects.create(movie=cls.second, user=cls.viewer, score=3)

    def test_directories_count_published_data_and_merge_country_variants(self):
        response = self.client.get(reverse('countries'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cinema/discovery_index.html')
        self.assertEqual(response.context['discovery_kind'], 'countries')
        countries = {item['name']: item for item in response.context['items']}
        self.assertEqual(set(countries), {'Việt Nam', 'Hoa Kỳ'})
        self.assertEqual(countries['Việt Nam']['count'], 3)
        country_page = self.client.get(countries['Việt Nam']['href'])
        self.assertEqual(country_page.context['page'].paginator.count, 3)

        response = self.client.get(reverse('categories'))
        self.assertEqual(response.context['discovery_kind'], 'categories')
        genres = {item['name']: item for item in response.context['items']}
        self.assertEqual({name: item['count'] for name, item in genres.items()}, {'Tâm lý': 4, 'Hài hước': 1})
        self.assertNotContains(response, 'Private genre')
        genre_page = self.client.get(genres['Tâm lý']['href'])
        self.assertEqual(genre_page.context['page'].paginator.count, 4)

    def test_country_and_genre_directory_search_is_based_on_real_names(self):
        response = self.client.get(reverse('countries'), {'q': 'viỆT'})
        self.assertEqual([item['name'] for item in response.context['items']], ['Việt Nam'])
        self.assertEqual(response.context['total_count'], 2)
        response = self.client.get(reverse('categories'), {'q': 'hài'})
        self.assertEqual([item['name'] for item in response.context['items']], ['Hài hước'])

    def test_combined_country_actor_category_kind_and_rating_filters(self):
        response = self.client.get(reverse('catalog'), {
            'country': '  việt nam ', 'actor': self.actor.pk, 'category': self.drama.slug,
            'kind': 'movie', 'q': 'Journey', 'sort': 'rating',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_browsing'])
        self.assertEqual([movie.pk for movie in response.context['page']], [self.first.pk, self.second.pk])
        self.assertEqual(response.context['selected_country'], 'Việt Nam')
        self.assertEqual(response.context['selected_actor'].pk, self.actor.pk)
        self.assertEqual(response.context['selected_category'].pk, self.drama.pk)
        self.assertEqual(response.context['actor_filter'], str(self.actor.pk))
        self.assertNotIn('Thái Lan', [country['name'] for country in response.context['countries']])
        self.assertEqual(response.context['shelves'], [])

    def test_unknown_and_invalid_actor_or_country_filters_return_an_empty_result(self):
        for value in ('invalid', '-1', '9' * 50, str(self.private_actor.pk)):
            with self.subTest(actor=value):
                response = self.client.get(reverse('catalog'), {'actor': value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['page'].paginator.count, 0)
                self.assertIsNone(response.context['selected_actor'])
        response = self.client.get(reverse('catalog'), {'country': 'Thái Lan'})
        self.assertEqual(response.context['page'].paginator.count, 0)

    def test_actor_pages_hide_draft_only_people_and_use_playable_movie_metadata(self):
        response = self.client.get(reverse('actors'))
        people = {actor.pk: actor for actor in response.context['actors']}
        self.assertEqual(set(people), {self.actor.pk, self.other_actor.pk})
        self.assertEqual(people[self.actor.pk].film_count, 3)
        response = self.client.get(reverse('actors'), {'q': 'An Performer'})
        self.assertEqual([actor.pk for actor in response.context['actors']], [self.actor.pk])
        response = self.client.get(reverse('actor', args=[self.actor.pk]))
        films = {film.pk: film for film in response.context['movies']}
        self.assertEqual(set(films), {self.first.pk, self.second.pk, self.series.pk})
        self.assertEqual(films[self.first.pk].ready_episode_id, self.episode.pk)
        self.assertEqual(films[self.first.pk].duration_minutes, 10)
        self.assertEqual(self.client.get(reverse('actor', args=[self.private_actor.pk])).status_code, 404)

    def test_country_and_actor_filter_state_survives_pagination(self):
        for number in range(13):
            film = Movie.objects.create(
                title=f'Journey extra {number}', slug=f'discovery-page-{number}',
                description='A journey film', country='Việt Nam', published=True,
            )
            film.categories.add(self.drama)
            film.actors.add(self.actor)
        response = self.client.get(reverse('catalog'), {
            'country': 'Việt Nam', 'actor': self.actor.pk, 'category': self.drama.slug,
            'kind': 'movie', 'q': 'Journey', 'sort': 'rating', 'page': 2,
        })
        self.assertEqual(response.context['page'].number, 2)
        self.assertEqual(response.context['page'].paginator.count, 15)
        self.assertEqual(len(response.context['page']), 3)
        self.assertEqual(response.context['selected_country'], 'Việt Nam')
        self.assertEqual(response.context['actor_filter'], str(self.actor.pk))
        self.assertTrue(all(movie.country.strip().casefold() == 'việt nam' for movie in response.context['page']))

    def test_old_country_and_actor_home_bookmarks_redirect_to_catalog(self):
        query = {'country': 'Việt Nam', 'actor': str(self.actor.pk)}
        response = self.client.get(reverse('landing'), query)
        self.assertRedirects(response, reverse('catalog') + '?' + urlencode(query), fetch_redirect_response=False)
