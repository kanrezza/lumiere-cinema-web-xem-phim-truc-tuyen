"""Create original media and throwaway users in the staging database only."""
import os
from datetime import timedelta

import django

django.setup()

from django.conf import settings
from django.core.management import call_command
from django.test.utils import override_settings
from django.utils import timezone

from cinema.models import Plan, User


def main():
    database = settings.DATABASES['default']
    if (
        os.environ.get('LUMIERE_STAGING') != '1'
        or settings.DEBUG
        or database['NAME'] != 'lumiere_staging'
        or database.get('HOST') != 'db'
        or settings.VNPAY_TMN_CODE != 'LUMIFIXT'
        or settings.VNPAY_URL != 'https://payments.example.invalid/vnpay-fixture'
    ):
        raise SystemExit('Staging fixture guard rejected this configuration.')

    # Keep the development-only command's guard intact for every other deployment.
    with override_settings(DEBUG=True):
        call_command('make_demo_series')

    Plan.objects.get_or_create(name='Staging VIP', defaults={'price': 59000, 'days': 30})
    for username, password_key in (
        ('staging-host', 'STAGING_HOST_PASSWORD'),
        ('staging-viewer', 'STAGING_VIEWER_PASSWORD'),
    ):
        user, created = User.objects.get_or_create(
            username=username, defaults={'email': f'{username}@example.invalid'},
        )
        if created or not user.check_password(os.environ[password_key]):
            user.set_password(os.environ[password_key])
            user.save(update_fields=['password'])
        if username == 'staging-host' and not user.is_vip:
            user.vip_until = timezone.now() + timedelta(days=1)
            user.save(update_fields=['vip_until'])


if __name__ == '__main__':
    main()
