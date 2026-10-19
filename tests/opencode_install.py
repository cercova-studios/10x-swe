#!/usr/bin/env python3
"""Opt-in npm/.tgz acceptance test against a real OpenCode v2 executable.

Runs a loopback npm registry and isolated servers; never publishes or calls a model.
"""
import argparse
import base64
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlencode, unquote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'plugins/10x-swe'


def run(args, cwd, env, success=True):
    result = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, timeout=90)
    if success and result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stdout} {result.stderr}')
    return result


def environment(root):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith('OPENCODE_') or key.lower().startswith('npm_config_'):
            del env[key]
    for name in ['CONFIG', 'DATA', 'STATE', 'CACHE']:
        env[f'XDG_{name}_HOME'] = str(root / name.lower())
    env['OPENCODE_TEST_HOME'] = str(root / 'home')
    env['npm_config_userconfig'] = str(root / 'npmrc')
    env['npm_config_cache'] = str(root / 'npm-cache')
    env['npm_config_ignore_scripts'] = 'true'
    (root / 'home').mkdir(parents=True)
    (root / 'npmrc').write_text('')
    return env


@contextlib.contextmanager
def registry(archive, manifest):
    payload = archive.read_bytes()
    requested = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            requested.append(self.path)
            if unquote(self.path) == '/' + manifest['name']:
                version = {**manifest, 'dist': {
                    'tarball': f'http://127.0.0.1:{self.server.server_port}/package.tgz',
                    'shasum': hashlib.sha1(payload).hexdigest(),
                }}
                body = json.dumps({'name': manifest['name'], 'dist-tags': {'latest': manifest['version']},
                                   'versions': {manifest['version']: version}}).encode()
                content_type = 'application/json'
            elif self.path == '/package.tgz':
                body, content_type = payload, 'application/octet-stream'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', requested
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@contextlib.contextmanager
def opencode_server(binary, root, env):
    project = root / 'project'
    project.mkdir(exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with (root / 'server.log').open('w') as log:
        process = subprocess.Popen([binary, 'serve', '--hostname', '127.0.0.1', '--port', str(port)],
                                   cwd=project, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                # The server creates a temporary password. Never emit it in test output.
                match = re.search(r'server password (\S+)', (root / 'server.log').read_text())
                if match:
                    break
                if process.poll() is not None:
                    raise RuntimeError('OpenCode server exited before startup')
                time.sleep(0.1)
            else:
                raise TimeoutError('OpenCode server startup timed out')
            auth = base64.b64encode(('opencode:' + match[1]).encode()).decode()
            query = urlencode({'location[directory]': str(project)})

            def get(domain):
                request = Request(f'http://127.0.0.1:{port}/api/{domain}?{query}',
                                  headers={'Authorization': 'Basic ' + auth})
                with urlopen(request, timeout=10) as response:
                    return json.load(response)['data']

            yield get
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def verify(binary, root, env, expected, loaded=True):
    with opencode_server(binary, root, env) as get:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            plugins = get('plugin')
            plugin = next((p for p in plugins if p.get('id') == 'cercova.10x-swe'), None)
            if (loaded and plugin and plugin['state']['status'] == 'active') or (
                    not loaded and not plugin and len(plugins) > 5):
                break
            if plugin and plugin['state']['status'] in ('error', 'failed'):
                raise AssertionError(plugin)
            time.sleep(0.1)
        else:
            raise AssertionError('Plugin reconciliation timed out')
        skills = {s['id']: s for s in get('skill')}
        agents = {a['id']: a for a in get('agent')}
        commands = {c['name']: c for c in get('command')}
        if not loaded:
            assert not any(s['id'] in skills for s in expected['skills'])
            assert not any(a['name'] in agents for a in expected['agents'])
            assert not any('10x-swe:' + c['name'] in commands for c in expected['commands'])
            return
        for source in expected['skills']:
            skill = skills[source['id']]
            path = Path(skill['path'])
            assert root in path.parents, path  # A global/workspace copy cannot mask failure.
            canonical = (PACKAGE / source['path']).read_text()
            assert skill['content'] == canonical[canonical.index('\n---\n', 4) + 5:]
            assert skill.get('autoinvoke') == source['autoinvoke']
        for source in expected['agents']:
            agent = agents[source['name']]
            assert agent['system'] == source['content']
            assert agent['mode'] == 'subagent'
            assert 'model' not in agent
        assert all('10x-swe:' + c['name'] in commands for c in expected['commands'])
        # A sibling reference must survive packaging and be readable at the installed path.
        resource = Path(skills['test-driven-development']['path']).parent / 'testing-anti-patterns.md'
        assert resource.read_bytes() == (PACKAGE / 'skills/test-driven-development/testing-anti-patterns.md').read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--opencode', default=shutil.which('opencode'))
    args = parser.parse_args()
    if not args.opencode:
        parser.error('pass --opencode /absolute/path/to/opencode')
    binary = str(Path(args.opencode).resolve())
    with tempfile.TemporaryDirectory(prefix='10x-opencode-') as temp:
        root = Path(temp).resolve()
        env = environment(root)
        packed = json.loads(run(['npm', 'pack', str(PACKAGE), '--ignore-scripts', '--json',
                                 '--pack-destination', str(root)], root, env).stdout)[0]
        archive = root / packed['filename']
        manifest = json.loads((PACKAGE / 'package.json').read_text())
        expected = json.loads((PACKAGE / 'opencode-data.json').read_text())
        entries = {f['path'] for f in packed['files']}
        assert {'index.js', 'package.json', 'LICENSE', 'opencode-data.json'} <= entries
        assert not any('node_modules' in p or p.startswith('../') for p in entries)
        assert all(p.startswith(('skills/', 'agents/', 'commands/')) or p in {'index.js', 'package.json', 'LICENSE',
                                                   'opencode-data.json', 'README.md'} for p in entries)
        for route in ['tgz', 'registry']:
            target = root / route
            target.mkdir()
            isolated = environment(target)
            config = target / 'config/opencode/opencode.jsonc'
            config.parent.mkdir(parents=True)
            if route == 'tgz':
                rejected = run([binary, 'plugin', 'add', str(archive)], target, isolated, success=False)
                assert rejected.returncode != 0
                assert 'npm registry package or Git' in rejected.stderr
                assert not config.exists()
                run(['npm', 'install', '--prefix', str(target), '--ignore-scripts', '--no-audit',
                     '--no-fund', str(archive)], target, isolated)
                installed = target / 'node_modules' / manifest['name']
                config.write_text(json.dumps({'plugins': [os.path.relpath(installed, config.parent)]}))
                verify(binary, target, isolated, expected)
            else:
                config.write_text('{}')
                with registry(archive, manifest) as (url, requests):
                    isolated['npm_config_registry'] = url
                    spec = manifest['name'] + '@' + manifest['version']
                    run([binary, 'plugin', 'add', spec], target, isolated)
                    assert spec in json.loads(config.read_text())['plugins']
                    verify(binary, target, isolated, expected)
                    run([binary, 'plugin', 'add', spec], target, isolated)
                    assert json.loads(config.read_text())['plugins'].count(spec) == 1
                    assert '/package.tgz' in requests
            # Restart against the saved installation, then remove and verify cleanup.
            verify(binary, target, isolated, expected)
            config.write_text('{"plugins": []}')
            verify(binary, target, isolated, expected, loaded=False)
            print(f'PASS {route}: install, load, restart, removal; '
                  f"{len(expected['skills'])} skills, {len(expected['agents'])} agents, "
                  f"{len(expected['commands'])} commands")


if __name__ == '__main__':
    main()
