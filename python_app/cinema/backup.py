"""Filesystem snapshots for media plus the application's SQL database."""
import hashlib
import json
import shutil
import sqlite3
import subprocess
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile


DATABASE_FILES = {'sqlite3': 'db.sqlite3', 'mysql': 'database.sql'}
MEDIA_FOLDERS = ('public_media', 'private_media')
CHUNK_SIZE = 1024 * 1024


class BackupError(Exception):
    """A snapshot cannot be created or safely restored."""


def _output_path(destination):
    path = Path(destination).absolute()
    return path.parent.resolve() / path.name


@contextmanager
def _new_directory(path):
    try:
        path.mkdir(mode=0o700)
    except FileExistsError as error:
        raise BackupError('Đích đã tồn tại. Hãy chọn một thư mục mới.') from error
    try:
        yield path
    except BaseException:
        shutil.rmtree(path, ignore_errors=True)
        raise


def _copy_and_hash(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with source.open('rb') as input_file, target.open('xb') as output_file:
        while chunk := input_file.read(CHUNK_SIZE):
            output_file.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def _sqlite_uri(path):
    return f'{path.resolve().as_uri()}?mode=ro'


def _check_sqlite(path):
    with closing(sqlite3.connect(_sqlite_uri(path), uri=True)) as database:
        if database.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise BackupError('Kiểm tra tính toàn vẹn SQLite thất bại.')


def _backup_sqlite(config, target):
    source = Path(config['NAME'])
    if not source.is_file():
        raise BackupError('Cần một file SQLite đang tồn tại để sao lưu.')
    with (
        closing(sqlite3.connect(_sqlite_uri(source), uri=True)) as original,
        closing(sqlite3.connect(target)) as snapshot,
    ):
        original.backup(snapshot, pages=4096)
    _check_sqlite(target)


def _mysql_option(value):
    escaped = str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
    return f'"{escaped}"'


def _backup_mysql(config, target):
    executable = shutil.which('mysqldump')
    if not executable:
        raise BackupError('Cài mysqldump của MySQL 8 trước khi sao lưu database MySQL.')
    options = {'user': config['USER'], 'password': config['PASSWORD'], 'port': config['PORT'] or 3306}
    if config['HOST'].startswith('/'):
        options['socket'] = config['HOST']
    else:
        options['host'] = config['HOST'] or 'localhost'
    with NamedTemporaryFile(mode='w', encoding='utf-8') as credentials, target.open('xb') as output:
        credentials.write('[client]\n')
        for key, value in options.items():
            credentials.write(f'{key}={_mysql_option(value)}\n')
        credentials.flush()
        result = subprocess.run(
            [executable, f'--defaults-file={credentials.name}', '--single-transaction', '--quick',
             '--no-tablespaces', '--set-gtid-purged=OFF', '--skip-add-drop-table', '--', config['NAME']],
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.PIPE, check=False,
        )
    if result.returncode or not target.stat().st_size:
        raise BackupError('Không tạo được MySQL dump. Kiểm tra thông tin kết nối và quyền mysqldump.')


def _copy_media(source, target, output_root, files):
    target.mkdir()
    if not source.exists():
        return
    if not source.is_dir():
        raise BackupError(f'Kho media phải là thư mục: {source}')
    def raise_walk_error(error):
        raise error

    for current, directories, names in source.walk(on_error=raise_walk_error):
        destination = target / current.relative_to(source)
        for name in sorted(directories + names):
            original = current / name
            new = destination / name
            if original.is_symlink():
                raise BackupError('Kho media chứa liên kết tượng trưng. Hãy xử lý liên kết trước khi sao lưu.')
            if original.is_dir():
                new.mkdir()
            elif original.is_file():
                files[new.relative_to(output_root).as_posix()] = _copy_and_hash(original, new)
            else:
                raise BackupError('Kho media chứa mục không phải file thông thường.')


def create_snapshot(destination, config, public_media, private_media):
    """Write a new snapshot and publish the manifest after copying every payload."""
    engine = config['ENGINE'].rsplit('.', 1)[-1]
    if engine not in DATABASE_FILES:
        raise BackupError('Chỉ hỗ trợ SQLite và MySQL.')
    destination = _output_path(destination)
    media_sources = (Path(public_media).resolve(), Path(private_media).resolve())
    public_source, private_source = media_sources
    if public_source.is_relative_to(private_source) or private_source.is_relative_to(public_source):
        raise BackupError('Kho media công khai và riêng tư phải nằm ở hai thư mục tách biệt.')
    if any(destination.is_relative_to(source) for source in media_sources):
        raise BackupError('Đích sao lưu cần nằm ngoài các kho media của ứng dụng.')

    files = {}
    with _new_directory(destination):
        database_file = DATABASE_FILES[engine]
        database_path = destination / database_file
        (_backup_sqlite if engine == 'sqlite3' else _backup_mysql)(config, database_path)
        with database_path.open('rb') as database:
            files[database_file] = {
                'bytes': database_path.stat().st_size,
                'sha256': hashlib.file_digest(database, 'sha256').hexdigest(),
            }
        for folder, source in zip(MEDIA_FOLDERS, media_sources, strict=True):
            _copy_media(source, destination / folder, destination, files)
        manifest = {'version': 1, 'created_at': datetime.now(UTC).isoformat(), 'engine': engine, 'files': files}
        unpublished = destination / 'manifest.tmp'
        unpublished.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        unpublished.rename(destination / 'manifest.json')
    return manifest


def _snapshot_path(name, database_file):
    relative = PurePosixPath(name)
    if name == database_file:
        return relative
    if (
        len(relative.parts) < 2 or relative.parts[0] not in MEDIA_FOLDERS
        or relative.as_posix() != name or '..' in relative.parts or '\\' in name or '\0' in name
    ):
        raise BackupError('Manifest chứa đường dẫn ngoài kho media hoặc database đã định.')
    return relative


def _snapshot_file(root, relative):
    source = root
    for part in relative.parts:
        source /= part
        if source.is_symlink():
            raise BackupError('Bản sao lưu chứa liên kết tượng trưng.')
    if not source.is_file():
        raise BackupError(f'Thiếu file trong bản sao lưu: {relative}')
    return source


def restore_snapshot(source, destination):
    """Restore to a new directory after checking each listed file's size and digest."""
    source = Path(source).resolve()
    destination = _output_path(destination)
    if destination.is_relative_to(source):
        raise BackupError('Đích khôi phục cần nằm ngoài thư mục sao lưu.')
    try:
        manifest_path = _snapshot_file(source, PurePosixPath('manifest.json'))
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (UnicodeError, ValueError) as error:
        raise BackupError('Manifest sao lưu không đọc được.') from error
    if not isinstance(manifest, dict) or manifest.get('version') != 1:
        raise BackupError('Phiên bản manifest không được hỗ trợ.')
    engine = manifest.get('engine')
    if not isinstance(engine, str) or engine not in DATABASE_FILES:
        raise BackupError('Manifest không có loại database hợp lệ.')
    database_file = DATABASE_FILES[engine]
    files = manifest.get('files')
    if not isinstance(files, dict) or database_file not in files:
        raise BackupError('Manifest không liệt kê file database.')

    with _new_directory(destination):
        for folder in MEDIA_FOLDERS:
            (destination / folder).mkdir()
        for name, expected in files.items():
            relative = _snapshot_path(name, database_file)
            original = _snapshot_file(source, relative)
            actual = _copy_and_hash(original, destination.joinpath(*relative.parts))
            if actual != expected:
                raise BackupError(f'File không khớp kích thước hoặc SHA-256: {relative}')
        if engine == 'sqlite3':
            _check_sqlite(destination / database_file)
    return manifest
