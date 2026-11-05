from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from .avatars import MAX_AVATAR_BYTES

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
            raise StopUpload(connection_reset=True)
        return raw_data
    def file_complete(self, file_size): return None
