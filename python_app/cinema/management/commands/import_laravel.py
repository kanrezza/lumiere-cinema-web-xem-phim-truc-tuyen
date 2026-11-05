"""Read a fixed allowlist of Laravel tables; never execute the SQL dump or write to source."""
import hashlib
import math
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import pymysql
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from cinema.models import Actor, Category, Comment, Episode, History, LegacyRecord, Movie, Rating, User, Watchlist

TABLES = ('users', 'categories', 'actors', 'movies', 'category_movie', 'episodes', 'comments', 'ratings', 'watchlists', 'watch_histories')


def read_source():
    database = os.getenv('LEGACY_DB_NAME', '')
    if not database:
        raise CommandError('Set LEGACY_DB_NAME and a SELECT-only LEGACY_DB_USER before importing.')
    if database == str(settings.DATABASES['default']['NAME']):
        raise CommandError('The legacy database name must differ from the Django destination database.')
    source = os.getenv('LEGACY_SOURCE_ID', database)
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', source):
        raise CommandError('LEGACY_SOURCE_ID must use 1–100 letters, numbers, dots, underscores or hyphens.')
    connection = pymysql.connect(host=os.getenv('LEGACY_DB_HOST', '127.0.0.1'), port=int(os.getenv('LEGACY_DB_PORT', '3306')), user=os.getenv('LEGACY_DB_USER', 'lumiere_reader'), password=os.getenv('LEGACY_DB_PASSWORD', ''), database=database, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, connect_timeout=10, read_timeout=60, autocommit=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute('START TRANSACTION READ ONLY, WITH CONSISTENT SNAPSHOT')
            cursor.execute('SHOW TABLES')
            available = {next(iter(row.values())) for row in cursor.fetchall()}
            if not {'users', 'movies'}.issubset(available):
                raise CommandError('Source is missing Laravel users or movies tables.')
            data = {}
            for table in TABLES:
                if table not in available:
                    data[table] = []
                    continue
                # `table` is chosen only from the fixed constant above, not user input.
                cursor.execute(f'SELECT * FROM `{table}`')
                data[table] = list(cursor.fetchall())
        return source, data
    finally:
        connection.rollback()
        connection.close()


def old_time(value):
    if not value:
        return None
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value))
    if timezone.is_naive(value):
        return timezone.make_aware(value, ZoneInfo(os.getenv('LEGACY_TIME_ZONE', 'Asia/Ho_Chi_Minh')))
    return value


def legacy_password(encoded):
    encoded = str(encoded or '')
    if re.fullmatch(r'\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}', encoded):
        return 'laravel_bcrypt$' + encoded
    return make_password(None)


