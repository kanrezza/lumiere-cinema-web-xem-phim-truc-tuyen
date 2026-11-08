"""IMDb metadata is optional, source-linked and separate from local reviews."""
from datetime import timedelta
from decimal import Decimal
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Movie, Rating
from .views import catalog_movies


class ImdbMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.buttons = []
        self.anchor_depth = 0
        self.nested_anchor = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.nested_anchor |= self.anchor_depth > 0
            self.anchor_depth += 1
            self.links.append(attrs)
        if tag == 'button':
            self.buttons.append(attrs)

    def handle_endtag(self, tag):
        if tag == 'a':
            self.anchor_depth = max(0, self.anchor_depth - 1)


class ImdbMetadataTests(TestCase):
    def movie(self, **overrides):
        values = dict(title='A source-rated film', slug='imdb-metadata-film',
                      description='A film with optional source metadata.', published=True)
        values.update(overrides)
        return Movie(**values)

    def test_valid_rating_has_a_canonical_source_url_and_round_trip(self):
        movie = self.movie(imdb_id='tt1254207', imdb_rating=Decimal('6.5'),
                           imdb_rating_checked_at=timezone.localdate())
        movie.full_clean()
        movie.save()
        movie.refresh_from_db()
        self.assertTrue(movie.has_imdb_rating)
        self.assertEqual(movie.imdb_url, 'https://www.imdb.com/title/tt1254207/')
        self.assertEqual(movie.imdb_rating, Decimal('6.5'))

    def test_optional_metadata_and_id_without_a_rating_are_valid(self):
        for values in ({}, {'imdb_id': 'tt1254207'}):
            with self.subTest(values=values):
                movie = self.movie(**values)
                movie.full_clean()
                self.assertFalse(movie.has_imdb_rating)

    def test_rating_bounds_reject_zero_and_scores_above_ten(self):
        for score in ('0.0', '-1.0', '10.1', 'NaN', 'Infinity'):
            with self.subTest(score=score):
                movie = self.movie(imdb_id='tt1254207', imdb_rating=Decimal(score))
                with self.assertRaises(ValidationError):
                    movie.full_clean()
        for score in ('1.0', '10.0'):
            with self.subTest(score=score):
                movie = self.movie(imdb_id='tt1254207', imdb_rating=Decimal(score))
                movie.full_clean()
                self.assertTrue(movie.has_imdb_rating)

    def test_invalid_ids_cannot_be_used_to_build_an_external_url(self):
        for imdb_id in ('https://www.imdb.com/title/tt1254207/', 'tt123456',
                        'tt12345678901', 'TT1254207', 'tt１２５４２０７',
                        'tt1254207/../../evil', 'tt1254207" onclick="alert(1)'):
            with self.subTest(imdb_id=imdb_id):
                movie = self.movie(imdb_id=imdb_id, imdb_rating=Decimal('6.5'))
                with self.assertRaises(ValidationError):
                    movie.full_clean()
                self.assertFalse(movie.has_imdb_rating)
                self.assertEqual(movie.imdb_url, '')

    def test_score_and_recorded_date_require_their_corresponding_metadata(self):
        for values in ({'imdb_rating': Decimal('6.5')},
                       {'imdb_id': 'tt1254207', 'imdb_rating_checked_at': timezone.localdate()},
                       {'imdb_id': 'tt1254207', 'imdb_rating': Decimal('6.5'),
                        'imdb_rating_checked_at': timezone.localdate() + timedelta(days=1)}):
            with self.subTest(values=values):
                with self.assertRaises(ValidationError):
                    self.movie(**values).full_clean()

    def test_malformed_recorded_date_raises_validation_error_instead_of_crashing(self):
        movie = self.movie(imdb_id='tt1254207', imdb_rating=Decimal('6.5'),
                           imdb_rating_checked_at='not-a-date')
        with self.assertRaises(ValidationError):
            movie.full_clean()


class ImdbDisplayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rated = Movie.objects.create(
            title='A "quoted" <script>film</script>', slug='imdb-display-film',
            description='A publicly available film.', published=True,
            imdb_id='tt1254207', imdb_rating=Decimal('6.5'),
            imdb_rating_checked_at=timezone.localdate(),
        )
        cls.plain = Movie.objects.create(title='No source score', slug='imdb-display-plain',
                                        description='No score has been entered.', published=True)
        cls.episode = Episode.objects.create(movie=cls.rated, title='Full film', status='ready')
        cls.viewer = get_user_model().objects.create_user('imdb-viewer', 'imdb-viewer@example.test')
        Rating.objects.create(user=cls.viewer, movie=cls.rated, score=4)

    def card(self, film):
        return render_to_string('cinema/card.html', {
            'movie': catalog_movies().get(pk=film.pk), 'portrait': True,
            'user': AnonymousUser(),
        })

    def test_card_source_link_is_independent_and_title_is_escaped(self):
        html = self.card(self.rated)
        parsed = ImdbMarkup(html)
        source = next(link for link in parsed.links if 'imdb-rating' in link.get('class', ''))
        self.assertEqual(source['href'], self.rated.imdb_url)
        self.assertEqual(source['target'], '_blank')
        self.assertTrue({'noopener', 'noreferrer'} <= set(source['rel'].split()))
        self.assertFalse(parsed.nested_anchor)
        trigger = next(button for button in parsed.buttons if 'quickview-trigger' in button.get('class', ''))
        self.assertEqual(trigger['data-movie-imdb-id'], 'tt1254207')
        self.assertEqual(trigger['data-movie-imdb-rating'], '6.5')
        self.assertNotIn('<script>film</script>', html)

    def test_unrated_card_clears_quickview_metadata_and_has_no_placeholder_score(self):
        html = self.card(self.plain)
        parsed = ImdbMarkup(html)
        self.assertFalse(any('imdb-rating' in link.get('class', '') and 'hidden' not in link for link in parsed.links))
        trigger = next(button for button in parsed.buttons if 'quickview-trigger' in button.get('class', ''))
        self.assertEqual(trigger['data-movie-imdb-id'], '')
        self.assertEqual(trigger['data-movie-imdb-rating'], '')
        self.assertNotIn('/10', html)

    def test_detail_keeps_imdb_ten_point_and_local_five_point_scales_separate(self):
        response = self.client.get(reverse('movie', args=[self.rated.slug]))
        self.assertContains(response, self.rated.imdb_url)
        self.assertContains(response, 'Điểm IMDb')
        self.assertContains(response, '/10')
        self.assertContains(response, '/5')
        self.assertContains(response, 'Lumière</span>', html=False)
        self.assertContains(response, 'Điểm do quản trị cập nhật, có thể thay đổi trên IMDb.')
        self.assertContains(response, self.rated.imdb_rating_checked_at.strftime('%d/%m/%Y'))
        self.assertNotContains(response, '<script>film</script>')

    def test_blank_and_invalid_persisted_metadata_never_show_an_imdb_score(self):
        response = self.client.get(reverse('movie', args=[self.plain.slug]))
        parsed = ImdbMarkup(response.content.decode())
        self.assertFalse(any('imdb-rating' in link.get('class', '') and 'hidden' not in link for link in parsed.links))
        # Direct SQL/bulk edits can bypass model.clean(); rendering remains defensive.
        Movie.objects.filter(pk=self.plain.pk).update(imdb_id='javascript:alert(1)', imdb_rating=Decimal('7.0'))
        self.assertNotIn('class="imdb-rating', self.card(self.plain))

    def test_catalog_feature_and_cards_use_the_same_source_without_revealing_drafts(self):
        Movie.objects.create(title='Private IMDb draft', slug='imdb-hidden-draft', description='Private.',
                             published=False, imdb_id='tt12345678', imdb_rating=Decimal('8.8'))
        response = self.client.get(reverse('catalog'))
        self.assertContains(response, self.rated.imdb_url)
        self.assertNotContains(response, 'https://www.imdb.com/title/tt12345678/')
        self.assertNotContains(response, 'Private IMDb draft')
