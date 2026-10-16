#!/usr/bin/env python3
"""Local, provenance-bound topic mapping and portable Obsidian skill notes."""
import argparse
import array
import collections
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import shutil

sys.dont_write_bytecode = True
VERSION = 'bge-body-v1:metadata-plus6chunks:mutual-knn6:cosine0.60:greedy-modularity1'
STOP = set('a an and are as at be by can do for from has have how if in into is it its not of on or our should that the their then these this to use using when where which with you your skill skills agent agents workflow instructions safety security must never always read run file files'.split())

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def bounded(path, limit=1024*1024):
    with Path(path).open('rb') as f:
        raw = f.read(limit+1)
    if len(raw)>limit:
        raise ValueError('Entry exceeds byte budget')
    return raw

def terms(text):
    return [s for s in re.findall(r'[A-Za-z][A-Za-z0-9-]{2,}',text.lower()) if s not in STOP]

def inputs(graph):
    if graph.get('schema')!=1 or graph.get('errors') or len(graph['nodes'])>2048:
        raise ValueError('Invalid/bounded graph required')
    records=[]
    for node in sorted(graph['nodes'],key=lambda n:n['id']):
        raw=bounded(node['path'])
        if sha(raw)!=node['sha256']:
            raise ValueError('Changed skill; rebuild inventory first')
        text=raw.decode();lines=text.splitlines();end=next(i for i in range(1,len(lines)) if lines[i].strip()=='---')
        metadata=' '.join((node['name']+' '+node['description']).split())
        chunks=[]
        def add(text, locator):
            text=' '.join(text.split())
            if not text: return
            text=text.encode()[:480].decode('utf-8',errors='ignore')
            chunks.append({'text':text,'locator':locator,'sha256':sha(text.encode())})
        add(metadata, 'frontmatter:name+description')
        # Bound evidence extraction; don't embed code blocks or generic policy sections.
        code=False;skip=False;paragraph=[];start=end+2
        for number,line in enumerate(lines[end+1:],end+2):
            if line.lstrip().startswith('```'):
                code=not code;continue
            if code:continue
            if line.startswith('#'):
                skip=any(word in line.lower() for word in ('safety','permission','verification','security','install','license','setup'))
            if skip:continue
            if line.strip():
                if not paragraph:start=number
                paragraph.append(line)
            elif paragraph:
                add(' '.join(paragraph),f'lines:{start}-{number-1}');paragraph=[]
                if len(chunks)>=7:break
        if paragraph and len(chunks)<7:add(' '.join(paragraph),f'lines:{start}-{len(lines)}')
        records.append({'id':node['id'],'entrypoint_sha256':node['sha256'],'chunks':chunks})
    return records

def embedding_helper():
    import local_embeddings as module
    return module

def vectors(records, cache):
    helper=embedding_helper();cache=Path(cache);cache.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(cache)
    db.execute('CREATE TABLE IF NOT EXISTS embeddings(key TEXT PRIMARY KEY, vector BLOB NOT NULL)')
    keys=[];missing=[];texts=[]
    for record in records:
        for chunk in record['chunks']:
            key=sha(encode([helper.SPEC,chunk['sha256']]))
            keys.append(key)
            if not db.execute('SELECT 1 FROM embeddings WHERE key=?',(key,)).fetchone() and key not in missing:
                missing.append(key);texts.append(chunk['text'])
    generated=helper.embed(texts)
    # Embedding failures occur before cache transaction/publication.
    with db:
        for key,vector in zip(missing,generated):db.execute('INSERT OR REPLACE INTO embeddings VALUES(?,?)',(key,vector))
    results=[];offset=0
    for record in records:
        parts=[]
        for _ in record['chunks']:
            vector=array.array('f');vector.frombytes(db.execute('SELECT vector FROM embeddings WHERE key=?',(keys[offset],)).fetchone()[0]);offset+=1
            if len(vector)!=384 or not all(math.isfinite(v) for v in vector):raise ValueError('Invalid cached embedding')
            parts.append(vector)
        # Metadata and body each get equal total mass; long prose cannot dominate.
        mean=[parts[0][d] if len(parts)==1 else 0.5*parts[0][d]+0.5*sum(p[d] for p in parts[1:])/(len(parts)-1) for d in range(384)]
        norm=math.sqrt(sum(v*v for v in mean))
        if norm<0.001:raise ValueError('Empty aggregate vector')
        results.append([v/norm for v in mean])
    db.close();return results,helper.SPEC,len(missing)

