#!/usr/bin/env python3
"""External CLI recipe; tools share records, never imports or orchestration state."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

LIMIT = 16*1024*1024
ROOT = Path(__file__).resolve().parents[1]


def read(path):
    if path.is_symlink(): raise ValueError('Symlinked workflow artifact')
    with path.open('rb') as f: raw=f.read(LIMIT+1)
    if len(raw)>LIMIT: raise ValueError('Workflow artifact exceeds 16 MiB')
    return raw


def sha(raw): return hashlib.sha256(raw).hexdigest()


def packet_data(raw):
    packet=json.loads(raw)
    if not isinstance(packet,dict) or packet.get('schema')!='knowledge-snapshot/v1' or packet.get('corpus')!='sessions' or not isinstance(packet.get('nodes'),list) or not all(isinstance(n,dict) for n in packet['nodes']):
        raise ValueError('Invalid session packet')
    return packet


def atomic(path,raw):
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f: f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def helper(*args,raw=None):
    p=subprocess.run([sys.executable,str(ROOT/'scripts/sources.py'),*map(str,args)],
                     input=raw,capture_output=True,timeout=180)
    if p.returncode: raise RuntimeError(p.stderr.decode(errors='replace').strip())
    return p.stdout


def binding(work,session,library):
    files={name:sha(read(work/name)) for name in ('records.jsonl','analysis.json',
           'evidence/manifest.json','evidence/session-records.json','evidence/source.md','evidence/document.md')}
    resources={name:sha(read(ROOT/name)) for name in ('scripts/session_workflow.py','workflows/session-to-insight.yaml')}
    value=dict(schema='workflow-review/v1',session=session,library=str(library),files=files,resources=resources)
    return value,sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['capture','prepare','review','publish'])
    parser.add_argument('--work',default=os.environ.get('SESSION_WORK'))
    parser.add_argument('--session',default=os.environ.get('SESSION_ID'))
    parser.add_argument('--library',default=os.environ.get('SESSION_LIBRARY'))
    parser.add_argument('--query',default=os.environ.get('SESSION_QUERY'))
    parser.add_argument('--records',default=os.environ.get('SESSION_RECORDS'),help='Explicit completed session packet, FILE or - for stdin; skips session-search')
    parser.add_argument('--agent',default=os.environ.get('SESSION_AGENT','codex'),choices=['codex','claude'])
    parser.add_argument('--review-digest',default=os.environ.get('SESSION_REVIEW_DIGEST'))
    parser.add_argument('--decision',default=os.environ.get('SESSION_REVIEW_DECISION'))
    args=parser.parse_args()
    if not args.work or not args.session or not args.library:raise ValueError('Explicit work, session ID and destination library are required')
    if not args.session.startswith('session:'+args.agent+':'):raise ValueError('Session ID must match the selected agent')
    work=Path(args.work).expanduser().absolute()
    if work.is_symlink():raise ValueError('Symlinked work directory')
    work.mkdir(parents=True,exist_ok=True,mode=0o700)
    work=work.resolve();library=Path(args.library).expanduser().resolve()
    if library==work or library.is_relative_to(work):raise ValueError('Keep destination library outside the work directory')
    lock_fd=os.open(work/'.workflow-lock',os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(lock_fd,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if args.operation=='capture':
            if not args.records and not args.query:raise ValueError('Query or an explicit session packet is required')
            if args.query and len(args.query.encode())>400:raise ValueError('Query must be at most 400 bytes')
            selected=(sys.stdin.buffer.read(LIMIT+1) if args.records=='-' else read(Path(args.records).expanduser())) if args.records else None
            if selected is not None and len(selected)>LIMIT:raise ValueError('Session export exceeds 16 MiB')
            if (work/'records.jsonl').exists():
                packet=packet_data(read(work/'records.jsonl'))
                if args.query and packet.get('query')!=args.query:raise ValueError('Captured query differs; use a fresh work directory')
                if selected is not None and selected!=read(work/'records.jsonl'):raise ValueError('Selected packet changed; use a fresh work directory')
            else:
                if args.records:
                    raw=selected
                else:
                    binary=shutil.which('session-search')
                    if binary is None:raise ValueError('session-search is not on PATH')
                    # Spool stdout: never publish a producer's partial or failed stream.
                    with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
                        p=subprocess.run([binary,'export','--mode','naive','--agent',args.agent,'--limit','1',args.query],
                                         stdout=output,stderr=errors,timeout=90)
                        if p.returncode:
                            errors.seek(0);raise RuntimeError('Session export failed: '+errors.read(4096).decode(errors='replace'))
                        output.seek(0);raw=output.read(LIMIT+1)
                if len(raw)>LIMIT:raise ValueError('Session export exceeds 16 MiB')
                packet=packet_data(raw)
                if args.query and packet.get('query')!=args.query:raise ValueError('Packet query differs from selected query')
                if not any(n.get('id')==args.session and n.get('kind')=='session' for n in packet.get('nodes',[])):
                    raise ValueError('Search returned another session; inspect results and select its ID or refine the query')
                atomic(work/'records.jsonl',raw)
            if not any(n.get('id')==args.session for n in packet.get('nodes',[])):raise ValueError('Captured session differs')
            print(work/'records.jsonl')
        elif args.operation=='prepare':
            print(helper('prepare-session',args.session,'--records','-','--work',work/'evidence',
                         raw=read(work/'records.jsonl')).decode().strip())
        else:
            if args.operation=='publish' and args.decision!='publish':raise ValueError('Publication denied: reviewer rejected or did not approve this run')
            bound,digest=binding(work,args.session,library)
            if args.operation=='review':
                analysis=json.loads(read(work/'analysis.json'))
                if not isinstance(analysis,dict):raise ValueError('Analysis must be a JSON object')
                print(json.dumps(dict(review_digest=digest,library=str(library),session=args.session,
                     title=analysis.get('title'),summary=analysis.get('summary'),tags=analysis.get('tags'),
                     evidence=str(work/'evidence/document.md'),coverage=analysis.get('coverage'),
                     insights=analysis.get('insights'),instruction='Inspect retained evidence and citations before submitting this digest.'),indent=2))
                return
            if args.decision!='publish' or args.review_digest!=digest:raise ValueError('Publication denied: decision or exact artifact/destination review digest differs')
            # Snapshot approved bytes so concurrent edits cannot change what the publisher reads.
            with tempfile.TemporaryDirectory(prefix='.approved-',dir=work) as tmp:
                stage=Path(tmp);evidence=stage/'evidence';evidence.mkdir()
                for name,expected in bound['files'].items():
                    raw=read(work/name)
                    if sha(raw)!=expected:raise ValueError('Artifact changed during approval snapshot')
                    dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
                if binding(work,args.session,library)[1]!=digest:raise ValueError('Reviewed artifacts changed')
                receipt=work/'publication.json'
                if receipt.exists():
                    saved=json.loads(read(receipt))
                    if saved['review_digest']!=digest:raise ValueError('This work was published under another review; use a fresh work directory')
                    # The publisher independently revalidates retained citations and deduplicates retries.
                note=helper('publish',evidence,stage/'analysis.json','--library',library).decode().strip()
                atomic(receipt,json.dumps(dict(schema='workflow-publication/v1',review_digest=digest,note=note,library=str(library))).encode())
                exports=helper('export','--library',library)
                atomic(work/'insights.jsonl',exports)
                print(receipt)


if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError,subprocess.TimeoutExpired) as exc:
        print('ERROR: '+str(exc),file=sys.stderr);sys.exit(1)
