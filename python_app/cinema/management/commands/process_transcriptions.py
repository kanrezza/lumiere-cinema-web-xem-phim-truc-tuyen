import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from cinema.models import SubtitleTranscription
from cinema.transcription import process_transcription


class Command(BaseCommand):
    help = 'Nhận dạng lời thoại thành phụ đề bằng dịch vụ local; không gửi phim ra bên ngoài.'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true')
        parser.add_argument('--limit', type=int, default=10)
        parser.add_argument('--retry-failed', action='store_true')

    def handle(self, *args, **options):
        if options['retry_failed']:
            SubtitleTranscription.objects.filter(status='failed').update(status='pending', error='')
        try:
            while True:
                SubtitleTranscription.objects.filter(status='processing', updated_at__lt=timezone.now() - timedelta(seconds=settings.SPEECH_TIMEOUT + 120)).update(status='failed', error='Quá trình nhận dạng hết thời gian. Bạn có thể thử lại.', updated_at=timezone.now())
                jobs = list(SubtitleTranscription.objects.filter(status='pending').values_list('pk', flat=True)[:max(1, min(100, options['limit']))])
                for job_id in jobs:
                    process_transcription(job_id)
                    job = SubtitleTranscription.objects.get(pk=job_id)
                    self.stdout.write(f'{job.pk}: {job.status}')
                if not options['watch']:
                    break
                time.sleep(2)
        except KeyboardInterrupt:
            pass
