import uuid
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from .storage import PrivateVideoStorage
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from .search import normalize_search

private_storage = PrivateVideoStorage()

def video_path(instance, filename):
    return f'originals/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'

def avatar_path(instance, filename):
    return f'avatars/{uuid.uuid4().hex}.webp'

def validate_video(file):
    if file.size > settings.MAX_VIDEO_BYTES:
        raise ValidationError('Video vượt quá dung lượng cho phép.')

class User(AbstractUser):
    email = models.EmailField(unique=True)
    bio = models.CharField(max_length=500, blank=True)
    vip_until = models.DateTimeField(null=True, blank=True)
    avatar = models.ImageField(upload_to=avatar_path, blank=True)
    @property
    def is_vip(self):
        return self.is_active and bool(self.vip_until and self.vip_until > timezone.now())

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    def __str__(self): return self.name

class SearchableModel(models.Model):
    """Keep derived search fields in sync without changing partial-save semantics."""
    search_sources = {}

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        requested = set(update_fields) if update_fields is not None else None
        deferred = self.get_deferred_fields()
        derived = set()
        for target, source in self.search_sources.items():
            should_update = source not in deferred if requested is None else bool({source, target} & requested)
            if should_update:
                setattr(self, target, normalize_search(getattr(self, source)))
                derived.add(target)
        if requested is not None:
            kwargs['update_fields'] = requested | derived
        return super().save(*args, **kwargs)


class Actor(SearchableModel):
    name = models.CharField(max_length=150)
    bio = models.TextField(blank=True)
    search_name = models.CharField(max_length=450, blank=True, editable=False, db_index=True)
    search_sources = {'search_name': 'name'}
    def __str__(self): return self.name

class Movie(SearchableModel):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    poster = models.ImageField(upload_to='posters/', blank=True)
    backdrop = models.ImageField(upload_to='backdrops/', blank=True, help_text='Ảnh ngang dùng cho trang chủ và trang chi tiết phim.')
    artwork = models.CharField(max_length=40, default='orbit', help_text='Tên artwork minh họa trong static/art/')
    categories = models.ManyToManyField(Category, blank=True)
    actors = models.ManyToManyField(Actor, blank=True)
    year = models.PositiveIntegerField(default=2026)
    country = models.CharField(max_length=100, default='Việt Nam')
    kind = models.CharField(max_length=20, choices=[('movie', 'Phim lẻ'), ('series', 'Phim bộ')], default='movie')
    is_vip = models.BooleanField(default=False)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    search_title = models.CharField(max_length=600, blank=True, editable=False, db_index=True)
    search_description = models.TextField(blank=True, editable=False)
    search_sources = {'search_title': 'title', 'search_description': 'description'}
    class Meta: ordering = ['-created_at']
    def __str__(self): return self.title

class Episode(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='episodes')
    number = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200)
    source = models.FileField(storage=private_storage, upload_to=video_path, validators=[FileExtensionValidator(['mp4', 'mkv', 'mov', 'webm']), validate_video])
    asset_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=[('pending', 'Chờ xử lý'), ('processing', 'Đang xử lý'), ('ready', 'Sẵn sàng'), ('failed', 'Lỗi')], default='pending')
    duration = models.FloatField(default=0)
    error = models.CharField(max_length=500, blank=True)
    class Meta:
        ordering = ['number']
        constraints = [models.UniqueConstraint(fields=['movie', 'number'], name='unique_episode')]
    def __str__(self): return f'{self.movie} — {self.number}'

class Watchlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    class Meta: constraints = [models.UniqueConstraint(fields=['user', 'movie'], name='unique_watchlist')]

class History(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE)
    position = models.FloatField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-updated_at']
        constraints = [models.UniqueConstraint(fields=['user', 'episode'], name='unique_history')]

class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='comments')
    content = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']

class Rating(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='ratings')
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    class Meta: constraints = [models.UniqueConstraint(fields=['user', 'movie'], name='unique_rating')]

class Report(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE)
    description = models.CharField(max_length=1000)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class Plan(models.Model):
    name = models.CharField(max_length=100)
    price = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    days = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    active = models.BooleanField(default=True)
    def __str__(self): return self.name

class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    amount = models.PositiveIntegerField()
    days = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default='pending', choices=[('pending', 'Chờ thanh toán'), ('paid', 'Đã thanh toán'), ('failed', 'Không thành công')])
    transaction_no = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host = models.ForeignKey(User, on_delete=models.CASCADE)
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    position = models.FloatField(default=0)
    playing = models.BooleanField(default=False)
    updated_at = models.DateTimeField(default=timezone.now)
    closed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class Membership(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    banned = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(default=timezone.now)
    class Meta: constraints = [models.UniqueConstraint(fields=['room', 'user'], name='unique_membership')]

class Chat(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

class LegacyRecord(models.Model):
    source = models.CharField(max_length=150)
    table = models.CharField(max_length=40)
    source_id = models.PositiveBigIntegerField()
    target_id = models.PositiveBigIntegerField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source', 'table', 'source_id'], name='unique_legacy_record')]
