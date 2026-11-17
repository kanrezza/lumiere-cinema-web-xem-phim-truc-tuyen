from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from cinema.models import SecurityEvent


class Command(BaseCommand):
    help = 'Xóa sự kiện WAF cũ hơn 30 ngày.'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=30)
        count, _ = SecurityEvent.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f'Đã xóa {count} sự kiện WAF.'))
