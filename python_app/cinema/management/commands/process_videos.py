import fcntl
import json
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkdtemp

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cinema.models import Episode
from cinema.video_quality import encoding_renditions, master_playlist, probe_dimensions, write_quality_metadata


@contextmanager
def episode_lock(path):
    # Keep the lock file in place so each worker locks the same inode.
    with path.open('ab') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            yield True


class Command(BaseCommand):
    help = 'Chuyển video đang chờ hoặc bị gián đoạn sang HLS trong worker riêng.'

    def add_arguments(self, parser):
        parser.add_argument('--episode', type=int)
        parser.add_argument('--retry-failed', action='store_true')
        parser.add_argument('--reencode', action='store_true', help='Tạo lại các mức chất lượng cho tập đã ready từ video gốc.')

    def handle(self, *args, **options):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise CommandError('Cần cài FFmpeg và ffprobe.')

        hls_root = settings.PRIVATE_MEDIA_ROOT / 'hls'
        work_root = hls_root / '.processing'
        statuses = ['pending', 'processing']
        if options['retry_failed']:
            statuses.append('failed')
        if options.get('reencode'):
            statuses.append('ready')
        query = Episode.objects.filter(status__in=statuses)
        if options['episode'] is not None:
            query = query.filter(pk=options['episode'])

        for pk, asset_id in list(query.values_list('pk', 'asset_id')):
            work_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with episode_lock(work_root / f'{asset_id}.lock') as acquired:
                if not acquired:
                    continue
                # Reread after locking. Another worker may have finished this item.
                episode = query.filter(pk=pk, asset_id=asset_id).first()
                if episode is not None:
                    self.process(episode, work_root, hls_root / str(asset_id))

    def process(self, episode, work_root, output):
        record = Episode.objects.filter(pk=episode.pk, asset_id=episode.asset_id, source=episode.source.name)
        if not record.filter(status=episode.status).update(status='processing', error=''):
            return
        claimed = record.filter(status='processing')
        workspace = work_root / str(episode.asset_id)
        try:
            if workspace.exists():
                shutil.rmtree(workspace)
            workspace.mkdir(mode=0o700)
            # A child encoder that survives a hard stop can only write to its old path.
            staging = Path(mkdtemp(dir=workspace))
            source = episode.source.path
            duration = self.probe_duration(source)
            self.encode(source, staging)
            with transaction.atomic():
                if claimed.select_for_update().first() is None:
                    return
                if output.exists():
                    shutil.rmtree(output)
                staging.rename(output)
                claimed.update(status='ready', duration=duration, error='')
        except KeyboardInterrupt:
            if claimed.update(status='pending', error=''):
                shutil.rmtree(output, ignore_errors=True)
            raise
        except Exception as exc:
            changed = claimed.update(
                status='failed',
                error=f'{type(exc).__name__}: kiểm tra định dạng video và log worker.',
            )
            if changed:
                shutil.rmtree(output, ignore_errors=True)
            self.stderr.write(f'Episode {episode.pk}: {type(exc).__name__}')
        else:
            self.stdout.write(self.style.SUCCESS(f'Episode {episode.pk}: ready'))
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    @staticmethod
    def probe_duration(source):
        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
             '-format_whitelist', 'mov,matroska,webm', '-show_format', '-show_streams',
             '-of', 'json', source],
            capture_output=True, text=True, check=True, timeout=60,
        )
        metadata = json.loads(probe.stdout)
        if not any(stream.get('codec_type') == 'video' for stream in metadata.get('streams', [])):
            raise ValueError('File không có luồng video.')
        duration = float(metadata['format']['duration'])
        if not 0 < duration <= 6 * 3600:
            raise ValueError('Thời lượng video không hợp lệ hoặc quá 6 giờ.')
        return duration

    @staticmethod
    def encode(source, output):
        renditions = encoding_renditions(*probe_dimensions(source))
        for rendition in renditions:
            subprocess.run(
                ['ffmpeg', '-nostdin', '-y', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                 '-format_whitelist', 'mov,matroska,webm', '-i', source, '-map', '0:v:0',
                 '-map', '0:a:0?', '-map_metadata', '-1',
                 '-vf', f'scale={rendition.width}:{rendition.video_height},setsar=1',
                 '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-threads', '2',
                 '-maxrate', str(rendition.bandwidth - 192000), '-bufsize', str(rendition.bandwidth * 2),
                 '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                 '-force_key_frames', 'expr:gte(t,n_forced*6)',
                 '-f', 'hls', '-hls_time', '6', '-hls_playlist_type', 'vod',
                 '-hls_flags', 'independent_segments',
                 '-hls_segment_filename', str(output / f'q{rendition.height}_seg%05d.ts'),
                 str(output / rendition.playlist)],
                capture_output=True, check=True, timeout=6 * 3600,
            )
        write_quality_metadata(output, renditions)
        (output / 'index.m3u8').write_text(master_playlist(renditions, lambda name: name), encoding='utf-8')
