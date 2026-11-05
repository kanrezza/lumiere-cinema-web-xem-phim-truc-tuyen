"""Acceptance coverage for release-year discovery and filter navigation."""

from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from django.contrib.auth import get_user_model
from django.template import Context
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .models import Actor, Category, Movie, Rating
from .templatetags.cinema_navigation import country_menu_data, genre_menu_data


class CatalogLinksAndOptions(HTMLParser):
    """Read visible control semantics without coupling tests to CSS/layout."""

    def __init__(self, html):
        super().__init__()
        self.links = []
        self.selects = {}
        self._select = None
        self._option = None
        self._link = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self._link = {'href': attrs.get('href', ''), 'text': ''}
            self.links.append(self._link)
        elif tag == 'select':
            self._select = attrs.get('name')
            self.selects[self._select] = []
        elif tag == 'option' and self._select is not None:
            self._option = {'value': attrs.get('value', ''), 'selected': 'selected' in attrs, 'text': ''}
            self.selects[self._select].append(self._option)

    def handle_data(self, data):
        if self._link is not None:
            self._link['text'] += data
        if self._option is not None:
            self._option['text'] += data

    def handle_endtag(self, tag):
        if tag == 'a':
            self._link = None
        elif tag == 'option':
            self._option = None
        elif tag == 'select':
            self._select = None


class YearFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.genre = Category.objects.create(name='Adventure', slug='year-adventure')
        cls.other_genre = Category.objects.create(name='Comedy', slug='year-comedy')
        cls.actor = Actor.objects.create(name='Alex Performer')
        cls.other_actor = Actor.objects.create(name='Blair Performer')
        cls.viewer = get_user_model().objects.create_user('year-viewer', 'year-viewer@example.test')
        cls.high = cls.make_film('Journey High', score=5)
        cls.low = cls.make_film('Journey Low', score=3)
        cls.previous = cls.make_film('Journey Previous', year=2025, score=5)
        cls.foreign = cls.make_film('Journey Foreign', country='Japan')
        cls.series = cls.make_film('Journey Series', kind='series')
        cls.free = cls.make_film('Journey Free', is_vip=False)
        cls.other_category = cls.make_film('Journey Comedy', genre=cls.other_genre)
        cls.other_performer = cls.make_film('Journey Blair', actor=cls.other_actor)
        cls.other_title = cls.make_film('Different Story')
        cls.hidden_same_year = cls.make_film('Private Journey', published=False)
        cls.hidden_future_year = cls.make_film('Private Future Journey', year=2099, published=False)

    @classmethod
    def make_film(cls, title, *, genre=None, actor=None, score=None, **overrides):
        values = {
            'title': title, 'slug': title.lower().replace(' ', '-'),
            'description': 'A film for discovery.', 'published': True,
            'year': 2026, 'country': 'Netherlands', 'kind': 'movie', 'is_vip': True,
        }
        values.update(overrides)
        film = Movie.objects.create(**values)
        film.categories.add(genre or cls.genre)
        film.actors.add(actor or cls.actor)
        if score is not None:
            Rating.objects.create(movie=film, user=cls.viewer, score=score)
        return film

    def combined_query(self, **extra):
        return {
            'year': '2026', 'q': 'Journey', 'category': self.genre.slug,
            'country': 'Netherlands', 'kind': 'movie', 'actor': str(self.actor.pk),
            'access': 'vip', 'sort': 'rating', **extra,
        }

    def test_year_limits_results_to_published_films_from_that_release_year(self):
        response = self.client.get(reverse('catalog'), {'year': '2026'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_browsing'])
        expected = {
            self.high.pk, self.low.pk, self.foreign.pk, self.series.pk, self.free.pk,
            self.other_category.pk, self.other_performer.pk, self.other_title.pk,
        }
        self.assertEqual({film.pk for film in response.context['page']}, expected)
        self.assertEqual(response.context['selected_year'], '2026')
        self.assertEqual(response.context['shelves'], [])

    def test_year_combines_with_every_existing_filter_and_rating_order(self):
        response = self.client.get(reverse('catalog'), self.combined_query())
        self.assertEqual(response.status_code, 200)
        self.assertEqual([film.pk for film in response.context['page']], [self.high.pk, self.low.pk])
        self.assertEqual(response.context['selected_actor'].pk, self.actor.pk)
        self.assertEqual(response.context['selected_country'], 'Netherlands')
        self.assertEqual(response.context['selected_category'].pk, self.genre.pk)
        self.assertEqual(response.context['selected_year'], '2026')

    def test_year_choices_are_distinct_descending_and_hide_draft_only_years(self):
        response = self.client.get(reverse('catalog'), {'year': '2025'})
        self.assertEqual(response.context['years'], [2026, 2025])
        parsed = CatalogLinksAndOptions(response.content.decode())
        self.assertIn('year', parsed.selects)
        options = parsed.selects['year']
        self.assertEqual([option['value'] for option in options], ['', '2026', '2025'])
        self.assertEqual([option['value'] for option in options if option['selected']], ['2025'])
        self.assertEqual([film.pk for film in response.context['page']], [self.previous.pk])

    def test_invalid_or_unknown_year_does_not_silently_show_unfiltered_movies(self):
        for year in ('not-a-year', '0', '-2026', '2e3', '2026.0', '9' * 50, '1999', '2099'):
            with self.subTest(year=year):
                response = self.client.get(reverse('catalog'), {'year': year})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['is_browsing'])
                self.assertEqual(response.context['page'].paginator.count, 0)
                self.assertContains(response, 'Chưa có phim phù hợp')

    def test_year_and_all_other_filters_survive_pagination(self):
        for number in range(13):
            self.make_film(f'Journey Extra {number}')
        first = self.client.get(reverse('catalog'), self.combined_query())
        self.assertEqual(first.context['page'].paginator.count, 15)
        parsed = CatalogLinksAndOptions(first.content.decode())
        next_href = next(link['href'] for link in parsed.links if link['text'].strip() == 'Tiếp')
        self.assertEqual(parse_qs(urlsplit(next_href).query), {
            key: [value] for key, value in self.combined_query(page='2').items()
        })
        second = self.client.get(urljoin(reverse('catalog'), next_href))
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.context['page'].number, 2)
        self.assertEqual(len(second.context['page']), 3)
        self.assertEqual(second.context['selected_year'], '2026')
        self.assertTrue(all(film.year == 2026 for film in second.context['page']))

    def test_dropdown_changes_keep_year_and_other_filters_but_reset_page(self):
        request = RequestFactory().get(reverse('catalog'), self.combined_query(page='4'))
        context = Context({'request': request})
        for menu, changing, key in (
            (genre_menu_data(context), 'category', 'slug'),
            (country_menu_data(context), 'country', 'name'),
        ):
            self.assertTrue(menu)
            for item in menu:
                parts = urlsplit(item['href'])
                self.assertEqual(parts.path, reverse('catalog'))
                expected = {key: [value] for key, value in self.combined_query().items()}
                expected[changing] = [item[key]]
                self.assertEqual(parse_qs(parts.query), expected)

    def test_old_home_year_bookmark_redirects_to_catalog_with_filters_intact(self):
        query = self.combined_query()
        response = self.client.get(reverse('landing'), query)
        self.assertRedirects(response, reverse('catalog') + '?' + urlencode(query), fetch_redirect_response=False)
        year_only = self.client.get(reverse('landing'), {'year': '2026'})
        self.assertRedirects(year_only, reverse('catalog') + '?year=2026', fetch_redirect_response=False)

    def test_reset_link_clears_year_along_with_the_other_filters(self):
        response = self.client.get(reverse('catalog'), self.combined_query())
        parsed = CatalogLinksAndOptions(response.content.decode())
        reset = next(link['href'] for link in parsed.links if link['text'].strip() == 'Xóa bộ lọc')
        self.assertEqual(reset, reverse('catalog'))
        cleared = self.client.get(reset)
        self.assertEqual(cleared.status_code, 200)
        self.assertFalse(cleared.context['is_browsing'])
        self.assertEqual(cleared.context['selected_year'], '')
