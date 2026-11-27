"""The header search only suggests public metadata and never resumes playback."""

import json

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .models import Actor, Episode, History, Movie, User
from .views.search import search_suggestions


class InstantSearchTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def film(self, title, slug, **kwargs):
        return Movie.objects.create(title=title, slug=slug, description='', published=True, **kwargs)

    def search(self, query, user=None):
        request = self.factory.get('/search/suggestions/', {'q': query})
        request.user = user or AnonymousUser()
        response = search_suggestions(request)
        self.assertEqual(response.status_code, 200)
        return response, json.loads(response.content)

    def test_diacritic_and_case_normalization_matches_public_films_and_performers(self):
        movie = self.film('Ánh sáng trong đêm', 'anh-sang')
        actor = Actor.objects.create(name='Đặng Thu Hà')
        movie.actors.add(actor)
        for query in ('ÁNH SÁNG', 'anh sang', 'a\u0301nh sa\u0301ng'):
            with self.subTest(query=query):
                _, result = self.search(query)
                self.assertEqual([item['id'] for item in result['movies']], [movie.pk])
        _, result = self.search('dang thu')
        self.assertEqual([item['id'] for item in result['movies']], [movie.pk])
        self.assertEqual(result['actors'], [{'id': actor.pk, 'name': actor.name, 'url': reverse('actor', args=[actor.pk])}])

    def test_draft_titles_descriptions_and_draft_only_performers_are_excluded(self):
        draft = Movie.objects.create(title='Bí mật', slug='secret', description='Nội dung riêng', published=False)
        actor = Actor.objects.create(name='Diễn viên bí mật')
        draft.actors.add(actor)
        for query in ('bi mat', 'noi dung rieng', 'dien vien'):
            with self.subTest(query=query):
                _, result = self.search(query)
                self.assertEqual(result['movies'], [])
                self.assertEqual(result['actors'], [])

    def test_public_vip_metadata_is_visible_but_never_exposes_a_playback_target(self):
        movie = self.film('Phim VIP', 'phim-vip', is_vip=True)
        episode = Episode.objects.create(movie=movie, title='Tập 1', source='originals/private.mp4', status='ready')
        _, result = self.search('Phim VIP')
        item = result['movies'][0]
        self.assertTrue(item['vip'])
        self.assertTrue(item['ready'])
        self.assertEqual(item['url'], reverse('movie', args=[movie.slug]))
        serialized = json.dumps(result)
        self.assertNotIn('/watch/', serialized)
        self.assertNotIn('/stream/', serialized)
        self.assertNotIn(episode.source.name, serialized)

    def test_drafts_and_actors_without_public_credits_are_never_suggested(self):
        draft = Movie.objects.create(title='Bí mật chưa phát hành', slug='secret-draft', description='bí mật', published=False)
        private_actor = Actor.objects.create(name='Bí mật riêng tư')
        shared_actor = Actor.objects.create(name='Công khai')
        draft.actors.add(private_actor, shared_actor)
        published = self.film('Phim đã công khai', 'public-film')
        published.actors.add(shared_actor)
        _, result = self.search('bi mat')
        self.assertEqual(result['movies'], [])
        self.assertEqual(result['actors'], [])
        _, result = self.search('cong khai')
        self.assertEqual([item['id'] for item in result['movies']], [published.pk])
        self.assertEqual([item['id'] for item in result['actors']], [shared_actor.pk])

    def test_only_ready_episodes_set_the_ready_flag(self):
        preparing = self.film('Chuẩn bị', 'chuan-bi')
        Episode.objects.create(movie=preparing, title='Đang xử lý', source='originals/pending.mp4', status='processing')
        _, result = self.search('chuan bi')
        self.assertFalse(result['movies'][0]['ready'])

    def test_short_or_blank_queries_do_not_scan_the_catalog(self):
        for query in ('', ' ', 'a', 'ắ', 'a\u0306\u0301'):
            with self.subTest(query=query), self.assertNumQueries(0):
                _, result = self.search(query)
                self.assertEqual(result['movies'], [])
                self.assertEqual(result['actors'], [])

    def test_query_length_is_capped_and_encoded_in_the_fallback_url(self):
        _, result = self.search('  ' + 'a' * 300 + '  ')
        self.assertEqual(result['query'], 'a' * 150)
        self.assertEqual(result['all_url'], reverse('catalog') + '?q=' + 'a' * 150)
        _, result = self.search('a&b /?')
        self.assertIn('q=a%26b+%2F%3F', result['all_url'])

    def test_limits_results_and_deduplicates_movies_with_multiple_matching_performers(self):
        actors = [Actor.objects.create(name=f'Đêm diễn viên {number}') for number in range(5)]
        for number in range(9):
            movie = self.film(f'Đêm số {number}', f'dem-{number}')
            movie.actors.add(*actors)
        _, result = self.search('dem')
        self.assertEqual(len(result['movies']), 6)
        self.assertEqual(len(result['actors']), 3)
        self.assertEqual(len({item['id'] for item in result['movies']}), 6)

    def test_title_prefixes_are_ranked_before_description_matches(self):
        prefix = self.film('Đêm bình yên', 'dem-binh-yen')
        description = self.film('Bình minh', 'binh-minh')
        description.description = 'Đêm vừa qua.'
        description.save(update_fields=['description'])
        _, result = self.search('dem')
        self.assertEqual([item['id'] for item in result['movies']], [prefix.pk, description.pk])

    def test_results_are_session_independent_and_not_cached(self):
        movie = self.film('Câu chuyện', 'cau-chuyen')
        episode = Episode.objects.create(movie=movie, title='Tập 1', source='originals/test.mp4', status='ready')
        viewer = User.objects.create_user('viewer', email='viewer@example.invalid')
        History.objects.create(user=viewer, episode=episode, position=83)
        response, anonymous = self.search('cau chuyen')
        _, authenticated = self.search('cau chuyen', viewer)
        self.assertEqual(anonymous, authenticated)
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertNotIn('position', json.dumps(authenticated))
        self.assertNotIn('resume', json.dumps(authenticated))

    def test_post_is_rejected_without_mutations(self):
        response = search_suggestions(self.factory.post('/search/suggestions/', {'q': 'hello'}))
        self.assertEqual(response.status_code, 405)
