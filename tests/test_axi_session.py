"""Session query commands must not initialize or upgrade an index."""
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]/'plugins/knowledge/skills/session-search/scripts'
sys.path.insert(0, str(SCRIPTS))
from session_search.models import SessionRecord
from session_search.store import Store


class SessionReadTests(unittest.TestCase):
    def invoke(self, db, *args):
        return subprocess.run([sys.executable, str(SCRIPTS/'session-search'), *args],
                              env={**os.environ, 'SESSION_SEARCH_DB': str(db), 'SESSION_SEARCH_EMBEDDER': 'hash'},
                              capture_output=True, timeout=15)

    def test_missing_queries_create_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands = [('search', '--mode', 'naive', '--json', 'needle'),
                        ('last', '--mode', 'naive', 'needle'),
                        ('export', '--mode', 'naive', 'needle'),
                        ('show', 'codex', 'missing')]
            for args in commands:
                with self.subTest(args=args):
                    parent = Path(tmp)/args[0]
                    db = parent/'index.db'
                    result = self.invoke(db, *args)
                    self.assertEqual(result.returncode, 1 if args[0] == 'show' else 2, result.stderr)
                    self.assertEqual(result.stdout, b'')
                    self.assertFalse(parent.exists())
            parent = Path(tmp)/'status'
            db = parent/'index.db'
            result = self.invoke(db, 'status', '--json')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)['exists'])
            self.assertFalse(parent.exists())

    def test_queries_do_not_migrate_or_chmod(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/'index ? #.db'
            store = Store(db)
            store.replace_agent('codex', [SessionRecord(agent='codex', native_id='fixture', title='needle')])
            # Retain a committed WAL while a reader queries it.
            os.chmod(db, 0o640)
            before = hashlib.sha256(db.read_bytes()).hexdigest()
            result = self.invoke(db, 'search', '--mode', 'naive', '--json', 'needle')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['hits'][0]['native_id'], 'fixture')
            self.assertEqual(db.stat().st_mode & 0o777, 0o640)
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)
            reader = Store(db, read_only=True)
            with self.assertRaises(sqlite3.OperationalError):
                reader.conn.execute('DELETE FROM sessions')
            reader.close()
            store.close()
            with closing(sqlite3.connect(db)) as writer:
                writer.execute('ALTER TABLE sessions DROP COLUMN turns_json')
                writer.commit()
            before = hashlib.sha256(db.read_bytes()).hexdigest()
            result = self.invoke(db, 'search', '--mode', 'naive', '--json', 'needle')
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(b'index', result.stderr.lower())
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)
            with closing(sqlite3.connect(db)) as check:
                self.assertNotIn('turns_json', {r[1] for r in check.execute('PRAGMA table_info(sessions)')})


if __name__ == '__main__':
    unittest.main()
