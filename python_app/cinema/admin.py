from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import BooleanField, Count

from .models import Actor, Category, Comment, Episode, Movie, Order, Plan, Rating, Report, Room, Subtitle, User
from .subtitles import normalize_subtitle


class LocalizedAdminMixin:
    """Present editor labels without changing model/database metadata."""
    model_label = ''
    model_label_plural = ''
    field_labels = {}
    field_help = {}
    list_per_page = 25
    empty_value_display = '—'

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Supply metadata while Django constructs fields. Editing base_fields
        # later is lost when upload-validation forms subclass the ModelForm.
        if db_field.name in self.field_labels:
            kwargs['label'] = self.field_labels[db_field.name]
        if db_field.name in self.field_help:
            kwargs['help_text'] = self.field_help[db_field.name]
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_list_filter(self, request):
        filters = []
        for entry in super().get_list_filter(request):
            if not isinstance(entry, str) or entry not in self.field_labels:
                filters.append(entry)
                continue
            field = self.model._meta.get_field(entry)
            base = admin.BooleanFieldListFilter if isinstance(field, BooleanField) else (
                admin.ChoicesFieldListFilter if field.choices else admin.AllValuesFieldListFilter)
            label = self.field_labels[entry]
            def build_filter(filter_base, title):
                class NamedFilter(filter_base):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.title = title
                return NamedFilter
            filters.append((entry, build_filter(base, label)))
        return filters

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            callback, name, _ = actions['delete_selected']
            actions['delete_selected'] = (callback, name, 'Xóa các bản ghi đã chọn')
        return actions

    def changelist_view(self, request, extra_context=None):
        context = {'title': self.model_label_plural or self.model_label}
        context.update(extra_context or {})
        return super().changelist_view(request, extra_context=context)

    def add_view(self, request, form_url='', extra_context=None):
        context = {'title': f'Thêm {self.model_label.lower()}'}
        context.update(extra_context or {})
        return super().add_view(request, form_url=form_url, extra_context=context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        context = {'title': f'Chỉnh sửa {self.model_label.lower()}'}
        context.update(extra_context or {})
        return super().change_view(request, object_id, form_url=form_url, extra_context=context)


@admin.register(User)
class CustomUserAdmin(LocalizedAdminMixin, UserAdmin):
    model_label = 'Tài khoản'
    model_label_plural = 'Tài khoản'
    field_labels = {'bio': 'Giới thiệu', 'vip_until': 'VIP có hiệu lực đến'}
    fieldsets = UserAdmin.fieldsets + (('Quyền lợi Lumière', {'fields': ('bio', 'vip_until')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Liên hệ', {'fields': ('email',)}),)

@admin.register(Movie)
class MovieAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Phim'
    model_label_plural = 'Phim'
    list_display = ('movie_title', 'release_year', 'movie_kind', 'imdb_score', 'cinema_release', 'vip_only', 'is_published')
    list_filter = ('is_vip', 'is_cinema_release', 'published', 'kind', 'country', 'year')
    search_fields = ('title', 'imdb_id')
    search_help_text = 'Tìm theo tên phim hoặc mã IMDb.'
    prepopulated_fields = {'slug': ('title',)}
    autocomplete_fields = ('categories', 'actors')
    field_labels = {
        'title': 'Tên phim', 'slug': 'Đường dẫn', 'description': 'Giới thiệu phim',
        'poster': 'Ảnh bìa', 'backdrop': 'Ảnh nền', 'artwork': 'Ảnh minh họa dự phòng',
        'categories': 'Thể loại', 'actors': 'Diễn viên', 'year': 'Năm phát hành',
        'country': 'Quốc gia', 'kind': 'Loại phim', 'is_vip': 'Dành cho thành viên VIP',
        'published': 'Hiển thị trong thư viện',
    }
    field_help = {
        'slug': 'Tự tạo từ tên phim; dùng chữ thường, số và dấu gạch nối.',
        'poster': 'Ảnh dọc hiển thị trên thẻ phim.',
        'artwork': 'Giữ mặc định nếu đã có ảnh bìa và ảnh nền.',
        'categories': 'Gõ tên để tìm và chọn một hoặc nhiều thể loại.',
        'actors': 'Gõ tên để tìm và chọn diễn viên trong phim.',
        'published': 'Bật khi thông tin phim đã sẵn sàng để người dùng khám phá.',
    }
    fieldsets = (
        ('Thông tin cơ bản', {'fields': ('title', 'slug', 'description', ('kind', 'year', 'country')), 'classes': ('studio-basic',)}),
        ('Hình ảnh', {'fields': ('poster', 'backdrop', 'artwork'), 'classes': ('studio-artwork',)}),
        ('Thể loại và diễn viên', {'fields': ('categories', 'actors'), 'classes': ('studio-relations',)}),
        ('Trailer', {'fields': ('trailer_url', 'trailer_file', 'trailer_credit'), 'description': 'Chọn một nguồn trailer: liên kết YouTube hoặc file MP4.', 'classes': ('studio-trailer',)}),
        ('Điểm IMDb', {'fields': ('imdb_id', ('imdb_rating', 'imdb_rating_checked_at')), 'classes': ('studio-imdb',)}),
        ('Xuất bản và quyền xem', {'fields': ('published', 'is_vip', 'is_cinema_release'), 'classes': ('studio-publishing',)}),
    )

    @admin.display(description='Tên phim', ordering='title')
    def movie_title(self, obj): return obj.title

    @admin.display(description='Năm', ordering='year')
    def release_year(self, obj): return obj.year

    @admin.display(description='Loại phim', ordering='kind')
    def movie_kind(self, obj): return obj.get_kind_display()

    @admin.display(description='IMDb', ordering='imdb_rating')
    def imdb_score(self, obj): return obj.imdb_rating

    @admin.display(description='Chiếu rạp', boolean=True, ordering='is_cinema_release')
    def cinema_release(self, obj): return obj.is_cinema_release

    @admin.display(description='VIP', boolean=True, ordering='is_vip')
    def vip_only(self, obj): return obj.is_vip

    @admin.display(description='Đã xuất bản', boolean=True, ordering='published')
    def is_published(self, obj): return obj.published

    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, **kwargs)
        class UploadCheckedForm(base):
            def clean(self):
                cleaned = super().clean()
                if getattr(request, '_trailer_upload_error', None):
                    raise forms.ValidationError(request._trailer_upload_error)
                return cleaned
        return UploadCheckedForm


@admin.register(Episode)
class EpisodeAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Tập phim'
    model_label_plural = 'Tập phim và video'
    list_display = ('episode_title', 'movie_name', 'episode_number', 'processing_state', 'duration_display')
    list_select_related = ('movie',)
    list_filter = ('status',)
    search_fields = ('movie__title', 'title')
    search_help_text = 'Tìm theo tên phim hoặc tên tập.'
    autocomplete_fields = ('movie',)
    readonly_fields = ('asset_identifier', 'processing_state', 'duration_display', 'processing_error')
    field_labels = {'movie': 'Phim', 'number': 'Số tập', 'title': 'Tên tập phim', 'source': 'File phim gốc', 'status': 'Trạng thái'}
    field_help = {'source': 'Chọn MP4, MKV, MOV hoặc WebM. Video được lưu riêng tư và xử lý trước khi phát.'}

    def get_fieldsets(self, request, obj=None):
        sections = [('Thông tin tập phim', {'fields': ('movie', ('number', 'title'))})]
        if not obj or not obj.source:
            sections.append(('Tải video', {'fields': ('source',)}))
        sections.append(('Trạng thái xử lý', {'fields': ('processing_state', 'duration_display', 'processing_error', 'asset_identifier')}))
        return sections

    @admin.display(description='Tên tập phim', ordering='title')
    def episode_title(self, obj): return obj.title

    @admin.display(description='Phim', ordering='movie__title')
    def movie_name(self, obj): return obj.movie.title

    @admin.display(description='Tập', ordering='number')
    def episode_number(self, obj): return obj.number

    @admin.display(description='Trạng thái', ordering='status')
    def processing_state(self, obj): return obj.get_status_display()

    @admin.display(description='Thời lượng', ordering='duration')
    def duration_display(self, obj):
        minutes, seconds = divmod(max(0, round(obj.duration)), 60)
        return f'{minutes}:{seconds:02d}' if obj.duration else 'Chưa có'

    @admin.display(description='Thông báo xử lý')
    def processing_error(self, obj): return obj.error or 'Không có lỗi'

    @admin.display(description='Mã video')
    def asset_identifier(self, obj): return str(obj.asset_id)

    def save_model(self, request, obj, form, change):
        if 'source' in form.changed_data:
            obj.status = 'pending'
            obj.error = ''
        super().save_model(request, obj, form, change)

    # Original file URLs are never rendered; replacement requires a new episode.
    def get_exclude(self, request, obj=None): return ('source',) if obj and obj.source else ()


class SubtitleAdminForm(forms.ModelForm):
    upload_file = forms.FileField(
        label='File phụ đề', required=False,
        help_text='SRT hoặc WebVTT UTF-8, tối đa 2 MB. Thêm mới cần file; khi sửa có thể giữ nguyên file hiện tại.',
    )

    class Meta:
        model = Subtitle
        fields = ('episode', 'language', 'label')

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get('upload_file')
        if upload:
            try:
                self.instance.content = normalize_subtitle(upload)
            except forms.ValidationError as error:
                self.add_error('upload_file', error)
        elif not self.instance.pk or not self.instance.content:
            self.add_error('upload_file', 'Chọn file SRT hoặc VTT cho phụ đề mới.')
        return cleaned


@admin.register(Subtitle)
class SubtitleAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Phụ đề'
    model_label_plural = 'Phụ đề'
    form = SubtitleAdminForm
    list_display = ('episode', 'language', 'label')
    list_select_related = ('episode__movie',)
    list_filter = ('language',)
    search_fields = ('episode__movie__title', 'label')
    autocomplete_fields = ('episode',)

    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, **kwargs)
        class UploadCheckedForm(base):
            def clean(self):
                cleaned = super().clean()
                if getattr(request, '_subtitle_upload_error', None):
                    raise forms.ValidationError(request._subtitle_upload_error)
                return cleaned
        return UploadCheckedForm


@admin.register(Order)
class OrderAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Giao dịch'
    model_label_plural = 'Giao dịch'
    list_display = ('order_reference', 'customer', 'plan_name', 'total_amount', 'payment_status', 'created_time')
    list_select_related = ('user', 'plan')
    list_filter = ('status',)
    search_fields = ('id', 'user__username', 'user__email', 'transaction_no')
    readonly_fields = tuple(f.name for f in Order._meta.fields) + ('full_reference', 'customer', 'plan_name', 'total_amount', 'term_days', 'payment_status', 'transaction_reference', 'created_time', 'paid_time')
    fieldsets = (
        ('Thông tin giao dịch', {'fields': ('full_reference', 'customer', 'plan_name', 'total_amount', 'term_days', 'payment_status')}),
        ('Đối soát thanh toán', {'fields': ('transaction_reference', 'created_time', 'paid_time')}),
    )
    field_labels = {'user': 'Khách hàng', 'plan': 'Gói thành viên', 'amount': 'Số tiền', 'days': 'Số ngày sử dụng', 'status': 'Trạng thái', 'transaction_no': 'Mã giao dịch VNPay', 'created_at': 'Ngày tạo', 'paid_at': 'Ngày thanh toán'}

    @admin.display(description='Mã đơn', ordering='id')
    def order_reference(self, obj): return str(obj.pk)[:8].upper()

    @admin.display(description='Mã đơn đầy đủ')
    def full_reference(self, obj): return str(obj.pk)

    @admin.display(description='Khách hàng', ordering='user__username')
    def customer(self, obj): return obj.user.username

    @admin.display(description='Gói thành viên', ordering='plan__name')
    def plan_name(self, obj): return obj.plan.name

    @admin.display(description='Số tiền', ordering='amount')
    def total_amount(self, obj): return f'{obj.amount:,}'.replace(',', '.') + ' ₫'

    @admin.display(description='Trạng thái', ordering='status')
    def payment_status(self, obj): return obj.get_status_display()

    @admin.display(description='Ngày tạo', ordering='created_at')
    def created_time(self, obj): return obj.created_at

    @admin.display(description='Số ngày sử dụng')
    def term_days(self, obj): return obj.days

    @admin.display(description='Mã giao dịch VNPay')
    def transaction_reference(self, obj): return obj.transaction_no or 'Chưa có'

    @admin.display(description='Ngày thanh toán')
    def paid_time(self, obj): return obj.paid_at

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(Category)
class CategoryAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Thể loại'
    model_label_plural = 'Thể loại'
    list_display = ('display_name', 'path_slug', 'movie_count')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    field_labels = {'name': 'Tên thể loại', 'slug': 'Đường dẫn'}

    def get_queryset(self, request): return super().get_queryset(request).annotate(_movie_count=Count('movie', distinct=True))

    @admin.display(description='Thể loại', ordering='name')
    def display_name(self, obj): return obj.name

    @admin.display(description='Đường dẫn', ordering='slug')
    def path_slug(self, obj): return obj.slug

    @admin.display(description='Số phim', ordering='_movie_count')
    def movie_count(self, obj): return obj._movie_count


@admin.register(Actor)
class ActorAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Diễn viên'
    model_label_plural = 'Diễn viên'
    list_display = ('display_name', 'movie_count', 'biography')
    search_fields = ('name',)
    field_labels = {'name': 'Tên diễn viên', 'bio': 'Tiểu sử'}

    def get_queryset(self, request): return super().get_queryset(request).annotate(_movie_count=Count('movie', distinct=True))

    @admin.display(description='Diễn viên', ordering='name')
    def display_name(self, obj): return obj.name

    @admin.display(description='Số phim', ordering='_movie_count')
    def movie_count(self, obj): return obj._movie_count

    @admin.display(description='Tiểu sử')
    def biography(self, obj): return obj.bio[:120] + ('…' if len(obj.bio) > 120 else '')


@admin.register(Comment)
class CommentAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Bình luận'
    model_label_plural = 'Bình luận'
    list_display = ('short_content', 'movie_name', 'author', 'created_time')
    list_select_related = ('user', 'movie')
    search_fields = ('content', 'movie__title', 'user__username')
    readonly_fields = ('created_time',)
    fields = ('user', 'movie', 'content', 'created_time')
    field_labels = {'user': 'Người dùng', 'movie': 'Phim', 'content': 'Nội dung bình luận'}

    @admin.display(description='Bình luận')
    def short_content(self, obj): return obj.content[:100] + ('…' if len(obj.content) > 100 else '')

    @admin.display(description='Phim', ordering='movie__title')
    def movie_name(self, obj): return obj.movie.title

    @admin.display(description='Người dùng', ordering='user__username')
    def author(self, obj): return obj.user.username

    @admin.display(description='Ngày gửi', ordering='created_at')
    def created_time(self, obj): return obj.created_at


@admin.register(Rating)
class RatingAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Đánh giá'
    model_label_plural = 'Đánh giá'
    list_display = ('movie_name', 'author', 'rating_score')
    list_select_related = ('user', 'movie')
    list_filter = ('score',)
    search_fields = ('movie__title', 'user__username')
    field_labels = {'user': 'Người dùng', 'movie': 'Phim', 'score': 'Điểm đánh giá (1–5)'}

    @admin.display(description='Phim', ordering='movie__title')
    def movie_name(self, obj): return obj.movie.title

    @admin.display(description='Người dùng', ordering='user__username')
    def author(self, obj): return obj.user.username

    @admin.display(description='Điểm / 5', ordering='score')
    def rating_score(self, obj): return obj.score


@admin.register(Report)
class ReportAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Báo lỗi'
    model_label_plural = 'Báo lỗi video'
    list_display = ('report_text', 'episode_name', 'reporter', 'is_resolved', 'created_time')
    list_select_related = ('user', 'episode__movie')
    list_filter = ('resolved',)
    search_fields = ('description', 'episode__movie__title', 'user__username')
    readonly_fields = ('created_time',)
    fields = ('user', 'episode', 'description', 'resolved', 'created_time')
    field_labels = {'user': 'Người báo lỗi', 'episode': 'Tập phim', 'description': 'Mô tả vấn đề', 'resolved': 'Đã xử lý'}

    @admin.display(description='Nội dung báo lỗi')
    def report_text(self, obj): return obj.description[:100] + ('…' if len(obj.description) > 100 else '')

    @admin.display(description='Tập phim', ordering='episode__movie__title')
    def episode_name(self, obj): return str(obj.episode)

    @admin.display(description='Người gửi', ordering='user__username')
    def reporter(self, obj): return obj.user.username

    @admin.display(description='Đã xử lý', boolean=True, ordering='resolved')
    def is_resolved(self, obj): return obj.resolved

    @admin.display(description='Ngày gửi', ordering='created_at')
    def created_time(self, obj): return obj.created_at


@admin.register(Plan)
class PlanAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Gói VIP'
    model_label_plural = 'Gói VIP'
    list_display = ('plan_name', 'price_display', 'duration_days', 'is_available')
    list_filter = ('active',)
    search_fields = ('name',)
    field_labels = {'name': 'Tên gói', 'price': 'Giá (VNĐ)', 'days': 'Số ngày sử dụng', 'active': 'Đang mở bán'}

    @admin.display(description='Gói VIP', ordering='name')
    def plan_name(self, obj): return obj.name

    @admin.display(description='Giá', ordering='price')
    def price_display(self, obj): return f'{obj.price:,}'.replace(',', '.') + ' ₫'

    @admin.display(description='Thời hạn (ngày)', ordering='days')
    def duration_days(self, obj): return obj.days

    @admin.display(description='Đang mở bán', boolean=True, ordering='active')
    def is_available(self, obj): return obj.active


@admin.register(Room)
class RoomAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Phòng xem'
    model_label_plural = 'Phòng xem chung'
    list_display = ('room_name', 'host_name', 'movie_name', 'is_closed', 'is_playing', 'created_time')
    list_select_related = ('host', 'episode__movie')
    list_filter = ('closed', 'playing')
    search_fields = ('name', 'host__username', 'episode__movie__title')
    readonly_fields = ('created_time',)
    fields = ('name', 'host', 'episode', 'closed', 'playing', 'position', 'created_time')
    field_labels = {'name': 'Tên phòng', 'host': 'Chủ phòng', 'episode': 'Tập phim', 'closed': 'Đã đóng phòng', 'playing': 'Đang phát', 'position': 'Vị trí phát (giây)'}

    @admin.display(description='Phòng xem', ordering='name')
    def room_name(self, obj): return obj.name

    @admin.display(description='Chủ phòng', ordering='host__username')
    def host_name(self, obj): return obj.host.username

    @admin.display(description='Phim', ordering='episode__movie__title')
    def movie_name(self, obj): return obj.episode.movie.title

    @admin.display(description='Đã đóng', boolean=True, ordering='closed')
    def is_closed(self, obj): return obj.closed

    @admin.display(description='Đang phát', boolean=True, ordering='playing')
    def is_playing(self, obj): return obj.playing

    @admin.display(description='Ngày tạo', ordering='created_at')
    def created_time(self, obj): return obj.created_at


admin.site.site_header = 'Lumière • Quản trị'
admin.site.site_title = 'Lumière Studio'