def communities(count, weighted):
    """Greedy agglomerative modularity; deterministic ties, no fixed topic taxonomy."""
    groups={i:{i} for i in range(count)};degree=[0.]*count;between={}
    for a,b,w in weighted:
        if a==b:continue
        degree[a]+=w;degree[b]+=w;between[(min(a,b),max(a,b))]=w
    total=sum(degree)/2
    strength={i:degree[i] for i in groups}
    if not total:return list(groups.values())
    while between:
        gain,(a,b)=max(((w/total-strength[a]*strength[b]/(2*total*total),(a,b)) for (a,b),w in between.items()),key=lambda v:(v[0],-v[1][0],-v[1][1]))
        if gain<=1e-9:break
        groups[a]|=groups.pop(b);strength[a]+=strength.pop(b)
        next_between={}
        for (x,y),w in between.items():
            x=a if x==b else x;y=a if y==b else y
            if x!=y:
                pair=(min(x,y),max(x,y));next_between[pair]=next_between.get(pair,0.)+w
        between=next_between
    return sorted(groups.values(),key=lambda g:(-len(g),min(g)))

def map_graph(graph, records, embeddings, spec):
    nodes=sorted(graph['nodes'],key=lambda n:n['id']);count=len(nodes);ids={n['id']:i for i,n in enumerate(nodes)}
    neighbors=[]
    for i,v in enumerate(embeddings):
        scores=sorted(((sum(a*b for a,b in zip(v,w)),j) for j,w in enumerate(embeddings) if j!=i),reverse=True)
        neighbors.append({j:score for score,j in scores[:6] if score>=0.60})
    edges=[dict(e,provenance=e.get('provenance','frontmatter'),status=e.get('status','declared'),weight=e.get('weight',1.)) for e in graph['edges'] if e.get('status')!='inferred']
    # Actual body links are references, not guessed uses.
    existing={(e['source'],e['target'],e['relation']) for e in edges}
    for e in graph.get('candidates',[]):
        key=(e['source'],e['target'],'references')
        if key not in existing:edges.append(dict(e,provenance='body-link',status='observed',weight=0.8));existing.add(key)
    similarities=[]
    for i,near in enumerate(neighbors):
        for j,score in near.items():
            if i<j and i in neighbors[j] and (nodes[i]['id'],nodes[j]['id'],'related') not in existing and (nodes[j]['id'],nodes[i]['id'],'related') not in existing:
                similarities.append((i,j,score));edges.append({'source':nodes[i]['id'],'target':nodes[j]['id'],'relation':'related','status':'inferred','provenance':'local-bge-mutual-knn','weight':round(score,6),'evidence':{'source_chunks':[c['locator'] for c in records[i]['chunks']],'target_chunks':[c['locator'] for c in records[j]['chunks']]}})
    weighted={}
    for e in edges:
        a,b=ids[e['source']],ids[e['target']]
        if a==b:continue
        pair=(min(a,b),max(a,b));weighted[pair]=max(weighted.get(pair,0.),e['weight'])
    groups=communities(count,[(a,b,w) for (a,b),w in weighted.items()]);membership={};clusters=[]
    documents=[set(terms(n['name']+' '+n['description'])) for n in nodes]
    frequency=collections.Counter(word for words in documents for word in words)
    for group in groups:
        members=sorted(nodes[i]['id'] for i in group);identity='c-'+sha(encode(members))[:10]
        relevance=collections.Counter()
        for i in group:
            for word in sorted(documents[i]):relevance[word]+=math.log((count+1)/(frequency[word]+1))+1
        labels=[word for word,_ in sorted(relevance.items(),key=lambda item:(-item[1],item[0]))[:4]]
        cluster={'id':identity,'label':' / '.join(labels),'keywords':labels,'members':members,'status':'inferred'};clusters.append(cluster)
        for i in group:membership[i]=identity
    adjacent=[{} for _ in nodes]
    for (a,b),w in weighted.items():adjacent[a][b]=w;adjacent[b][a]=w
    for i,node in enumerate(nodes):
        weights=collections.Counter()
        for j,w in adjacent[i].items():weights[membership[j]]+=w
        total=sum(weights.values());node['cluster']=membership[i]
        node['secondary_clusters']=[c for c,_ in weights.most_common(3) if c!=membership[i]]
        node['bridge_score']=round(1-sum((v/total)**2 for v in weights.values()),6) if total else 0.
    graph=dict(graph,nodes=nodes,edges=edges,clusters=clusters)
    graph['concepts']={'schema':1,'method':VERSION,'model':spec,'records':records,'vectors':embeddings,'input_digest':sha(encode([(r['id'],r['entrypoint_sha256']) for r in records])),'status':'fresh','limitations':['Similarity is not complementarity, applicability or confidence.','Clusters are heuristic; rare links may be missed.','Only bounded entrypoint text was embedded; linked reference bodies were not embedded.']}
    return graph

