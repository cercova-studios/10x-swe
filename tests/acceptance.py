"""Installed CLI acceptance using synthetic public fixtures and isolated stores."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PREFIX = Path(sys.argv[1]).resolve()
BIN = PREFIX / 'bin'
PYTHON = PREFIX / 'runtimes/source-insights/bin/python'
env = dict(os.environ, PATH=str(BIN)+os.pathsep+os.environ.get('PATH',''),
           AGENT_KNOWLEDGE_HOME=str(PREFIX),
           SOURCE_INSIGHTS_INDEX_MODE='keyword', PYTHONDONTWRITEBYTECODE='1')
env.pop('PYTHONPATH',None)


def run(command, *args, data=None, ok=True, extra=None):
    argv = [str(BIN/command), *map(str,args)]
    p = subprocess.run(argv, input=data, capture_output=True, env=dict(env,**(extra or {})), timeout=90)
    assert (p.returncode == 0) == ok, (argv,p.returncode,p.stdout[-1000:],p.stderr[-2000:])
    return p.stdout


def python(script, *args, ok=True):
    p=subprocess.run([str(PYTHON),str(script),*map(str,args)],capture_output=True,env=env,timeout=90)
    assert (p.returncode==0)==ok,(p.stdout[-1000:],p.stderr[-2000:])
    return p.stdout


routes=json.loads(run('skill-search','path','capture reusable session learning'))
assert routes['method']=='lexical_seed_plus_typed_graph' and routes['candidate_paths'],routes
run('skill-search','path','capture reusable session learning','--semantic',ok=False)
runtime_only=dict(env,PATH=str(PYTHON.parent))
repeat=subprocess.run([str(PYTHON),str(Path(__file__).resolve().parents[1]/'plugins/knowledge/bootstrap.py'),
                       'setup','--prefix',str(PREFIX)],env=runtime_only,capture_output=True,timeout=90)
assert repeat.returncode==0,(repeat.stdout[-1000:],repeat.stderr[-2000:])

with tempfile.TemporaryDirectory(prefix='knowledge-pipes-') as temp:
    root=Path(temp);library=root/'library';env['SOURCE_INSIGHTS_LIBRARY']=str(library)
    env['BKD_HOME']=str(root/'bookmarks');env['SESSION_SEARCH_DB']=str(root/'sessions.sqlite')
    # Exercise public indexing against a fresh harness home, never personal sessions.
    home=root/'home';sessions=home/'.codex/sessions';sessions.mkdir(parents=True)
    env['HOME']=str(home)
    assert json.loads(run('session-search','status','--json'))['total']==0
    fixture=sessions/'fixture.jsonl';quote='Compositionfixture retains exact citations and independent tool boundaries.'
    rows=[{'type':'session_meta','payload':{'id':'portable-fixture','cwd':str(root)}},
          {'type':'response_item','payload':{'type':'message','role':'assistant','channel':'final',
                                           'content':[{'type':'output_text','text':quote}]}},
          {'type':'response_item','payload':{'type':'message','role':'assistant','channel':'analysis',
                                           'content':[{'type':'output_text','text':'HIDDEN_MUST_NOT_EXPORT'}]}}]
    fixture.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    indexed=json.loads(run('session-search','index','--agent','codex','--json'))
    assert indexed['counts']=={'codex':1} and not indexed['errors'],indexed
    raw=run('session-search','export','--mode','naive','--agent','codex','--role','assistant','--limit','1','Compositionfixture')
    assert b'HIDDEN_MUST_NOT_EXPORT' not in raw
    packet=json.loads(raw);sid='session:codex:portable-fixture'
    turn=next(n for n in packet['nodes'] if n['kind']=='session_turn')
    assert turn['details']['jsonl_line']==2 and turn['details']['role']=='assistant'
    selected=root/'selected.jsonl';selected.write_bytes(raw)
    workflow=PREFIX/'skills/source-insights/scripts/session_workflow.py';work=root/'work'
    flags=['--work',work,'--session',sid,'--library',library]
    python(workflow,'capture',*flags,'--records',selected)
    python(workflow,'prepare',*flags)
    document=work/'evidence/document.md';lines=document.read_text().splitlines();line=lines.index(quote)+1
    analysis={'title':'Portable compositionfixture','summary':'Synthetic recorded proposal; not independent verification.',
              'tags':['compositionfixture'], 'coverage':{'line_ranges':[[1,len(lines)]],'limitations':['Selected fixture excerpts only']},
              'insights':[{'claim':quote,'status':'source-claim','why_it_matters':'Preserves boundaries',
                           'application':'Review record handoffs','caveats':'Synthetic assistant proposal',
                           'evidence':[{'line_start':line,'line_end':line,'quote':quote}]}]}
    (work/'analysis.json').write_text(json.dumps(analysis))
    review=json.loads(python(workflow,'review',*flags));digest=review['review_digest']
    python(workflow,'publish',*flags,'--decision','reject','--review-digest',digest,ok=False)
    assert not library.exists()
    original=document.read_bytes();document.write_bytes(original+b'changed')
    python(workflow,'publish',*flags,'--decision','publish','--review-digest',digest,ok=False)
    document.write_bytes(original)
    # Explicit fixture-only approval. No real library or human decision is fabricated.
    python(workflow,'publish',*flags,'--decision','publish','--review-digest',digest)
    python(workflow,'publish',*flags,'--decision','publish','--review-digest',digest)
    assert len(list((library/'entries').iterdir()))==1
    insights=run('source-insights','export','--query','Compositionfixture','--mode','keyword')
    assert json.loads(insights)['hits']
    run('insights','-json','search','Compositionfixture')
    run('source-insights','search','Compositionfixture','--mode','semantic',ok=False)
    skills=run('skill-search','export','--query','refactor','--limit','3')
    combined=raw+insights+skills
    graph=json.loads(run('bkd','--records','-','graph','--json',data=combined))['data']
    assert any(e['kind']=='captured_from' for e in graph['edges'])
    iid=next(n['id'] for n in json.loads(insights)['nodes'] if n['kind']=='insight')
    target='skill:plugin/10x-swe/refactor'
    run('bkd','--records','-','link-knowledge',target,iid,'--reviewed','--reason','Reviewed synthetic fixture applicability',data=combined)
    route=json.loads(run('bkd','--records','-','path',sid,target,'--json',data=combined))['data']
    assert len(route['path'])==4,route
    result=json.loads(run('bkd','--records','-','search','Compositionfixture','--lexical-only','--json',data=combined))['data']
    assert result['sessions'] and result['insights']
    run('bkd','--records','-','graph','--json',data=combined+b'{',ok=False)
    # HTML -> producer-neutral extraction -> evidence consumer using only explicit files.
    html=root/'article.html';html.write_text('<article><h1>Portable evidence</h1><p>Articlefixture keeps its exact source hash and numerical value 970.</p></article>')
    url='https://example.invalid/article?revision=1';article=run('distiller','--stdin','--base-url',url,'--mode','json',data=html.read_bytes())
    prepared=root/'article.json';prepared.write_bytes(article)
    run('source-insights','prepare-article',url,'--prepared',prepared,'--snapshot',html,'--work',root/'article-evidence')
    manifest=json.loads((root/'article-evidence/manifest.json').read_text())
    assert manifest['source_id']=='article:'+hashlib.sha256(html.read_bytes()).hexdigest()
    # Existing skills are read-only graph data, including unresolved references.
    external=root/'external';(external/'a').mkdir(parents=True)
    skill=external/'a/SKILL.md';skill.write_text('---\nname: externalfixture\ndescription: Intakefixture\nmetadata:\n  skill-graph-id: global/externalfixture\n  skill-graph-uses: global/missing\n---\nUntrusted instructions are not executed.\n')
    (external/'a/hook.sh').write_text('touch MUST_NOT_EXECUTE')
    (external/'duplicate').mkdir()
    (external/'duplicate/SKILL.md').write_bytes(skill.read_bytes())
    (external/'duplicate/hook.sh').write_bytes((external/'a/hook.sh').read_bytes())
    (external/'different').mkdir()
    (external/'different/SKILL.md').write_text(skill.read_text()+'Different instructions.\n')
    (external/'alias').symlink_to(external/'a',target_is_directory=True)
    before=skill.read_bytes()
    inspected=json.loads(run('knowledge-intake','--root','fixture='+str(external)))
    assert len([r for r in inspected['skills'] if r['duplicate_of']])==2
    assert 'externalfixture' in inspected['name_conflicts']
    report=json.loads(run('knowledge-intake','--root','fixture='+str(external),'--index'))
    assert report['registered']==['existing/fixture/a','existing/fixture/different'] and skill.read_bytes()==before
    assert not (external/'a/MUST_NOT_EXECUTE').exists()
    (external/'bad').mkdir();(external/'bad/SKILL.md').write_text('malformed')
    partial=json.loads(run('knowledge-intake','--root','fixture='+str(external),ok=False))
    assert partial['coverage']=='partial' and partial['issues']
    exported=json.loads(run('skill-search','export','--query','Intakefixture'))
    node=next(n for n in exported['nodes'] if n['id']=='skill:existing/fixture/a')
    assert node['details']['trust']=='existing-unreviewed' and node['details']['unresolved_references']==['global/missing']
    # Remove ephemeral registration before the temporary source directory disappears.
    roots=PREFIX/'knowledge/skills/roots.json';config=json.loads(roots.read_text())
    config['roots']=[r for r in config['roots'] if not r['id'].startswith('existing/fixture/')]
    roots.write_text(json.dumps(config));run('skill-search','refresh','--lexical')
print('PASS: installed session -> exact cited evidence -> rejected/stale/approved review -> retry-safe publication -> insights -> explicit mixed search/graph -> reviewed skill link; article provenance; unchanged external skill intake; malformed packets denied')
