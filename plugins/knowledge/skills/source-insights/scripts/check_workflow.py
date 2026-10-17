"""Disposable workflow boundaries; real Dagu acceptance runs separately."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from unittest.mock import patch

script=Path(__file__).with_name('session_workflow.py')
spec=importlib.util.spec_from_file_location('workflow',script)
workflow=importlib.util.module_from_spec(spec);spec.loader.exec_module(workflow)
sid='session:codex:fixture';tid='turn:codex:fixture:3';version='a'*64
quote='Selected public evidence, not independent verification.'
details=dict(agent='codex',session_id='fixture',source_path='/unavailable/session.jsonl',jsonl_line=3,json_pointer='$.payload.content',role='assistant',timestamp=None,record_sha256=version,original_text_sha256=version,indexed_text_sha256='b'*64,excerpt_sha256=hashlib.sha256(quote.encode()).hexdigest(),char_start=0,char_end=len(quote),redacted=False,quote=quote,version=version,session_revision=version)
packet=dict(schema='knowledge-snapshot/v1',corpus='sessions',query='evidence',nodes=[dict(id=sid,kind='session',label='Fixture',details=dict(version=version,coverage={'limitations':['Selected excerpts only']})),dict(id=tid,kind='session_turn',details=details)],edges=[dict(a=tid,b=sid,kind='part_of',status='recorded')],versions={sid:version,tid:version},hits=[])

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);work=root/'work';library=root/'library';bins=root/'bin';bins.mkdir()
    producer=bins/'session-search'
    def fake(raw,code=0):
        program='import sys; sys.stdout.buffer.write('+repr(raw)+'); sys.exit('+str(code)+')'
        producer.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' -c '+shlex.quote(program)+'\n');producer.chmod(0o700)
    env=dict(os.environ,PATH=str(bins))
    def run(op,dest=work,**kwargs):
        flags=[sys.executable,str(script),op,'--work',str(dest),'--session',sid,'--library',str(library)]
        for key,value in kwargs.items():flags.extend(['--'+key.replace('_','-'),value])
        return subprocess.run(flags,env=env,capture_output=True,timeout=30)
    raw=json.dumps(packet).encode();fake(raw,7)
    selected=root/'selected.jsonl';selected.write_bytes(raw)
    assert run('capture',dest=root/'selected-work',records=str(selected)).returncode==0
    assert (root/'selected-work/records.jsonl').read_bytes()==raw
    assert run('prepare',dest=root/'selected-work').returncode==0
    selected.write_bytes(raw+b' ')
    assert run('capture',dest=root/'selected-work',records=str(selected)).returncode
    selected.write_bytes(raw)
    assert run('capture',dest=root/'mismatch-work',records=str(selected),query='different').returncode
    argv=[sys.executable,str(script),'capture','--records','-','--work',str(root/'piped-work'),'--session',sid,'--library',str(library)]
    p=subprocess.run(argv,input=raw,env=env,capture_output=True);assert p.returncode==0,p.stderr
    assert (root/'piped-work/records.jsonl').read_bytes()==raw
    p=subprocess.run(argv,input=raw+b' ',env=env,capture_output=True);assert p.returncode
    p=run('capture',query='evidence');assert p.returncode and not (work/'records.jsonl').exists()
    for bad in [b'[]',b'{',b'{"schema":"knowledge-snapshot/v1","corpus":"sessions","nodes":[null]}']:
        fake(bad);p=run('capture',query='evidence');assert p.returncode and not p.stdout and b'Traceback' not in p.stderr
    fake(raw);assert run('capture',query='evidence').returncode==0
    assert (work/'records.jsonl').read_bytes()==raw
    fake(b'invalid',9);assert run('capture',query='evidence').returncode==0  # Successful capture freezes retries.
    assert run('capture',query='changed').returncode
    assert run('prepare').returncode==0
    lines=(work/'evidence/document.md').read_text().splitlines();line=lines.index(quote)+1
    analysis=dict(title='Fixture evidence',summary='Recorded public claim',tags=['session'],coverage={'line_ranges':[[1,len(lines)]],'limitations':['Selected excerpts only']},insights=[dict(claim=quote,status='source-claim',why_it_matters='Review boundaries',application='Inspect original evidence',caveats='Unverified fixture',evidence=[dict(line_start=line,line_end=line,quote=quote)])])
    (work/'analysis.json').write_text(json.dumps(analysis))
    review=json.loads(run('review').stdout);digest=review['review_digest']
    assert review['title']==analysis['title'] and review['summary']==analysis['summary'] and review['tags']==analysis['tags']
    assert run('publish',decision='reject',review_digest=digest).returncode and not library.exists()
    assert run('publish',decision='publish',review_digest='0'*64).returncode and not library.exists()
    for name in ('analysis.json','records.jsonl','evidence/document.md'):
        path=work/name;before=path.read_bytes();path.write_bytes(before+b' ')
        assert run('publish',decision='publish',review_digest=digest).returncode and not library.exists()
        path.write_bytes(before)
    assert workflow.binding(work,sid,root/'other')[1]!=digest
    # Simulate export failure after confirmed publication; snapshot bytes are the approved ones.
    calls=[]
    def helper(*args,raw=None):
        calls.append(args[0])
        if args[0]=='publish':
            assert Path(args[1],'document.md').read_bytes()==(work/'evidence/document.md').read_bytes()
            return b'/confirmed/note.md\n'
        raise RuntimeError('injected downstream export failure')
    argv=[str(script),'publish','--work',str(work),'--session',sid,'--library',str(library),'--decision','publish','--review-digest',digest]
    with patch.object(sys,'argv',argv),patch.object(workflow,'helper',helper):
        try:workflow.main();raise AssertionError('expected export failure')
        except RuntimeError as exc:assert 'export failure' in str(exc)
    assert calls==['publish','export'] and json.loads((work/'publication.json').read_text())['review_digest']==digest
    assert not (work/'insights.jsonl').exists() and not list(work.glob('.approved-*'))
    assert not list(work.glob('.records.jsonl-*'))
    (work/'.workflow-lock').unlink();(work/'.workflow-lock').symlink_to(root/'outside')
    assert run('review').returncode and not (root/'outside').exists()
print('PASS: failed/partial/malformed producer isolation, frozen capture, stdin preparation, rejection, stale artifact/destination denial, approved-byte snapshot, confirmed-publication recovery receipt, lock symlink denial')
