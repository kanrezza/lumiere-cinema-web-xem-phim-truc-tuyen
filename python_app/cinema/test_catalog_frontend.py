import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, Episode, History, Movie


class CatalogFrontendTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.genre = Category.objects.create(name='Hoạt hình', slug='hoat-hinh')
        cls.viewer = get_user_model().objects.create_user('catalog-frontend')
        for index in range(13):
            movie = Movie.objects.create(
                title=f'Phim thử {index}', slug=f'phim-thu-{index}',
                country='Việt Nam', year=2026, published=True,
            )
            movie.categories.add(cls.genre)
        cls.movie = movie
        cls.episode = Episode.objects.create(
            movie=movie, title='Bản phim', status='ready', duration=100,
        )
        Movie.objects.create(
            title='Bản nháp', slug='draft', country='Nhật Bản', year=2030,
            published=False,
        )

    def test_bootstrap_matches_the_json_endpoint_and_paging_preserves_filters(self):
        catalog = reverse('catalog')
        query = {'q': 'phim thu', 'category': self.genre.slug, 'country': 'Việt Nam', 'year': '2026'}
        page = self.client.get(catalog, query)
        response = self.client.get(catalog, query, headers={'X-Lumiere-Catalog': 'vue'})

        self.assertContains(page, 'data-catalog-fallback')
        self.assertContains(page, 'data-catalog-app')
        self.assertContains(page, 'id="browse-search"')
        self.assertContains(page, reverse('movie', args=[self.movie.slug]))
        self.assertIn('X-Lumiere-Catalog', page.headers['Vary'])
        self.assertIn('X-Lumiere-Catalog', response.headers['Vary'])
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')

        bootstrap = re.search(r'<script id="catalog-data" type="application/json">(.*?)</script>', page.content.decode())
        self.assertIsNotNone(bootstrap)
        data = response.json()
        grid = data.pop('gridHtml')
        self.assertEqual(json.loads(bootstrap[1]), data)
        self.assertEqual(data['count'], 13)
        self.assertEqual(data['title'], 'Kết quả cho “phim thu”')
        self.assertEqual(data['countries'], [{'label': 'Việt Nam', 'value': 'Việt Nam'}])
        self.assertEqual(grid.count('class="movie-card"'), 12)
        self.assertNotIn('movie-grid', grid)
        self.assertEqual(parse_qs(urlsplit(data['pagination']['next']).query), {
            key: [value] for key, value in {**query, 'page': '2'}.items()
        })

        next_page = self.client.get(catalog + data['pagination']['next'], headers={'X-Lumiere-Catalog': 'vue'}).json()
        self.assertEqual(next_page['pagination']['page'], 2)
        self.assertIsNone(next_page['pagination']['next'])
        self.assertEqual(next_page['gridHtml'].count('class="movie-card"'), 1)

    def test_resume_card_uses_the_current_viewer_and_is_never_cacheable(self):
        catalog = reverse('catalog')
        query = {'availability': 'ready'}
        view = {'X-Lumiere-Catalog': 'vue'}
        History.objects.create(user=self.viewer, episode=self.episode, position=30)

        guest_grid = self.client.get(catalog, query, headers=view).json()['gridHtml']
        self.assertIn('Đăng nhập để xem', guest_grid)
        self.assertNotIn('data-movie-play-label="Xem tiếp"', guest_grid)
        self.client.force_login(self.viewer)
        signed_in = self.client.get(catalog, query, headers=view)
        self.assertEqual(signed_in.headers['Cache-Control'], 'private, no-store')
        self.assertIn('data-movie-play-label="Xem tiếp"', signed_in.json()['gridHtml'])

    def test_results_escape_page_bootstrap_and_card_values(self):
        markup = '</script><strong>Phim thử</strong>'
        movie = Movie.objects.create(title=markup, slug='encoded-catalog-movie', published=True)
        catalog = reverse('catalog')
        page = self.client.get(catalog, {'q': markup})
        self.assertNotContains(page, markup)
        self.assertContains(page, r'\u003C/script\u003E')
        result = self.client.get(catalog, {'sort': 'newest'}, headers={'X-Lumiere-Catalog': 'vue'}).json()
        self.assertNotIn(markup, result['gridHtml'])
        self.assertIn('&lt;/script&gt;', result['gridHtml'])
        self.assertIn(reverse('movie', args=[movie.slug]), result['gridHtml'])

    def test_unfiltered_browse_keeps_normal_shelves_without_the_results_frontend(self):
        response = self.client.get(reverse('catalog'), headers={'X-Lumiere-Catalog': 'vue'})
        self.assertIn('text/html', response.headers['Content-Type'])
        self.assertContains(response, 'data-shelf')
        self.assertNotContains(response, 'data-catalog-app')

    def test_catalog_loads_the_correct_bundle_and_falls_back_when_it_is_missing(self):
        catalog = reverse('catalog')
        with TemporaryDirectory() as temp, self.settings(BASE_DIR=Path(temp)):
            bundle = Path(temp) / 'static/bundles/catalog'
            assets = bundle / 'assets'
            assets.mkdir(parents=True)
            (bundle / 'manifest.json').write_text(json.dumps({
                'src/home/main.ts': {'file': 'assets/home-test.js'},
                'src/catalog/main.ts': {'file': 'assets/results-test.js'},
            }), encoding='utf-8')
            self.assertNotContains(self.client.get(catalog), 'data-feature-vue')
            self.assertNotContains(self.client.get(catalog), 'data-shelf-vue')
            (assets / 'home-test.js').touch()
            (assets / 'results-test.js').touch()

            home = self.client.get(catalog)
            self.assertContains(home, '/bundles/catalog/assets/home-test.js')
            self.assertContains(home, 'data-feature-vue')
            self.assertContains(home, 'data-shelf-vue')
            self.assertNotContains(home, '/bundles/catalog/assets/results-test.js')

            results = self.client.get(catalog, {'sort': 'newest'})
            self.assertContains(results, '/bundles/catalog/assets/results-test.js')
            self.assertNotContains(results, '/bundles/catalog/assets/home-test.js')