class Importer:
    def __init__(self, source):
        self.source = source
        self.prefix = hashlib.sha256(source.encode()).hexdigest()[:8]
        self.counts = {'created': 0, 'reused': 0, 'unknown_password': 0}

    def mapped(self, table, row, model, create):
        source_id = int(row['id'])
        if source_id <= 0:
            raise CommandError(f'{table} contains a non-positive ID.')
        record = LegacyRecord.objects.filter(source=self.source, table=table, source_id=source_id).first()
        if record:
            obj = model.objects.filter(pk=record.target_id).first()
            if obj is None:
                raise CommandError(f'Mapping {table}:{source_id} points to a deleted destination row; review it manually.')
            self.counts['reused'] += 1
            return obj, False
        obj = create()
        LegacyRecord.objects.create(source=self.source, table=table, source_id=source_id, target_id=obj.pk)
        self.counts['created'] += 1
        return obj, True

    def import_all(self, data):
        users, categories, movies = {}, {}, {}
        for row in data['users']:
            def create_user(row=row):
                email = (row.get('email') or '').strip().lower()
                if not email or User.objects.filter(email__iexact=email).exists():
                    raise CommandError(f"User {row['id']}: missing email or destination email conflict. Existing accounts are never merged automatically.")
                password = legacy_password(row.get('password'))
                if password.startswith('!'):
                    self.counts['unknown_password'] += 1
                user = User(username=f"legacy_{self.prefix}_{row['id']}", email=email, first_name=(row.get('name') or '')[:150], bio=(row.get('bio') or '')[:500], is_active=row.get('status', 'active') == 'active', password=password)
                # Roles are deliberately not elevated on import. Assign verified staff permissions in Django admin.
                user.full_clean()
                user.save()
                return user
            users[row['id']], _ = self.mapped('users', row, User, create_user)
        for row in data['categories']:
            def create_category(row=row):
                slug = f"legacy-{self.prefix}-{row['id']}"
                return Category.objects.create(name=(row.get('name') or 'Thể loại')[:100], slug=slug[:50])
            categories[row['id']], _ = self.mapped('categories', row, Category, create_category)
        for row in data['actors']:
            self.mapped('actors', row, Actor, lambda row=row: Actor.objects.create(name=(row.get('name') or 'Diễn viên')[:150], bio=row.get('bio') or ''))
        for row in data['movies']:
            def create_movie(row=row):
                return Movie.objects.create(title=(row.get('title') or 'Phim chưa đặt tên')[:200], slug=f"legacy-{self.prefix}-{row['id']}", description=row.get('description') or '', year=int(row.get('year') or 2026), country=(row.get('country') or '')[:100], kind='series' if row.get('type') == 'Phim bộ' else 'movie', published=row.get('status', 'active') == 'active')
            movie, created = self.mapped('movies', row, Movie, create_movie)
            movies[row['id']] = movie
            if created:
                if categories.get(row.get('category_id')):
                    movie.categories.add(categories[row['category_id']])
                created_at = old_time(row.get('created_at'))
                if created_at:
                    Movie.objects.filter(pk=movie.pk).update(created_at=created_at)
                for name in re.split(r'[,;\n]+', row.get('actors') or ''):
                    name = name.strip()[:150]
                    if name:
                        actor = Actor.objects.filter(name=name).first() or Actor.objects.create(name=name)
                        movie.actors.add(actor)
        for row in data['category_movie']:
            if row.get('movie_id') not in movies or row.get('category_id') not in categories:
                raise CommandError('Dangling movie/category relationship found in legacy data.')
            movies[row['movie_id']].categories.add(categories[row['category_id']])
        for row in data['episodes']:
            movie = movies.get(row.get('movie_id'))
            if movie is None:
                raise CommandError(f"Episode {row['id']} has no source movie.")
            self.mapped('episodes', row, Episode, lambda row=row, movie=movie: Episode.objects.create(movie=movie, number=max(1, int(row.get('episode_number') or 1)), title=(row.get('title') or f"Tập {row.get('episode_number', 1)}")[:200], source='', status='failed', error='Dữ liệu cũ dùng URL. Admin cần upload file video.'))
        # Legacy movies may use a URL directly without any episode row.
        for movie in movies.values():
            if not movie.episodes.exists():
                Episode.objects.create(movie=movie, number=1, title='Phim đầy đủ', source='', status='failed', error='Admin cần upload file video thay nguồn URL cũ.')
        for table, model in [('comments', Comment), ('ratings', Rating), ('watchlists', Watchlist), ('watch_histories', History)]:
            for row in data[table]:
                user, movie = users.get(row.get('user_id')), movies.get(row.get('movie_id'))
                if not user or not movie:
                    raise CommandError(f"{table}:{row['id']} has a dangling user/movie relationship.")
                def create_related(row=row, table=table, user=user, movie=movie):
                    if table == 'comments':
                        obj = Comment.objects.create(user=user, movie=movie, content=(row.get('content') or '')[:1000])
                        created_at = old_time(row.get('created_at'))
                        if created_at:
                            Comment.objects.filter(pk=obj.pk).update(created_at=created_at)
                        return obj
                    if table == 'ratings':
                        score = int(row.get('score') or 0)
                        if not 1 <= score <= 10:
                            raise CommandError('Legacy rating must be between 1 and 10.')
                        return Rating.objects.get_or_create(user=user, movie=movie, defaults={'score':math.ceil(score / 2)})[0]
                    if table == 'watchlists':
                        return Watchlist.objects.get_or_create(user=user, movie=movie)[0]
                    obj, created = History.objects.get_or_create(user=user, episode=movie.episodes.order_by('number').first(), defaults={'position':0})
                    watched_at = old_time(row.get('watched_at'))
                    if created and watched_at:
                        History.objects.filter(pk=obj.pk).update(updated_at=watched_at)
                    return obj
                self.mapped(table, row, model, create_related)
        return self.counts


class Command(BaseCommand):
    help = 'Dry-run Laravel MySQL import. Use --apply only after reviewing the report and backing up destination.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Commit destination writes. Default performs a rollback.')

    def handle(self, *args, **options):
        try:
            source, data = read_source()
            self.stdout.write('Source rows: ' + ', '.join(f'{table}={len(data[table])}' for table in TABLES))
            with transaction.atomic():
                counts = Importer(source).import_all(data)
                if not options['apply']:
                    transaction.set_rollback(True)
            mode = 'APPLIED' if options['apply'] else 'DRY RUN — rolled back'
            self.stdout.write(self.style.SUCCESS(f'{mode}: mapped={counts["created"]}, reused={counts["reused"]}, unknown-password={counts["unknown_password"]}'))
            self.stdout.write('No video URLs or sessions copied. Upload episode files and verify imported users before granting admin permissions.')
        except (pymysql.MySQLError, ValueError, ValidationError) as exc:
            raise CommandError(f'Import failed ({type(exc).__name__}); destination transaction rolled back. Verify schema and connection settings.') from None
