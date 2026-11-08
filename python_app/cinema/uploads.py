from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from .avatars import MAX_AVATAR_BYTES
from .trailers import MAX_TRAILER_BYTES
from .subtitles import MAX_SUBTITLE_BYTES

class BoundedUploadHandler(FileUploadHandler):
    """Stop oversize uploads while streaming, before they fill temporary storage."""
    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        user = self.request.user
        avatar_request = self.request.method == 'POST' and getattr(getattr(self.request, 'resolver_match', None), 'url_name', None) == 'profile_avatar'
        if avatar_request:
            if not (user.is_authenticated and user.is_active) or self.field_name != 'avatar':
                self.request._avatar_upload_error = 'Chỉ có thể tải ảnh đại diện cho tài khoản đang đăng nhập.'
                raise StopUpload(connection_reset=True)
            self.avatar_files = getattr(self, 'avatar_files', 0) + 1
            if self.avatar_files > 1:
                self.request._avatar_upload_error = 'Chỉ chọn một ảnh đại diện mỗi lần.'
                raise StopUpload(connection_reset=True)
            self.received = 0
            self.limit = MAX_AVATAR_BYTES
            if self.content_length and self.content_length > self.limit:
                self.request._avatar_upload_error = 'Ảnh đại diện tối đa 5 MB.'
                raise StopUpload(connection_reset=True)
            return
        if self.field_name == 'upload_file':
            view_name = getattr(getattr(self.request, 'resolver_match', None), 'view_name', '')
            permission = {'admin:cinema_subtitle_add': 'cinema.add_subtitle', 'admin:cinema_subtitle_change': 'cinema.change_subtitle'}.get(view_name)
            if not (self.request.method == 'POST' and permission and user.is_authenticated and user.is_active and user.is_staff and user.has_perm(permission)):
                self.request._subtitle_upload_error = 'Chỉ nhân viên có quyền quản lý phụ đề mới được upload tại trang quản trị phụ đề.'
                raise StopUpload(connection_reset=True)
            self.subtitle_files = getattr(self, 'subtitle_files', 0) + 1
            if self.subtitle_files > 1:
                self.request._subtitle_upload_error = 'Chỉ chọn một file phụ đề mỗi lần.'
                raise StopUpload(connection_reset=True)
            self.received = 0
            self.limit = MAX_SUBTITLE_BYTES
            if self.content_length and self.content_length > self.limit:
                self.request._subtitle_upload_error = 'Phụ đề tối đa 2 MB.'
                raise StopUpload(connection_reset=True)
            return
        if self.field_name == 'trailer_file':
            view_name = getattr(getattr(self.request, 'resolver_match', None), 'view_name', '')
            permission = {'admin:cinema_movie_add': 'cinema.add_movie', 'admin:cinema_movie_change': 'cinema.change_movie'}.get(view_name)
            if not (self.request.method == 'POST' and permission and user.is_authenticated and user.is_active and user.is_staff and user.has_perm(permission)):
                self.request._trailer_upload_error = 'Chỉ nhân viên có quyền quản lý phim mới được upload trailer tại trang quản trị phim.'
                raise StopUpload(connection_reset=True)
            self.trailer_files = getattr(self, 'trailer_files', 0) + 1
            if self.trailer_files > 1:
                self.request._trailer_upload_error = 'Chỉ chọn một file trailer mỗi lần.'
                raise StopUpload(connection_reset=True)
            self.received = 0
            self.limit = MAX_TRAILER_BYTES
            if self.content_length and self.content_length > self.limit:
                self.request._trailer_upload_error = 'Trailer tối đa 50 MB.'
                raise StopUpload(connection_reset=True)
            return
        # Other public forms cannot upload files; video/admin permissions stay unchanged.
        if not (user.is_authenticated and user.is_active and user.is_staff):
            raise StopUpload(connection_reset=True)
        if self.field_name == 'source' and not (user.has_perm('cinema.add_episode') or user.has_perm('cinema.change_episode')):
            raise StopUpload(connection_reset=True)
        self.received = 0
        self.limit = settings.MAX_VIDEO_BYTES if self.field_name == 'source' else 8 * 1024**2
        if self.content_length and self.content_length > self.limit:
            raise StopUpload(connection_reset=True)
    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > self.limit:
            if self.request.method == 'POST' and getattr(getattr(self.request, 'resolver_match', None), 'url_name', None) == 'profile_avatar':
                self.request._avatar_upload_error = 'Ảnh đại diện tối đa 5 MB.'
            if self.field_name == 'trailer_file':
                self.request._trailer_upload_error = 'Trailer tối đa 50 MB.'
            if self.field_name == 'upload_file':
                self.request._subtitle_upload_error = 'Phụ đề tối đa 2 MB.'
            raise StopUpload(connection_reset=True)
        return raw_data
    def file_complete(self, file_size): return None
