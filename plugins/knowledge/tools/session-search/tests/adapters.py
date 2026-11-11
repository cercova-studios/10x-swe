"""Exercise all supported adapters using isolated harness fixtures."""
import json,os,sqlite3,subprocess,sys,tempfile
from contextlib import closing
from pathlib import Path
native=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='session-port-parity-') as tmp:
    root = Path(tmp)
    home = root / 'home'
    home.mkdir()

    def write(rel, rows):
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(''.join((json.dumps(v, ensure_ascii=False) + '\n' for v in rows)))
        os.utime(p, (1791300000, 1791300000))
        return p

    def db(rel, script):
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(p)) as c:
            c.executescript(script)
            c.commit()
        return p
    codex = write('.codex/sessions/rollout-fixture.jsonl', [{'type': 'session_meta', 'payload': {'id': 'codex-fixture', 'cwd': '/fixture/日本語'}}, {'timestamp': '2026-10-12T12:00:00Z', 'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'userneedle ' + 'padding ' * 5000}]}}, {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'channel': 'final', 'content': [{'type': 'output_text', 'text': 'assistantneedle Unicode 🙂 retains pipes. sk-' + 'x' * 20}]}}, {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'channel': 'analysis', 'content': [{'type': 'output_text', 'text': 'HIDDEN_NEEDLE'}]}}, {'type': 'response_item', 'payload': {'type': 'function_call_output', 'output': 'toolneedle passed.'}}, {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'DUPLICATE_EVENT'}}])
    write('.codex/session_index.jsonl', [{'id': 'codex-fixture', 'thread_name': '  explicit pipes  ', 'updated_at': '2026-10-12T12:00:00Z'}, {'id': 'metadata-only', 'thread_name': 'metadata needle'}])
    write('.codex/history.jsonl', [{'session_id': 'metadata-only', 'text': 'metadata needle preserved'}])
    write('.codex/sessions/guardian.jsonl', [{'type': 'session_meta', 'payload': {'id': 'guardian', 'source': {'subagent': {'other': 'guardian'}}}}])
    write('.claude/projects/p/claude.jsonl', [{'type': 'user', 'sessionId': 'claude-fixture', 'cwd': '/fixture', 'message': {'role': 'user', 'content': 'claudeneedle request'}}, {'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'thinking', 'thinking': 'HIDDEN_CLAUDE'}, {'type': 'text', 'text': 'claudeneedle answer with citations'}]}}])
    for agent in ['pi', 'prime', 'omp']:
        write(f'.{agent}/agent/sessions/{agent}.jsonl', [{'type': 'session', 'id': f'{agent}-fixture', 'cwd': '/fixture', 'title': f'{agent} title'}, {'type': 'message', 'message': {'role': 'user', 'content': f'{agent}needle remembered'}}, {'type': 'title_change', 'title': f'{agent} final title'}])
    write('.grok/sessions/%2Ffixture/grok/summary.json', [{'info': {'id': 'grok-fixture'}, 'session_summary': 'grokneedle summary', 'last_active_at': '2026-10-12T12:00:00Z'}])
    write('.grok/sessions/%2Ffixture/grok/chat_history.jsonl', [{'type': 'user', 'content': 'grokneedle question'}])
    write('.gemini/antigravity-cli/history.jsonl', [{'workspace': '/fixture', 'display': 'agyneedle older', 'timestamp': 1791000000000}, {'workspace': '/fixture', 'display': 'agyneedle newer', 'timestamp': 1791000000100}])
    write('.local/share/amp/history.jsonl', [{'id': 'amp-fixture', 'text': 'ampneedle local history', 'cwd': '/fixture', 'timestamp': 1791000000000}])
    db('.copilot/session-store.db', "CREATE TABLE turns(session_id,user_message,timestamp,turn_index); INSERT INTO turns VALUES('copilot-fixture','copilotneedle turn',1,0); CREATE TABLE sessions(id,cwd,summary,created_at,updated_at); INSERT INTO sessions VALUES('copilot-fixture','/fixture','copilotneedle summary',1791000000000,1791000000001);")
    db('Library/Application Support/Cursor/User/globalStorage/conversation-search.db', "CREATE TABLE conversations(id,title,updated_at,fts_rowid);CREATE VIRTUAL TABLE conversation_fts USING fts5(body); INSERT INTO conversation_fts(body) VALUES('cursorneedle text'); INSERT INTO conversations VALUES('cursor-fixture','cursorneedle title',1791000000000,1);")
    db('.local/share/opencode/opencode.db', 'CREATE TABLE session(id,title,directory,time_updated,time_created);CREATE TABLE message(id,session_id,data);CREATE TABLE part(message_id,data);INSERT INTO session VALUES(\'opencode-fixture\',\'New session temporary\',\'/fixture\',1791000000000,1);INSERT INTO message VALUES(\'m\',\'opencode-fixture\',\'{"role":"user"}\');INSERT INTO part VALUES(\'m\',\'{"type":"text","text":"opencodeneedle exact body"}\');')
    db('.omp/agent/history.db', "CREATE TABLE session_titles(session_id,title,updated_at);CREATE TABLE history(id,session_id,prompt,created_at,cwd);INSERT INTO session_titles VALUES('omp-history','omp history title',1791000000000);INSERT INTO history VALUES(1,'omp-history','ompneedle history body',1791000000000,'/fixture');")
    db('.gemini/antigravity-cli/conversation_summaries.db', "CREATE TABLE summaries(id,title,summary,updated_at,cwd);INSERT INTO summaries VALUES('agy-summary','agyneedle summary title','agyneedle summary body',1791000000000,'/fixture');")

    env={**os.environ,'HOME':str(home),'PATH':'/usr/bin:/bin','SESSION_SEARCH_DB':str(root/'index.db'),'SESSION_SEARCH_EMBEDDER':'hash'}
    env.pop('AGENT_KNOWLEDGE_HOME',None)
    def run(*args):
     p=subprocess.run([str(native),*args],env=env,capture_output=True,timeout=30)
     assert p.returncode==0,(args,p.stdout,p.stderr)
     return json.loads(p.stdout)
    indexed=run('index','--json')
    assert not indexed['errors'] and set(indexed['counts'])=={'claude','codex','cursor','grok','copilot','agy','opencode','amp','omp','prime','pi'}
    assert all(v>0 for v in indexed['counts'].values())
    for agent in indexed['counts']:
     query='assistantneedle' if agent=='codex' else agent+'needle'
     hits=run('search','--agent',agent,'--mode','naive','--json',query)['hits']
     assert hits and all(h['agent']==agent for h in hits),(agent,hits)
    assert run('search','--agent','gemini','--mode','naive','--json','agyneedle')['hits']
    # Metadata-only sources cannot fabricate exact evidence.
    rejected=subprocess.run([str(native),'export','--agent','pi','--mode','naive','pineedle'],env=env,capture_output=True,timeout=10)
    assert rejected.returncode==2 and not rejected.stdout
    # An installed Amp CLI is an independent acquisition boundary.
    shim=home/'bin/amp';shim.parent.mkdir()
    shim.write_text('#!'+sys.executable+'\nimport json,sys\nif sys.argv[1:3]==["threads","list"]: print(json.dumps([{"id":"remote","title":"ampremote needle","updated":1791000000000}]))\nelse: print(json.dumps({"title":"ampremote needle","env":{"initial":{"workingDirectory":"file:///fixture%20space"}},"messages":[{"role":"user","content":"ampremote evidence"}]}))\n')
    shim.chmod(0o700);env['PATH']=str(shim.parent);env['SESSION_SEARCH_AMP_LIMIT']='1'
    assert run('index','--agent','amp','--json')['counts']=={'amp':1}
    hit=run('search','--agent','amp','--mode','naive','--json','ampremote')['hits'][0]
    assert hit['source_path']=='amp://threads/remote' and hit['cwd']=='/fixture space'
print('PASS: eleven adapters, aliases, metadata-only export rejection and native Amp CLI acquisition')
