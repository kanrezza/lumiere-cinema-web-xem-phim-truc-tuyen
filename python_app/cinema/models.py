import uuid
import re
from decimal import Decimal, InvalidOperation
from datetime import date
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from .storage import PrivateVideoStorage
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from .search import normalize_search
from .trailers import validate_trailer_file, validate_youtube_url, youtube_embed_url
from .subtitles import subtitle_language_validator

private_storage = PrivateVideoStorage()

def video_path(instance, filename):
    return f'originals/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'

def avatar_path(instance, filename):
    return f'avatars/{uuid.uuid4().hex}.webp'

def trailer_path(instance, filename):
    return f'trailers/{uuid.uuid4().hex}.mp4'

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
    imdb_id = models.CharField('Mã phim IMDb', max_length=12, blank=True, validators=[RegexValidator(r'\Att[0-9]{7,10}\Z', 'Nhập mã IMDb như tt1254207, không dán URL.')], help_text='Mã title trên IMDb. Liên kết nguồn được tạo từ mã này.')
    imdb_rating = models.DecimalField('Điểm IMDb', max_digits=3, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(Decimal('1.0')), MaxValueValidator(Decimal('10.0'))], help_text='Điểm 1,0–10,0 do quản trị đối chiếu từ IMDb; để trống nếu chưa có dữ liệu.')
    imdb_rating_checked_at = models.DateField('Ngày đối chiếu điểm IMDb', null=True, blank=True)
    is_cinema_release = models.BooleanField('Phim chiếu rạp', default=False, help_text='Phân loại phim điện ảnh; không khẳng định phim hiện đang chiếu ngoài rạp.')
    trailer_url = models.URLField('Liên kết trailer YouTube', max_length=500, blank=True, validators=[validate_youtube_url], help_text='Chọn liên kết YouTube HTTPS hoặc upload MP4 bên dưới, không dùng đồng thời cả hai.')
    trailer_file = models.FileField('File trailer MP4', upload_to=trailer_path, blank=True, validators=[FileExtensionValidator(['mp4']), validate_trailer_file], help_text='Trailer công khai, tối đa 50 MB / 5 phút, MP4 H.264 và AAC. Video phim đầy đủ vẫn upload ở Tập phim và lưu riêng tư.')
    trailer_credit = models.CharField('Nguồn/ghi công trailer', max_length=500, blank=True, help_text='Ghi tác giả, nguồn và giấy phép sử dụng trailer nếu cần; chỉ nhập văn bản hoặc liên kết, không nhập HTML.')
    is_vip = models.BooleanField(default=False)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    search_title = models.CharField(max_length=600, blank=True, editable=False, db_index=True)
    search_description = models.TextField(blank=True, editable=False)
    search_sources = {'search_title': 'title', 'search_description': 'description'}
    class Meta: ordering = ['-created_at']
    def __str__(self): return self.title

    def clean(self):
        super().clean()
        errors = {}
        if self.trailer_url and self.trailer_file:
            errors.update({'trailer_url': 'Chỉ chọn một nguồn trailer: YouTube hoặc file MP4.', 'trailer_file': 'Xóa nguồn còn lại trước khi lưu.'})
        if self.imdb_rating is not None and not self.imdb_url:
            errors['imdb_id'] = 'Cần mã IMDb hợp lệ để xác định nguồn điểm.'
        if self.imdb_rating_checked_at:
            if self.imdb_rating is None:
                errors['imdb_rating_checked_at'] = 'Chỉ nhập ngày đối chiếu khi có điểm IMDb.'
            elif isinstance(self.imdb_rating_checked_at, date) and self.imdb_rating_checked_at > timezone.localdate():
                errors['imdb_rating_checked_at'] = 'Ngày đối chiếu không được ở tương lai.'
        if errors:
            raise ValidationError(errors)

    @property
    def imdb_url(self):
        return f'https://www.imdb.com/title/{self.imdb_id}/' if isinstance(self.imdb_id, str) and re.fullmatch(r'tt[0-9]{7,10}', self.imdb_id) else ''

    @property
    def has_imdb_rating(self):
        try:
            score = Decimal(str(self.imdb_rating))
            return bool(self.imdb_url and score.is_finite() and Decimal('1') <= score <= Decimal('10'))
        except (InvalidOperation, ValueError, TypeError):
            return False

    @property
    def trailer_embed_url(self):
        return youtube_embed_url(self.trailer_url)

    @property
    def has_trailer(self):
        return bool(self.trailer_file or self.trailer_embed_url)

    @property
    def trailer_source_kind(self):
        return 'file' if self.trailer_file else ('youtube' if self.trailer_embed_url else '')

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

