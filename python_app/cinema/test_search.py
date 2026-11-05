import unicodedata
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from .models import Actor, Movie
from .search import filter_actor_search, filter_movie_search, normalize_search


class VietnameseSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = Actor.objects.create(name='Đỗ Hải Yến')
        cls.summer = Movie.objects.create(
            title='Mùa hè năm ấy', slug='search-summer', description='Một câu chuyện nhẹ nhàng.', published=True,
        )
        cls.summer.actors.add(cls.actor)
        cls.orbit = Movie.objects.create(
            title='Chạm vào vô tận', slug='search-orbit', description='Đường về những vì sao.', published=True,
        )
        cls.draft = Movie.objects.create(
            title='Mùa hè bí mật', slug='search-draft', description='Nội dung chưa công bố.', published=False,
        )
        cls.draft.actors.add(cls.actor)

    def assert_movie_matches(self, query, expected):
        with self.assertNumQueries(0):
            matching = filter_movie_search(Movie.objects.filter(published=True), query)
        with self.assertNumQueries(1):
            self.assertEqual(set(matching.values_list('pk', flat=True)), {movie.pk for movie in expected})

    def test_movie_search_accepts_uppercase_accents_and_accentless_queries(self):
        for query in ('Mùa hè', 'MÙA HÈ', 'mua he', '  MUA   HE  ', unicodedata.normalize('NFD', 'MÙA HÈ')):
            with self.subTest(query=query):
                self.assert_movie_matches(query, [self.summer])
        for query in ('CHẠM', 'cham', unicodedata.normalize('NFD', 'Chạm')):
            with self.subTest(query=query):
                self.assert_movie_matches(query, [self.orbit])

    def test_actor_search_accepts_vietnamese_d_and_decomposed_accents(self):
        for query in ('Đỗ Hải', 'ĐỖ HẢI', 'do hai', unicodedata.normalize('NFD', 'ĐỖ HẢI')):
            with self.subTest(query=query):
                self.assertEqual(list(filter_actor_search(Actor.objects.all(), query)), [self.actor])

    def test_catalog_endpoint_finds_uppercase_and_accentless_names_without_drafts(self):
        for query in ('MÙA HÈ', 'mua he', unicodedata.normalize('NFD', 'MÙA HÈ'), 'DO HAI YEN'):
            with self.subTest(query=query):
                response = self.client.get(reverse('catalog'), {'q': query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([film.pk for film in response.context['page']], [self.summer.pk])

    def test_actor_endpoint_finds_uppercase_and_accentless_names_without_private_performers(self):
        private_actor = Actor.objects.create(name='Đỗ Hải Bình')
        self.draft.actors.add(private_actor)
        for query in ('ĐỖ HẢI', 'do hai', unicodedata.normalize('NFD', 'ĐỖ HẢI')):
            with self.subTest(query=query):
                response = self.client.get(reverse('actors'), {'q': query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([actor.pk for actor in response.context['actors']], [self.actor.pk])

    def test_movie_search_includes_description_and_related_actor_without_draft_leaks(self):
        self.assert_movie_matches('DUONG VE', [self.orbit])
        self.assert_movie_matches('DO HAI YEN', [self.summer])
        another_actor = Actor.objects.create(name='Đỗ Hải Nam')
        self.summer.actors.add(another_actor)
        self.assert_movie_matches('do hai', [self.summer])

    def test_empty_whitespace_and_no_match_preserve_scope(self):
        for query in ('', '  \t\n'):
            self.assert_movie_matches(query, [self.summer, self.orbit])
        self.assert_movie_matches('khong co phim nay', [])
        self.assertEqual(list(filter_actor_search(Actor.objects.filter(pk=-1), '')), [])

    def test_literal_like_characters_are_not_wildcards(self):
        self.assert_movie_matches('%', [])
        self.assert_movie_matches('_', [])

    def test_regular_and_partial_saves_refresh_only_persisted_source_fields(self):
        self.summer.title = 'Đường về nhà'
        self.summer.description = 'Mô tả chưa lưu'
        self.summer.save(update_fields=['title'])
        self.summer.refresh_from_db()
        self.assertEqual(self.summer.search_title, 'duong ve nha')
        self.assertEqual(self.summer.search_description, 'mot cau chuyen nhe nhang.')
        self.assert_movie_matches('duong ve nha', [self.summer])
        self.assert_movie_matches('mua he', [])
        self.actor.name = 'Trần Ánh Hùng'
        self.actor.save(update_fields=['name'])
        self.actor.refresh_from_db()
        self.assertEqual(self.actor.search_name, 'tran anh hung')
        self.assert_movie_matches('TRAN ANH HUNG', [self.summer])
        self.summer.description = 'Câu chuyện của đêm'
        self.summer.save()
        self.assert_movie_matches('cua dem', [self.summer])

    def test_update_or_create_and_deferred_saves_keep_search_values_current(self):
        Movie.objects.update_or_create(pk=self.orbit.pk, defaults={'title': 'Đêm thành phố'})
        self.assert_movie_matches('dem thanh pho', [self.orbit])
        partial = Movie.objects.only('pk', 'title').get(pk=self.orbit.pk)
        partial.title = 'Ánh đèn phố'
        partial.save()
        self.assert_movie_matches('anh den pho', [self.orbit])
        self.orbit.refresh_from_db()
        self.assertEqual(self.orbit.search_description, 'duong ve nhung vi sao.')

    def test_empty_update_fields_is_a_no_op(self):
        self.actor.name = 'Tên chưa lưu'
        self.actor.save(update_fields=[])
        self.actor.refresh_from_db()
        self.assertEqual(self.actor.name, 'Đỗ Hải Yến')
        self.assertEqual(self.actor.search_name, 'do hai yen')

    def test_normalization_handles_casefold_and_vietnamese_crossed_d(self):
        self.assertEqual(normalize_search(' ĐẶNG\t THỊ  HỒNG\n '), 'dang thi hong')
        self.assertEqual(normalize_search('Straße'), 'strasse')
        self.assertEqual(normalize_search('𝑴Ù𝑨 𝑯È'), 'mua he')

    def test_reindex_command_repairs_bulk_updates_without_changing_source_content(self):
        Movie.objects.filter(pk=self.summer.pk).update(title='Đêm tháng sáu', description='Ký ức mới')
        Actor.objects.filter(pk=self.actor.pk).update(name='Trần Ánh Hùng')
        output = StringIO()
        call_command('reindex_search', batch_size=1, stdout=output)
        self.summer.refresh_from_db()
        self.actor.refresh_from_db()
        self.assertEqual(self.summer.title, 'Đêm tháng sáu')
        self.assertEqual(self.summer.search_title, 'dem thang sau')
        self.assertEqual(self.summer.search_description, 'ky uc moi')
        self.assertEqual(self.actor.search_name, 'tran anh hung')
        self.assert_movie_matches('dem thang sau', [self.summer])
        self.assert_movie_matches('TRAN ANH HUNG', [self.summer])
        self.assertIn('Movie: 3', output.getvalue())
        self.assertIn('Actor: 1', output.getvalue())


class SearchBackfillMigrationTests(TransactionTestCase):
    def test_existing_movies_and_actors_are_searchable_after_migration(self):
        executor = MigrationExecutor(connection)
        before = [('cinema', '0003_movie_backdrop')]
        after = [('cinema', '0004_normalized_search_fields')]
        try:
            executor.migrate(before)
            old_apps = executor.loader.project_state(before).apps
            actor = old_apps.get_model('cinema', 'Actor').objects.create(name='Đỗ Hải Yến')
            movie = old_apps.get_model('cinema', 'Movie').objects.create(
                title='Mùa hè năm ấy', slug='pre-search-migration', description='Đường về nhà.',
            )
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            new_apps = executor.loader.project_state(after).apps
            migrated_actor = new_apps.get_model('cinema', 'Actor').objects.get(pk=actor.pk)
            migrated_movie = new_apps.get_model('cinema', 'Movie').objects.get(pk=movie.pk)
            self.assertEqual(migrated_actor.search_name, 'do hai yen')
            self.assertEqual(migrated_movie.search_title, 'mua he nam ay')
            self.assertEqual(migrated_movie.search_description, 'duong ve nha.')
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
