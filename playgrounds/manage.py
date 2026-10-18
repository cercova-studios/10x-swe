#!/usr/bin/env python3
"""Local microVMs with explicit host shares and recoverable workspaces. Commands compose through stdio."""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import mounts
CONFIG = json.loads((HERE / 'runtime.json').read_text())
VERSION = '0.1.0'
WORKSPACE = '/home/agent/workspace'
ENVIRONMENT = '. /home/agent/playground-env.sh; '
HEALTH = '''set -eu
test -f /home/agent/.playground-ready
. /home/agent/playground-env.sh
python3 --version
git --version
nix --version
for tool in skill-search session-search bkd distiller insights source-insights knowledge-intake; do
    "$tool" --help >/dev/null
done
dagu version
test -d /home/agent/workspace
'''
BOUNDARY = '''import json, pathlib, subprocess, sys
expected = json.loads(sys.argv[1])
seen = set()
for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines():
    entry, fs = line.split(' - ', 1)
    target = entry.split()[4].replace(chr(92) + '040', ' ').replace(chr(92) + '134', chr(92))
    if fs.split()[0] in ('virtiofs', '9p') and target != '/etc/resolv.conf':
        assert target in expected, 'unexpected host share: ' + target
        assert expected[target] in entry.split()[5].split(','), 'wrong mount mode: ' + target
        seen.add(target)
assert seen == set(expected), 'missing host shares'
result = subprocess.run(['ssh-add', '-l'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
assert result.returncode == 2, 'SSH proxy must not reach a host agent'
assert not pathlib.Path('/run/host-services').exists(), 'unexpected host services'
'''


def label(value):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}', value):
        raise argparse.ArgumentTypeError('Use 1-48 letters, digits, underscores or hyphens')
    return value


digest = mounts.sha256
atomic = mounts.write_json


def sbx(*args, capture=False, check=True, passthrough=False):
    env = os.environ.copy()
    env.pop('SSH_AUTH_SOCK', None)
    # Use local sbx commands; no workstation variables are passed with --env.
    result = subprocess.run(['sbx', *map(str, args)], env=env, check=False,
                            stdin=None if passthrough else subprocess.DEVNULL,
                            stdout=subprocess.PIPE if capture else (None if passthrough else sys.stderr),
                            stderr=subprocess.PIPE if capture else None, text=True)
    if check and result.returncode:
        if capture:
            print(result.stderr, file=sys.stderr, end='')
        result.check_returncode()
    return result


def guest(vm, argv, *, capture=False, check=True, interactive=False):
    flags = ['-i'] if interactive else []
    if interactive and sys.stdin.isatty() and sys.stdout.isatty():
        flags.append('-t')
    # Workspace argv is never interpolated as shell source.
    return sbx('exec', *flags, '--workdir', WORKSPACE, vm, 'bash', '-c',
               ENVIRONMENT + 'exec "$@"', 'playground', *argv,
               capture=capture, check=check, passthrough=not capture)


def preflight(*, setup=False):
    if sys.platform not in ('darwin', 'linux'):
        raise ValueError('Use a macOS or Linux host supported by Docker Sandboxes')
    if not shutil.which('sbx'):
        raise ValueError('Install Docker Sandboxes and sign in: https://docs.docker.com/ai/sandboxes/install/')
    version = sbx('version', capture=True).stdout
    if CONFIG['sbx_version'] not in version.split():
        raise ValueError('This runtime contract requires sbx ' + CONFIG['sbx_version'])
    if sbx('settings', 'get', 'ssh.agentForwardingEnabled', capture=True).stdout.strip() != 'false':
        raise ValueError('Disable host SSH forwarding explicitly: sbx settings set ssh.agentForwardingEnabled false; sbx daemon restart')
    for key in ('ssh.agentSocketPath', 'clipboard.imagePaste'):
        value = sbx('settings', 'get', key, capture=True).stdout.strip()
        if value not in ('', 'false'):
            raise ValueError(key + ' exposes host access; disable it explicitly before using playground')
    if setup:
        rules = json.loads(sbx('policy', 'ls', '--json', capture=True).stdout)['rules']
        if any(r.get('scope') == 'global' and r.get('resource_type') == 'network'
               and r.get('decision') == 'allow' and r.get('status') == 'active' for r in rules):
            raise ValueError('Setup requires a deny-by-default sbx global policy; review sbx policy ls first')


