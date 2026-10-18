#!/usr/bin/env python3
"""Source-built, owned-prefix installation. No credentials, crawls or publication."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[1]
MARKER = '.knowledge-owner.json'
COMMANDS = ('skill-search', 'bkd', 'distiller', 'insights', 'source-insights', 'session-search', 'knowledge-intake')
# Minimum free disk space for a full source build (cargo target dirs dominate).
MINIMUM_FREE_BYTES = 3 * 1024**3


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inputs():
    return {str(p.relative_to(REPO)): digest(p) for base in (PACKAGE, REPO / 'plugins/10x-swe/skills')
            for p in sorted(base.rglob('*')) if p.is_file()
            and not any(part in ('__pycache__', 'target', '.venv') for part in p.parts)}


def require_disk_space(prefix):
    probe = prefix if prefix.exists() else prefix.parent
    free = shutil.disk_usage(probe).free
    if free < MINIMUM_FREE_BYTES:
        raise ValueError(
            'Not enough free disk space for setup: %d MiB available at %s, need at least %d MiB'
            % (free // 1024**2, probe, MINIMUM_FREE_BYTES // 1024**2))


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2); stream.write('\n')
        temporary = Path(stream.name)
    temporary.replace(path)


def run(argv, **kwargs):
    print('+ ' + shlex.join(map(str, argv)), flush=True)
    subprocess.run(list(map(str, argv)), check=True, **kwargs)


def command_check(command, arguments, *, input=None):
    path = shutil.which(command)
    result = {'command': command, 'path': path, 'passed': False}
    if not path:
        result['error'] = 'Missing build prerequisite: ' + command
        return result
    try:
        probe = subprocess.run([path, *arguments], input=input, capture_output=True,
                               text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        result['error'] = f'{command} probe failed: {error}'
        return result
    result['output'] = probe.stdout.strip()[:500]
    result['passed'] = probe.returncode == 0
    if not result['passed']:
        result['error'] = f'{command} probe failed: {probe.stderr.strip()[:500] or probe.returncode}'
    return result


def version_check(command, arguments, pattern, minimum):
    result = command_check(command, arguments)
    if result['passed']:
        match = re.match(pattern, result['output'])
        result['passed'] = bool(match and tuple(map(int, match.groups())) >= minimum)
        if not result['passed']:
            label = 'Go' if command == 'go' else command
            version = '.'.join(map(str, minimum))
            result['error'] = f'{result["path"]} must report {label} {version}+; check PATH or update the compiler'
    return result


def build_checks():
    python = {'command': 'python', 'path': sys.executable, 'output': platform.python_version(),
              'passed': sys.version_info >= (3, 11)}
    if not python['passed']:
        python['error'] = 'Python 3.11+ is required'
    checks = [python, version_check('cargo', ['--version'], r'^cargo (\d+)\.(\d+)', (1, 88)),
              version_check('rustc', ['--version'], r'^rustc (\d+)\.(\d+)', (1, 88)),
              version_check('go', ['version'], r'^go version go(\d+)\.(\d+)', (1, 22)),
              command_check('cc', ['-x', 'c', '-fsyntax-only', '-'], input='int main(void) { return 0; }\n')]
    if platform.system() == 'Linux':
        checks.append(command_check('pkg-config', ['--modversion', 'openssl']))
    return checks


def environment(prefix):
    env = os.environ.copy()
    env.update(AGENT_KNOWLEDGE_HOME=str(prefix), SOURCE_INSIGHTS_LIBRARY=str(prefix / 'knowledge/sources'),
               SOURCE_INSIGHTS_INDEX_MODE='keyword', SESSION_SEARCH_DB=str(prefix / 'state/session-search.sqlite'),
               BKD_HOME=str(prefix / 'state/bookmarks'), PYTHONDONTWRITEBYTECODE='1')
    env['PYTHONPATH'] = str(prefix / 'lib')
    env['PATH'] = str(prefix / 'bin') + os.pathsep + env.get('PATH', '')
    return env


def owned(prefix, fingerprint):
    if prefix.is_symlink():
        raise ValueError('Installation prefix must not be a symlink')
    marker = prefix / MARKER
    if prefix.exists():
        if not marker.is_file() or marker.is_symlink():
            raise ValueError('Refusing an existing unowned prefix; choose a fresh directory')
        if json.loads(marker.read_text()) != {'schema': 'knowledge-owner/v1', 'fingerprint': fingerprint}:
            raise ValueError('Prefix belongs to different source bytes; choose a fresh prefix for this revision')
        for path in prefix.rglob('*'):
            if path.is_symlink() and not path.resolve().is_relative_to(prefix):
                # A venv interpreter points to its host runtime, never a write target.
                if not path.is_relative_to(prefix / 'runtimes'):
                    raise ValueError('Unexpected external symlink in owned prefix: ' + str(path))
    else:
        prefix.mkdir(parents=True)
        atomic(marker, {'schema': 'knowledge-owner/v1', 'fingerprint': fingerprint})


def graph(prefix, python, env):
    helper = prefix / 'skills/skill-graph/scripts/graph.py'
    roots = prefix / 'knowledge/skills/roots.json'
    atomic(roots, {'roots': [{'id': 'global', 'path': str(prefix / 'skills')},
                            {'id': 'plugin/10x-swe', 'path': str(prefix / 'engineering-skills')}]})
    # Generate backlinks only inside this installation, never against pre-existing skills.
    with tempfile.TemporaryDirectory(prefix='knowledge-backlinks-') as stage:
        proposal = Path(stage) / 'proposal'
        run([python, helper, 'annotate', '--roots', roots, '--output', proposal], env=env)
        for path in proposal.rglob('SKILL.md'):
            rel = path.relative_to(proposal)
            parts = rel.parts
            destination = prefix / ('skills' if parts[0] == 'global' else 'engineering-skills')
            tail = parts[1:] if parts[0] == 'global' else parts[2:]
            shutil.copyfile(path, destination.joinpath(*tail))
    run([prefix / 'bin/skill-search', 'refresh', '--lexical'], env=env)


def activation_text(prefix):
    return ('export PATH=' + shlex.quote(str(prefix / 'bin')) + ':"$PATH"\n'
            + 'export AGENT_KNOWLEDGE_HOME=' + shlex.quote(str(prefix)) + '\n'
            + 'export SOURCE_INSIGHTS_INDEX_MODE="${SOURCE_INSIGHTS_INDEX_MODE:-keyword}"\n')


def check_activation(prefix):
    path = prefix / 'env.sh'
    if not path.exists() and not path.is_symlink():
        raise ValueError('Missing env.sh; rerun setup with the same source and prefix to restore activation')
    if path.is_symlink() or not path.is_file() or path.read_text() != activation_text(prefix):
        raise ValueError('Installed env.sh changed; preserve your changes and choose a fresh prefix')


def ensure_activation(prefix):
    path = prefix / 'env.sh'
    if not path.exists() and not path.is_symlink():
        with tempfile.NamedTemporaryFile(mode='w', dir=prefix, prefix='.env-', delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(activation_text(prefix))
                stream.close()
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
    check_activation(prefix)


def next_steps(prefix):
    print('Activate explicitly: . ' + shlex.quote(str(prefix / 'env.sh')))
    print("Then try: skill-search search 'debug a regression' --limit 5")


def doctor(prefix, verify=True):
    receipt = prefix / 'installation.json'
    if not receipt.is_file():
        raise ValueError('No completed installation receipt; rerun setup after fixing its error')
    data = json.loads(receipt.read_text())
    errors = [rel for rel, sha in data['artifacts'].items()
              if not (prefix / rel).is_file() or digest(prefix / rel) != sha]
    if errors:
        if errors == ['env.sh'] and not (prefix / 'env.sh').exists():
            check_activation(prefix)
        raise ValueError('Installed artifacts changed: ' + ', '.join(errors[:10]))
    check_activation(prefix)
    for command in COMMANDS:
        target = prefix / 'bin' / command
        if not target.is_symlink() or target.resolve() != (prefix / 'libexec/launch.py').resolve():
            raise ValueError('Installed command launcher changed: ' + command)
    if verify:
        env = environment(prefix)
        for command in COMMANDS:
            run([prefix / 'bin' / command, '--help'], env=env, stdout=subprocess.DEVNULL)
        run([prefix / 'bin/skill-search', 'export'], env=env, stdout=subprocess.DEVNULL)
    capabilities = {name: {'executable_found': shutil.which(name) is not None, 'required_for': purpose,
                           'capability_verified': False}
                    for name, purpose in {'pandoc': 'EPUB conversion', 'dagu': 'optional workflow runner; use 2.19.2',
                                          'llama-embedding': 'optional local neural ranking; pinned model also required',
                                          'ffmpeg': 'media', 'yt-dlp': 'media'}.items()}
    print(json.dumps({'status': 'passed', 'profile': 'keyword', 'prefix': str(prefix),
                      'optional': capabilities, 'excluded': ['Kindle delivery', 'credentials', 'source-session indexing']}, indent=2))


def setup(prefix):
    if prefix.resolve().is_relative_to(REPO):
        raise ValueError('Keep installation state outside the source repository')
    if platform.system() not in ('Darwin', 'Linux'):
        raise ValueError('This source package targets macOS and Linux/WSL; native Windows is unsupported')
    if sys.version_info < (3, 11):
        raise ValueError('Python 3.11+ is required')
    manifest = inputs()
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    owned(prefix, fingerprint)
    with (prefix / '.setup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (prefix / 'installation.json').exists():
            ensure_activation(prefix)
            doctor(prefix)
            next_steps(prefix)
            return
        failed = [check['error'] for check in build_checks() if not check['passed']]
        if failed:
            raise ValueError('; '.join(failed))
        require_disk_space(prefix)
        for folder in ('bin', 'libexec/native', 'knowledge/sources/entries', 'state', 'runtimes', 'build'):
            (prefix / folder).mkdir(parents=True, exist_ok=True)
        for source, dest in ((PACKAGE / 'skills', prefix / 'skills'),
                             (PACKAGE / 'lib', prefix / 'lib'),
                             (REPO / 'plugins/10x-swe/skills', prefix / 'engineering-skills')):
            shutil.copytree(source, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', 'target'))
        python = prefix / 'runtimes/source-insights/bin/python'
        if not python.exists():
            run([sys.executable, '-m', 'venv', prefix / 'runtimes/source-insights'])
        run([python, '-m', 'pip', 'install', '--require-hashes', '-r', PACKAGE / 'requirements.lock'])
        runtime = prefix / 'runtimes/skill-graph'
        if not runtime.exists():
            runtime.symlink_to('source-insights', target_is_directory=True)
        env = environment(prefix)
        for source, command in ((PACKAGE / 'skills/skill-graph/scripts/search-core', 'skill-search'),
                                (PACKAGE / 'tools/bkd', 'bkd'), (PACKAGE / 'tools/distiller', 'distiller')):
            run(['cargo', 'build', '--locked', '--release', '--bin', command,
                 '--manifest-path', source / 'Cargo.toml', '--target-dir', prefix / 'build/rust'], env=env)
            shutil.copy2(prefix / 'build/rust/release' / command, prefix / 'libexec/native' / command)
        run(['go', 'build', '-trimpath', '-o', prefix / 'libexec/native/insights', '.'],
            cwd=PACKAGE / 'tools/insights', env=env)
        for name in ('launch.py', 'intake.py'):
            shutil.copy2(PACKAGE / name, prefix / 'libexec' / name)
        (prefix / 'libexec/launch.py').chmod(0o755)
        for command in COMMANDS:
            target = prefix / 'bin' / command
            if target.exists() or target.is_symlink():
                target.unlink()
            target.symlink_to('../libexec/launch.py')
        graph(prefix, python, env)
        run([prefix / 'bin/source-insights', 'reindex', '--rebuild'], env=env)
        if inputs() != manifest:
            raise ValueError('Source changed during setup; installation not certified')
        ensure_activation(prefix)
        artifacts = {str(p.relative_to(prefix)): digest(p) for base in ('libexec', 'lib', 'skills', 'engineering-skills')
                     for p in sorted((prefix / base).rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
        artifacts['env.sh'] = digest(prefix / 'env.sh')
        atomic(prefix / 'installation.json', {'schema': 'knowledge-installation/v1', 'fingerprint': fingerprint,
                                             'profile': 'keyword', 'artifacts': artifacts, 'created': int(time.time())})
        try:
            doctor(prefix)
        except Exception:
            (prefix / 'installation.json').unlink()
            raise
        # Build scratch is no longer needed; installed binaries live in libexec/native.
        # Pruning keeps the owned prefix small (a full cargo target dir is ~1.4 GiB).
        shutil.rmtree(prefix / 'build', ignore_errors=True)
        next_steps(prefix)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'setup', 'doctor'))
    parser.add_argument('--prefix', type=Path, default=Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / '10x-swe/knowledge')
    args = parser.parse_args()
    prefix = args.prefix.expanduser().absolute()
    try:
        if prefix.is_symlink():
            raise ValueError('Installation prefix must not be a symlink')
        prefix = prefix.resolve()
        if args.command == 'plan':
            checks = build_checks()
            print(json.dumps({'prefix': str(prefix), 'profile': 'keyword', 'tools': COMMANDS,
                              'build_prerequisites': ['Python 3.11+', 'Rust 1.88+ (current locked dependency minimum)', 'Go 1.22+', 'C compiler', 'OpenSSL development headers and pkg-config on Linux'],
                              'build_checks': checks, 'build_ready': all(check['passed'] for check in checks),
                              'effects': ['download hash-locked dependencies', 'compile sources', 'create owned empty libraries'],
                              'excluded': ['Kindle delivery', 'credentials', 'external skills activation', 'session crawl', 'cloud AI', 'publication']}, indent=2))
        elif args.command == 'setup':
            setup(prefix)
        else:
            doctor(prefix)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
