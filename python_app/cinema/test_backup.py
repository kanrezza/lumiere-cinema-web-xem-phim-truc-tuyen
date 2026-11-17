import json
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from .backup import BackupError, create_snapshot, restore_snapshot


class BackupRestoreTests(SimpleTestCase):
    def setUp(self):
        workspace = TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        self.database = self.root / 'source.sqlite3'
        self.public = self.root / 'public'
        self.private = self.root / 'private'
        self.public.mkdir()
        (self.private / 'hls' / 'demo').mkdir(parents=True)
        (self.public / 'backdrop.jpg').write_bytes(b'fixture image')
        (self.private / 'hls' / 'demo' / 'seg00000.ts').write_bytes(b'fixture segment')

        self.connection = sqlite3.connect(self.database)
        self.addCleanup(self.connection.close)
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('PRAGMA wal_autocheckpoint=0')
        self.connection.execute('CREATE TABLE item (title TEXT)')
        self.connection.execute('INSERT INTO item VALUES (?)', ('movie',))
        self.connection.commit()
        self.snapshot = self.root / 'snapshot'
        self.destination = self.root / 'restored'

    def backup(self):
        return create_snapshot(
            self.snapshot, {'ENGINE': 'django.db.backends.sqlite3', 'NAME': self.database}, self.public, self.private,
        )

    def test_restores_committed_sqlite_wal_data_and_both_media_roots(self):
        self.assertTrue(self.database.with_name(f'{self.database.name}-wal').is_file())
        self.backup()
        restore_snapshot(self.snapshot, self.destination)

        with closing(sqlite3.connect(self.destination / 'db.sqlite3')) as restored:
            self.assertEqual(restored.execute('SELECT title FROM item').fetchall(), [('movie',)])
        self.assertEqual((self.destination / 'public_media' / 'backdrop.jpg').read_bytes(), b'fixture image')
        self.assertEqual((self.destination / 'private_media' / 'hls/demo/seg00000.ts').read_bytes(), b'fixture segment')

    def test_corruption_rejects_restore_and_removes_partial_output(self):
        self.backup()
        segment = self.snapshot / 'private_media' / 'hls/demo/seg00000.ts'
        segment.write_bytes(b'corrupt segment')

        with self.assertRaisesMessage(BackupError, 'SHA-256'):
            restore_snapshot(self.snapshot, self.destination)

        self.assertFalse(self.destination.exists())

    def test_refuses_restore_when_destination_already_exists(self):
        self.backup()
        self.destination.mkdir()
        existing = self.destination / 'user-video'
        existing.write_bytes(b'untouched')

        with self.assertRaisesMessage(BackupError, 'Đích đã tồn tại'):
            restore_snapshot(self.snapshot, self.destination)

        self.assertEqual(list(self.destination.iterdir()), [existing])
        self.assertEqual(existing.read_bytes(), b'untouched')

    def test_output_cannot_be_a_dangling_symbolic_link(self):
        self.backup()
        unwanted = self.root / 'unwanted'
        self.destination.symlink_to(unwanted, target_is_directory=True)

        with self.assertRaisesMessage(BackupError, 'Đích đã tồn tại'):
            restore_snapshot(self.snapshot, self.destination)

        self.assertFalse(unwanted.exists())

    def test_manifest_cannot_list_an_unrelated_location(self):
        manifest = self.backup()
        manifest['files']['unrelated/file.txt'] = manifest['files']['public_media/backdrop.jpg']
        (self.snapshot / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

        with self.assertRaisesMessage(BackupError, 'đường dẫn ngoài kho media'):
            restore_snapshot(self.snapshot, self.destination)

        self.assertFalse(self.destination.exists())

    def test_restore_refuses_symbolic_link_payload(self):
        self.backup()
        payload = self.snapshot / 'public_media' / 'backdrop.jpg'
        payload.unlink()
        payload.symlink_to(self.public / 'backdrop.jpg')

        with self.assertRaisesMessage(BackupError, 'liên kết tượng trưng'):
            restore_snapshot(self.snapshot, self.destination)

        self.assertFalse(self.destination.exists())

    def test_mysql_dump_credentials_stay_in_a_private_file_and_restore_as_sql(self):
        mysql_database = {
            'ENGINE': 'django.db.backends.mysql', 'NAME': 'isolated', 'USER': 'snapshot-user',
            'PASSWORD': 'synthetic-credential', 'HOST': 'localhost', 'PORT': '3306',
        }
        dump = b'-- simulated MySQL snapshot\n'

        def fake_dump(args, *, stdout, **kwargs):
            self.assertNotIn(mysql_database['PASSWORD'], args)
            credential_file = Path(args[1].split('=', 1)[1])
            self.assertEqual(credential_file.stat().st_mode & 0o777, 0o600)
            self.assertIn('password="synthetic-credential"', credential_file.read_text())
            self.assertIn('--single-transaction', args)
            self.assertIn('--skip-add-drop-table', args)
            stdout.write(dump)
            return subprocess.CompletedProcess(args, 0)

        with patch('cinema.backup.shutil.which', return_value='/bin/mysqldump'), patch(
            'cinema.backup.subprocess.run', side_effect=fake_dump,
        ):
            manifest = create_snapshot(self.snapshot, mysql_database, self.public, self.private)
        restore_snapshot(self.snapshot, self.destination)

        self.assertEqual(manifest['engine'], 'mysql')
        self.assertEqual((self.destination / 'database.sql').read_bytes(), dump)
        self.assertFalse((self.destination / 'db.sqlite3').exists())