def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        f.write(encode(value));f.flush();os.fsync(f.fileno());tmp=Path(f.name)
    os.replace(tmp,path)

def wiki(identity, nodes=None):return '[['+identity+('/WORKFLOW' if nodes and nodes[identity].get('kind')=='workflow' else '/SKILL')+']]'

def _export_vault(graph, output, inferred=False):
    import yaml
    output=Path(output)
    if output.exists():raise ValueError('Vault output must be fresh; existing notes are never overwritten')
    output.mkdir(parents=True);nodes={n['id']:n for n in graph['nodes']};copied={};notes={}
    total_bytes=0;total_files=0
    workflow_paths={str(Path(n['path']).resolve()) for n in nodes.values() if n.get('kind')=='workflow'}
    for node in nodes.values():
        parts=Path(node['id']).parts
        if Path(node['id']).is_absolute() or any(p in ('.','..') or any(c in p for c in '#|^:%[]') for p in parts):raise ValueError('Unsafe Obsidian identity')
        source=Path(node['path']).parent.resolve();dest=output/node['id'];dest.mkdir(parents=True)
        workflow=node.get('kind')=='workflow'
        for path in ([Path(node['path'])] if workflow else source.rglob('*.md')):
            if path.is_symlink() or not path.resolve().is_relative_to(source):continue
            if not workflow and str(path.resolve()) in workflow_paths:continue
            raw=bounded(path);total_bytes+=len(raw);total_files+=1
            if total_bytes>128*1024*1024 or total_files>8192:raise ValueError('Vault exceeds file/byte budget')
            target=dest/('WORKFLOW.md' if workflow else path.relative_to(source));target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);copied[str(path.resolve())]=target.relative_to(output).as_posix()
        notes[node['id']]=dest/('WORKFLOW.md' if workflow else 'SKILL.md')
    for identity,path in notes.items():
        source=Path(nodes[identity]['path']);raw=path.read_text();lines=raw.splitlines(keepends=True);end=next(i for i in range(1,len(lines)) if lines[i].strip()=='---');data=yaml.safe_load(''.join(lines[1:end]));body=''.join(lines[end+1:]);relations={'uses':set(),'references':set(),'related':set(),'related-inferred':set(),'used-by':set(),'associated_workflow':set(),'uses_skill':set()}
        for edge in graph['edges']:
            status=edge.get('status','declared');kind=edge['relation']
            if status=='inferred' and not inferred:continue
            if edge['source']==identity:
                field='related-inferred' if status=='inferred' else kind
                if field in relations:relations[field].add(edge['target'])
            if kind=='related' and edge['target']==identity:
                relations['related-inferred' if status=='inferred' else 'related'].add(edge['source'])
            if kind=='uses' and edge['target']==identity:relations['used-by'].add(edge['source'])
        data['workflow-id' if nodes[identity].get('kind')=='workflow' else 'skill-id']=identity
        data['aliases']=list(dict.fromkeys([*(data.get('aliases',[]) if isinstance(data.get('aliases',[]),list) else []),identity]))
        for field,targets in relations.items():
            if targets:
                legacy=[value for value in data.get(field,[]) if isinstance(value,str) and not value.startswith('[[')] if field=='references' else []
                data[field]=legacy+[wiki(target,nodes) for target in sorted(targets)]
        if inferred and nodes[identity].get('cluster'):
            data['topic-clusters']=['[[Topics/'+nodes[identity]['cluster']+']]'];data['topic-map-status']='inferred'
        # Rewrite known cross-skill Markdown links into portable, root-qualified Wikilinks.
        def link(match):
            label,target=match.group(1),match.group(2)
            if '://' in target or target.startswith('#'):return match.group(0)
            raw_target=target.split('#',1)[0];resolved=str((source.parent/raw_target).resolve())
            if resolved in copied:return '[['+copied[resolved].removesuffix('.md')+'|'+label+']]'
            return match.group(0)
        body=re.sub(r'\[([^\]\n]+)\]\(([^\s)]+)\)',link,body)
        body+='\n\n## Skill connections\n\n'
        for field,targets in relations.items():
            if targets:body+='- '+field+': '+', '.join(wiki(target,nodes) for target in sorted(targets))+'.\n'
        if inferred and nodes[identity].get('cluster'):body+='- Inferred topic: [[Topics/'+nodes[identity]['cluster']+']]. Suggested connections require applicability review.\n'
        path.write_text('---\n'+yaml.safe_dump(data,sort_keys=False,allow_unicode=True)+'---\n'+body)
    if inferred:
        (output/'Topics').mkdir()
        for cluster in graph.get('clusters',[]):
            (output/'Topics'/f"{cluster['id']}.md").write_text('---\n'+yaml.safe_dump({'title':cluster['label'],'tags':['topic-map/inferred'],'mapping-status':'inferred','members':[wiki(i,nodes) for i in cluster['members']]},sort_keys=False)+'---\n# '+cluster['label']+'\n\nHeuristic community, not a reviewed taxonomy.\n\n'+'\n'.join('- '+wiki(i,nodes) for i in cluster['members'])+'\n')
    (output/'README.md').write_text('# Skill knowledge graph\n\nOpen this folder as an Obsidian vault. Scoped folders preserve canonical identities; aliases remain metadata. Directed workflow, observed references and inferred related links share one graph. Inferred edges/topics are labeled in properties and notes; Obsidian renders links without relation-specific styling. Disable the inferred export for a declared-only vault. Skill guidance and Markdown reference notes are copied without execution; runtime/scripts/media are not included.\n')
    atomic(output/'manifest.json',{'schema':1,'nodes':len(nodes),'inferred':inferred,'source_digest':sha(encode([(n['id'],n['sha256']) for n in nodes.values()])),'note_paths':{i:str(p.relative_to(output)) for i,p in notes.items()}})
    return {'vault':str(output),'notes':len(nodes),'topic_notes':len(graph.get('clusters',[])) if inferred else 0}

