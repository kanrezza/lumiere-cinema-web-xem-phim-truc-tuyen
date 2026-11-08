"""Run translation inference outside web requests."""
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from cinema.models import SubtitleTranslation
from cinema.translation import MAX_TRANSLATION_SECONDS, TranslationError, process_translation, service_url


class Command(BaseCommand):
    help = 'Xử lý hàng đợi dịch phụ đề qua máy chủ dịch đã cấu hình.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--watch', action='store_true', help='Tiếp tục kiểm tra hàng đợi mỗi 2 giây.')
        parser.add_argument('--retry-failed', action='store_true', help='Đưa bản dịch lỗi về hàng đợi một lần trước khi chạy.')

    def handle(self, *args, **options):
        if not 1 <= options['limit'] <= 100:
            raise CommandError('--limit phải từ 1 đến 100.')
        try:
            service_url()
        except TranslationError as error:
            raise CommandError(str(error)) from error
        if options['retry_failed']:
            SubtitleTranslation.objects.filter(status='failed').update(status='pending', error='', started_at=None, finished_at=None, updated_at=timezone.now())
        active_job = None
        try:
            while True:
                # An interrupted process must not leave an eternal spinner.
                stale_before = timezone.now() - timedelta(seconds=MAX_TRANSLATION_SECONDS + 120)
                SubtitleTranslation.objects.filter(status='processing', started_at__lt=stale_before).update(status='failed', error='Việc dịch đã bị gián đoạn. Bạn có thể yêu cầu thử lại.', content='', finished_at=timezone.now(), updated_at=timezone.now())
                processed = 0
                for job in SubtitleTranslation.objects.filter(status='pending').select_related('subtitle')[:options['limit']]:
                    # Compare-and-swap prevents duplicate inference if two workers
                    # observed the same pending row before either claimed it.
                    claimed = SubtitleTranslation.objects.filter(pk=job.pk, status='pending').update(status='processing', started_at=timezone.now(), updated_at=timezone.now())
                    if not claimed:
                        continue
                    job.status = 'processing'
                    active_job = job.pk
                    ready = process_translation(job)
                    active_job = None
                    processed += 1
                    self.stdout.write(f'{job.pk}: {"ready" if ready else "failed"}')
                if not options['watch']:
                    self.stdout.write(f'Đã xử lý {processed} bản dịch.')
                    break
                time.sleep(2)
        except KeyboardInterrupt:
            if active_job is not None:
                SubtitleTranslation.objects.filter(pk=active_job, status='processing').update(status='failed', error='Việc dịch đã bị gián đoạn. Bạn có thể yêu cầu thử lại.', content='', finished_at=timezone.now(), updated_at=timezone.now())
            self.stdout.write('Đã dừng worker dịch phụ đề.')
