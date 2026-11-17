import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from cinema.backup import BackupError, create_snapshot


class Command(BaseCommand):
    help = 'Sao lưu database và cả hai kho media vào một thư mục mới.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('destination', help='Thư mục mới để chứa bản sao lưu')

    def handle(self, *args, **options):
        try:
            manifest = create_snapshot(
                options['destination'], settings.DATABASES['default'],
                settings.MEDIA_ROOT, settings.PRIVATE_MEDIA_ROOT,
            )
        except (BackupError, OSError, sqlite3.Error) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(
            f"Đã sao lưu {manifest['engine']} và media, có SHA-256 cho {len(manifest['files'])} file."
        ))
