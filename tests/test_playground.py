"""Host orchestration failures are deterministic; real microVM checks are separate."""
import importlib.util
import argparse
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('playground', REPO / 'playgrounds/manage.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PlaygroundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pg = p.Playground(self.root, 'demo')
        self.pg.directory.mkdir()
        self.old = 'tenx-' + 'a' * 32
        self.pg.data = {'schema': 'playground/v1', 'current': self.old,
                        'owned': [self.old], 'source_sha256': 'source', 'flake_lock_sha256': 'lock'}
        self.pg.save()

    def fake(self, *args, **kwargs):
        return subprocess.CompletedProcess(args, 0, '[]')

    def snapshot(self):
        folder = self.pg.directory / 'checkpoints/good'
        folder.mkdir(parents=True)
        archive = folder / 'image.tar'
        archive.write_bytes(b'known-good-image')
        p.atomic(folder / 'checkpoint.json', {'schema': 'playground-checkpoint/v1',
                 'image': 'tenx-checkpoint:test', 'archive_sha256': p.digest(archive),
                 'source_sha256': 'snapshot-source', 'flake_lock_sha256': 'snapshot-lock'})
        return archive

    def test_repository_import_has_no_escaped_links(self):
        output = self.root / 'source.tar'
        p.safe_bundle(REPO, output, repository=True)
        with tarfile.open(output) as archive:
            self.assertFalse(any('.git' in Path(x.name).parts for x in archive))
            self.assertEqual(archive.getmember('.github/plugin/marketplace.json').linkname,
                             '../../.claude-plugin/marketplace.json')

    def test_import_preserves_ignored_files_modes_and_internal_links(self):
        source = self.root / 'input'
        source.mkdir()
        (source / 'ignored').write_text('keep me')
        (source / 'ignored').chmod(0o755)
        (source / 'link').symlink_to('ignored')
        p.safe_bundle(source, self.root / 'data.tar')
        with tarfile.open(self.root / 'data.tar') as archive:
            self.assertEqual(archive.getmember('ignored').mode, 0o755)
            self.assertTrue(archive.getmember('link').issym())

    def test_import_rejects_external_symlinks_and_linked_worktrees(self):
        source = self.root / 'input'
        source.mkdir()
        (source / 'escape').symlink_to('../outside')
        with self.assertRaisesRegex(ValueError, 'escapes'):
            p.safe_bundle(source, self.root / 'data.tar')
        (source / 'escape').unlink()
        (source / '.git').write_text('gitdir: /private/host/repository')
        with self.assertRaisesRegex(ValueError, 'standalone'):
            p.safe_bundle(source, self.root / 'data.tar')

    def test_labels_cannot_escape_state(self):
        for value in ('../demo', '/tmp', '--cloud', 'x/y', ''):
            with self.assertRaises(argparse.ArgumentTypeError):
                p.label(value)

    def test_corrupt_checkpoint_does_not_stop_current_guest(self):
        archive = self.snapshot()
        archive.write_bytes(b'corrupt')
        with patch.object(p, 'sbx') as runtime:
            with self.assertRaisesRegex(ValueError, 'checksum'):
                self.pg.rewind('good')
        runtime.assert_not_called()
        self.assertEqual(json.loads(self.pg.statefile.read_text())['current'], self.old)

    def test_failed_candidate_keeps_current_and_records_candidate_for_cleanup(self):
        self.snapshot()
        with patch.object(p, 'preflight'), patch.object(p, 'boundary'), \
             patch.object(p, 'create', side_effect=RuntimeError('start failed')), patch.object(p, 'sbx', self.fake):
            with self.assertRaisesRegex(RuntimeError, 'start failed'):
                self.pg.rewind('good')
        state = json.loads(self.pg.statefile.read_text())
        self.assertEqual(state['current'], self.old)
        self.assertEqual(len(state['owned']), 2)

    def test_failed_health_does_not_switch_workspace(self):
        self.snapshot()
        def runtime(*args, **kwargs):
            if args[:1] == ('exec',):
                raise subprocess.CalledProcessError(1, args)
            return self.fake(*args, **kwargs)
        with patch.object(p, 'preflight'), patch.object(p, 'boundary'), patch.object(p, 'create'), \
             patch.object(p, 'sbx', runtime):
            with self.assertRaises(subprocess.CalledProcessError):
                self.pg.rewind('good')
        self.assertEqual(json.loads(self.pg.statefile.read_text())['current'], self.old)

    def test_successful_rewind_preserves_old_vm_and_snapshot_identity(self):
        self.snapshot()
        with patch.object(p, 'preflight'), patch.object(p, 'boundary'), patch.object(p, 'create') as create, \
             patch.object(p, 'sbx', self.fake):
            result = self.pg.rewind('good')
        self.assertEqual(result['preserved'], self.old)
        self.assertNotEqual(result['current'], self.old)
        self.assertIn(self.old, self.pg.data['owned'])
        self.assertEqual(self.pg.data['source_sha256'], 'snapshot-source')
        self.assertTrue(create.call_args.kwargs['offline'])

    def test_interrupted_checkpoint_is_not_visible_and_never_deletes_vm(self):
        with patch.object(p, 'sbx', side_effect=[self.fake(), KeyboardInterrupt()]):
            with self.assertRaises(KeyboardInterrupt):
                self.pg.checkpoint('interrupted')
        self.assertFalse((self.pg.directory / 'checkpoints/interrupted').exists())
        self.assertEqual(self.pg.data['current'], self.old)

    def test_checkpoint_stops_writers_and_publishes_hash_bound_archive(self):
        calls = []
        def runtime(*args, **kwargs):
            calls.append(args)
            if args[:2] == ('template', 'save'):
                Path(args[-1]).write_bytes(b'stopped-filesystem')
            return self.fake(*args, **kwargs)
        with patch.object(p, 'sbx', runtime):
            self.pg.checkpoint('baseline')
        self.assertEqual(calls[0], ('stop', self.old))
        manifest = json.loads((self.pg.directory / 'checkpoints/baseline/checkpoint.json').read_text())
        self.assertEqual(manifest['archive_sha256'], p.digest(self.pg.directory / 'checkpoints/baseline/image.tar'))
        with self.assertRaisesRegex(ValueError, 'exists'):
            self.pg.checkpoint('baseline')

    def test_create_never_mounts_host_workspace_or_enables_shared_skills(self):
        with patch.object(p, 'sbx') as runtime:
            p.create('owned', 'pinned:image', offline=True)
        args = runtime.call_args_list[0].args
        self.assertEqual(args[-1], 'shell')
        self.assertEqual(args[args.index('--skills') + 1], 'off')
        self.assertEqual(args[args.index('--deny-network') + 1], '**')
        self.assertNotIn('--cloud', args)
        self.assertNotIn('--clone', args)
        self.assertEqual(runtime.call_args_list[1].args, ('run', '--detach', '--name', 'owned'))

    def test_run_preserves_argv_exit_status_and_stdio(self):
        argv = ['printf', '%s', '$(touch /outside)']
        with patch.object(p, 'preflight'), patch.object(p, 'seal'), patch.object(p, 'boundary'), \
             patch.object(p, 'guest', return_value=subprocess.CompletedProcess([], 17)) as guest:
            self.assertEqual(self.pg.run(argv), 17)
        self.assertEqual(guest.call_args.args, (self.old, argv))
        self.assertTrue(guest.call_args.kwargs['interactive'])

    def test_guest_keeps_stdout_pipeable(self):
        with patch.object(p, 'sbx') as runtime:
            p.guest(self.old, ['cat'], interactive=True)
        self.assertTrue(runtime.call_args.kwargs['passthrough'])
        self.assertIn('-i', runtime.call_args.args)

    def test_control_calls_cannot_consume_workspace_stdin(self):
        with patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '')) as run:
            p.sbx('version', capture=True)
            self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)
            p.sbx('exec', 'vm', 'cat', passthrough=True)
            self.assertIsNone(run.call_args.kwargs['stdin'])

    def test_lock_refuses_concurrent_commands(self):
        other = p.Playground(self.root, 'demo')
        with self.pg.locked():
            with self.assertRaisesRegex(ValueError, 'busy'):
                with other.locked():
                    self.fail('must not enter')

    def test_up_refuses_to_copy_host_checkpoints_into_guest(self):
        self.pg.data = None
        with patch.object(p, 'preflight'), patch.object(p, 'create') as create:
            with self.assertRaisesRegex(ValueError, 'outside imported'):
                self.pg.up(self.root)
        create.assert_not_called()

    def test_lock_refuses_unowned_state_directory(self):
        other = p.Playground(self.root, 'unowned')
        other.directory.mkdir()
        (other.directory/'valuable.txt').write_text('preserve')
        with self.assertRaisesRegex(ValueError, 'unowned'):
            with other.locked():
                self.fail('must not enter')
        self.assertEqual((other.directory/'valuable.txt').read_text(), 'preserve')

    def test_destroy_only_removes_owned_vms_and_retains_checkpoints(self):
        archive = self.snapshot()
        calls = []
        def runtime(*args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, json.dumps([{'name': self.old}, {'name': 'unrelated'}]))
        with patch.object(p, 'sbx', runtime):
            self.pg.destroy()
            self.pg.destroy()
        self.assertTrue(archive.exists())
        self.assertEqual([a for a in calls if a[0] == 'rm'], [('rm', '--force', self.old)])
        self.assertIsNone(self.pg.data['current'])

    def test_preflight_rejects_host_forwarding_without_mutating_settings(self):
        calls = []
        def runtime(*args, **kwargs):
            calls.append(args)
            value = 'sbx version v0.48.0' if args == ('version',) else (
                'false' if args[-1] == 'ssh.agentForwardingEnabled' else '/host/agent.sock')
            return subprocess.CompletedProcess(args, 0, value)
        with patch.object(p.shutil, 'which', return_value='/bin/sbx'), patch.object(p, 'sbx', runtime):
            with self.assertRaisesRegex(ValueError, 'exposes host'):
                p.preflight()
        self.assertFalse(any('set' in a for a in calls))


if __name__ == '__main__':
    unittest.main()