class Subtitle(models.Model):
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='subtitles', verbose_name='Tập phim')
    language = models.CharField('Mã ngôn ngữ', max_length=35, validators=[subtitle_language_validator], help_text='Ví dụ: vi, en hoặc en-US.')
    label = models.CharField('Tên hiển thị', max_length=80, help_text='Ví dụ: Tiếng Việt hoặc English.')
    content = models.TextField('WebVTT đã chuẩn hóa', editable=False)

    class Meta:
        ordering = ['language', 'pk']
        constraints = [models.UniqueConstraint(fields=['episode', 'language'], name='unique_episode_subtitle_language')]
        verbose_name = 'Phụ đề'
        verbose_name_plural = 'Phụ đề'

    def clean(self):
        super().clean()
        self.language = self.language.strip().lower()
        self.label = self.label.strip()
        if not self.label or any(ord(char) < 32 for char in self.label) or '<' in self.label or '>' in self.label:
            raise ValidationError({'label': 'Tên phụ đề cần là văn bản thuần, không chứa mã HTML hoặc ký tự điều khiển.'})

    def __str__(self):
        return f'{self.episode} · {self.label}'

class Watchlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    class Meta: constraints = [models.UniqueConstraint(fields=['user', 'movie'], name='unique_watchlist')]

class History(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE)
    position = models.FloatField(default=0)
    hidden_from_continue = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-updated_at']
        constraints = [models.UniqueConstraint(fields=['user', 'episode'], name='unique_history')]

class Comment(models.Model):
    class Status(models.TextChoices):
        PUBLISHED = 'published', 'Đang hiển thị'
        PENDING = 'pending', 'Chờ duyệt'
        HIDDEN = 'hidden', 'Đã ẩn'

    class Reason(models.TextChoices):
        REGIONAL = 'regional', 'Phân biệt vùng miền'
        COUNTRY_PARTY = 'country_party', 'Xúc phạm đất nước hoặc tổ chức chính trị'
        HARASSMENT = 'harassment', 'Công kích, quấy rối'
        SENSITIVE = 'sensitive', 'Nội dung nhạy cảm'
        PROFANITY = 'profanity', 'Chửi bới, tục tĩu'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='comments')
    content = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    moderation_status = models.CharField(max_length=12, choices=Status.choices, default=Status.PUBLISHED, db_index=True)
    moderation_reason = models.CharField(max_length=16, choices=Reason.choices, blank=True, default='')
    moderation_matches = models.JSONField(default=dict, editable=False)
    class Meta: ordering = ['-created_at']

    def save(self, *args, **kwargs):
        from .moderation import classify_comment_v1

        fields = kwargs.get('update_fields')
        if fields is None or 'content' in fields:
            previous = None
            if not self._state.adding:
                comments = type(self).objects.using(kwargs.get('using') or self._state.db)
                previous = comments.filter(pk=self.pk).values_list('content', 'moderation_status').first()
            if previous is None or previous[0] != self.content:
                self.moderation_matches = classify_comment_v1(self.content)
                self.moderation_reason = next(iter(self.moderation_matches), '')
                if self.moderation_matches and self.moderation_status != self.Status.HIDDEN:
                    self.moderation_status = self.Status.PENDING
                elif previous and previous[1] == self.Status.PENDING and self.moderation_status == self.Status.PENDING:
                    self.moderation_status = self.Status.PUBLISHED
                if fields is not None:
                    kwargs['update_fields'] = set(fields) | {'moderation_status', 'moderation_reason', 'moderation_matches'}
        super().save(*args, **kwargs)

class Rating(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='ratings')
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    updated_at = models.DateTimeField(auto_now=True, null=True)
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
    password_hash = models.CharField(max_length=128, blank=True, editable=False)
    requires_approval = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class RoomJoinRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Chờ duyệt'
        APPROVED = 'approved', 'Đã duyệt'
        REJECTED = 'rejected', 'Từ chối'

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='join_requests')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['room', 'user'], name='unique_room_join_request')]
        indexes = [models.Index(fields=['room', 'status', 'created_at'], name='room_approval_queue_idx')]

class Membership(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    banned = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(default=timezone.now)
    voice_session = models.UUIDField(null=True, blank=True, editable=False)
    voice_seen_at = models.DateTimeField(null=True, blank=True, editable=False)
    voice_mic_on = models.BooleanField(default=False, editable=False)
    voice_host_muted = models.BooleanField(default=False, editable=False)
    class Meta: constraints = [models.UniqueConstraint(fields=['room', 'user'], name='unique_membership')]


class RoomVoiceSignal(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    sender_session = models.UUIDField()
    recipient_session = models.UUIDField()
    kind = models.CharField(max_length=9)
    payload = models.JSONField()
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=['room', 'recipient', 'recipient_session', 'id'], name='room_voice_pending_idx')]


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


