"""Crash a host restore and exercise explicit recovery on a disposable mounted VM.

Usage: python3 tests/playground_recovery_acceptance.py STATE_DIR NAME
Requires a completed 'baseline' checkpoint and at least one writable user mount.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery_acceptance', REPO / 'playgrounds/manage.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def interrupt(root, name):
    pg = p.Playground(root, name)
    with pg.locked():
        pg.stop_owned()
        folder = pg.directory / 'checkpoints/baseline'
        snapshot = json.loads((folder / 'checkpoint.json').read_text())
        p.mounts.verify(snapshot['mounts'], folder, pg.shares())
        restore = p.mounts.Restore(pg.directory)
        transaction = restore.prepare(snapshot['mounts'], folder, pg.data)
        assert len(transaction['rows']) >= 2
        for index, row in enumerate(transaction['rows'][:2]):
            Path(row['path']).rename(row['backup'])
            if index == 0:
                Path(row['stage']).rename(row['path'])
        os._exit(17)  # No finally/exception path: leave one replaced and one missing mount root.


def main(root, name):
    pg = p.Playground(root, name)
    state = json.loads(pg.statefile.read_text())
    assert state['current']
    before = {m['path']: p.mounts.tree(m['path']) for m in state['mounts'] if m['mode'] == 'rw'}
    child = subprocess.run([sys.executable, __file__, '--interrupt', str(root), name])
    assert child.returncode == 17, child.returncode
    cli = [str(REPO / 'playground'), '--state-dir', str(root)]
    blocked = subprocess.run([*cli, 'run', name, '--', 'true'], capture_output=True, text=True)
    assert blocked.returncode != 0 and 'recover' in blocked.stderr, blocked.stderr
    result = subprocess.run([*cli, 'recover', name], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert before == {path: p.mounts.tree(path) for path in before}
    recovered = json.loads(pg.statefile.read_text())
    assert recovered['current'] == state['current']
    assert recovered['mounts'] == state['mounts']
    result = subprocess.run([*cli, 'run', name, '--', 'printf', '%s', 'recovered'], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == 'recovered', (result.stdout, result.stderr)
    print('PASS: abrupt host-process exit after partial replacement blocks execution; explicit recover restores all trees and original VM identity')


if __name__ == '__main__':
    if sys.argv[1] == '--interrupt':
        interrupt(Path(sys.argv[2]).resolve(), sys.argv[3])
    else:
        main(Path(sys.argv[1]).resolve(), sys.argv[2])
