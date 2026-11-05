from urllib.parse import parse_qs, urlsplit

from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .models import Category, Movie
from .templatetags.cinema_navigation import country_menu_data, genre_menu_data


class GenreNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.comedy = Category.objects.create(name='Hài hước', slug='hai-huoc')
        cls.drama = Category.objects.create(name='Tâm lý', slug='tam-ly')
        cls.private = Category.objects.create(name='Private genre', slug='private-genre')
        Category.objects.create(name='Empty genre', slug='empty-genre')
        first = Movie.objects.create(title='First public film', slug='nav-public-one', description='Film', published=True)
        second = Movie.objects.create(title='Second public film', slug='nav-public-two', description='Film', published=True)
        hidden = Movie.objects.create(title='A private film', slug='nav-private', description='Film', published=False)
        first.categories.add(cls.comedy, cls.drama)
        second.categories.add(cls.drama)
        hidden.categories.add(cls.drama, cls.private)

    def test_dropdown_contains_only_published_genres_and_real_counts_in_one_query(self):
        request = RequestFactory().get(reverse('catalog'))
        with self.assertNumQueries(1):
            genres = genre_menu_data(Context({'request': request}))
        self.assertEqual([genre['name'] for genre in genres], ['Hài hước', 'Tâm lý'])
        self.assertEqual([genre['count'] for genre in genres], [1, 2])
        self.assertEqual([genre['slug'] for genre in genres], ['hai-huoc', 'tam-ly'])
        self.assertEqual(parse_qs(urlsplit(genres[0]['href']).query), {'category': ['hai-huoc']})

    def test_changing_genre_keeps_catalog_filters_but_resets_page_and_unrelated_parameters(self):
        request = RequestFactory().get(reverse('catalog'), {
            'q': 'A & B', 'country': 'Việt Nam', 'actor': '7', 'kind': 'movie',
            'sort': 'rating', 'access': 'vip', 'category': 'old-genre', 'page': '4',
            'next': 'https://example.invalid/', 'token': 'not-for-navigation',
        })
        for genre in genre_menu_data(Context({'request': request})):
            parts = urlsplit(genre['href'])
            self.assertEqual(parts.path, reverse('catalog'))
            self.assertEqual(parse_qs(parts.query), {
                'q': ['A & B'], 'country': ['Việt Nam'], 'actor': ['7'], 'kind': ['movie'],
                'sort': ['rating'], 'access': ['vip'], 'category': [genre['slug']],
            })

    def test_non_catalog_search_does_not_become_a_movie_filter_and_tag_is_template_usable(self):
        request = RequestFactory().get(reverse('actors'), {'q': 'An actor', 'page': 3})
        genres = genre_menu_data(Context({'request': request}))
        self.assertEqual(parse_qs(urlsplit(genres[0]['href']).query), {'category': ['hai-huoc']})
        rendered = Template(
            '{% load cinema_navigation %}{% genre_menu_data as genres %}'
            '{% for genre in genres %}{{ genre.name }}:{{ genre.count }};{% endfor %}'
        ).render(Context({'request': request}))
        self.assertEqual(rendered, 'Hài hước:1;Tâm lý:2;')
        self.assertEqual(len(genre_menu_data(Context())), 2)


class CountryNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for title, country, published in (
            ('First local film', 'Việt Nam', True),
            ('Second local film', ' VIỆT NAM ', True),
            ('An overseas film', 'Hà Lan', True),
            ('No country yet', '  ', True),
            ('Draft film', 'Thái Lan', False),
            ('Draft local film', 'Việt Nam', False),
        ):
            Movie.objects.create(title=title, slug=title.lower().replace(' ', '-'),
                                 description='Film', country=country, published=published)

    def test_countries_merge_variants_count_published_films_and_ignore_private_or_blank(self):
        request = RequestFactory().get(reverse('catalog'), {'country': ' viỆt nAm '})
        with self.assertNumQueries(1):
            countries = country_menu_data(Context({'request': request}))
        by_name = {country['name']: country for country in countries}
        self.assertEqual(set(by_name), {'Việt Nam', 'Hà Lan'})
        self.assertEqual(by_name['Việt Nam']['count'], 2)
        self.assertEqual(by_name['Hà Lan']['count'], 1)
        self.assertTrue(by_name['Việt Nam']['selected'])
        self.assertFalse(by_name['Hà Lan']['selected'])

    def test_country_selection_keeps_other_catalog_filters_and_resets_page(self):
        request = RequestFactory().get(reverse('catalog'), {
            'q': 'A & B', 'category': 'hoat-hinh', 'actor': '12', 'kind': 'movie',
            'sort': 'rating', 'access': 'vip', 'country': 'Old country', 'page': '3',
            'next': 'https://example.invalid/', 'token': 'not-for-navigation',
        })
        for country in country_menu_data(Context({'request': request})):
            parts = urlsplit(country['href'])
            self.assertEqual(parts.path, reverse('catalog'))
            self.assertEqual(parse_qs(parts.query), {
                'q': ['A & B'], 'category': ['hoat-hinh'], 'actor': ['12'],
                'kind': ['movie'], 'sort': ['rating'], 'access': ['vip'],
                'country': [country['name']],
            })

    def test_country_tag_is_template_usable_and_does_not_copy_non_catalog_search(self):
        request = RequestFactory().get(reverse('countries'), {'q': 'Hà', 'page': 2})
        countries = country_menu_data(Context({'request': request}))
        for country in countries:
            self.assertEqual(parse_qs(urlsplit(country['href']).query), {'country': [country['name']]})
        rendered = Template(
            '{% load cinema_navigation %}{% country_menu_data as countries %}'
            '{% for country in countries %}{{ country.name }}:{{ country.count }};{% endfor %}'
        ).render(Context({'request': request}))
        self.assertEqual(rendered, 'Hà Lan:1;Việt Nam:2;')
        self.assertEqual(len(country_menu_data(Context())), 2)
