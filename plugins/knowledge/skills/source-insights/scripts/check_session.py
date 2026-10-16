"""Session records remain inert, bounded and retained without producer access."""
import copy, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

helper=Path(__file__).with_name('sources.py')
sid='session:codex:fixture';tid='turn:codex:fixture:3';version='a'*64
quote='Selected assistant evidence; not independent verification.'
d=dict(agent='codex',session_id='fixture',source_path='/not-readable/or-executable/session.jsonl',jsonl_line=3,json_pointer='$.payload.content',role='assistant',timestamp=None,record_sha256=version,original_text_sha256=version,indexed_text_sha256='b'*64,excerpt_sha256=hashlib.sha256(quote.encode()).hexdigest(),char_start=0,char_end=len(quote),redacted=False,quote=quote,version=version,session_revision=version)
packet=dict(schema='knowledge-snapshot/v1',corpus='sessions',query='evidence',nodes=[dict(id=sid,kind='session',label='Fixture session',details=dict(version=version,coverage={'limitations':['Oversized turn omitted']})),dict(id=tid,kind='session_turn',details=d)],edges=[dict(a=tid,b=sid,kind='part_of',status='recorded')],versions={sid:version,tid:version},hits=[])
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);work=root/'work';raw=json.dumps(packet).encode()
 def run(data,dest=work):
  return subprocess.run([sys.executable,str(helper),'prepare-session',sid,'--records','-','--work',str(dest)],input=data,capture_output=True,env=dict(os.environ,PATH='/no-producers'))
 assert run(raw).returncode==0
 before={p.name:p.read_bytes() for p in work.iterdir()}
 assert before['session-records.json']==raw and b'Oversized turn omitted' in before['document.md']
 assert run(raw).returncode==0 and before=={p.name:p.read_bytes() for p in work.iterdir()}
 bad=[]
 for key,value in [('quote','tampered'),('record_sha256','c'*64),('jsonl_line',True),('char_start',True),('session_revision','c'*64),('source_path',['/evil']),('agent',1)]:
  p=copy.deepcopy(packet);p['nodes'][1]['details'][key]=value;bad.append(p)
 for key,value in [('nodes',[None]),('nodes',[{'id':[]}]),('versions',[]),('edges',[None])]:
  p=copy.deepcopy(packet);p[key]=value;bad.append(p)
 for data in [b'{',b'\xff',b'[]',raw+b'{}',*[json.dumps(p).encode() for p in bad],b'x'*(16*1024*1024+1)]:
  dest=root/'invalid';result=run(data,dest)
  assert result.returncode and not dest.exists() and not result.stdout,(result.stdout,result.stderr)
  assert b'Traceback' not in result.stderr,result.stderr
 (work/'document.md').write_text('changed')
 assert run(raw).returncode!=0
print('PASS: independent stdin preparation, exact retained packet, omissions, idempotence, identity/hash/type/bounds denial before mutation, changed evidence rejection')
