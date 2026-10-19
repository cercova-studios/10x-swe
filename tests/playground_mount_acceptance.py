"""Opt-in real microVM recovery using a previously built playground checkpoint.

python3 tests/playground_mount_acceptance.py CHECKPOINT_DIRECTORY NEW_ARTIFACT_DIRECTORY
Only newly created fixture directories and VMs owned by that fixture are changed.
The completed review and checkpoints remain on the host for inspection.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mount_acceptance', REPO / 'playgrounds/manage.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def main():
    image_folder, output = (Path(arg).resolve() for arg in sys.argv[1:])
    output.mkdir(mode=0o700)  # Refuse existing data.
    os.environ['XDG_STATE_HOME'] = str(output / 'xdg')
    os.umask(0o077)
    reference = output / 'reference'
    reference.mkdir()
    (reference / 'reading.txt').write_text('reference remains read-only')
    first, second = output / 'project', output / 'dataset'
    first.mkdir()
    second.mkdir()
    (output / 'host-only').write_text('not exported')
    (reference / 'outside-link').symlink_to('../host-only')
    snapshot = json.loads((image_folder / 'checkpoint.json').read_text())
    assert p.digest(image_folder / 'guest.msb') == snapshot['archive_sha256']
    pg = p.Playground(output / 'states', 'mount-test')
    cli = [str(REPO / 'playground'), '--state-dir', str(pg.directory.parent)]

    def host(action, *args, data=None):
        result = subprocess.run([*cli, action, 'mount-test', *args], input=data,
                                text=True, capture_output=True)
        assert result.returncode == 0, (result.stdout[-2000:], result.stderr[-4000:])
        return result.stdout

    def guest(script):
        result = host('run', '--', 'python3', '-', data=script)
        assert 'PASS:' in result, result
        print(result.strip(), flush=True)

    p.preflight()
    with pg.locked():
        pg.data = {'schema': 'playground/v2', 'current': None, 'owned': [], 'runtime': p.CONFIG,
                   'source_sha256': snapshot['source_sha256'], 'flake_lock_sha256': snapshot['flake_lock_sha256']}
        pg.save()
        pg.data['mounts'] = p.mounts.declarations([reference], [first, second], pg.directory, REPO)
        pg.save()
        pg.ready()
        vm = pg.reserve()
        p.create(vm, image_folder / 'guest.msb', offline=True, shares=pg.shares())
        p.seal(vm)
        p.boundary(vm, pg.shares())
        p.msb('exec', '--no-stdin', vm, '--', 'bash', '-c', p.HEALTH)
        pg.data['current'] = vm
        pg.save()
    print('PASS: reused pinned tool environment; exact declared host shares admitted', flush=True)
    paths = 'reference, project, dataset = map(Path, ' + repr([str(reference), str(first), str(second)]) + ')\n'
    guest('''from pathlib import Path
import subprocess
''' + paths + f'''
assert (reference/'reading.txt').read_text() == 'reference remains read-only'
assert not Path({str(output / 'host-only')!r}).exists()
try:
    (reference/'outside-link').read_text()
except OSError:
    pass
else:
    raise AssertionError('reference symlink escaped its host grant')
for sudo in ([], ['sudo']):
    result = subprocess.run([*sudo, 'python3', '-c', 'from pathlib import Path; Path(' + repr(str(reference/'forbidden')) + ').write_text("forbidden")'], capture_output=True)
    assert result.returncode != 0 and b'Read-only file system' in result.stderr, result.stderr
result = subprocess.run(['sudo','ln',str(reference/'reading.txt'),str(project/'reference-alias')], capture_output=True)
assert result.returncode != 0, 'reference hardlink crossed mount grants'
subprocess.run(['sudo', 'mount', '-o', 'remount,rw', str(reference)], check=True)
result = subprocess.run(['sudo','touch',str(reference/'forbidden')], capture_output=True)
assert result.returncode != 0 and b'Read-only file system' in result.stderr, result.stderr
subprocess.run(['sudo','mount','-o','remount,bind,ro',str(reference)], check=True)
print('PASS: unselected host files hidden; references readable; user, root and root-remount writes denied')
''')
    guest('''from pathlib import Path
import subprocess, sys, time
''' + paths + '''
subprocess.run(['git','init','-q',str(project)], check=True)
def git(*args):
    return subprocess.check_output(['git','-C',str(project),*args])
git('config','user.email','fixture@example.invalid')
git('config','user.name','Mount fixture')
(project/'.gitignore').write_text('ignored\\n')
(project/'tracked').write_text('base')
git('add','.gitignore','tracked')
git('commit','-qm','base')
(project/'tracked').write_text('staged')
git('add','tracked')
(project/'tracked').write_text('unstaged')
(project/'ignored').write_text('ignored but retained')
(project/'untracked').write_text('untracked but retained')
(project/'executable').write_text('#!/bin/sh\\nexit 0\\n')
(project/'executable').chmod(0o755)
(project/'link').symlink_to('tracked')
(project/'index.before').write_bytes(git('show',':tracked'))
(dataset/'valuable').write_text('restore deleted data')
fixture = Path.cwd()/'mount-acceptance'
fixture.mkdir()
(fixture/'guest.txt').write_text('restore guest data')
writer = "import sqlite3,time,pathlib; c=sqlite3.connect('live.sqlite'); c.execute('pragma journal_mode=wal'); c.execute('create table records(value text)'); c.execute(\\\"insert into records values ('committed')\\\"); c.commit(); pathlib.Path('writer.ready').write_text('ready'); time.sleep(600)"
subprocess.Popen([sys.executable,'-c',writer],cwd=str(dataset),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
for _ in range(100):
    if (dataset/'writer.ready').exists(): break
    time.sleep(.1)
assert (dataset/'writer.ready').exists()
print('PASS: guest edits visible in two host mounts; Git index, ignored files, modes, symlink and live SQLite WAL seeded')
''')
    assert (first/'tracked').read_text() == 'unstaged'
    checkpoint = json.loads(host('checkpoint', 'baseline'))
    expected = [p.mounts.tree(path) for path in (first, second)]
    print('PASS: VM and host archives checkpointed with all guest writers stopped', flush=True)
    guest('''from pathlib import Path
import os, shutil
''' + paths + '''
for root in (project, dataset):
    for path in root.iterdir():
        if path.is_dir() and not path.is_symlink(): shutil.rmtree(path)
        else: path.unlink()
    (root/'uncheckpointed').write_text('discard on rewind')
(project/'broken-link').symlink_to('/etc/passwd')
os.mkfifo(dataset/'broken-fifo')
shutil.rmtree(Path.cwd()/'mount-acceptance')
print('PASS: deleted host trees and guest files; introduced uncheckpointed data and unsafe links/special files')
''')
    assert not (first/'tracked').exists() and not (second/'valuable').exists()
    restored = json.loads(host('rewind','baseline'))
    assert expected == [p.mounts.tree(path) for path in (first, second)]
    assert (reference/'reading.txt').read_text() == 'reference remains read-only'
    guest('''from pathlib import Path
import sqlite3, subprocess
''' + paths + '''
assert (Path.cwd()/'mount-acceptance/guest.txt').read_text() == 'restore guest data'
assert subprocess.check_output(['git','-C',str(project),'show',':tracked']) == b'staged'
assert (project/'tracked').read_text() == 'unstaged'
db = sqlite3.connect(str(dataset/'live.sqlite'))
assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
assert db.execute('select value from records').fetchone()[0] == 'committed'
print('PASS: single rewind restored host files, Git staging, metadata, committed SQLite WAL and guest files')
''')
    review = json.loads(host('review'))
    packet = json.loads(Path(review['review']).read_text())
    assert packet['publication'] == 'pending-human-review'
    assert len(packet['mounts']) == 3
    for record in packet['mounts']:
        if record['mode'] == 'rw':
            assert p.digest(Path(review['review']).parent/record['archive']) == record['sha256']
    assert p.digest(Path(review['archive'])) == review['sha256']
    subprocess.run([sys.executable, str(REPO/'tests/playground_recovery_acceptance.py'),
                    str(pg.directory.parent), 'mount-test'], check=True)
    result = {'result':'PASS','checkpoint':checkpoint,'restore':restored,'review':review,
              'abrupt_host_restore_recovery':'passed',
              'runtime':p.CONFIG['msb_version'],'fixture':str(output)}
    p.atomic(output/'result.json', result)
    print(json.dumps(result,indent=2), flush=True)
    host('destroy','--yes')


if __name__ == '__main__':
    main()