def seal(vm):
    sbx('policy', 'deny', 'network', '--sandbox', vm, '**', capture=True)


def create(vm, image, *, offline, shares=()):
    args = ['create', '--name', vm, '--skills', 'off', '--cpus', '2', '--memory', '4g',
            '--template', image, '--pull', 'never' if offline else 'missing']
    if offline:
        args += ['--deny-network', '**']
    # No implicit cwd or automatic skill shares. Paths are identical on host and guest.
    sbx(*args, 'shell', *(m['path'] + (':ro' if m['mode'] == 'ro' else '') for m in shares))
    # Keep the runtime alive across long saves; stopping it still stops writers.
    sbx('run', '--detach', '--name', vm)


def boundary(vm, shares=()):
    sbx('exec', vm, 'python3', '-c', BOUNDARY, json.dumps({m['path']: m['mode'] for m in shares}))


def import_bundle(vm, source, destination):
    path = '/tmp/tenx-' + uuid.uuid4().hex + '.tar'
    sbx('cp', source, vm + ':' + path)
    # sbx cp creates root-owned files; host umask deliberately makes them private.
    sbx('exec', vm, 'sudo', 'chown', 'agent:agent', path)
    sbx('exec', vm, 'tar', '-xf', path, '-C', destination)
    sbx('exec', vm, 'rm', path)


def safe_bundle(source, output, *, repository=False):
    """Copy selected data without following symlinks or special files."""
    source = source.resolve(strict=True)
    if not source.is_dir() or source == Path.home() or source == Path('/'):
        raise ValueError('Select a project directory, not a home directory or filesystem root')
    if (source / '.git').is_file():
        raise ValueError('Import a standalone repository; linked worktree metadata points outside the workspace')
    with tarfile.open(output, 'w') as bundle:
        def accept(info):
            if repository and any(p in ('.git', '__pycache__', 'target', '.venv') for p in Path(info.name).parts):
                return None
            if not (info.isfile() or info.isdir() or info.issym() or info.islnk()):
                raise ValueError('Special files cannot be imported: ' + info.name)
            if info.issym():
                target = (source / info.name).parent / info.linkname
                if not target.resolve().is_relative_to(source):
                    raise ValueError('Symlink escapes selected directory: ' + info.name)
            info.uid = info.gid = 1000
            info.uname = info.gname = 'agent'
            return info
        for child in sorted(source.iterdir()):
            bundle.add(child, arcname=child.name, filter=accept)