def export_vault(graph, output, inferred=False):
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    # Reserve a fresh destination before work. Stage all notes; failed extraction leaves no partial vault.
    output.mkdir()
    published=[]
    try:
        with tempfile.TemporaryDirectory(prefix='.skill-vault-',dir=output.parent) as temporary:
            staged=Path(temporary)/'vault'
            result=_export_vault(graph,staged,inferred)
            if any(output.iterdir()):raise ValueError('Vault destination changed during export')
            for path in staged.iterdir():
                target=output/path.name
                if target.exists():raise ValueError('Vault destination changed during publication')
                os.rename(path,target);published.append(target)
        result['vault']=str(output)
        return result
    except BaseException:
        for target in published:
            if target.is_dir():shutil.rmtree(target)
            else:target.unlink(missing_ok=True)
        try:output.rmdir()
        except OSError:pass
        raise

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build');b.add_argument('--graph',required=True);b.add_argument('--output',required=True);b.add_argument('--cache',required=True)
    e=sub.add_parser('export');e.add_argument('--graph',required=True);e.add_argument('--output',required=True);e.add_argument('--include-inferred',action='store_true')
    q=sub.add_parser('query');q.add_argument('--graph',required=True);q.add_argument('--query',required=True)
    args=p.parse_args();graph=json.loads(bounded(args.graph,16*1024*1024))
    if args.command=='build':
        records=inputs(graph);values,spec,generated=vectors(records,args.cache);mapped=map_graph(graph,records,values,spec);atomic(args.output,mapped);print(json.dumps({'nodes':len(records),'edges':len(mapped['edges']),'clusters':len(mapped['clusters']),'new_chunks':generated,'output':args.output}))
    elif args.command=='export':print(json.dumps(export_vault(graph,args.output,args.include_inferred)))
    else:
        helper=embedding_helper(); text=' '.join(args.query.split())
        if not text or len(text.encode())>400:raise ValueError('Semantic query requires1–400UTF-8bytes')
        if graph.get('concepts',{}).get('model')!=helper.SPEC:raise ValueError('Rebuild map for current embedding model')
        v=array.array('f');v.frombytes(helper.embed([text],query=True)[0])
        nodes=sorted(graph['nodes'],key=lambda n:n['id']);doc_vectors=graph['concepts']['vectors']
        if len(nodes)!=len(doc_vectors):raise ValueError('Map vector count mismatch')
        print(json.dumps([{'id':n['id'],'score':sum(a*b for a,b in zip(v,w))} for n,w in zip(nodes,doc_vectors)]))
if __name__=='__main__':main()
