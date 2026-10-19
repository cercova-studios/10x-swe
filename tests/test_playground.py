"""Host orchestration failures are deterministic; real microVM checks are separate."""
import importlib.util
import argparse
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import io
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
        env = patch.dict(p.os.environ, XDG_DATA_HOME=str(self.root / 'data'))
        env.start()
        self.addCleanup(env.stop)
        self.pg = p.Playground(self.root, 'demo')
        self.pg.directory.mkdir()
        self.old = 'tenx-' + 'a' * 32
        self.pg.data = {'schema': 'playground/v2', 'current': self.old,
                        'owned': [self.old], 'source_sha256': 'source', 'flake_lock_sha256': 'lock'}
        self.pg.save()

    def fake(self, *args, **kwargs):
        if args and args[0] == 'ls':
            return subprocess.CompletedProcess(args, 0, json.dumps([{'name': n} for n in self.pg.data['owned']]))
        if args and args[0] == 'inspect':
            return subprocess.CompletedProcess(args, 0, json.dumps({'status': 'Running', 'config': {
                'network': {'policy': {'default_egress': 'deny', 'default_ingress': 'deny', 'rules': []},
                            'ports': [], 'secrets': {'secrets': []}, 'trust_host_cas': False}}}))
        return subprocess.CompletedProcess(args, 0, '[]')

    def snapshot(self):
        folder = self.pg.directory / 'checkpoints/good'
        folder.mkdir(parents=True)
        archive = folder / 'guest.msb'
        archive.write_bytes(b'known-good-image')
        p.atomic(folder / 'checkpoint.json', {'schema': 'playground-checkpoint/v2',
                 'runtime': p.CONFIG['msb_version'], 'archive_sha256': p.digest(archive),
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
        with patch.object(p, 'msb') as runtime:
            with self.assertRaisesRegex(ValueError, 'checksum'):
                self.pg.rewind('good')
        runtime.assert_not_called()
        self.assertEqual(json.loads(self.pg.statefile.read_text())['current'], self.old)

    def test_failed_candidate_keeps_current_and_records_candidate_for_cleanup(self):
        self.snapshot()
        with patch.object(p, 'preflight'), patch.object(p, 'boundary'), \
             patch.object(p, 'create', side_effect=RuntimeError('start failed')), patch.object(p, 'msb', self.fake):
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
             patch.object(p, 'msb', runtime):
            with self.assertRaises(subprocess.CalledProcessError):
                self.pg.rewind('good')
        self.assertEqual(json.loads(self.pg.statefile.read_text())['current'], self.old)

    def test_successful_rewind_preserves_old_vm_and_snapshot_identity(self):
        self.snapshot()
        with patch.object(p, 'preflight'), patch.object(p, 'boundary'), patch.object(p, 'create') as create, \
             patch.object(p, 'msb', self.fake):
            result = self.pg.rewind('good')
        self.assertEqual(result['preserved'], self.old)
        self.assertNotEqual(result['current'], self.old)
        self.assertIn(self.old, self.pg.data['owned'])
        self.assertEqual(self.pg.data['source_sha256'], 'snapshot-source')
        self.assertTrue(create.call_args.kwargs['offline'])

    def test_interrupted_checkpoint_is_not_visible_and_never_deletes_vm(self):
        def runtime(*args, **kwargs):
            if args[:2] == ('snap', 'create'):
                raise KeyboardInterrupt()
            return self.fake(*args, **kwargs)
        with patch.object(p, 'msb', runtime):
            with self.assertRaises(KeyboardInterrupt):
                self.pg.checkpoint('interrupted')
        self.assertFalse((self.pg.directory / 'checkpoints/interrupted').exists())
        self.assertEqual(self.pg.data['current'], self.old)

    def test_absent_reserved_candidate_does_not_block_stopping_writers(self):
        self.pg.data['owned'].append('tenx-' + 'b' * 32)
        with patch.object(p, 'msb', return_value=subprocess.CompletedProcess([], 0, json.dumps([{'name': self.old}]))) as runtime:
            self.pg.stop_owned()
        self.assertEqual(runtime.call_args.args, ('stop', self.old))
        self.assertEqual(runtime.call_count, 2)

    def test_checkpoint_stops_writers_and_publishes_hash_bound_archive(self):
        calls = []
        def runtime(*args, **kwargs):
            calls.append(args)
            if args[:2] == ('snap', 'create'):
                Path(args[-1]).write_bytes(b'stopped-filesystem')
            return self.fake(*args, **kwargs)
        with patch.object(p, 'msb', runtime):
            self.pg.checkpoint('baseline')
        self.assertEqual(calls[1], ('stop', self.old))
        manifest = json.loads((self.pg.directory / 'checkpoints/baseline/checkpoint.json').read_text())
        self.assertEqual(manifest['archive_sha256'], p.digest(self.pg.directory / 'checkpoints/baseline/guest.msb'))
        with self.assertRaisesRegex(ValueError, 'exists'):
            self.pg.checkpoint('baseline')

    def test_restore_is_offline_and_has_no_implicit_host_grants(self):
        with patch.object(p, 'msb') as runtime:
            p.create('owned', 'pinned:image', offline=True)
        args = runtime.call_args_list[0].args
        self.assertEqual(args[:3], ('snap', 'restore', 'pinned:image'))
        self.assertIn('--no-net', args)
        self.assertNotIn('--disk-only', args)  # Cold archives reject full-snapshot-only restore flags.
        self.assertNotIn('--volume', args)
        self.assertNotIn('--net-rule', args)
        self.assertNotIn('--vsock', args)
        self.assertEqual(runtime.call_count, 1)

    def test_run_preserves_argv_exit_status_and_stdio(self):
        argv = ['printf', '%s', '$(touch /outside)']
        with patch.object(p, 'preflight'), patch.object(p, 'seal'), patch.object(p, 'boundary'), \
             patch.object(p, 'guest', return_value=subprocess.CompletedProcess([], 17)) as guest:
            self.assertEqual(self.pg.run(argv), 17)
        self.assertEqual(guest.call_args.args, (self.old, argv))
        self.assertTrue(guest.call_args.kwargs['interactive'])

    def test_guest_keeps_stdout_pipeable(self):
        with patch.object(p, 'msb') as runtime:
            p.guest(self.old, ['cat'], interactive=True)
        self.assertTrue(runtime.call_args.kwargs['passthrough'])
        self.assertIn('--stream', runtime.call_args.args)

    def test_control_calls_cannot_consume_workspace_stdin(self):
        with patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '')) as run:
            p.msb('--version', capture=True)
            self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)
            p.msb('exec', 'vm', '--', 'cat', passthrough=True)
            self.assertIsNone(run.call_args.kwargs['stdin'])

    def test_runtime_never_inherits_cloud_secrets_or_proxy_settings(self):
        with patch.dict(p.os.environ, MSB_BACKEND='cloud', MSB_API_KEY='not-a-real-key',
                        MSB_CONFIG_PATH='/untrusted/config', HTTPS_PROXY='http://untrusted', SSH_AUTH_SOCK='/host/agent'), \
             patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '')) as run:
            p.msb('--version')
        env = run.call_args.kwargs['env']
        self.assertEqual(env['MSB_BACKEND'], 'local')
        self.assertNotIn('MSB_API_KEY', env)
        self.assertNotIn('HTTPS_PROXY', env)
        self.assertNotIn('SSH_AUTH_SOCK', env)
        self.assertEqual(Path(env['MSB_CONFIG_PATH']).read_text().strip(), '{}')

    def test_seal_rejects_network_drift_before_starting_guest(self):
        info = json.loads(self.fake('inspect').stdout)
        info['status'] = 'Stopped'
        info['config']['network']['policy']['rules'] = [{'action': 'allow'}]
        with patch.object(p, 'msb', return_value=subprocess.CompletedProcess([], 0, json.dumps(info))) as run:
            with self.assertRaisesRegex(ValueError, 'not sealed'):
                p.seal(self.old)
        self.assertEqual(run.call_count, 1)

    def test_installer_checks_hash_and_preserves_existing_install(self):
        archive = self.root / 'release.tar.gz'
        with tarfile.open(archive, 'w:gz') as bundle:
            item = tarfile.TarInfo('msb')
            item.size, item.mode = 7, 0o755
            bundle.addfile(item, io.BytesIO(b'runtime'))
        config = dict(p.CONFIG, runtime_archives={'darwin-arm64': p.digest(archive)})
        def download(url, destination):
            p.shutil.copyfile(archive, destination)
        with patch.object(p, 'CONFIG', config), patch.object(p.sys, 'platform', 'darwin'), \
             patch.object(p.platform, 'machine', return_value='arm64'), \
             patch.object(p.urllib.request, 'urlretrieve', side_effect=download) as fetch:
            result = p.install_runtime()
            self.assertEqual(p.install_runtime(), result)
            self.assertEqual(fetch.call_count, 1)
            Path(result['binary']).write_text('changed')
            with self.assertRaisesRegex(ValueError, 'differs'):
                p.install_runtime()
        p.shutil.rmtree(p.runtime_home() / 'bin')
        config['runtime_archives']['darwin-arm64'] = '0' * 64
        with patch.object(p, 'CONFIG', config), patch.object(p.sys, 'platform', 'darwin'), \
             patch.object(p.platform, 'machine', return_value='arm64'), \
             patch.object(p.urllib.request, 'urlretrieve', side_effect=download):
            with self.assertRaisesRegex(ValueError, 'checksum'):
                p.install_runtime()
        self.assertFalse((p.runtime_home() / 'bin').exists())

    def test_previous_runtime_state_is_rejected_without_changes(self):
        previous = dict(self.pg.data, schema='playground/v1')
        p.atomic(self.pg.statefile, previous)
        before = self.pg.statefile.read_bytes()
        with self.assertRaisesRegex(ValueError, 'fresh Microsandbox'):
            with self.pg.locked():
                self.fail('must not adopt another runtime state')
        self.assertEqual(before, self.pg.statefile.read_bytes())

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
        with patch.object(p, 'msb', runtime):
            self.pg.destroy()
            self.pg.destroy()
        self.assertTrue(archive.exists())
        self.assertEqual([a for a in calls if a[0] == 'rm'], [('rm', '--force', self.old)])
        self.assertIsNone(self.pg.data['current'])

    def test_preflight_rejects_cloud_without_mutating_settings(self):
        calls = []
        def runtime(*args, **kwargs):
            calls.append(args)
            value = 'msb 0.7.8' if args == ('--version',) else '{"kind":"cloud"}'
            return subprocess.CompletedProcess(args, 0, value)
        with patch.object(p.shutil, 'which', return_value='/bin/msb'), patch.object(p, 'msb', runtime):
            with self.assertRaisesRegex(ValueError, 'local'):
                p.preflight()
        self.assertFalse(any('set' in a for a in calls))


if __name__ == '__main__':
    unittest.main()
