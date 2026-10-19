"""Host snapshots and interrupted replacement use real files, never user directories."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('playground_mount_tests', REPO / 'playgrounds/manage.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
m = p.mounts


class MountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = patch.dict(os.environ, XDG_STATE_HOME=str(self.root / 'xdg'))
        self.env.start()
        self.addCleanup(self.env.stop)
        self.pg = p.Playground(self.root / 'states', 'demo')
        self.pg.directory.mkdir(parents=True)
        self.host = self.root / 'project'
        self.host.mkdir()
        (self.host / 'file').write_text('checkpoint')
        self.shares = m.declarations([], [self.host], self.pg.directory, REPO)
        self.pg.data = {'schema': 'playground/v2', 'current': 'tenx-' + 'a' * 32,
                        'owned': ['tenx-' + 'a' * 32], 'mounts': self.shares,
                        'source_sha256': 'source', 'flake_lock_sha256': 'lock'}
        self.pg.save()
        self.folder = self.root / 'snapshot'
        self.folder.mkdir()

    def snapshot(self):
        return m.snapshot(self.shares, self.folder)

    def test_only_explicit_paths_are_mounted_with_host_protection(self):
        reference = self.root / 'reference repo'
        reference.mkdir()
        shares = m.declarations([reference], [self.host], self.pg.directory, REPO)
        with patch.object(p, 'msb') as runtime:
            p.create('vm', 'image', offline=True, shares=shares)
        args = runtime.call_args.args
        volumes = [args[i+1] for i, arg in enumerate(args) if arg == '--volume']
        self.assertEqual(len(volumes), 2)
        self.assertTrue(volumes[0].startswith(str(reference) + ':' + str(reference) + ':ro,'))
        self.assertTrue(volumes[1].startswith(str(self.host) + ':' + str(self.host) + ':rw,'))
        self.assertTrue(all('nosuid,nodev' in v for v in volumes))
        self.assertFalse((self.pg.directory / 'primary').exists())

    def test_mounts_reject_overlap_control_state_home_and_link_aliases(self):
        cases = [([], [self.root]), ([self.pg.directory], []), ([], [Path.home()]),
                 ([self.host], [self.host]), ([], [REPO])]
        for ro, rw in cases:
            with self.assertRaises(ValueError):
                m.declarations(ro, rw, self.pg.directory, REPO)
        alias = self.root / 'alias'
        alias.symlink_to(self.host)
        with self.assertRaises(ValueError):
            m.declarations([], [alias], self.pg.directory, REPO)

    def test_writable_links_cannot_escape_grant(self):
        (self.host / 'escape').symlink_to('../outside')
        with self.assertRaisesRegex(ValueError, 'symlink escapes'):
            m.tree(self.host)
        (self.host / 'escape').unlink()
        os.link(self.host / 'file', self.root / 'outside')
        with self.assertRaisesRegex(ValueError, 'hardlink points outside'):
            m.tree(self.host)

    def test_root_substitution_refuses_access(self):
        self.host.rename(self.root / 'saved')
        self.host.mkdir()
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            m.validate(self.shares)

    def test_readonly_sharing_and_writable_exclusion_across_state_dirs(self):
        owner = self.pg.statefile
        with m.leases(owner, self.shares):
            pass
        with self.assertRaisesRegex(ValueError, 'already leased'):
            with m.leases(self.root / 'other/state.json', [dict(self.shares[-1], mode='ro')]):
                pass
        with m.leases(owner):
            pass
        for name in ('first', 'second'):
            with m.leases(self.root / name, [dict(self.shares[-1], mode='ro')]):
                pass

    def test_archive_restores_modes_hardlinks_symlinks_and_xattrs(self):
        (self.host / 'file').chmod(0o755)
        group = next((g for g in os.getgroups() if g != os.getgid()), os.getgid())
        os.chown(self.host / 'file', os.getuid(), group)
        (self.host / 'link').symlink_to('file')
        os.link(self.host / 'file', self.host / 'hardlink')
        attr = 'user.tenx' if os.sys.platform == 'linux' else 'com.tenx.test'
        if hasattr(os, 'setxattr'):
            os.setxattr(self.host / 'file', attr, b'retain metadata')
        else:
            subprocess.run(['xattr', '-w', attr, 'retain metadata', str(self.host / 'file')], check=True)
        before = m.tree(self.host)
        records = self.snapshot()
        m.verify(records, self.folder, self.shares)
        (self.host / 'file').write_text('broken')
        (self.host / 'added').write_text('uncheckpointed')
        restore = m.Restore(self.pg.directory)
        txn = restore.prepare(records, self.folder, self.pg.data)
        restore.replace(txn)
        self.assertEqual(m.tree(self.host), before)
        backup = Path(txn['rows'][-1]['backup'])
        self.assertEqual((backup / 'file').read_text(), 'broken')
        self.assertTrue((backup / 'added').exists())
        restore.rollback()
        self.assertEqual((self.host / 'file').read_text(), 'broken')
        restore.finish()

    def test_native_archive_restores_acl(self):
        file = self.host / 'file'
        if os.sys.platform == 'darwin':
            subprocess.run(['chmod', '+a', 'everyone allow readattr', str(file)], check=True)
            def acl():
                return subprocess.check_output(['ls', '-le', str(file)], text=True).splitlines()[1:]
        else:
            entries = [(1, 7, 0xffffffff), (2, 4, 65534), (4, 4, 0xffffffff),
                       (16, 4, 0xffffffff), (32, 0, 0xffffffff)]
            os.setxattr(file, 'system.posix_acl_access', struct.pack('<I', 2) +
                        b''.join(struct.pack('<HHI', *entry) for entry in entries))
            def acl():
                return os.getxattr(file, 'system.posix_acl_access')
        before = acl()
        records = self.snapshot()
        if os.sys.platform == 'darwin':
            subprocess.run(['chmod', '-N', str(file)], check=True)
        else:
            os.removexattr(file, 'system.posix_acl_access')
        restore = m.Restore(self.pg.directory)
        txn = restore.prepare(records, self.folder, self.pg.data)
        restore.replace(txn)
        self.assertEqual(acl(), before)
        restore.finish()

    def test_partial_multidirectory_replacement_is_recoverable(self):
        records = self.snapshot()
        (self.host / 'file').write_text('before-rewind')
        restore = m.Restore(self.pg.directory)
        txn = restore.prepare(records, self.folder, self.pg.data)
        first = txn['rows'][0]
        Path(first['path']).rename(first['backup'])  # Interrupt between the two renames.
        with self.assertRaisesRegex(ValueError, 'recover'):
            self.pg.ready()
        before = restore.rollback()
        self.assertEqual(before['current'], self.pg.data['current'])
        self.assertEqual((self.host / 'file').read_text(), 'before-rewind')
        self.assertEqual(m.identity(first['path']), first['original'])
        restore.finish()
        self.pg.ready()

    def test_rewind_can_replace_unsafe_guest_entries_without_following_them(self):
        records = self.snapshot()
        outside = self.root / 'outside'
        outside.write_text('must remain unchanged')
        (self.host / 'escape').symlink_to(outside)
        os.mkfifo(self.host / 'fifo')
        restore = m.Restore(self.pg.directory)
        txn = restore.prepare(records, self.folder, self.pg.data)
        restore.replace(txn)
        self.assertEqual((self.host / 'file').read_text(), 'checkpoint')
        self.assertFalse((self.host / 'escape').exists())
        self.assertEqual(outside.read_text(), 'must remain unchanged')
        restore.rollback()
        self.assertTrue((self.host / 'escape').is_symlink())
        restore.finish()

    def test_host_changes_during_staging_refuse_replacement(self):
        records = self.snapshot()
        restore = m.Restore(self.pg.directory)
        txn = restore.prepare(records, self.folder, self.pg.data)
        (self.host / 'file').write_text('new host edit')
        with self.assertRaisesRegex(ValueError, 'changed during restore'):
            restore.replace(txn)
        restore.rollback()
        self.assertEqual((self.host / 'file').read_text(), 'new host edit')

    def test_corrupt_host_archive_does_not_stop_guest(self):
        records = self.snapshot()
        folder = self.pg.directory / 'checkpoints/good'
        folder.parent.mkdir()
        self.folder.rename(folder)
        (folder / 'guest.msb').write_bytes(b'image')
        p.atomic(folder / 'checkpoint.json', {'schema': 'playground-checkpoint/v2', 'mounts': records,
                 'archive_sha256': p.digest(folder / 'guest.msb')})
        (folder / records[-1]['archive']).write_bytes(b'corrupt')
        with patch.object(p, 'msb') as runtime:
            with self.assertRaisesRegex(ValueError, 'checksum'):
                self.pg.rewind('good')
        runtime.assert_not_called()

    def test_checkpoint_stops_every_guest_before_reading_writable_contents(self):
        stopped = []
        original = m.tree
        def inspect(path):
            self.assertEqual(stopped, self.pg.data['owned'])
            return original(path)
        def runtime(*args, **kwargs):
            if args[0] == 'ls':
                return subprocess.CompletedProcess(args, 0, json.dumps([{'name': n} for n in self.pg.data['owned']]))
            if args[0] == 'stop':
                stopped.append(args[1])
            elif args[:2] == ('snap', 'create'):
                Path(args[-1]).write_bytes(b'cold image')
            return subprocess.CompletedProcess(args, 0, '')
        with patch.object(p, 'msb', runtime), patch.object(m, 'tree', inspect):
            self.pg.checkpoint('cold')

    def test_failed_health_requires_explicit_recovery_and_stops_candidate(self):
        records = self.snapshot()
        folder = self.pg.directory / 'checkpoints/good'
        folder.parent.mkdir()
        self.folder.rename(folder)
        (folder / 'guest.msb').write_bytes(b'image')
        p.atomic(folder / 'checkpoint.json', {'schema': 'playground-checkpoint/v2', 'mounts': records,
                 'archive_sha256': p.digest(folder / 'guest.msb'),
                 'source_sha256': 'source', 'flake_lock_sha256': 'lock'})
        (self.host / 'file').write_text('preserve failed work')
        def runtime(*args, **kwargs):
            if args[:1] == ('exec',):
                raise subprocess.CalledProcessError(1, args)
            if args[:1] == ('ls',):
                return subprocess.CompletedProcess(args, 0, json.dumps([{'name': n} for n in self.pg.data['owned']]))
            return subprocess.CompletedProcess(args, 0, '')
        with patch.object(p, 'preflight'), patch.object(p, 'create'), patch.object(p, 'boundary'), \
             patch.object(p, 'seal'), patch.object(p, 'msb', runtime) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                self.pg.rewind('good')
            self.assertEqual((self.host / 'file').read_text(), 'checkpoint')
            with self.assertRaisesRegex(ValueError, 'recover'):
                self.pg.run(['true'])
            result = self.pg.recover()
        self.assertTrue(result['recovered'])
        self.assertEqual((self.host / 'file').read_text(), 'preserve failed work')
        self.assertEqual(self.pg.data['current'], 'tenx-' + 'a' * 32)
        self.assertEqual(len(self.pg.data['owned']), 2)

    def test_guest_boundary_rejects_unknown_share_and_wrong_mode(self):
        good = '1 0 0:1 / /reference ro - virtiofs host rw\n'
        class Result:
            returncode = 2
        for text, expected, passes in ((good, {'/reference': 'ro'}, True),
                                       (good, {}, False), (good, {'/reference': 'rw'}, False)):
            with patch.object(Path, 'read_text', return_value=text), patch.object(Path, 'exists', return_value=False), \
                 patch('subprocess.run', return_value=Result()), patch('sys.argv', ['boundary', json.dumps(expected)]):
                if passes:
                    exec(p.BOUNDARY, {})
                else:
                    with self.assertRaises(AssertionError):
                        exec(p.BOUNDARY, {})

    def test_mountinfo_escaped_spaces_match_explicit_paths(self):
        text = '1 0 0:1 / /reference\\040repo ro - virtiofs host rw\n'
        with patch.object(Path, 'read_text', return_value=text), patch.object(Path, 'exists', return_value=False), \
             patch('subprocess.run', return_value=subprocess.CompletedProcess([], 2)), \
             patch('sys.argv', ['boundary', json.dumps({'/reference repo': 'ro'})]):
            exec(p.BOUNDARY, {})


if __name__ == '__main__':
    unittest.main()
