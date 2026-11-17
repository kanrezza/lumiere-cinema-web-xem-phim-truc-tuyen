import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Diễn tập SQLite trong môi trường mới và kiểm tra phát HLS sau khi khôi phục.'
    requires_system_checks = []

    def handle(self, *args, **options):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise CommandError('Cần cài FFmpeg và ffprobe để diễn tập.')

        environment = {
            **os.environ, 'DEBUG': '1', 'DB_NAME': '', 'REDIS_URL': '', 'TRUST_PROXY': '0',
            'DJANGO_SETTINGS_MODULE': 'config.recovery', 'ALLOWED_HOSTS': 'testserver',
            'DJANGO_SECRET_KEY': secrets.token_urlsafe(48),
        }

        def run(data_root, command, *arguments):
            subprocess.run(
                [sys.executable, str(settings.BASE_DIR / 'manage.py'), command, *arguments],
                env={**environment, 'LUMIERE_RECOVERY_ROOT': str(data_root)}, check=True, timeout=300,
            )

        with TemporaryDirectory(prefix='lumiere-recovery-') as folder:
            workspace = Path(folder)
            original, snapshot, restored = (workspace / name for name in ('source', 'snapshot', 'restored'))
            original.mkdir(mode=0o700)
            try:
                run(original, 'migrate', '--noinput', '--verbosity', '0')
                run(original, 'make_demo_series')
                run(original, 'shell', '-c', 'from cinema.recovery_checks import create_fixtures; create_fixtures()')
                run(original, 'backup_lumiere', str(snapshot))
                run(original, 'restore_lumiere', str(snapshot), str(restored))
                # Make source files unavailable before starting the verification process.
                original.rename(workspace / 'source-disabled')
                run(restored, 'shell', '-c', 'from cinema.recovery_checks import verify_fixtures; verify_fixtures()')
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                raise CommandError('Diễn tập phục hồi thất bại. Xem lỗi của bước tương ứng ở trên.') from error

        self.stdout.write(self.style.SUCCESS('Diễn tập phục hồi SQLite và media hoàn tất.'))