class Playground:
    def __init__(self, root, name):
        self.directory = root / label(name)
        self.statefile = self.directory / 'state.json'
        self.data = None

    @contextlib.contextmanager
    def locked(self):
        if self.directory.is_symlink():
            raise ValueError('Playground directory must not be a symlink')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.directory / '.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('Playground is busy; wait for its current command to finish') from None
            if self.statefile.exists():
                if self.statefile.is_symlink():
                    raise ValueError('State file must not be a symlink')
                self.data = json.loads(self.statefile.read_text())
                if self.data.get('schema') != 'playground/v1':
                    raise ValueError('Unknown playground state schema')
                if any(not re.fullmatch(r'tenx-[a-f0-9]{32}', vm) for vm in self.data['owned']):
                    raise ValueError('Invalid owned VM identity')
                if self.data['current'] is not None and self.data['current'] not in self.data['owned']:
                    raise ValueError('Current VM is not owned by this playground')
            elif any(path.name != '.lock' for path in self.directory.iterdir()):
                raise ValueError('Refusing an existing unowned playground directory')
            yield

    def save(self):
        atomic(self.statefile, self.data)

    def reserve(self):
        vm = 'tenx-' + uuid.uuid4().hex
        self.data['owned'].append(vm)
        self.save()  # Record ownership before a potentially interrupted creation.
        return vm

    def current(self):
        if not self.data or not self.data['current']:
            raise ValueError('No active workspace; run up or rewind a checkpoint')
        return self.data['current']

    def shares(self):
        return self.data.get('mounts', []) if self.data else []

    def ready(self, *, contents=True):
        mounts.Restore(self.directory).pending()
        mounts.validate(self.shares(), contents=contents)
        if self.shares():
            with mounts.leases(self.statefile, self.shares()):
                pass

    def stop_owned(self):
        for vm in self.data['owned']:
            sbx('stop', vm)

    def up(self, workspace, read_only=(), writable=()):
        mounts.Restore(self.directory).pending()
        if self.data and (self.data['current'] or self.data['owned']):
            raise ValueError('Playground exists; use run, rewind, or destroy before retrying setup')
        preflight(setup=True)
        if not (HERE / 'flake.lock').is_file():
            raise ValueError('Missing pinned playgrounds/flake.lock')
        for source in (REPO, workspace):
            if source is not None and self.directory.parent.resolve().is_relative_to(source.resolve()):
                raise ValueError('Host playground state must be outside imported directories')
        # Validate and freeze host input before creating any guest resources.
        with tempfile.TemporaryDirectory(prefix='tenx-input-') as tmp:
            tmp = Path(tmp)
            source = tmp / 'source.tar'
            safe_bundle(REPO, source, repository=True)
            selected = tmp / 'workspace.tar'
            if workspace is not None:
                safe_bundle(workspace, selected)
            self.data = {'schema': 'playground/v1', 'current': None, 'owned': [],
                         'source_sha256': digest(source), 'runtime': CONFIG,
                         'flake_lock_sha256': digest(HERE / 'flake.lock')}
            self.save()
            self.data['mounts'] = mounts.declarations(read_only, writable, self.directory, REPO)
            self.save()
            self.ready()
            vm = self.reserve()
            create(vm, CONFIG['image'], offline=False, shares=self.shares())
            try:
                boundary(vm, self.shares())
                sbx('policy', 'allow', 'network', '--sandbox', vm, ','.join(CONFIG['setup_hosts']))
                sbx('exec', vm, 'sudo', 'mkdir', '-p', '/opt/10x-swe')
                sbx('exec', vm, 'sudo', 'chown', 'agent:agent', '/opt/10x-swe')
                import_bundle(vm, source, '/opt/10x-swe')
                # Only the hash-frozen repository bootstrap runs while downloads are enabled.
                sbx('exec', vm, 'bash', '/opt/10x-swe/playgrounds/bootstrap.sh')
            finally:
                seal(vm)
            if workspace is not None:
                import_bundle(vm, selected, WORKSPACE)
            sbx('exec', vm, 'bash', '-c', HEALTH)
            self.data['current'] = vm
            self.save()
        return self.status()

    def run(self, argv):
        if not argv:
            raise ValueError('Supply a command after --, for example: run demo -- bash')
        vm = self.current()
        self.ready()
        preflight()
        seal(vm)
        boundary(vm, self.shares())
        return guest(vm, argv, check=False, interactive=True).returncode

    def checkpoint(self, name):
        vm = self.current()
        self.ready(contents=False)
        folder = self.directory / 'checkpoints' / label(name)
        if folder.exists():
            raise ValueError('Checkpoint already exists; choose a new label')
        folder.parent.mkdir(exist_ok=True)
        # Stop all writers first: images exclude tmpfs, mounts and /var/lib/docker.
        self.stop_owned()
        with tempfile.TemporaryDirectory(prefix='.checkpoint-', dir=folder.parent) as tmp:
            tmp = Path(tmp)
            image = 'tenx-checkpoint:' + uuid.uuid4().hex
            archive = tmp / 'image.tar'
            host = mounts.snapshot(self.shares(), tmp)
            sbx('template', 'save', vm, image, '--output', archive)
            mounts.sync_file(archive)
            atomic(tmp / 'checkpoint.json', {'schema': 'playground-checkpoint/v1',
                   'image': image, 'archive_sha256': digest(archive),
                   'mounts': host,
                   'source_sha256': self.data['source_sha256'],
                   'flake_lock_sha256': self.data['flake_lock_sha256']})
            tmp.rename(folder)  # Publish only a completed archive and manifest.
            mounts.sync_directory(folder.parent)
        return {'checkpoint': name, 'path': str(folder)}

    def rewind(self, name):
        if not self.data:
            raise ValueError('Unknown playground')
        folder = self.directory / 'checkpoints' / label(name)
        snapshot = json.loads((folder / 'checkpoint.json').read_text())
        if snapshot.get('schema') != 'playground-checkpoint/v1':
            raise ValueError('Unknown checkpoint schema')
        if digest(folder / 'image.tar') != snapshot['archive_sha256']:
            raise ValueError('Checkpoint archive checksum mismatch; current workspace is unchanged')
        self.ready(contents=False)
        mounts.verify(snapshot.get('mounts', []), folder, self.shares())
        preflight()
        # Hash-check before stopping anything. Never execute the damaged guest to recover it.
        old = self.data['current']
        self.stop_owned()
        sbx('template', 'load', folder / 'image.tar')
        candidate = self.reserve()
        restore = mounts.Restore(self.directory)
        transaction = None
        try:
            if self.shares():
                # Journal includes the candidate in owned, so recovery can stop it after a crash.
                transaction = restore.prepare(snapshot['mounts'], folder, self.data)
                restore.replace(transaction)
            create(candidate, snapshot['image'], offline=True, shares=self.shares())
            boundary(candidate, self.shares())
            sbx('exec', candidate, 'bash', '-c', HEALTH)
            self.data['current'] = candidate  # Old VM remains owned and inspectable.
            self.data['source_sha256'] = snapshot['source_sha256']
            self.data['flake_lock_sha256'] = snapshot['flake_lock_sha256']
            for share in self.shares():
                share['identity'] = mounts.identity(share['path'])
            self.save()
        except BaseException:
            # A pending host restore blocks commands until recover stops every owned guest.
            if restore.journal.exists():
                print('Host restore pending; run playground recover ' + self.directory.name, file=sys.stderr)
            raise
        history = restore.finish() if transaction is not None else None
        return {'restored': name, 'current': candidate, 'preserved': old, 'host_recovery_record': history}

    def recover(self):
        restore = mounts.Restore(self.directory)
        if not restore.journal.exists():
            raise ValueError('No interrupted host restore')
        existing = {vm['name'] for vm in json.loads(sbx('ls', '--json', capture=True).stdout)}
        for vm in self.data['owned']:
            if vm in existing:
                sbx('stop', vm)
        before = restore.rollback()
        # Do not lose a candidate reserved before a crash or reuse its possibly changed disk.
        before['owned'] = sorted(set(before['owned'] + self.data['owned']))
        self.data = before
        self.save()
        return {'recovered': True, 'current': self.data['current'], 'record': restore.finish()}

    def review(self):
        vm = self.current()
        self.ready()
        preflight()
        seal(vm)
        boundary(vm, self.shares())
        reviews = self.directory / 'reviews'
        reviews.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.review-', dir=reviews) as tmp:
            tmp = Path(tmp)
            # GNU tar reports files changed during archiving; failures never certify a review.
            guest(vm, ['tar', '--one-file-system', '-cf', '/tmp/tenx-review.tar', '-C', WORKSPACE, '.'])
            sbx('cp', vm + ':/tmp/tenx-review.tar', tmp / 'workspace.tar')
            mounts.sync_file(tmp / 'workspace.tar')
            with tarfile.open(tmp / 'workspace.tar') as archive:
                members = []
                for member in archive:
                    if len(members) >= 100000:
                        raise ValueError('Review exceeds 100000 entries; select a smaller workspace')
                    # Never extract guest-controlled archives or run their hooks on the host.
                    members.append({'path': member.name, 'bytes': member.size,
                                    'type': member.type.decode('ascii'), 'link': member.linkname})
            sha = digest(tmp / 'workspace.tar')
            self.stop_owned()
            host = mounts.snapshot(self.shares(), tmp)
            atomic(tmp / 'review.json', {'schema': 'playground-review/v1',
                   'sha256': sha, 'publication': 'pending-human-review', 'files': members, 'mounts': host})
            destination = reviews / uuid.uuid4().hex
            tmp.rename(destination)
            mounts.sync_directory(destination.parent)
        return {'review': str(destination / 'review.json'), 'archive': str(destination / 'workspace.tar'),
                'sha256': sha, 'publication': 'pending-human-review'}

    def status(self):
        if not self.data:
            raise ValueError('Unknown playground')
        return dict(self.data, checkpoints=sorted(p.name for p in (self.directory / 'checkpoints').glob('*')
                                                 if not p.name.startswith('.')))

    def stop(self):
        sbx('stop', self.current())
        return {'stopped': self.data['current']}

    def destroy(self):
        if not self.data:
            raise ValueError('Unknown playground')
        mounts.Restore(self.directory).pending()
        existing = {vm['name'] for vm in json.loads(sbx('ls', '--json', capture=True).stdout)}
        for vm in self.data['owned']:
            if vm in existing:
                sbx('rm', '--force', vm)
        self.data['current'] = None
        self.data['owned'] = []
        self.save()
        if self.shares():
            with mounts.leases(self.statefile):
                pass
        return {'destroyed': True, 'checkpoints_and_reviews_retained': str(self.directory)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--state-dir', type=Path, default=Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / '10x-swe/playgrounds')
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('doctor', help='Check the host runtime and setup boundary without creating a VM')
    for action in ('up', 'run', 'checkpoint', 'rewind', 'recover', 'review', 'status', 'stop', 'destroy'):
        command = commands.add_parser(action)
        command.add_argument('name', type=label)
        if action == 'up':
            command.add_argument('--workspace', type=Path, help='Copy this selected directory; never mount it')
            command.add_argument('--read-only', action='append', type=Path, default=[], help='Share a reference directory read-only; repeat for more paths')
            command.add_argument('--writable', action='append', type=Path, default=[], help='Share a directory with host snapshots; pause other host writers during checkpoint and rewind')
        if action in ('checkpoint', 'rewind'):
            command.add_argument('label', type=label)
        if action == 'run':
            command.add_argument('argv', nargs=argparse.REMAINDER)
        if action == 'destroy':
            command.add_argument('--yes', action='store_true', required=True, help='Remove only owned VMs; keep checkpoints and reviews')
    args = parser.parse_args(argv)
    try:
        os.umask(0o077)
        if args.action == 'doctor':
            preflight(setup=True)
            print(json.dumps({'runtime': CONFIG['sbx_version'], 'host_preflight': 'passed',
                              'guest_workflow': 'not-tested', 'local_only': True}, indent=2))
            return 0
        root = args.state_dir.expanduser()
        if root.is_symlink():
            raise ValueError('State directory must not be a symlink')
        root = root.absolute()
        playground = Playground(root, args.name)
        with playground.locked():
            if args.action == 'run':
                return playground.run(args.argv[1:] if args.argv[:1] == ['--'] else args.argv)
            if args.action == 'up':
                result = playground.up(args.workspace, args.read_only, args.writable)
            elif args.action in ('checkpoint', 'rewind'):
                result = getattr(playground, args.action)(args.label)
            else:
                result = getattr(playground, args.action)()
            print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print('playground: ' + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('playground: interrupted; owned resources and completed checkpoints are retained', file=sys.stderr)
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
