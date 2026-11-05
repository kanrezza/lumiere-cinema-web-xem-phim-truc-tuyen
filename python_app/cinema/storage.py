from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

@deconstructible
class PrivateVideoStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, file_permissions_mode=0o600, directory_permissions_mode=0o700)
    def url(self, name):
        raise ValueError('Video gốc không có URL công khai. Dùng nguồn phát đã xác thực.')
