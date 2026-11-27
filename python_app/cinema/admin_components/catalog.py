"""Film, episode, genre and actor editing."""
from django.contrib import admin

from .common import LocalizedAdminMixin, MovieCountAdminMixin, UploadValidationAdminMixin, preview_text
from .readiness import ContentHealthFilter


class MovieAdmin(UploadValidationAdminMixin, LocalizedAdminMixin, admin.ModelAdmin):
    upload_error_attribute = '_trailer_upload_error'
    model_label = 'Phim'
    model_label_plural = 'Phim'
    list_display = ('movie_title', 'release_year', 'movie_kind', 'imdb_score', 'cinema_release', 'vip_only', 'is_published')
    list_filter = (ContentHealthFilter, 'is_vip', 'is_cinema_release', 'published', 'kind', 'country', 'year')
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
        fields = set(form.changed_data)
        if 'source' in fields:
            obj.status = 'pending'
            obj.error = ''
            fields.update(('status', 'error'))
        if not change:
            super().save_model(request, obj, form, change)
        elif fields:
            # A metadata form can remain open while FFmpeg updates status and duration.
            obj.save(update_fields=fields)

    # Original file URLs are never rendered; replacement requires a new episode.
    def get_exclude(self, request, obj=None): return ('source',) if obj and obj.source else ()


class CategoryAdmin(MovieCountAdminMixin, LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Thể loại'
    model_label_plural = 'Thể loại'
    list_display = ('display_name', 'path_slug', 'movie_count')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    field_labels = {'name': 'Tên thể loại', 'slug': 'Đường dẫn'}

    @admin.display(description='Thể loại', ordering='name')
    def display_name(self, obj): return obj.name

    @admin.display(description='Đường dẫn', ordering='slug')
    def path_slug(self, obj): return obj.slug


class ActorAdmin(MovieCountAdminMixin, LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Diễn viên'
    model_label_plural = 'Diễn viên'
    list_display = ('display_name', 'movie_count', 'biography')
    search_fields = ('name',)
    field_labels = {'name': 'Tên diễn viên', 'bio': 'Tiểu sử'}

    @admin.display(description='Diễn viên', ordering='name')
    def display_name(self, obj): return obj.name

    @admin.display(description='Tiểu sử')
    def biography(self, obj): return preview_text(obj.bio, 120)
