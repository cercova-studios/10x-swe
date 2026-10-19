"""Opt-in destructive test of an already-created disposable playground.

Usage: python3 tests/playground_acceptance.py STATE_DIR NAME
The named playground must be disposable: this test deletes its guest workspace
and tool installation, restores a checkpoint, and stops it at publication review.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

REPO = Path(__file__).resolve().parents[1]
STATE, NAME = sys.argv[1:]
CLI = [str(REPO / 'playground'), '--state-dir', STATE]


def host(action, *args, code=0, data=None):
    result = subprocess.run([*CLI, action, NAME, *args], input=data, capture_output=True, text=True)
    assert result.returncode == code, (action, result.returncode, result.stdout[-2000:], result.stderr[-3000:])
    return result.stdout


def guest(script, *, code=0):
    return host('run', '--', 'python3', '-', data=script, code=code)


checkpoint = 'acceptance-' + uuid.uuid4().hex[:12]
initial = json.loads(host('status'))
assert initial['current'], 'Create a fresh disposable playground with playground up first'

with tempfile.TemporaryDirectory(prefix='tenx-host-canary-') as temporary:
    sentinel = Path(temporary) / 'host-only'
    sentinel.write_text('host must remain unchanged')
    checks = guest(f'''
from pathlib import Path
import subprocess
assert not Path({str(sentinel)!r}).exists(), 'host files are mounted'
assert subprocess.run(['ssh-add', '-l'], capture_output=True).returncode == 2
result = subprocess.run(['curl', '--fail', '--max-time', '3', 'https://github.com'], capture_output=True)
assert result.returncode != 0, 'public network escaped host policy'
result = subprocess.run(['curl', '--fail', '--max-time', '3', 'http://192.168.127.1:8123'], capture_output=True)
assert result.returncode != 0, 'host network escaped host policy'
probe = "import socket\\ns=socket.socket(); s.settimeout(2)\\ntry: s.connect(('1.1.1.1',443))\\nexcept OSError: pass\\nelse: raise AssertionError('direct TCP escaped host policy')"
for prefix in ([], ['sudo']):
    result = subprocess.run([*prefix, 'python3', '-c', probe], capture_output=True)
    assert result.returncode == 0, result.stderr
print('PASS: host files unavailable; SSH forwarding disabled; network explicitly denied')
''')
    assert 'PASS: host files unavailable' in checks, 'piped boundary probe did not execute'
    print(checks.strip())

    seed = guest('''
from pathlib import Path
import os, subprocess, sys, time
p = Path.cwd()
subprocess.run(['git', 'init', '-q'], check=True)
subprocess.run(['git', 'config', 'user.email', 'fixture@example.invalid'], check=True)
subprocess.run(['git', 'config', 'user.name', 'Playground fixture'], check=True)
(p / '.gitignore').write_text('ignored.txt\\n')
(p / 'tracked.txt').write_text('baseline\\n')
subprocess.run(['git', 'add', '.gitignore', 'tracked.txt'], check=True)
subprocess.run(['git', 'commit', '-qm', 'baseline'], check=True)
(p / 'tracked.txt').write_text('staged change\\n')
subprocess.run(['git', 'add', 'tracked.txt'], check=True)
(p / 'tracked.txt').write_text('unstaged change\\n')
(p / 'untracked.txt').write_text('retain untracked\\n')
(p / 'ignored.txt').write_text('retain ignored\\n')
(p / 'executable').write_text('#!/bin/sh\\nexit 0\\n')
(p / 'executable').chmod(0o755)
(p / 'link').symlink_to('tracked.txt')
(p / 'git-status.before').write_bytes(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no']))
(p / 'git-index.before').write_bytes(subprocess.check_output(['git', 'show', ':tracked.txt']))
writer = "import sqlite3,time,pathlib; c=sqlite3.connect('state.sqlite'); c.execute('pragma journal_mode=wal'); c.execute('create table records(value text)'); c.execute(\\\"insert into records values ('committed before snapshot')\\\"); c.commit(); pathlib.Path('writer.ready').write_text('ready'); time.sleep(600)"
subprocess.Popen([sys.executable, '-c', writer], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
for _ in range(100):
    if (p / 'writer.ready').exists(): break
    time.sleep(.1)
assert (p / 'writer.ready').exists()
Path('/home/agent/workflow-state/draft.json').write_text('{"review":"pending"}')
print('PASS: staged/unstaged Git, ignored/untracked files, modes, symlink and committed live SQLite WAL seeded')
''')
    assert 'PASS: staged/unstaged Git' in seed, 'piped seed fixture did not execute'
    print(seed.strip())
    print(json.loads(host('checkpoint', checkpoint)))

    # The host can recover even when installed tools and the whole workspace vanish.
    host('run', '--', 'bash', '-c',
         'rm -rf /home/agent/workspace /home/agent/knowledge/bin /home/agent/tenx-profile /home/agent/workflow-state')
    broken = subprocess.run([*CLI, 'run', NAME, '--', 'skill-search', '--help'], capture_output=True)
    assert broken.returncode != 0, 'destructive fixture did not break the guest'
    recovered = json.loads(host('rewind', checkpoint))
    assert recovered['preserved'] == initial['current']
    assert recovered['current'] != initial['current']
    assert sentinel.read_text() == 'host must remain unchanged'

    restored = guest('''
from pathlib import Path
import json, sqlite3, stat, subprocess
p = Path.cwd()
assert (p/'tracked.txt').read_text() == 'unstaged change\\n'
assert subprocess.check_output(['git','show',':tracked.txt']) == (p/'git-index.before').read_bytes()
assert subprocess.check_output(['git','status','--porcelain','--untracked-files=no']) == (p/'git-status.before').read_bytes()
assert (p/'untracked.txt').read_text() == 'retain untracked\\n'
assert (p/'ignored.txt').read_text() == 'retain ignored\\n'
assert stat.S_IMODE((p/'executable').stat().st_mode) == 0o755
assert (p/'link').readlink() == Path('tracked.txt')
db = sqlite3.connect('state.sqlite')
assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
assert db.execute('select value from records').fetchone()[0] == 'committed before snapshot'
assert json.loads(Path('/home/agent/workflow-state/draft.json').read_text()) == {'review':'pending'}
print('PASS: filesystem, Git index, executable mode, link, SQLite WAL and workflow state restored')
''')
    assert 'PASS: filesystem' in restored
    print(restored.strip())

    # Exercise independent record producers/consumers, without approving publication.
    workflow = guest('''
import json, os, pathlib, subprocess
p = pathlib.Path.cwd()
env = dict(os.environ, SESSION_SEARCH_DB=str(p/'sessions.sqlite'), HOME=str(p/'fixture-home'))
session = p/'fixture-home/.codex/sessions/session.jsonl'
session.parent.mkdir(parents=True)
quote = 'Playgroundfixture keeps independent tools and a separate publication review.'
rows = [{'type':'session_meta','payload':{'id':'playground-fixture','cwd':str(p)}},
        {'type':'response_item','payload':{'type':'message','role':'assistant','channel':'final',
         'content':[{'type':'output_text','text':quote}]}}]
session.write_text(''.join(json.dumps(x)+'\\n' for x in rows))
def run(argv, data=None):
    result = subprocess.run(argv, input=data, text=True, capture_output=True, env=env)
    assert result.returncode == 0, (argv, result.stdout[-1000:],result.stderr[-2000:])
    return result.stdout
run(['session-search','index','--agent','codex','--json'])
records = run(['session-search','export','--agent','codex','--mode','naive','--role','assistant','Playgroundfixture'])
(p/'session.jsonl').write_text(records)
recipe = '/home/agent/knowledge/skills/source-insights/scripts/session_workflow.py'
work = p/'insight-review'
library = p/'unpublished-library'
flags = ['--session','session:codex:playground-fixture','--work',str(work),'--library',str(library)]
run(['python3',recipe,'capture',*flags,'--records','-'], records)
run(['python3',recipe,'prepare',*flags])
lines = (work/'evidence/document.md').read_text().splitlines()
line = lines.index(quote)+1
analysis = {'title':'Playgroundfixture','summary':'Synthetic assistant proposal used to verify pipes.',
            'tags':['playgroundfixture'],'coverage':{'line_ranges':[[1,len(lines)]],'limitations':['Fixture only']},
            'insights':[{'claim':quote,'status':'source-claim','why_it_matters':'Independent operation',
             'application':'Review evidence before publication','caveats':'Synthetic fixture',
             'evidence':[{'line_start':line,'line_end':line,'quote':quote}]}]}
(work/'analysis.json').write_text(json.dumps(analysis))
review = json.loads(run(['python3',recipe,'review',*flags]))
assert review['review_digest'] and not library.exists()
skills = run(['skill-search','export','--query','refactor','--limit','3'])
combined = records+skills
result = json.loads(run(['bkd','--records','-','search','Playgroundfixture','--lexical-only','--json'],combined))
assert result['data']['sessions']
html = '<article><h1>Playgroundfixture</h1><p>Preserve exact evidence and local review.</p></article>'
article = run(['distiller','--stdin','--base-url','https://example.invalid/fixture','--mode','json'],html)
(p/'article.json').write_text(article)
(p/'article.html').write_text(html)
run(['source-insights','prepare-article','https://example.invalid/fixture','--prepared',str(p/'article.json'),
     '--snapshot',str(p/'article.html'),'--work',str(p/'article-evidence')])
assert not library.exists()
print('PASS: session-search -> cited source-insights review; skill-search + bkd records; distiller -> source-insights; no publication')
''')
    assert 'PASS: session-search' in workflow
    print(workflow.strip())

    # Real stdin/stdout across the microVM boundary must remain ordinary streams.
    output = host('run', '--', 'python3', '-c', 'import sys; sys.stdout.write(sys.stdin.read())', data='pipe contract\n')
    assert output == 'pipe contract\n', repr(output)
    payload = bytes(range(256)) * 1024
    output = subprocess.run([*CLI, 'run', NAME, '--', 'python3', '-c',
                             'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'],
                            input=payload, capture_output=True)
    assert output.returncode == 0 and output.stdout == payload, (output.returncode, output.stderr)
    assert host('run', '--', 'printf', '%s', '$(touch /tmp/must-not-run)') == '$(touch /tmp/must-not-run)'
    host('run', '--', 'bash', '-c', 'exit 23', code=23)
    review = json.loads(host('review'))
    archive = Path(review['archive'])
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == review['sha256']
    assert review['publication'] == 'pending-human-review'
    assert not Path(STATE, NAME, 'published').exists()
    host('stop')
    print(json.dumps({'result':'PASS','checkpoint':checkpoint,'review':review,'restored':recovered},indent=2))
