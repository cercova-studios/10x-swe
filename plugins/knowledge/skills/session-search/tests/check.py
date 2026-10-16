"""Disposable recall, provenance, export and failed-refresh regressions."""
import hashlib,json,os,sys,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from session_search.adapters.codex import CodexAdapter
from session_search.adapters.claude import ClaudeAdapter
from session_search.store import Store
from session_search.records import export_snapshot
from session_search.models import SearchResult
from session_search.turns import excerpts
from session_search.turns import read_turns
from session_search.cli import main
from contextlib import redirect_stdout
from io import StringIO

with tempfile.TemporaryDirectory() as tmp:
 r=Path(tmp);path=r/'session.jsonl';rows=[{'type':'session_meta','payload':{'id':'test-session','cwd':str(r)}}]
 for i in range(30):rows.append({'timestamp':'2026-10-12T12:00:00Z','type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'Repeated instructions '+('padding '*2000) if i<29 else 'bookmarkdrop lateuserneedle'}]}})
 rows.extend([{'type':'response_item','payload':{'type':'message','role':'assistant','channel':'final','content':[{'type':'output_text','text':'assistantneedle: prefer independent pipes. Token sk-'+('x'*20)}]}},{'type':'response_item','payload':{'type':'message','role':'assistant','channel':'analysis','content':[{'type':'output_text','text':'hiddenneedle'}]}},{'type':'response_item','payload':{'type':'function_call_output','output':'toolneedle passed with exit code 0'}},{'type':'event_msg','payload':{'type':'user_message','message':'Duplicate event not selected'}}])
 raw=''.join(json.dumps(x)+'\n' for x in rows);path.write_text(raw)
 rec=CodexAdapter()._from_rollout(path,{},{});assert rec.native_id=='test-session'
 assert all(x in rec.body for x in ['lateuserneedle','assistantneedle','toolneedle'])
 assert 'hiddenneedle' not in rec.body and 'Duplicate event' not in rec.body and 'sk-'+('x'*20) not in rec.body
 assert len(rec.body)>32000 and len(rec.turns)==32
 cites=excerpts(rec,'assistantneedle');c=cites[0]
 assert c['role']=='assistant' and c['jsonl_line']==32 and c['redacted']
 assert c['record_sha256']==hashlib.sha256(raw.splitlines()[31].encode()).hexdigest()
 assert c['excerpt_sha256']==hashlib.sha256(c['quote'].encode()).hexdigest()
 store=Store(r/'index.db');store.replace_agent('codex',[rec])
 for q in ['bookmarkdrop','assistantneedle','toolneedle']:
  assert store.search(q)[0].native_id=='test-session'
 roundtrip=store.get('codex','test-session');assert roundtrip.turns==rec.turns
 result=SearchResult('assistantneedle','naive',store.search('assistantneedle'))
 packet=export_snapshot(store,result);assert packet['corpus']=='sessions' and len(packet['nodes'])==2
 assert export_snapshot(store,result,role='assistant')['nodes'][1]['details']['role']=='assistant'
 assert 'filtered to assistant' in export_snapshot(store,result,role='assistant')['nodes'][1]['details']['coverage']['limitations'][0]
 assert excerpts(rec,'assistantneedle toolneedle',role='assistant')[0]['record_sha256']==c['record_sha256']
 assert excerpts(rec,'assistantneedle',role='tool')==[]
 assert packet['nodes'][1]['details']['record_sha256']==c['record_sha256']
 with patch('session_search.embedder.get_embedder',side_effect=RuntimeError('injected model failure')):
  try:store.replace_agent('codex',[]+[rec])
  except RuntimeError:pass
  else:raise AssertionError('refresh error hidden')
 assert store.get('codex','test-session').turns==rec.turns and store.count()==1
 store.set_meta('indexed_at','last-successful-refresh')
 with patch.dict(os.environ,SESSION_SEARCH_DB=str(r/'index.db')),patch('session_search.cli.adapters.crawl',return_value=iter([('codex',[],'injected adapter failure')])),redirect_stdout(StringIO()):
  assert main(['index','--agent','codex','--json'])==1
 assert store.get_meta('indexed_at')=='last-successful-refresh' and store.count()==1
 path.write_text(raw+'{"unfinished":')
 assert CodexAdapter()._from_rollout(path,{},{}).turns==rec.turns
 path.write_text(raw+'bad JSON\n')
 try:CodexAdapter()._from_rollout(path,{},{});
 except ValueError:pass
 else:raise AssertionError('invalid completed record accepted')
 claude=r/'claude.jsonl';claude.write_text(''.join(json.dumps({'type':'user','message':{'role':'user','content':'padding '+str(i)}})+'\n' for i in range(30))+json.dumps({'type':'assistant','message':{'role':'assistant','content':[{'type':'thinking','thinking':'hiddenclaude'},{'type':'text','text':'claudeneedle'}]}})+'\n')
 cr=ClaudeAdapter()._from_jsonl(claude);assert 'claudeneedle' in cr.body and 'hiddenclaude' not in cr.body
 env=dict(os.environ,SESSION_SEARCH_DB=str(r/'index.db'),SESSION_SEARCH_EMBEDDER='hash')
 cli=Path(__file__).resolve().parents[1]/'scripts/session-search'
 p=subprocess.run([sys.executable,str(cli),'export','--mode','naive','--limit','1','assistantneedle'],capture_output=True,env=env)
 assert p.returncode==0,(p.stdout,p.stderr);assert len(p.stdout.splitlines())==1
 assert json.loads(p.stdout)['nodes'][1]['details']['role']=='assistant'
 p=subprocess.run([sys.executable,str(cli),'export','--mode','naive','--role','tool','assistantneedle'],capture_output=True,env=env)
 assert p.returncode==2 and not p.stdout
 p=subprocess.run([sys.executable,str(cli),'export','--mode','naive','--role','assistant','assistantneedle'],capture_output=True,env=env)
 assert p.returncode==0 and json.loads(p.stdout)['nodes'][1]['details']['record_sha256']==c['record_sha256']
 p=subprocess.run([sys.executable,str(cli),'export','--mode','naive','unfindabletoken'],capture_output=True,env=env)
 assert p.returncode==1 and not p.stdout
 guardian=r/'guardian.jsonl';guardian.write_text(json.dumps({'type':'session_meta','payload':{'id':'guardian','source':{'subagent':{'other':'guardian'}}}})+'\n')
 assert CodexAdapter()._from_rollout(guardian,{}, {}) is None
 guardian.write_text(json.dumps({'type':'session_meta','payload':{'id':'worker','source':{'subagent':{'other':'worker'}}}})+'\n'+json.dumps(rows[-1])+'\n')
 assert CodexAdapter()._from_rollout(guardian,{},{}).native_id=='worker'
 oversized=r/'large.jsonl'
 oversized.write_bytes(b'"'+b'x'*(16*1024*1024)+b'"\n'+json.dumps(rows[30]).encode()+b'\n')
 limits=[];ts=read_turns(oversized,'codex',limits)
 assert len(ts)==1 and ts[0].line==2 and 'line 1 omitted' in limits[0]
 store.close()
print('PASS: late user/assistant/tool recall, no hidden reasoning, exact line/pointer/hash/role provenance, redaction labels, duplicate suppression, retained-turn roundtrip, atomic failed refresh, malformed records, Claude parity, JSONL export')
