"""Bounded public records, independent of every consumer and private source path."""
import json
from dataclasses import asdict
from .turns import sha, excerpts
from .textutil import redact


def export_snapshot(store, result, role=None):
    nodes, edges, versions, hits = [], [], {}, []
    for rank, hit in enumerate(result.hits, 1):
        rec = store.get(hit.agent, hit.native_id)
        citations = excerpts(rec, result.query, role=role)
        if not citations:
            raise ValueError('Selected session has no exact matching turn provenance; refresh a supported adapter or use another query')
        sid = 'session:' + rec.id
        revision = sha(json.dumps({'turns':[asdict(t) for t in rec.turns], 'limitations':rec.limitations}, sort_keys=True, ensure_ascii=False))
        details = dict(agent=rec.agent, session_id=rec.native_id, cwd=rec.cwd, updated_at=rec.updated_at,
                       source_path=rec.source_path, version=revision, coverage={'limitations':['Selected public-text excerpts, not a reviewed full transcript.', *rec.limitations]},
                       open_with=['session-search','show',rec.agent,rec.native_id,'--json'],
                       summary=redact(rec.summary), description='\n'.join(c['quote'] for c in citations), evidence=citations, authority='Discovery evidence, not verified findings or permission.')
        nodes.append(dict(id=sid,label=rec.title,kind='session',url=None,bookmark_kind=None,details=details))
        versions[sid]=revision
        for c in citations:
            tid=f'turn:{rec.id}:{c["jsonl_line"]}'
            details=dict(c, version=c['record_sha256'], evidence=[c], coverage={'limitations':[c['coverage']]},
                         description=c['quote'], session_revision=revision)
            nodes.append(dict(id=tid,label=f'{c["role"]} · line {c["jsonl_line"]}',kind='session_turn',url=None,bookmark_kind=None,details=details))
            versions[tid]=details['version']
            edges.append(dict(a=tid,b=sid,kind='part_of',status='recorded',evidence=c))
        hits.append(dict(id=sid,rank=rank,method=hit.strategy,matched_by=[hit.strategy]))
    packet=dict(schema='knowledge-snapshot/v1',corpus='sessions',query=result.query,nodes=nodes,edges=edges,versions=versions,hits=hits)
    if len(json.dumps(packet,ensure_ascii=False).encode())>16*1024*1024:
        raise ValueError('Export exceeds 16 MiB')
    return packet
