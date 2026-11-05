import io
import shutil
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from .models import Category, Episode, Movie


@skipUnless(shutil.which('ffprobe'), 'ffprobe is required to validate the bundled MP4.')
class TrailerDemoTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings = override_settings(MEDIA_ROOT=Path(self.media.name))
        self.settings.enable()
        self.addCleanup(self.settings.disable)

    def test_demo_creates_an_attributed_trailer_without_an_episode_or_theatrical_claim(self):
        call_command('seed_trailer_demo', stdout=io.StringIO())
        movie = Movie.objects.get(slug='big-buck-bunny')
        self.assertTrue(movie.has_trailer)
        self.assertIn('CC BY 3.0', movie.trailer_credit)
        self.assertIn('không phải trailer chính thức', movie.trailer_credit)
        self.assertFalse(movie.is_cinema_release)
        self.assertEqual(Episode.objects.count(), 0)
        path = movie.trailer_file.name
        call_command('seed_trailer_demo', stdout=io.StringIO())
        movie.refresh_from_db()
        self.assertEqual(movie.trailer_file.name, path)
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual(len(list(Path(self.media.name).rglob('*.mp4'))), 1)

    def test_demo_does_not_replace_an_existing_trailer_or_movie_settings(self):
        movie = Movie.objects.create(title='Existing title', slug='big-buck-bunny',
                                     description='Existing text', is_vip=True,
                                     trailer_url='https://youtu.be/AbCdEfGhI12')
        call_command('seed_trailer_demo', stdout=io.StringIO())
        movie.refresh_from_db()
        self.assertEqual(movie.title, 'Existing title')
        self.assertEqual(movie.description, 'Existing text')
        self.assertTrue(movie.is_vip)
        self.assertEqual(movie.trailer_url, 'https://youtu.be/AbCdEfGhI12')
        self.assertFalse(movie.trailer_file)


class TrailerDemoValidationFailureTests(TestCase):
    def test_invalid_bundled_clip_rolls_back_new_movie_and_never_writes_public_media(self):
        with tempfile.TemporaryDirectory(prefix='lumiere-invalid-demo-') as directory:
            base = Path(directory) / 'app'
            media = Path(directory) / 'media'
            clip = base / 'static' / 'imagery' / 'big-buck-bunny-preview.mp4'
            clip.parent.mkdir(parents=True)
            clip.write_bytes(b'<!doctype html><script>not a video</script>')
            with override_settings(BASE_DIR=base, MEDIA_ROOT=media):
                with self.assertRaises(ValidationError):
                    call_command('seed_trailer_demo', stdout=io.StringIO())
            self.assertFalse(Movie.objects.filter(slug='big-buck-bunny').exists())
            self.assertFalse(Category.objects.exists())
            self.assertFalse(Episode.objects.exists())
            self.assertEqual(list(media.rglob('*')), [])