class SubtitleTranslation(models.Model):
    """Versioned, private translations never overwrite a curated subtitle."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subtitle = models.ForeignKey(Subtitle, on_delete=models.CASCADE, related_name='translations')
    source_hash = models.CharField(max_length=64, editable=False)
    source_language = models.CharField(max_length=35, editable=False)
    target_language = models.CharField(max_length=35, editable=False)
    provider_key = models.CharField(max_length=64, editable=False)
    source_content = models.TextField(editable=False)
    content = models.TextField(blank=True, editable=False)
    status = models.CharField(max_length=12, default='pending', choices=[('pending', 'Đang chờ'), ('processing', 'Đang dịch'), ('ready', 'Sẵn sàng'), ('failed', 'Lỗi')])
    error = models.CharField(max_length=300, blank=True)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [models.UniqueConstraint(fields=['subtitle', 'source_hash', 'target_language', 'provider_key'], name='unique_subtitle_translation_version')]


class SubtitleTranscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='transcriptions')
    source_key = models.CharField(max_length=64, editable=False)
    language = models.CharField(max_length=12, default='auto')
    detected_language = models.CharField(max_length=35, blank=True)
    status = models.CharField(max_length=12, default='pending', choices=[('pending', 'Đang chờ'), ('processing', 'Đang nhận dạng'), ('ready', 'Sẵn sàng'), ('failed', 'Lỗi')])
    subtitle = models.ForeignKey(Subtitle, on_delete=models.SET_NULL, null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [models.UniqueConstraint(fields=['episode', 'source_key', 'language'], name='unique_episode_transcription_version')]


class SecurityEvent(models.Model):
    class Action(models.TextChoices):
        OBSERVED = 'observed', 'Cảnh báo'
        BLOCKED = 'blocked', 'Đã chặn'

    class Reason(models.TextChoices):
        UNSAFE_PATH = 'unsafe_path', 'Đường dẫn không hợp lệ'
        REQUEST_TARGET = 'request_target', 'Địa chỉ yêu cầu vượt giới hạn'
        INVALID_METHOD = 'invalid_method', 'Phương thức không được hỗ trợ'
        RATE_LIMIT = 'rate_limit', 'Vượt giới hạn tần suất POST'
        ROUTE_MISS_BURST = 'route_miss_burst', 'Nhiều yêu cầu đến đường dẫn không khả dụng'
        QUERY_ANOMALY = 'query_anomaly', 'Chuỗi truy vấn khác thường'
        BEHAVIOR_ANOMALY = 'behavior_anomaly', 'Nhiều tín hiệu bất thường cùng nguồn'
        BEHAVIOR_COOLDOWN = 'behavior_cooldown', 'Giảm tốc do hành vi bất thường'

    class Area(models.TextChoices):
        AUTH = 'auth', 'Tài khoản'
        STUDIO = 'studio', 'Quản trị'
        CATALOG = 'catalog', 'Danh mục'
        VIEWING = 'viewing', 'Xem phim'
        ROOM = 'room', 'Phòng xem'
        PAYMENT = 'payment', 'Thanh toán'
        ASSET = 'asset', 'Tài nguyên'
        OTHER = 'other', 'Khác'

    class Signal(models.TextChoices):
        LENGTH = 'length', 'Truy vấn dài hiếm gặp'
        FIELD_COUNT = 'field_count', 'Số trường truy vấn hiếm gặp'
        COMBINATION = 'combination', 'Độ dài và số trường hiếm khi xuất hiện cùng nhau'
        ROUTE_MISSES = 'route_misses', 'Đường dẫn không khả dụng'
        RULE_MATCHES = 'rule_matches', 'Yêu cầu khớp quy tắc WAF'
        DENIED = 'denied', 'Yêu cầu bị từ chối quyền truy cập'
        LOGIN_FAILURES = 'login_failures', 'Lần đăng nhập thất bại'
        QUERY_ANOMALIES = 'query_anomalies', 'Truy vấn có điểm bất thường cao'
        AREAS = 'areas', 'Khu vực có hoạt động bất thường'

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(max_length=8, choices=Action.choices)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    area = models.CharField(max_length=8, choices=Area.choices)
    method = models.CharField(max_length=8)
    source = models.CharField(max_length=16)
    risk_score = models.PositiveSmallIntegerField(null=True, blank=True)
    baseline_samples = models.PositiveIntegerField(null=True, blank=True)
    signals = models.JSONField(default=list, blank=True)
    behavior_metadata = models.JSONField(default=dict, blank=True)

    @property
    def model_signal_labels(self):
        return [signal.label for signal in self.Signal if signal.value in self.signals]

    @property
    def behavior_evidence(self):
        return [
            (signal.label, count)
            for signal in self.Signal
            if (count := self.behavior_metadata.get(signal.value, 0)) > 0
        ]

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.CheckConstraint(condition=models.Q(risk_score__lte=100), name='waf_risk_score_max_100')]
        indexes = [models.Index(fields=['source', '-created_at'], name='waf_source_time_idx')]
