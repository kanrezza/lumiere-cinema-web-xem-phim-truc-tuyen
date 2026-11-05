import bcrypt
from unittest.mock import patch
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import TestCase
from cinema.models import Category, Comment, Episode, History, LegacyRecord, Movie, Rating, User, Watchlist
from cinema.management.commands.import_laravel import Importer, TABLES, legacy_password


class LegacyImportTests(TestCase):
    def snapshot(self):
        data = {table: [] for table in TABLES}
        hashed = bcrypt.hashpw(b'legacy-password', bcrypt.gensalt(rounds=4)).decode().replace('$2b$', '$2y$')
        data['users'] = [{'id': 10, 'name': 'Demo Legacy', 'email': 'OLD@example.com', 'password': hashed, 'status':'active', 'role':'admin'}]
        data['categories'] = [{'id': 4, 'name':'Viễn tưởng', 'slug':'vien-tuong'}]
        data['movies'] = [{'id': 6, 'title':'Old Film', 'description':'Imported', 'category_id':4, 'type':'Phim lẻ','status':'active','actors':'Actor A, Actor B','video_url':'https://external.example/video.mp4'}]
        data['episodes'] = [{'id':22, 'movie_id':6, 'episode_number':1, 'title':'Full Film', 'video_url':'https://external.example/video.mp4'}]
        data['comments'] = [{'id':1,'user_id':10,'movie_id':6,'content':'Great'}]
        data['ratings'] = [{'id':2,'user_id':10,'movie_id':6,'score':9}]
        data['watchlists'] = [{'id':3,'user_id':10,'movie_id':6}]
        data['watch_histories'] = [{'id':4,'user_id':10,'movie_id':6,'watched_at':'2026-01-02 03:04:05'}]
        return data

    def test_import_preserves_relations_and_hashes_without_privilege(self):
        Importer('test-source').import_all(self.snapshot())
        user = User.objects.get()
        self.assertEqual(user.email,'old@example.com')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password('legacy-password'))
        user.refresh_from_db()
        self.assertTrue(user.password.startswith('pbkdf2_sha256$'))
        self.assertEqual(Movie.objects.get().categories.get(), Category.objects.get())
        self.assertEqual(Movie.objects.get().actors.count(), 2)
        self.assertEqual(Rating.objects.get().score, 5)
        self.assertEqual(Comment.objects.get().content, 'Great')
        self.assertEqual(Watchlist.objects.get().user,user)
        self.assertEqual(History.objects.get().position,0)
        self.assertEqual(Episode.objects.get().source.name,'')
        self.assertEqual(Episode.objects.get().status,'failed')

    def test_second_import_is_idempotent_and_preserves_target_edits(self):
        data = self.snapshot()
        Importer('test-source').import_all(data)
        movie = Movie.objects.get(); movie.title = 'Locally edited'; movie.save()
        initial_count = LegacyRecord.objects.count()
        Importer('test-source').import_all(data)
        self.assertEqual(Movie.objects.count(),1)
        self.assertEqual(Movie.objects.get().title,'Locally edited')
        self.assertEqual(Episode.objects.count(),1)
        self.assertEqual(Comment.objects.count(),1)
        self.assertEqual(LegacyRecord.objects.count(),initial_count)

    def test_default_command_rolls_back(self):
        with patch('cinema.management.commands.import_laravel.read_source', return_value=('test-source',self.snapshot())):
            call_command('import_laravel', verbosity=0)
        self.assertEqual(User.objects.count(),0)
        self.assertEqual(LegacyRecord.objects.count(),0)

    def test_apply_command_commits(self):
        with patch('cinema.management.commands.import_laravel.read_source', return_value=('test-source',self.snapshot())):
            call_command('import_laravel', apply=True, verbosity=0)
        self.assertEqual(User.objects.count(),1)

    def test_email_conflict_never_merges_accounts(self):
        User.objects.create_user('existing','old@example.com')
        with self.assertRaises(CommandError), transaction.atomic():
            Importer('test-source').import_all(self.snapshot())
        self.assertEqual(User.objects.count(),1)
        self.assertEqual(LegacyRecord.objects.count(),0)

    def test_unsupported_hash_is_unusable(self):
        self.assertTrue(legacy_password('unknown').startswith('!'))

    def test_legacy_bcrypt_72_byte_behavior(self):
        password = 'a' * 72 + 'suffix'
        encoded = 'laravel_bcrypt$' + bcrypt.hashpw(b'a'*72, bcrypt.gensalt(rounds=4)).decode()
        self.assertTrue(check_password(password, encoded))
        self.assertFalse(check_password('wrong', encoded))
