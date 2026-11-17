"""Isolated SQLite settings for recovery with an explicit data directory."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


recovery_directory = os.environ.get('LUMIERE_RECOVERY_ROOT')
if not recovery_directory or not Path(recovery_directory).is_absolute():
    raise ImproperlyConfigured('LUMIERE_RECOVERY_ROOT phải là đường dẫn tuyệt đối.')
if os.getenv('DEBUG', '1') != '1' or os.getenv('DB_NAME') or os.getenv('REDIS_URL'):
    raise ImproperlyConfigured('Cấu hình phục hồi SQLite cần DEBUG=1 và database/cache riêng.')

recovery_root = Path(recovery_directory).resolve()
if recovery_root == BASE_DIR:  # noqa: F405
    raise ImproperlyConfigured('Chọn một thư mục phục hồi riêng.')

DATABASES = {'default': {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': recovery_root / 'db.sqlite3',
    'OPTIONS': {'transaction_mode': 'IMMEDIATE'},
}}
MEDIA_ROOT = recovery_root / 'public_media'
PRIVATE_MEDIA_ROOT = recovery_root / 'private_media'
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
VNPAY_TMN_CODE = ''
VNPAY_HASH_SECRET = ''
SPEECH_API_URL = ''
TRANSLATION_API_URL = ''
ROOM_VOICE_ICE_SERVERS = []
