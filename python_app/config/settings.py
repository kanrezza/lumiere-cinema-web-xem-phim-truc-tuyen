import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('DEBUG', '1') == '1'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'local-development-only-do-not-deploy-this-key')
if not DEBUG and (len(SECRET_KEY) < 50 or SECRET_KEY.startswith('local-')):
    raise ImproperlyConfigured('Production requires a unique DJANGO_SECRET_KEY of at least 50 characters.')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]').split(',')
CSRF_TRUSTED_ORIGINS = [s for s in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if s]
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'cinema']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'cinema.middleware.SecurityMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
if os.getenv('DB_NAME'):
    import pymysql
    pymysql.install_as_MySQLdb()
    DATABASES = {'default': {'ENGINE': 'django.db.backends.mysql', 'NAME': os.environ['DB_NAME'], 'USER': os.getenv('DB_USER', 'root'), 'PASSWORD': os.getenv('DB_PASSWORD', ''), 'HOST': os.getenv('DB_HOST', '127.0.0.1'), 'PORT': os.getenv('DB_PORT', '3306'), 'OPTIONS': {'charset': 'utf8mb4', 'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"}}}
AUTH_USER_MODEL = 'cinema.User'
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'vi'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'public_media'
MEDIA_URL = '/media/'
PRIVATE_MEDIA_ROOT = Path(os.getenv('PRIVATE_MEDIA_ROOT', str(BASE_DIR / 'private_media')))
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/browse/'
LOGOUT_REDIRECT_URL = '/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
FILE_UPLOAD_MAX_MEMORY_SIZE = 0
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200
MAX_VIDEO_BYTES = int(os.getenv('MAX_VIDEO_BYTES', str(4 * 1024**3)))
STREAM_TOKEN_AGE = 600
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'Lumiere <noreply@localhost>')
REDIS_URL = os.getenv('REDIS_URL')
if not DEBUG and not REDIS_URL:
    raise ImproperlyConfigured('Production requires REDIS_URL for shared rate limits.')
CACHES = {'default': {'BACKEND': 'django_redis.cache.RedisCache', 'LOCATION': REDIS_URL, 'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'}}} if REDIS_URL else {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
VNPAY_TMN_CODE = os.getenv('VNPAY_TMN_CODE', '')
VNPAY_HASH_SECRET = os.getenv('VNPAY_HASH_SECRET', '')
VNPAY_URL = os.getenv('VNPAY_URL', 'https://sandbox.vnpayment.vn/paymentv2/vpcpay.html')
PUBLIC_ORIGIN = os.getenv('PUBLIC_ORIGIN', 'http://127.0.0.1:8000').rstrip('/')

PASSWORD_HASHERS = ['django.contrib.auth.hashers.PBKDF2PasswordHasher', 'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher', 'django.contrib.auth.hashers.BCryptSHA256PasswordHasher', 'cinema.hashers.LaravelBCryptPasswordHasher']

if os.getenv('TRUST_PROXY', '0') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

FILE_UPLOAD_HANDLERS = ['cinema.uploads.BoundedUploadHandler', 'django.core.files.uploadhandler.TemporaryFileUploadHandler']

AUTHENTICATION_BACKENDS = ['cinema.backends.EmailOrUsernameBackend']
TRUST_PROXY = os.getenv('TRUST_PROXY', '0') == '1'
TRUSTED_PROXY_IPS = os.getenv('TRUSTED_PROXY_IPS', '127.0.0.1,::1').split(',')
