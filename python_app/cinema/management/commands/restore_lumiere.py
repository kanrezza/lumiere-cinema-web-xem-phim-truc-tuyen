import sqlite3

from django.core.management.base import BaseCommand, CommandError

from cinema.backup import BackupError, restore_snapshot


class Command(BaseCommand):
    help = 'Xác minh SHA-256 rồi khôi phục database và media vào một thư mục mới.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('snapshot', help='Thư mục bản sao lưu chứa manifest.json')
        parser.add_argument('destination', help='Thư mục phục hồi mới')

    def handle(self, *args, **options):
        try:
            manifest = restore_snapshot(options['snapshot'], options['destination'])
        except (BackupError, OSError, sqlite3.Error) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(
            f"Đã xác minh và khôi phục {len(manifest['files'])} file vào {options['destination']}."
        ))
        if manifest['engine'] == 'mysql':
            self.stdout.write('Đã khôi phục database.sql. Nhập file vào database MySQL trống trong môi trường phục hồi.')
