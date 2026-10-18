"""Installation ownership, failed readiness and concurrency boundaries."""
import importlib.util
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
bootstrap=load('bootstrap',REPO/'plugins/knowledge/bootstrap.py')


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        # Direct helper calls use the same canonical prefix as the CLI (macOS /var is an alias).
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
    def tearDown(self): self.temp.cleanup()
    def test_plan_has_no_writes(self):
        target=self.root/'absent'
        p=subprocess.run([sys.executable,str(REPO/'plugins/knowledge/bootstrap.py'),'plan','--prefix',str(target)],capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertFalse(target.exists())
        self.assertIn('Kindle delivery',json.loads(p.stdout)['excluded'])
    def test_plan_reports_missing_prerequisites_without_writes(self):
        target = self.root / 'absent'
        result = subprocess.run([sys.executable, str(REPO / 'plugins/knowledge/bootstrap.py'),
                                 'plan', '--prefix', str(target)],
                                env=dict(os.environ, PATH=str(self.root / 'no-tools')),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data['build_ready'])
        self.assertTrue(any(item['command'] == 'cargo' and not item['passed']
                            for item in data['build_checks']))
        self.assertFalse(target.exists())

    def test_version_probes_reject_wrong_identity_and_old_versions(self):
        for output in ['unrelated utility 4.0', 'go version go1.21.9 linux/amd64']:
            with self.subTest(output=output), \
                    patch.object(bootstrap.shutil, 'which', return_value='/fixture/go'), \
                    patch.object(bootstrap.subprocess, 'run', return_value=subprocess.CompletedProcess(
                        [], 0, stdout=output, stderr='')):
                check = bootstrap.version_check('go', ['version'], r'^go version go(\d+)\.(\d+)', (1, 22))
                self.assertFalse(check['passed'])
                self.assertIn('Go 1.22+', check['error'])

    def test_version_probes_accept_supported_versions_and_report_timeout(self):
        with patch.object(bootstrap.shutil, 'which', return_value='/fixture/go'):
            with patch.object(bootstrap.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 0, stdout='go version go1.27.2 linux/amd64', stderr='')):
                check = bootstrap.version_check('go', ['version'], r'^go version go(\d+)\.(\d+)', (1, 22))
                self.assertTrue(check['passed'])
                self.assertEqual(check['path'], '/fixture/go')
            with patch.object(bootstrap.subprocess, 'run', side_effect=subprocess.TimeoutExpired('go', 10)):
                check = bootstrap.version_check('go', ['version'], r'^go version go(\d+)\.(\d+)', (1, 22))
                self.assertFalse(check['passed'])
                self.assertIn('timed out', check['error'])

    def test_rust_preflight_uses_locked_dependency_minimum(self):
        def probe(argv, **kwargs):
            output = {'cargo': 'cargo 1.87.0', 'rustc': 'rustc 1.87.0',
                      'go': 'go version go1.22.0 linux/amd64', 'cc': '',
                      'pkg-config': '3.0.0'}[Path(argv[0]).name]
            return subprocess.CompletedProcess(argv, 0, stdout=output, stderr='')
        with patch.object(bootstrap.shutil, 'which', side_effect=lambda name: '/tools/' + name), \
                patch.object(bootstrap.subprocess, 'run', side_effect=probe):
            checks = {item['command']: item for item in bootstrap.build_checks()}
        self.assertFalse(checks['cargo']['passed'])
        self.assertFalse(checks['rustc']['passed'])
        self.assertTrue(checks['go']['passed'])
    def test_default_prefix_respects_data_home_without_writes(self):
        data_home=self.root/'data home'
        p=subprocess.run([sys.executable,str(REPO/'plugins/knowledge/bootstrap.py'),'plan'],
                         env=dict(os.environ,XDG_DATA_HOME=str(data_home)),capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['prefix'],str((data_home/'10x-swe/knowledge').resolve()))
        self.assertFalse(data_home.exists())
    def test_owned_retries_reject_conflicts_and_changed_source(self):
        target=self.root/'owned';bootstrap.owned(target,'a'*64);bootstrap.owned(target,'a'*64)
        with self.assertRaisesRegex(ValueError,'different source'): bootstrap.owned(target,'b'*64)
        conflict=self.root/'existing';conflict.mkdir();(conflict/'valuable').write_text('retain')
        with self.assertRaisesRegex(ValueError,'unowned'): bootstrap.owned(conflict,'a'*64)
        self.assertEqual((conflict/'valuable').read_text(),'retain')
        alias=self.root/'alias';alias.symlink_to(target)
        with self.assertRaisesRegex(ValueError,'symlink'): bootstrap.owned(alias,'a'*64)
    def test_failed_setup_is_not_readiness_and_tampered_artifacts_fail(self):
        target=self.root/'owned';bootstrap.owned(target,'a'*64)
        with self.assertRaisesRegex(ValueError,'No completed'): bootstrap.doctor(target,verify=False)
        (target/'artifact').write_text('changed')
        (target/'installation.json').write_text(json.dumps({'artifacts':{'artifact':'a'*64}}))
        with self.assertRaisesRegex(ValueError,'artifacts changed'): bootstrap.doctor(target,verify=False)
    def test_source_tree_install_is_rejected_before_write(self):
        with self.assertRaisesRegex(ValueError,'outside the source'): bootstrap.setup(REPO/'never-create-this')
        self.assertFalse((REPO/'never-create-this').exists())
    def test_incomplete_setup_still_requires_build_tools_and_retains_no_receipt(self):
        target=self.root/'missing-tools'
        for _ in range(2):
            p=subprocess.run([sys.executable,str(REPO/'plugins/knowledge/bootstrap.py'),'setup','--prefix',str(target)],
                             env=dict(os.environ,PATH=str(self.root/'no-tools')),capture_output=True)
            self.assertNotEqual(p.returncode,0)
            self.assertIn(b'Missing build prerequisite: cargo',p.stderr)
            self.assertFalse((target/'installation.json').exists())

    def completed_installation(self):
        target = self.root / "installed tools' prefix"
        manifest = {'source': 'a' * 64}
        fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        bootstrap.owned(target, fingerprint)
        (target / 'libexec').mkdir()
        launcher = target / 'libexec/launch.py'
        launcher.write_text('#!/bin/sh\nexit 0\n')
        launcher.chmod(0o755)
        (target / 'bin').mkdir()
        for name in bootstrap.COMMANDS:
            (target / 'bin' / name).symlink_to('../libexec/launch.py')
        bootstrap.atomic(target / 'installation.json', {
            'artifacts': {'libexec/launch.py': bootstrap.digest(launcher)}})
        return target, manifest

    def test_doctor_detects_missing_activation_file(self):
        target, _ = self.completed_installation()
        with self.assertRaisesRegex(ValueError, 'env.sh.*rerun setup'):
            bootstrap.doctor(target, verify=False)

    def test_completed_setup_restores_activation_and_always_prints_next_step(self):
        target, manifest = self.completed_installation()
        for _ in range(2):
            output = io.StringIO()
            with patch.object(bootstrap, 'inputs', return_value=manifest), \
                    patch.object(bootstrap.shutil, 'which', return_value=None), \
                    contextlib.redirect_stdout(output):
                bootstrap.setup(target)
            self.assertTrue((target / 'env.sh').is_file())
            self.assertIn('Activate explicitly: . ', output.getvalue())
            self.assertIn('skill-search search', output.getvalue())
            command = output.getvalue().split('Activate explicitly: ', 1)[1].splitlines()[0]
            result = subprocess.run(['/bin/sh', '-c', command + '; printf "%s" "$AGENT_KNOWLEDGE_HOME"'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, str(target))

    def test_setup_does_not_replace_modified_activation(self):
        target, manifest = self.completed_installation()
        (target / 'env.sh').write_text('custom activation\n')
        with patch.object(bootstrap, 'inputs', return_value=manifest):
            with self.assertRaisesRegex(ValueError, 'env.sh'):
                bootstrap.setup(target)
        self.assertEqual((target / 'env.sh').read_text(), 'custom activation\n')

    def test_cli_resolves_parent_alias_before_recovering_activation(self):
        target, manifest = self.completed_installation()
        alias = self.root / 'parent-alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with patch.object(sys, 'argv', ['knowledge', 'setup', '--prefix', str(alias / target.name)]), \
                patch.object(bootstrap, 'inputs', return_value=manifest), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap.main(), 0)
        self.assertEqual((target / 'env.sh').read_text(), bootstrap.activation_text(target))

    def test_missing_receipted_activation_is_restored_without_changing_receipt(self):
        target, manifest = self.completed_installation()
        bootstrap.ensure_activation(target)
        receipt = target / 'installation.json'
        data = json.loads(receipt.read_text())
        data['artifacts']['env.sh'] = bootstrap.digest(target / 'env.sh')
        bootstrap.atomic(receipt, data)
        before = receipt.read_bytes()
        (target / 'env.sh').unlink()
        with self.assertRaisesRegex(ValueError, 'env.sh.*rerun setup'):
            bootstrap.doctor(target, verify=False)
        with patch.object(bootstrap, 'inputs', return_value=manifest), contextlib.redirect_stdout(io.StringIO()):
            bootstrap.setup(target)
        self.assertEqual(receipt.read_bytes(), before)
        self.assertEqual(bootstrap.digest(target / 'env.sh'), data['artifacts']['env.sh'])

    def test_setup_rejects_activation_symlink_without_modifying_target(self):
        target, manifest = self.completed_installation()
        saved = target / 'saved-environment'
        saved.write_text('retain\n')
        (target / 'env.sh').symlink_to(saved)
        with patch.object(bootstrap, 'inputs', return_value=manifest):
            with self.assertRaisesRegex(ValueError, 'env.sh'):
                bootstrap.setup(target)
        self.assertEqual(saved.read_text(), 'retain\n')


if __name__=='__main__': unittest.main()
