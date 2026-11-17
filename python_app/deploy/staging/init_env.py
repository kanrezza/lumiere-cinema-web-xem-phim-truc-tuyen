"""Generate an independent, private env file for the loopback staging stack."""
import os
import secrets
from pathlib import Path


ENV_FILE = Path(__file__).with_name('.env')
SECRET_LENGTHS = {
    'STAGING_DJANGO_SECRET_KEY': 64,
    'STAGING_DB_PASSWORD': 32,
    'STAGING_DB_ROOT_PASSWORD': 32,
    'STAGING_REDIS_PASSWORD': 32,
    'STAGING_PAYMENT_SECRET': 48,
    'STAGING_HOST_PASSWORD': 32,
    'STAGING_VIEWER_PASSWORD': 32,
}


def main():
    try:
        fd = os.open(ENV_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print('Staging .env already exists.')
        return

    with os.fdopen(fd, 'w') as stream:
        stream.write('STAGING_PORT=8443\n')
        for name, length in SECRET_LENGTHS.items():
            stream.write(f'{name}={secrets.token_urlsafe(length)}\n')
    print('Created the staging .env (mode 0600).')


if __name__ == '__main__':
    main()
