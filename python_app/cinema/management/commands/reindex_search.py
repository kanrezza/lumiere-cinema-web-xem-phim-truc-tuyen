from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS

from cinema.models import Actor, Movie
from cinema.search import normalize_search


class Command(BaseCommand):
    help = 'Tạo lại dữ liệu tìm kiếm sau bulk import. Chạy khi không có thao tác sửa tên/mô tả đồng thời.'

    def add_arguments(self, parser):
        parser.add_argument('--database', default=DEFAULT_DB_ALIAS)
        parser.add_argument('--batch-size', type=int, default=500)

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        if not 1 <= batch_size <= 5000:
            raise CommandError('--batch-size phải nằm trong khoảng 1–5000.')
        for model in (Actor, Movie):
            manager = model.objects.using(options['database'])
            batch, count = [], 0
            for record in manager.only('pk', *model.search_sources.values()).iterator(chunk_size=batch_size):
                for target, source in model.search_sources.items():
                    setattr(record, target, normalize_search(getattr(record, source)))
                batch.append(record)
                if len(batch) == batch_size:
                    manager.bulk_update(batch, list(model.search_sources), batch_size=batch_size)
                    count += len(batch)
                    batch = []
            if batch:
                manager.bulk_update(batch, list(model.search_sources), batch_size=batch_size)
                count += len(batch)
            self.stdout.write(f'{model.__name__}: {count}')
