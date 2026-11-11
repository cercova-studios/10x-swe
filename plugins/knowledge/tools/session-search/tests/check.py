"""Native CLI regressions: isolated harnesses, exact provenance and failure recovery."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing

binary = Path(sys.argv[1] if len(sys.argv)>1 else shutil.which('session-search') or '').resolve()
assert binary.is_file(), 'Pass the built session-search executable or put it on PATH'

with tempfile.TemporaryDirectory(prefix='native-session-check-') as tmp:
    root=Path(tmp);home=root/'home';home.mkdir();database=root/'index ? #.db'
    env={**os.environ,'HOME':str(home),'SESSION_SEARCH_DB':str(database),'SESSION_SEARCH_EMBEDDER':'hash'}
    env.pop('AGENT_KNOWLEDGE_HOME',None)
    def run(*args,code=0,extra=None):
        p=subprocess.run([str(binary),*args],env={**env,**(extra or {})},capture_output=True,timeout=30)
        assert p.returncode==code,(args,p.returncode,p.stdout[-1000:],p.stderr[-2000:])
        return p
    for args,code in [(('search','--mode','naive','--json','needle'),2),(('last','needle'),2),
                      (('export','needle'),2),(('show','codex','missing'),1)]:
        missing=root/args[0]/'absent.db'
        assert not run(*args,code=code,extra={'SESSION_SEARCH_DB':str(missing)}).stdout
        assert not missing.parent.exists()
    assert not json.loads(run('status','--json').stdout)['exists'] and not database.exists()
    # Invalid input is rejected before index creation.
    run('search','needle','--limit','0',code=2)
    run('index','--unknown',code=2)
    assert not database.exists()
    path=home/'.codex/sessions/fixture.jsonl';path.parent.mkdir(parents=True)
    rows=[{'type':'session_meta','payload':{'id':'fixture','cwd':'/fixture'}}]
    for n in range(30):
        rows.append({'timestamp':'2026-10-12T12:00:00Z','type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':('Repeated instructions '+('padding '*2000)) if n<29 else 'bookmarkdrop lateuserneedle'}]}})
    text='assistantneedle: preserve Unicode 🙂 日本語 and pipes. Token sk-'+('x'*20)
    rows.extend([{'type':'response_item','payload':{'type':'message','role':'assistant','channel':'final','content':[{'type':'output_text','text':text}]}},
                 {'type':'response_item','payload':{'type':'message','role':'assistant','channel':'analysis','content':[{'type':'output_text','text':'hiddenneedle'}]}},
                 {'type':'response_item','payload':{'type':'function_call_output','output':'toolneedle passed with exit code 0'}},
                 {'type':'event_msg','payload':{'type':'user_message','message':'Duplicate event not selected'}}])
    raw=''.join(json.dumps(v)+'\n' for v in rows);path.write_text(raw)
    indexed=json.loads(run('index','--agent','codex','--json').stdout)
    assert indexed['counts']=={'codex':1} and not indexed['errors']
    for term in ['bookmarkdrop','assistantneedle','toolneedle']:
        hit=json.loads(run('search','--mode','naive','--json',term).stdout)['hits'][0]
        assert hit['native_id']=='fixture'
    with closing(sqlite3.connect(database)) as db:
        body,turns=db.execute('SELECT body,turns_json FROM sessions').fetchone()
    assert len(body)>32000 and len(json.loads(turns))==32
    assert 'hiddenneedle' not in body and 'Duplicate event' not in body and 'sk-'+('x'*20) not in body
    exported=run('export','--mode','naive','--role','assistant','assistantneedle').stdout
    assert len(exported.splitlines())==1
    packet=json.loads(exported);citation=next(n['details'] for n in packet['nodes'] if n['kind']=='session_turn')
    assert citation['role']=='assistant' and citation['jsonl_line']==32 and citation['redacted']
    assert citation['record_sha256']==hashlib.sha256(raw.splitlines()[31].encode()).hexdigest()
    assert citation['excerpt_sha256']==hashlib.sha256(citation['quote'].encode()).hexdigest()
    assert citation['quote']==text.replace('sk-'+('x'*20),'[redacted]')
    assert not run('export','--mode','naive','--role','tool','assistantneedle',code=2).stdout
    assert not run('export','--mode','naive','unfindabletoken',code=1).stdout
    # A failed adapter or model never replaces the successful generation.
    before=run('status','--json').stdout
    path.write_text(raw+'bad JSON\n')
    failed=json.loads(run('index','--agent','codex','--json',code=1).stdout)
    assert 'codex' in failed['errors'] and run('status','--json').stdout==before
    assert run('export','--mode','naive','--role','assistant','assistantneedle').stdout==exported
    path.write_text(raw+'{"unfinished":')
    run('index','--agent','codex','--json')
    refreshed=json.loads(run('export','--mode','naive','--role','assistant','assistantneedle').stdout)
    assert refreshed['versions']==json.loads(exported)['versions']
    assert next(n['details']['record_sha256'] for n in refreshed['nodes'] if n['kind']=='session_turn')==citation['record_sha256']
    before=run('status','--json').stdout
    run('index','--agent','codex','--enrich-only','--json',code=2,extra={'SESSION_SEARCH_EMBEDDER':'fastembed','SESSION_SEARCH_MODEL_DIR':str(root/'no-model')})
    assert run('status','--json').stdout==before
    # Existing live WAL remains visible, without permission or schema changes.
    with closing(sqlite3.connect(database)) as writer:
        writer.execute('PRAGMA journal_mode=WAL');writer.execute("UPDATE sessions SET title='walneedle' WHERE native_id='fixture'");writer.commit()
        os.chmod(database,0o640);digest=hashlib.sha256(database.read_bytes()).hexdigest()
        assert json.loads(run('search','--mode','naive','--json','walneedle').stdout)['hits']
        assert database.stat().st_mode&0o777==0o640 and hashlib.sha256(database.read_bytes()).hexdigest()==digest
    with closing(sqlite3.connect(database)) as writer:
        writer.execute('ALTER TABLE sessions DROP COLUMN turns_json');writer.commit()
    digest=hashlib.sha256(database.read_bytes()).hexdigest()
    run('search','--mode','naive','needle',code=2)
    assert hashlib.sha256(database.read_bytes()).hexdigest()==digest
    run('index','--agent','codex','--json') # Explicit indexing owns schema upgrades.
    claude=home/'.claude/projects/fixture/claude.jsonl';claude.parent.mkdir(parents=True)
    claude.write_text(json.dumps({'type':'user','message':{'role':'user','content':'claudeneedle user'}})+'\n'+json.dumps({'type':'assistant','message':{'role':'assistant','content':[{'type':'thinking','thinking':'hiddenclaude'},{'type':'text','text':'claudeneedle answer'}]}})+'\n')
    run('index','--agent','claude','--json')
    packet=json.loads(run('export','--agent','claude','--mode','naive','--role','assistant','claudeneedle').stdout)
    assert 'hiddenclaude' not in json.dumps(packet) and any(n['kind']=='session_turn' for n in packet['nodes'])
    guardian=home/'.codex/sessions/guardian.jsonl'
    guardian.write_text(json.dumps({'type':'session_meta','payload':{'id':'guardian','source':{'subagent':{'other':'guardian'}}}})+'\n')
    assert json.loads(run('index','--agent','codex','--json').stdout)['counts']['codex']==1
    oversized=home/'.codex/sessions/oversized.jsonl'
    oversized.write_bytes(b'"'+b'x'*(16*1024*1024)+b'"\n'+json.dumps(rows[31]).encode()+b'\n')
    run('index','--agent','codex','--json')
    with closing(sqlite3.connect(database)) as db:
        limits,turns=db.execute("SELECT limitations_json,turns_json FROM sessions WHERE native_id='oversized'").fetchone()
    assert 'line 1 omitted' in json.loads(limits)[0] and json.loads(turns)[0]['line']==2
    # Owned installation commands work with no Python or shell available on PATH,
    # invoked directly and through the installed bin/ symlink (current_exe keeps
    # the symlink path on macOS, so prefix resolution must read through it).
    prefix=root/'installed';native=prefix/'libexec/native/session-search';native.parent.mkdir(parents=True)
    shutil.copy2(binary,native);(prefix/'.knowledge-owner.json').write_text('{}')
    launcher=prefix/'bin'/'session-search';launcher.parent.mkdir();launcher.symlink_to('../libexec/native/session-search')
    expected=str(prefix.resolve()/'state/session-search.sqlite')  # canonicalize resolves macOS /var -> /private/var
    for invoked in (native,launcher):
        p=subprocess.run([str(invoked),'status','--json'],env={'HOME':str(home),'PATH':str(root/'empty-path')},capture_output=True,timeout=10)
        assert p.returncode==0,p.stderr
        assert json.loads(p.stdout)['db']==expected and not (prefix/'state').exists()
print('PASS: native recall, hidden reasoning exclusion, exact citation hashes/roles/Unicode, read-only queries, failed refresh rollback, bounded JSONL, schema upgrade authority and Python-free installation')
