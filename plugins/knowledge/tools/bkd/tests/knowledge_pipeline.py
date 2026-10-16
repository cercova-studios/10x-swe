"""Real public exporters -> bkd pipe, without companion executables in the consumer PATH."""
import hashlib, json, os, subprocess, tempfile
from pathlib import Path

bkd=Path(os.environ['BKD_BINARY']).resolve()
skills=Path(os.environ['SKILL_SEARCH_BINARY']).resolve()
sources=Path(os.environ['SOURCE_INSIGHTS']).resolve()
library=Path(os.environ['INSIGHTS_LIBRARY']).resolve()
query='unix pipes'
def checked(argv, **kw):
    out=subprocess.run([str(x) for x in argv],capture_output=True,**kw)
    assert out.returncode==0,(out.args,out.stdout.decode(errors='replace'),out.stderr.decode(errors='replace'))
    return out.stdout
with tempfile.TemporaryDirectory(prefix='bkd-knowledge-pipe-') as tmp:
    root=Path(tmp); home=root/'state'
    insight_raw=checked(['python3',sources,'export','--library',library,'--query',query,'--mode','hybrid'])
    skill_raw=checked([skills,'export','--query',query,'--state',root/'skill-state'])
    insight, skill=json.loads(insight_raw),json.loads(skill_raw)
    assert insight['hits'] and len(insight_raw.splitlines())==1 and len(skill_raw.splitlines())==1
    iid=insight['hits'][0]['id']; node=next(n for n in insight['nodes'] if n['id']==iid)
    url=node['url']; bid=hashlib.sha256(url.encode()).hexdigest()
    fixture=root/'bookmarks.jsonl'; fixture.write_text(json.dumps(dict(provider='manual',account='trial',external_id='1',url=url,title='The UNIX Pipe Card Game'))+'\n')
    checked([bkd,'--home',home,'index',fixture,'--lexical-only'])
    before=checked([bkd,'--home',home,'export'])
    env=dict(os.environ,PATH='/no-companion-tools',HOME=str(root/'no-private-libraries'))
    def consume(args,raw=insight_raw+skill_raw):
        out=checked([bkd,'--home',home,'--records','-',*args,'--json'],input=raw,env=env)
        result=json.loads(out); assert result['ok'],result
        return result['data']
    result=consume(['search',query,'--lexical-only'])
    hit=next(h for h in result['insights'] if h['node']['id']==iid)
    assert hit['method']=='hybrid' and hit['node']['details']['evidence']==node['details']['evidence']
    assert hit['node']['details']['coverage']==node['details']['coverage']
    assert result['bookmarks'][0]['id']==bid
    consume(['link-knowledge','skill:global/cli-developer',iid,'--reviewed','--reason','Reviewed CLI composition application'])
    route=consume(['path',bid,'skill:global/cli-developer'])
    assert len(route['path'])==3,route
    assert consume(['related',iid])['neighbors']
    inspected=consume(['inspect',bid]); assert inspected['node']['details']['inspected_sources']
    graph=consume(['graph']); assert any(n['id']=='skill:global/cli-developer' for n in graph['nodes'])
    local=consume(['search','teaching commands','--lexical-only'])
    assert local['insights'][0]['method']=='snapshot lexical'
    file=root/'records.jsonl'; file.write_bytes(insight_raw+skill_raw)
    saved=json.loads(checked([bkd,'--home',home,'--records',file,'graph','--json'],env=env))
    assert saved['data']==graph
    changed=json.loads(insight_raw); new='b'*64
    for n in changed['nodes']:
        n['details']['version']=new; changed['versions'][n['id']]=new
    stale=consume(['graph'],json.dumps(changed).encode()+b'\n'+skill_raw)
    assert len(stale['knowledge']['stale_links'])==1
    for raw in [b'',b'{"schema":',b'\xff',insight_raw+insight_raw,insight_raw+b'not JSON\n']:
        out=subprocess.run([str(bkd),'--home',str(home),'--records','-','graph','--json'],input=raw,capture_output=True,env=env)
        assert out.returncode and not json.loads(out.stdout)['ok']
    assert checked([bkd,'--home',home,'export'])==before
    print('PASS: real producer snapshots, stdin/file equality, separate hybrid ranks, exact citations/coverage, reviewed bookmark-entry-insight-skill path, stale revisions, local snapshot search, malformed input, unchanged bookmark cache; no consumer tool/library dependencies')
