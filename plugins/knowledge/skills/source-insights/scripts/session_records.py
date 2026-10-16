"""Prepare caller-supplied session excerpts. No producer or source-store access."""
import hashlib
import json
import re
import sys
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def evidence(record, session_id):
    if not isinstance(record, dict) or record.get('schema') != 'knowledge-snapshot/v1' or record.get('corpus') != 'sessions':
        raise ValueError('Expected a sessions knowledge-snapshot/v1 record')
    nodes = record.get('nodes')
    if not isinstance(nodes, list) or len(nodes) > 100:
        raise ValueError('Invalid session node count')
    if any(not isinstance(n, dict) or not isinstance(n.get('id'), str) or not isinstance(n.get('details'), dict) for n in nodes):
        raise ValueError('Invalid session node')
    ids = [n['id'] for n in nodes]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate session node')
    session = next((n for n in nodes if n.get('id') == session_id and n.get('kind') == 'session'), None)
    if session is None:
        raise ValueError('Select an exported session ID explicitly')
    revisions = record.get('versions', {})
    edges = record.get('edges')
    if not isinstance(revisions, dict) or not isinstance(edges, list) or any(not isinstance(e, dict) for e in edges):
        raise ValueError('Invalid session revisions or edges')
    if not isinstance(session.get('label'), str) or not isinstance(session['details'].get('coverage'), dict):
        raise ValueError('Invalid session label or coverage')
    def revision(n):
        v = revisions.get(n['id'])
        if not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) or n['details'].get('version') != v:
            raise ValueError('Invalid node revision')
        return v
    session_revision = revision(session)
    selected = []
    for n in nodes:
        if n.get('kind') != 'session_turn':
            continue
        d = n.get('details', {})
        if not isinstance(d.get('agent'), str) or not isinstance(d.get('session_id'), str):
            raise ValueError('Invalid session identity')
        parent = 'session:'+d.get('agent', '')+':'+d.get('session_id', '')
        if parent != session_id:
            continue
        v = revision(n)
        quote = d.get('quote')
        if (not isinstance(quote, str) or not quote.strip() or len(quote)>2000
            or sha(quote.encode()) != d.get('excerpt_sha256')
            or d.get('role') not in ('user','assistant','tool')
            or not isinstance(d.get('jsonl_line'), int) or isinstance(d['jsonl_line'], bool) or d['jsonl_line']<1
            or n['id'] != 'turn:'+d['agent']+':'+d['session_id']+':'+str(d['jsonl_line'])
            or d.get('session_revision') != session_revision
            or v != d.get('record_sha256')
            or not isinstance(d.get('char_start'), int) or isinstance(d['char_start'], bool) or d['char_start']<0
            or not isinstance(d.get('char_end'), int) or isinstance(d['char_end'], bool)
            or d.get('char_end') != d['char_start']+len(quote)
            or not isinstance(d.get('json_pointer'), str) or not d['json_pointer'].startswith('$.')
            or not isinstance(d.get('source_path'), str) or len(d['source_path'])>4096
            or not isinstance(d.get('redacted'), bool)):
            raise ValueError('Invalid session excerpt provenance')
        for field in ('record_sha256','original_text_sha256','indexed_text_sha256'):
            if not isinstance(d.get(field), str) or not re.fullmatch('[0-9a-f]{64}', d[field]):
                raise ValueError('Invalid citation hash')
        if not any(e.get('a')==n['id'] and e.get('b')==session_id and e.get('kind')=='part_of' and e.get('status')=='recorded' for e in edges):
            raise ValueError('Unresolved session turn')
        selected.append(n)
    if not 1 <= len(selected) <= 3:
        raise ValueError('Expected 1–3 selected session excerpts')
    lines = [f'# Session evidence: {session["label"]}', '', f'Session: {session_id}',
             'Coverage: selected public-text excerpts only; hidden reasoning and omitted context are not reviewed.',
             'Provenance is asserted by the producer. Excerpt hashes are verified; original source bytes are not available to this consumer.', '']
    lines.extend(['Producer coverage: '+json.dumps(session['details']['coverage'],ensure_ascii=False), ''])
    for n in selected:
        d=n['details']
        lines.extend([f'## {n["id"]}', json.dumps({k:d.get(k) for k in ('agent','session_id','source_path','jsonl_line','json_pointer','role','timestamp','record_sha256','original_text_sha256','indexed_text_sha256','excerpt_sha256','char_start','char_end','redacted')},ensure_ascii=False), '',d['quote'],''])
    return session, selected, '\n'.join(lines)


def prepare(args, helpers):
    if args.records == '-':
        raw = sys.stdin.buffer.read(16*1024*1024+1)
    else:
        with Path(args.records).open('rb') as stream:
            raw = stream.read(16*1024*1024+1)
    if len(raw)>16*1024*1024:
        raise ValueError('Session input exceeds 16 MiB')
    record=json.loads(raw)
    session, selected, document = evidence(record,args.session)
    work=args.work.expanduser().resolve()
    content={'session-records.json':raw,'source.md':document.encode(),'document.md':document.encode()}
    hashes={name:sha(data) for name,data in content.items()}
    manifest=dict(schema=2,kind='article',ready=True,source=session['id'],source_id='article:'+sha(raw),
                  request_title=None,title=session['label'],published=None,analyzed_at=helpers['now'](),
                  line_count=len(document.splitlines()),retained=list(content),prepared_sha256=hashes,
                  extraction=dict(tool='session-evidence/v1',method='selected-public-turns',session_id=session['id'],
                                  session_revision=record['versions'][session['id']],
                                  coverage=session['details']['coverage'],
                                  turns=[dict(id=n['id'],version=record['versions'][n['id']]) for n in selected]))
    if work.exists():
        old=helpers['read'](work/'manifest.json')
        if old.get('source_id')!=manifest['source_id'] or old.get('prepared_sha256')!=hashes:
            raise ValueError('Work directory differs; use a new directory')
        for name,v in hashes.items():
            if helpers['digest'](work/name)!=v:raise ValueError('Retained session evidence changed')
        print(work/'manifest.json');return
    work.parent.mkdir(parents=True,exist_ok=True)
    import tempfile
    import os
    with tempfile.TemporaryDirectory(prefix='.session-evidence-',dir=work.parent) as tmp:
        stage=Path(tmp)/'work';stage.mkdir(mode=0o700)
        for name,data in content.items():helpers['atomic'](stage/name,data.decode('utf-8'))
        helpers['write_json'](stage/'manifest.json',manifest)
        os.rename(stage,work)
    print(work/'manifest.json')
