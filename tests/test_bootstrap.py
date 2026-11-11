"""Installation ownership, failed readiness and concurrency boundaries.

The bootstrap entry point is POSIX sh. These tests drive that script instead of
importing the old Python module.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
BOOT = REPO / 'plugins/knowledge/bootstrap'
COMMANDS = ('skill-search', 'bkd', 'distiller', 'insights', 'source-insights', 'session-search', 'knowledge-intake')


def run_boot(args, env=None, **kwargs):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(['/bin/sh', str(BOOT), *args], capture_output=True, text=True, env=merged, **kwargs)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def test_plan_has_no_writes(self):
        target = self.root / 'absent'
        result = run_boot(['plan', '--prefix', str(target)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())
        self.assertIn('Kindle delivery', json.loads(result.stdout)['excluded'])

    def test_plan_reports_missing_prerequisites_without_writes(self):
        target = self.root / 'absent'
        result = run_boot(['plan', '--prefix', str(target)], env={'PATH': str(self.root / 'no-tools')})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data['build_ready'])
        self.assertTrue(any(item['command'] == 'cargo' and not item['passed'] for item in data['build_checks']))
        self.assertFalse(target.exists())

    def test_version_probes_reject_wrong_identity_and_old_versions(self):
        tools = self.root / 'tools'
        tools.mkdir()
        (tools / 'go').write_text('#!/bin/sh\necho "unrelated utility 4.0"\n')
        (tools / 'go').chmod(0o755)
        for name in ('cargo', 'rustc', 'cc', 'pkg-config', 'python3'):
            path = tools / name
            path.write_text('#!/bin/sh\nexec /usr/bin/python3 "$@"\n' if name == 'python3' else '#!/bin/sh\nexit 0\n')
            path.chmod(0o755)
        (tools / 'cargo').write_text('#!/bin/sh\necho "cargo 1.99.0"\n')
        (tools / 'rustc').write_text('#!/bin/sh\necho "rustc 1.99.0"\n')
        (tools / 'cc').write_text('#!/bin/sh\nexit 0\n')
        (tools / 'pkg-config').write_text('#!/bin/sh\necho 3.0.0\n')
        (tools / 'go').chmod(0o755)
        result = run_boot(['plan', '--prefix', str(self.root / 'p')], env={'PATH': str(tools)})
        self.assertEqual(result.returncode, 0, result.stderr)
        checks = {item['command']: item for item in json.loads(result.stdout)['build_checks']}
        self.assertFalse(checks['go']['passed'])
        self.assertIn('Go 1.22+', checks['go']['error'])
        (tools / 'go').write_text('#!/bin/sh\necho "go version go1.21.9 linux/amd64"\n')
        (tools / 'go').chmod(0o755)
        result = run_boot(['plan', '--prefix', str(self.root / 'p2')], env={'PATH': str(tools)})
        checks = {item['command']: item for item in json.loads(result.stdout)['build_checks']}
        self.assertFalse(checks['go']['passed'])
        self.assertIn('Go 1.22+', checks['go']['error'])

    def test_version_probes_accept_supported_versions_and_report_timeout(self):
        tools = self.root / 'tools'
        tools.mkdir()
        for name, body in {
            'go': '#!/bin/sh\necho "go version go1.27.2 linux/amd64"\n',
            'cargo': '#!/bin/sh\necho "cargo 1.99.0"\n',
            'rustc': '#!/bin/sh\necho "rustc 1.99.0"\n',
            'cc': '#!/bin/sh\nexit 0\n',
            'pkg-config': '#!/bin/sh\necho 3.0.0\n',
            'python3': '#!/bin/sh\nexec /usr/bin/python3 "$@"\n',
        }.items():
            path = tools / name
            path.write_text(body)
            path.chmod(0o755)
        result = run_boot(['plan', '--prefix', str(self.root / 'p')], env={'PATH': str(tools)})
        self.assertEqual(result.returncode, 0, result.stderr)
        checks = {item['command']: item for item in json.loads(result.stdout)['build_checks']}
        self.assertTrue(checks['go']['passed'])
        self.assertEqual(checks['go']['path'], str(tools / 'go'))
        (tools / 'go').write_text('#!/bin/sh\n/bin/sleep 30\n')
        (tools / 'go').chmod(0o755)
        result = run_boot(['plan', '--prefix', str(self.root / 'slow')], env={'PATH': str(tools)})
        checks = {item['command']: item for item in json.loads(result.stdout)['build_checks']}
        self.assertFalse(checks['go']['passed'])
        self.assertIn('timed out', checks['go']['error'])

    def test_rust_preflight_uses_locked_dependency_minimum(self):
        tools = self.root / 'tools'
        tools.mkdir()
        for name, body in {
            'cargo': '#!/bin/sh\necho "cargo 1.87.0"\n',
            'rustc': '#!/bin/sh\necho "rustc 1.87.0"\n',
            'go': '#!/bin/sh\necho "go version go1.22.0 linux/amd64"\n',
            'cc': '#!/bin/sh\nexit 0\n',
            'pkg-config': '#!/bin/sh\necho 3.0.0\n',
            'python3': '#!/bin/sh\nexec /usr/bin/python3 "$@"\n',
        }.items():
            path = tools / name
            path.write_text(body)
            path.chmod(0o755)
        result = run_boot(['plan', '--prefix', str(self.root / 'p')], env={'PATH': str(tools)})
        checks = {item['command']: item for item in json.loads(result.stdout)['build_checks']}
        self.assertFalse(checks['cargo']['passed'])
        self.assertFalse(checks['rustc']['passed'])
        self.assertTrue(checks['go']['passed'])
        self.assertEqual(json.loads(result.stdout)['fix'], [
            'rustup update stable (or install rustup from https://rustup.rs; distro Rust is often older than 1.88)'])

    def test_default_prefix_respects_data_home_without_writes(self):
        data_home = self.root / 'data home'
        env = {key: value for key, value in os.environ.items() if key != 'AGENT_KNOWLEDGE_HOME'}
        env['XDG_DATA_HOME'] = str(data_home)
        result = subprocess.run(['/bin/sh', str(BOOT), 'plan'], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['prefix'], str((data_home / '10x-swe/knowledge').resolve()))
        self.assertFalse(data_home.exists())

    def test_owned_retries_reject_conflicts_and_changed_source(self):
        target = self.root / 'owned'
        first = subprocess.run(['/bin/sh', '-c',
                                'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"',
                                'sh', str(BOOT), str(target), 'a' * 64], capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = subprocess.run(['/bin/sh', '-c',
                                 'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"',
                                 'sh', str(BOOT), str(target), 'a' * 64], capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        changed = subprocess.run(['/bin/sh', '-c',
                                  'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"',
                                  'sh', str(BOOT), str(target), 'b' * 64], capture_output=True, text=True)
        self.assertNotEqual(changed.returncode, 0)
        self.assertEqual(changed.returncode, 2)
        conflict = self.root / 'existing'
        conflict.mkdir()
        (conflict / 'valuable').write_text('retain')
        refused = subprocess.run(['/bin/sh', '-c',
                                  'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"',
                                  'sh', str(BOOT), str(conflict), 'a' * 64], capture_output=True, text=True)
        self.assertIn('unowned', refused.stderr)
        self.assertEqual((conflict / 'valuable').read_text(), 'retain')
        alias = self.root / 'alias'
        alias.symlink_to(target)
        rejected = run_boot(['plan', '--prefix', str(alias)])
        self.assertIn('symlink', rejected.stderr)

    def test_failed_setup_is_not_readiness_and_tampered_artifacts_fail(self):
        target = self.root / 'owned'
        subprocess.run(['/bin/sh', '-c',
                        'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"',
                        'sh', str(BOOT), str(target), 'a' * 64], check=True)
        missing = run_boot(['doctor', '--prefix', str(target)])
        self.assertIn('No completed', missing.stderr)
        (target / 'artifact').write_text('changed')
        (target / 'installation.json').write_text(json.dumps({'artifacts': {'artifact': 'a' * 64}}))
        tampered = run_boot(['doctor', '--prefix', str(target)], env={'PATH': str(self.root / 'no-tools')})
        self.assertIn('artifacts changed', tampered.stderr)
        self.assertNotIn('python3', tampered.stderr)

    def test_source_tree_install_is_rejected_before_write(self):
        target = REPO / 'never-create-this'
        result = run_boot(['setup', '--prefix', str(target)])
        self.assertIn('outside the source', result.stderr)
        self.assertFalse(target.exists())

    def test_incomplete_setup_still_requires_build_tools_and_retains_no_receipt(self):
        target = self.root / 'missing-tools'
        for _ in range(2):
            result = run_boot(['setup', '--prefix', str(target)], env={'PATH': str(self.root / 'no-tools')})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Missing build prerequisite: cargo', result.stderr)
            self.assertFalse((target / 'installation.json').exists())

    def test_shell_quote_matches_python_for_the_activation_file(self):
        sample = "installed tools' prefix"
        result = subprocess.run(['/bin/sh', '-c',
                                 'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; shell_quote "$2"',
                                 'sh', str(BOOT), sample], capture_output=True, text=True)
        self.assertEqual(result.stdout, "'installed tools'\"'\"' prefix'")

    def test_source_fingerprint_matches_python_json_dumps(self):
        shell = subprocess.run(['/bin/sh', '-c',
                                'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; source_fingerprint',
                                'sh', str(BOOT)], capture_output=True, text=True, check=True)
        git = subprocess.run(['git', '-C', str(REPO), 'ls-files', '-z', '--cached', '--',
                              'plugins/knowledge', 'plugins/10x-swe/skills'], capture_output=True, check=True)
        manifest = {}
        for name in git.stdout.split(b'\0'):
            if not name:
                continue
            path = REPO / os.fsdecode(name)
            if path.is_file() and not path.is_symlink():
                manifest[str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        self.assertEqual(shell.stdout.strip(), expected)

    def test_failed_build_checks_come_with_a_one_line_fix(self):
        result = run_boot(['setup', '--prefix', str(self.root / 'x')], env={'PATH': str(self.root / 'no-tools')})
        self.assertIn('Missing build prerequisite: cargo', result.stderr)
        self.assertRegex(result.stderr, r'fix: (sudo apt-get|sudo dnf|xcode-select)')
        plan = run_boot(['plan', '--prefix', str(self.root / 'y')], env={'PATH': str(self.root / 'no-tools')})
        self.assertTrue(json.loads(plan.stdout)['fix'])

    def test_failed_build_repeats_disk_and_network_causes(self):
        script = self.root / 'fail.py'
        script.write_text(
            'import sys\n'
            'print("cargo:warning=ar: bcm.o: No space left on device")\n'
            'print("noise")\n'
            'print("error: failed to download crate: Could not resolve host: example.invalid")\n'
            'sys.exit(101)\n')
        result = subprocess.run(['/bin/sh', '-c',
                                 'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; run_stream "$2" "$3"',
                                 'sh', str(BOOT), '/usr/bin/python3', str(script)], capture_output=True, text=True)
        self.assertIn('exit status 101', result.stderr)
        self.assertIn('cause: cargo:warning=ar: bcm.o: No space left on device', result.stderr)
        self.assertIn('Could not resolve host: example.invalid', result.stderr)
        self.assertNotIn('noise', result.stderr)

    def test_release_build_scratch_removes_only_the_build_tree(self):
        target = self.root / 'prefix'
        (target / 'build/rust/release').mkdir(parents=True)
        (target / 'build/rust/release/skill-search').write_text('bin')
        (target / 'libexec/native').mkdir(parents=True)
        result = subprocess.run(['/bin/sh', '-c',
                                 'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; release_build_scratch "$2"',
                                 'sh', str(BOOT), str(target)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((target / 'build').exists())
        self.assertTrue((target / 'libexec/native').is_dir())

    def test_require_disk_space_names_the_shortfall(self):
        result = subprocess.run(['/bin/sh', '-c',
                                 'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"\n'
                                 'disk_free_bytes() { echo 1073741824; }\n'
                                 'require_disk_space "$2"\n',
                                 'sh', str(BOOT), str(self.root)], capture_output=True, text=True)
        self.assertIn('1024 MiB available', result.stderr)

    def test_setup_points_temp_files_at_the_prefix(self):
        tools = self.root / 'tools'
        tools.mkdir()
        seen = self.root / 'seen-tmp'
        wrapper = tools / 'python3'
        wrapper.write_text('#!/bin/sh\n'
                           'if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then\n'
                           '  printf "%s\\n" "$TMPDIR" > "$SEEN"\n'
                           '  exit 1\n'
                           'fi\n'
                           'exec /usr/bin/python3 "$@"\n')
        wrapper.chmod(0o755)
        for name, body in {
            'cargo': '#!/bin/sh\necho "cargo 1.99.0"\n',
            'rustc': '#!/bin/sh\necho "rustc 1.99.0"\n',
            'go': '#!/bin/sh\necho "go version go1.22.0 linux/amd64"\n',
            'cc': '#!/bin/sh\nexit 0\n',
            'pkg-config': '#!/bin/sh\necho 3.0.0\n',
        }.items():
            path = tools / name
            path.write_text(body)
            path.chmod(0o755)
        target = self.root / 'installed'
        result = run_boot(['setup', '--prefix', str(target)], env={'PATH': str(tools), 'SEEN': str(seen)})
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertEqual(seen.read_text().strip(), str(target / 'build/tmp'))
        self.assertTrue((target / 'build/tmp').is_dir())

    def test_old_pkg_config_miss_uses_the_os_line(self):
        tools = self.root / 'tools'
        tools.mkdir()
        for name, body in {
            'cargo': '#!/bin/sh\necho "cargo 1.99.0"\n',
            'rustc': '#!/bin/sh\necho "rustc 1.99.0"\n',
            'go': '#!/bin/sh\necho "go version go1.22.0 linux/amd64"\n',
            'cc': '#!/bin/sh\nexit 0\n',
            'python3': '#!/bin/sh\nexec /usr/bin/python3 "$@"\n',
        }.items():
            path = tools / name
            path.write_text(body)
            path.chmod(0o755)
        result = run_boot(['plan', '--prefix', str(self.root / 'p')], env={'PATH': str(tools)})
        fixes = json.loads(result.stdout)['fix']
        self.assertTrue(fixes)
        self.assertRegex(fixes[0], r'sudo apt-get|sudo dnf|xcode-select')

    def test_untracked_files_do_not_change_the_fingerprint(self):
        before = subprocess.run(['/bin/sh', '-c',
                                 'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; source_fingerprint',
                                 'sh', str(BOOT)], capture_output=True, text=True, check=True).stdout
        skill = REPO / 'plugins/10x-swe/skills/chrome-devtools/scripts'
        created = [skill / 'node_modules/fingerprint-probe/index.js', skill / 'fingerprint-probe.untracked']
        try:
            for path in created:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('probe')
            after = subprocess.run(['/bin/sh', '-c',
                                    'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; source_fingerprint',
                                    'sh', str(BOOT)], capture_output=True, text=True, check=True).stdout
            self.assertEqual(before, after)
        finally:
            for path in created:
                path.unlink(missing_ok=True)
            probe = skill / 'node_modules/fingerprint-probe'
            if probe.exists():
                probe.rmdir()
            node = skill / 'node_modules'
            if node.exists():
                node.rmdir()

    def test_stage_sources_skips_untracked_files(self):
        skill = REPO / 'plugins/10x-swe/skills/chrome-devtools'
        extra = skill / 'fingerprint-probe.untracked'
        go_extra = REPO / 'plugins/knowledge/tools/insights/fingerprint_probe.go'
        extra.write_text('not certified')
        go_extra.write_text('package main\n')
        target = self.root / 'installed'
        try:
            result = subprocess.run(['/bin/sh', '-c',
                                     'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; stage_sources "$2"',
                                     'sh', str(BOOT), str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            installed = target / 'engineering-skills/chrome-devtools'
            self.assertTrue((installed / 'SKILL.md').is_file())
            self.assertFalse((installed / extra.name).exists())
            self.assertFalse((target / 'build/source/tools/insights' / go_extra.name).exists())
            self.assertTrue((target / 'build/source/tools/insights/main.go').is_file())
        finally:
            extra.unlink(missing_ok=True)
            go_extra.unlink(missing_ok=True)

    def test_upgrade_carries_user_data_and_rejects_a_missing_source(self):
        old = self.root / 'old'
        new = self.root / 'new'
        subprocess.run(['/bin/sh', '-c',
                        'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"; owned "$4" "$5"',
                        'sh', str(BOOT), str(old), 'a' * 64, str(new), 'b' * 64], check=True, capture_output=True, text=True)
        (old / 'knowledge/sources/entries').mkdir(parents=True)
        (old / 'knowledge/sources/entries/note.md').write_text('kept')
        (old / 'state/bookmarks').mkdir(parents=True)
        (old / 'state/bookmarks/db.json').write_text('{}')
        copied = subprocess.run(['/bin/sh', '-c',
                                 'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; carry_over "$2" "$3"',
                                 'sh', str(BOOT), str(old), str(new)], capture_output=True, text=True)
        self.assertEqual(copied.returncode, 0, copied.stderr)
        self.assertEqual((new / 'knowledge/sources/entries/note.md').read_text(), 'kept')
        self.assertTrue((new / 'state/bookmarks/db.json').is_file())
        self.assertTrue((old / 'knowledge/sources/entries/note.md').is_file())
        missing = subprocess.run(['/bin/sh', '-c',
                                  'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; carry_over "$2" "$3"',
                                  'sh', str(BOOT), str(self.root / 'nowhere'), str(new)], capture_output=True, text=True)
        self.assertIn('existing knowledge installation', missing.stderr)

    def test_upgrade_rejects_links_overlaps_and_nonempty_destinations(self):
        old = self.root / 'old'
        new = self.root / 'new'
        subprocess.run(['/bin/sh', '-c',
                        'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"; owned "$4" "$5"',
                        'sh', str(BOOT), str(old), 'a' * 64, str(new), 'b' * 64], check=True, capture_output=True, text=True)
        (old / 'knowledge/sources/entries').mkdir(parents=True)
        (old / 'knowledge/sources/entries/note.md').write_text('kept')
        (old / 'state').mkdir()
        (old / 'state/alias').symlink_to(old / 'knowledge/sources')
        linked = subprocess.run(['/bin/sh', '-c',
                                 'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; carry_over "$2" "$3"',
                                 'sh', str(BOOT), str(old), str(new)], capture_output=True, text=True)
        self.assertIn('symlink', linked.stderr)
        self.assertFalse((new / 'knowledge').exists())
        (old / 'state/alias').unlink()
        nested = old / 'state/new'
        subprocess.run(['/bin/sh', '-c',
                        'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"',
                        'sh', str(BOOT), str(nested), 'b' * 64], check=True, capture_output=True, text=True)
        overlap = subprocess.run(['/bin/sh', '-c',
                                  'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; carry_over "$2" "$3"',
                                  'sh', str(BOOT), str(old), str(nested)], capture_output=True, text=True)
        self.assertIn('overlap', overlap.stderr)
        fresh = self.root / 'fresh'
        subprocess.run(['/bin/sh', '-c',
                        'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"',
                        'sh', str(BOOT), str(fresh), 'c' * 64], check=True, capture_output=True, text=True)
        (fresh / 'state').mkdir()
        (fresh / 'state/bookmark').write_text('new')
        (old / 'state/bookmark').write_text('old')
        nonempty = subprocess.run(['/bin/sh', '-c',
                                   'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; carry_over "$2" "$3"',
                                   'sh', str(BOOT), str(old), str(fresh)], capture_output=True, text=True)
        self.assertIn('empty', nonempty.stderr)
        self.assertEqual((fresh / 'state/bookmark').read_text(), 'new')

    def test_changed_source_error_points_at_the_upgrade_path(self):
        target = self.root / 'old'
        subprocess.run(['/bin/sh', '-c',
                        'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"',
                        'sh', str(BOOT), str(target), '0' * 64], check=True, capture_output=True, text=True)
        result = run_boot(['setup', '--prefix', str(target)])
        self.assertIn('--from', result.stderr)
        self.assertFalse((target / 'installation.json').exists())

    def test_interrupted_migration_cannot_be_certified_by_retrying_setup(self):
        target = self.root / 'new'
        fingerprint = subprocess.run(['/bin/sh', '-c',
                                      'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; source_fingerprint',
                                      'sh', str(BOOT)], capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(['/bin/sh', '-c',
                        'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"',
                        'sh', str(BOOT), str(target), fingerprint], check=True, capture_output=True, text=True)
        (target / '.migration-pending').write_text('old\n')
        result = run_boot(['setup', '--prefix', str(target)])
        self.assertIn('migration was interrupted', result.stderr)
        self.assertFalse((target / 'installation.json').exists())

    def test_upgrade_preserves_committed_wal_data(self):
        old = self.root / 'old'
        new = self.root / 'new'
        subprocess.run(['/bin/sh', '-c',
                        'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"; owned "$4" "$5"',
                        'sh', str(BOOT), str(old), 'a' * 64, str(new), 'b' * 64], check=True, capture_output=True, text=True)
        (old / 'state').mkdir()
        database = old / 'state/session-search.sqlite'
        connection = sqlite3.connect(database)
        try:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('CREATE TABLE sessions (body TEXT)')
            connection.execute("INSERT INTO sessions VALUES ('kept')")
            connection.commit()
            self.assertTrue(Path(str(database) + '-wal').is_file())
            copied = subprocess.run(['/bin/sh', '-c',
                                     'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; carry_over "$2" "$3"',
                                     'sh', str(BOOT), str(old), str(new)], capture_output=True, text=True)
            self.assertEqual(copied.returncode, 0, copied.stderr)
            restored = sqlite3.connect(new / 'state/session-search.sqlite')
            try:
                self.assertEqual(restored.execute('SELECT body FROM sessions').fetchall(), [('kept',)])
                self.assertEqual(restored.execute('PRAGMA integrity_check').fetchone(), ('ok',))
            finally:
                restored.close()
        finally:
            connection.close()

    def test_stale_setup_lock_is_replaced_when_its_pid_is_gone(self):
        target = self.root / 'locked'
        fingerprint = subprocess.run(['/bin/sh', '-c',
                                      'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; source_fingerprint',
                                      'sh', str(BOOT)], capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(['/bin/sh', '-c',
                        'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"',
                        'sh', str(BOOT), str(target), fingerprint], check=True, capture_output=True, text=True)
        lock = target / '.setup.lock.d'
        lock.mkdir()
        (lock / 'pid').write_text('999999\n')
        result = run_boot(['setup', '--prefix', str(target)], env={'PATH': str(self.root / 'no-tools')})
        self.assertIn('Missing build prerequisite: cargo', result.stderr)
        self.assertNotIn('Resource temporarily unavailable', result.stderr)
        self.assertFalse(lock.exists())

    def test_doctor_names_the_prefix_it_checked(self):
        home = self.root / 'agent home'
        result = run_boot(['doctor'], env={'AGENT_KNOWLEDGE_HOME': str(home)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Checking installation at ' + str(home.resolve()), result.stderr)
        self.assertIn('No completed installation receipt at ' + str(home.resolve()), result.stderr)
        self.assertFalse(home.exists())

    def install_fake_commands(self, target):
        launcher = target / 'libexec/launch.py'
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text('#!/bin/sh\nexit 0\n')
        launcher.chmod(0o755)
        native = target / 'libexec/native/session-search'
        native.parent.mkdir(parents=True, exist_ok=True)
        native.write_text('#!/bin/sh\nexit 0\n')
        native.chmod(0o755)
        bindir = target / 'bin'
        bindir.mkdir(exist_ok=True)
        for name in COMMANDS:
            link = bindir / name
            if link.exists() or link.is_symlink():
                link.unlink()
            if name == 'session-search':
                link.symlink_to('../libexec/native/session-search')
            else:
                link.symlink_to('../libexec/launch.py')

    def test_completed_setup_restores_activation_without_rebuilding(self):
        target = self.root / 'installed'
        fingerprint = subprocess.run(['/bin/sh', '-c',
                                      'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; source_fingerprint',
                                      'sh', str(BOOT)], capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(['/bin/sh', '-c',
                        'KNOWLEDGE_BOOTSTRAP_LIBRARY=1; KNOWLEDGE_BOOTSTRAP_PATH="$1"; . "$1"; owned "$2" "$3"',
                        'sh', str(BOOT), str(target), fingerprint], check=True, capture_output=True, text=True)
        self.install_fake_commands(target)
        (target / 'installation.json').write_text(json.dumps({
            'schema': 'knowledge-installation/v1',
            'fingerprint': fingerprint,
            'profile': 'keyword',
            'artifacts': {'libexec/launch.py': hashlib.sha256((target / 'libexec/launch.py').read_bytes()).hexdigest()},
            'created': 1,
        }))
        result = run_boot(['setup', '--prefix', str(target)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((target / 'env.sh').is_file())
        self.assertIn('Activate explicitly: . ', result.stdout)
        command = result.stdout.split('Activate explicitly: ', 1)[1].splitlines()[0]
        activated = subprocess.run(['/bin/sh', '-c', command + '; printf "%s" "$AGENT_KNOWLEDGE_HOME"'],
                                   capture_output=True, text=True)
        self.assertEqual(activated.returncode, 0, activated.stderr)
        self.assertEqual(activated.stdout, str(target))
        (target / 'env.sh').write_text('custom activation\n')
        refused = run_boot(['setup', '--prefix', str(target)])
        self.assertIn('env.sh', refused.stderr)
        self.assertEqual((target / 'env.sh').read_text(), 'custom activation\n')


if __name__ == '__main__':
    unittest.main()
