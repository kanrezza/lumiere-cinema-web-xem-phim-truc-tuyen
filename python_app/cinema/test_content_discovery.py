from html import unescape
import re
from urllib.parse import parse_qs, urlsplit

from django.template import Context
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .models import Category, Episode, Movie
from .templatetags.cinema_navigation import country_menu_data, genre_menu_data


class ContentDiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.genre = Category.objects.create(name='Adventure', slug='content-adventure')
        cls.cinema = cls.film('Ready cinema', is_cinema_release=True, trailer_url='https://youtu.be/AbCdEfGhI12')
        Episode.objects.create(movie=cls.cinema, title='Full', status='ready')
        cls.online = cls.film('Ready online')
        Episode.objects.create(movie=cls.online, title='Full', status='ready')
        cls.upcoming = cls.film('Future cinema', is_cinema_release=True, trailer_url='https://youtu.be/AbCdEfGhI12')
        cls.preparing = cls.film('Preparing series', kind='series')
        cls.hidden = cls.film('Hidden cinema', published=False, is_cinema_release=True, trailer_url='https://youtu.be/AbCdEfGhI12')

    @classmethod
    def film(cls, title, **values):
        movie = Movie.objects.create(title=title, slug=title.lower().replace(' ', '-'),
                                     description='Discovery test.', year=2026, country='Việt Nam',
                                     **{'published': True, **values})
        movie.categories.add(cls.genre)
        return movie

    def ids(self, **query):
        response = self.client.get(reverse('catalog'), query)
        self.assertEqual(response.status_code, 200)
        return {movie.pk for movie in response.context['page']}

    def test_cinema_and_video_readiness_are_independent_public_filters(self):
        self.assertEqual(self.ids(release='cinema'), {self.cinema.pk, self.upcoming.pk})
        self.assertEqual(self.ids(availability='ready'), {self.cinema.pk, self.online.pk})
        self.assertEqual(self.ids(availability='upcoming'), {self.upcoming.pk, self.preparing.pk})
        self.assertEqual(self.ids(release='cinema', availability='upcoming', trailer='1', q='Future',
                                  year='2026', country='Việt Nam', category=self.genre.slug), {self.upcoming.pk})
        self.assertEqual(self.ids(trailer='1'), {self.cinema.pk, self.upcoming.pk})

    def test_invalid_content_filters_do_not_expand_results(self):
        for query in ({'release': 'unknown'}, {'availability': 'unknown'}, {'trailer': 'true'}):
            with self.subTest(query=query):
                self.assertEqual(self.ids(**query), set())

    def test_content_links_toggle_one_filter_and_keep_other_conditions(self):
        query = {'q': 'Future', 'year': '2026', 'release': 'cinema', 'availability': 'upcoming', 'trailer': '1', 'page': '4'}
        response = self.client.get(reverse('catalog'), query)
        links = {item['label']: item for item in response.context['content_links']}
        self.assertTrue(links['Phim chiếu rạp']['active'])
        cinema = parse_qs(urlsplit(links['Phim chiếu rạp']['href']).query)
        self.assertEqual(cinema, {'q': ['Future'], 'year': ['2026'], 'availability': ['upcoming'], 'trailer': ['1']})
        ready = parse_qs(urlsplit(links['Đã có phim']['href']).query)
        self.assertEqual(ready['availability'], ['ready'])
        self.assertEqual(ready['release'], ['cinema'])
        cleared = parse_qs(urlsplit(links['Tất cả']['href']).query)
        self.assertEqual(cleared, {'q': ['Future'], 'year': ['2026']})

    def test_pagination_keeps_content_filters(self):
        for number in range(14):
            self.film(f'Future extra {number}', is_cinema_release=True, trailer_url='https://youtu.be/AbCdEfGhI12')
        query = {'q': 'Future', 'year': '2026', 'release': 'cinema', 'availability': 'upcoming', 'trailer': '1'}
        response = self.client.get(reverse('catalog'), query)
        self.assertEqual(response.context['page'].paginator.count, 15)
        match = re.search(r'href="([^"]+)"[^>]*>Tiếp</a>', response.content.decode())
        self.assertIsNotNone(match)
        href = unescape(match.group(1))
        self.assertEqual(parse_qs(urlsplit(href).query), {key: [value] for key, value in {**query, 'page': '2'}.items()})
        following = self.client.get(reverse('catalog') + href)
        self.assertEqual(len(following.context['page']), 3)

    def test_navigation_and_legacy_bookmarks_keep_content_filters(self):
        query = {'year': '2026', 'release': 'cinema', 'availability': 'upcoming', 'trailer': '1', 'page': '3'}
        request = RequestFactory().get(reverse('catalog'), query)
        for items in (genre_menu_data(Context({'request': request})), country_menu_data(Context({'request': request}))):
            self.assertTrue(items)
            for item in items:
                params = parse_qs(urlsplit(item['href']).query)
                for key in ('year', 'release', 'availability', 'trailer'):
                    self.assertEqual(params[key], [query[key]])
                self.assertNotIn('page', params)
        response = self.client.get(reverse('landing'), {'trailer': '1'})
        self.assertRedirects(response, reverse('catalog') + '?trailer=1', fetch_redirect_response=False)
