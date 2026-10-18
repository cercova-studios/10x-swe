#!/usr/bin/env python3
"""Public catalog acquisition: JSON research request on stdin, evidence JSONL on stdout."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
import sys
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

HOSTS = {'zenml.io', 'www.zenml.io', 'aietalks.com', 'ai.engineer', 'www.ai.engineer'}
STOP = set('ai the and with for from into using how new recent releases research engineering models tools systems'.split())


def tokens(text):
    return set(re.findall(r'[a-z][a-z0-9]{2,}', text.lower())) - STOP


def public_url(url, catalog=False):
    p = urlsplit(url)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.port not in (None, 443) or any(ord(c) < 33 for c in url)
            or (catalog and p.hostname not in HOSTS)):
        raise ValueError('Expected an allowed, credential-free public HTTPS URL')
    return url


def download(url, work):
    public_url(url, True)
    key = hashlib.sha256(url.encode()).hexdigest()
    path = work/(key+'.body')
    meta = work/(key+'.json')
    if path.exists() and meta.exists():
        if path.is_symlink() or meta.is_symlink() or path.stat().st_size > 8*1024*1024 or meta.stat().st_size > 16384:
            raise ValueError('Invalid cached response file')
        raw = path.read_bytes()
        record = json.loads(meta.read_text())
        if record['url'] != url or record['sha256'] != hashlib.sha256(raw).hexdigest():
            raise ValueError('Cached response changed')
        return raw, record
    pending = work/(key+'.pending')
    if pending.exists():
        raise ValueError('Prior acquisition incomplete; inspect it before using a fresh work directory')
    pending.write_text(url)
    def check(target):
        public_url(target, True)
        if any(not ipaddress.ip_address(r[4][0]).is_global for r in socket.getaddrinfo(urlsplit(target).hostname, 443)):
            raise ValueError('Catalog resolved to a non-public address')
    class Redirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            check(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    check(url)
    with build_opener(Redirect()).open(Request(url, headers={'User-Agent': 'public-research/1'}), timeout=40) as response:
        raw = response.read(8*1024*1024+1)
        if len(raw) > 8*1024*1024:
            raise ValueError('Catalog response exceeds 8 MiB')
        raw.decode('utf-8')
        record = {'url': url, 'final_url': response.url, 'sha256': hashlib.sha256(raw).hexdigest(),
                  'retrieved_at': datetime.now(timezone.utc).isoformat()}
    path.write_bytes(raw)
    meta.write_text(json.dumps(record))
    pending.unlink()
    return raw, record


def ranked(rows, topics, limit):
    scored = []
    for row in rows:
        title, summary = tokens(row['title']), tokens(row.get('summary', '')[:500])
        matches = [(3*len(tokens(t['query']) & title)+len(tokens(t['query']) & summary), t['name']) for t in topics]
        score = max((n for n, _ in matches), default=0)
        if score:
            row = dict(row, topics=[name for n, name in matches if n == score])
            scored.append((score, row))
    return [r for _, r in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]


def acquire(source, request, work, limit=3):
    topics = request['topics']
    if (request.get('schema') != 'research-request/v1' or not 1 <= len(topics) <= 24
            or not 1 <= limit <= 6 or any(not isinstance(t['name'], str) or not isinstance(t['query'], str) for t in topics)):
        raise ValueError('Invalid research request or source limit')
    work.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(json.dumps({'request': request, 'source': source, 'limit': limit}, sort_keys=True).encode()).hexdigest()
    owner = work/'request.sha256'
    if owner.exists() and owner.read_text() != fingerprint:
        raise ValueError('Catalog request changed; use a new work directory')
    if not owner.exists():
        if any(work.iterdir()):
            raise ValueError('Refusing to adopt nonempty catalog workspace')
        owner.write_text(fingerprint)
    def get(url):
        raw, metadata = download(url, work)
        return raw.decode(), metadata
    if source == 'zenml':
        text, index = get('https://www.zenml.io/llmops-index.json')
        data = json.loads(text)
        if not isinstance(data, list) or not all(isinstance(r.get('summary'), str) and isinstance(r.get('link'), str) for r in data):
            raise ValueError('ZenML catalog schema changed')
        rows = []
        for r in data:
            try:
                original = public_url(r['link'])
            except ValueError:
                continue
            rows.append({'title': r['title'], 'summary': r['summary'], 'original_url': original,
                         'url': 'https://www.zenml.io/llmops-database/'+r['slug'],
                         'added_at': r.get('addedAt'), 'reported_year': r.get('year')})
    elif source == 'aietalks':
        text, index = get('https://aietalks.com/llms.txt')
        rows = [{'title': m[1], 'url': m[2], 'summary': m[3]} for m in
                re.finditer(r'^- \[([^\n]+)\]\((https://aietalks.com/talks/[a-z0-9-]+)\): ([^\n]+)', text, re.M)]
        if not rows:
            raise ValueError('AIETalks catalog schema changed')
    else:
        text, index = get('https://ai.engineer/api/data/talks?format=json')
        data = json.loads(text)
        if not isinstance(data, list) or not all(isinstance(r.get('videoId'), str) and re.fullmatch(r'[A-Za-z0-9_-]{11}', r['videoId']) and isinstance(r.get('slug'), str) for r in data):
            raise ValueError('AI Engineer catalog schema changed')
        rows = [{'title': r['title'], 'summary': r.get('summary') or '', 'slug': r['slug'],
                 'url': public_url(r['url'], True), 'original_url': 'https://www.youtube.com/watch?v='+r['videoId'],
                 'video_id': r['videoId']} for r in data]
        text, _ = get('https://ai.engineer/api/data/transcripts?format=json')
        transcript_index = json.loads(text)
        if not isinstance(transcript_index, list):
            raise ValueError('AI Engineer transcript index schema changed')
        available = {r['talkSlug']: public_url(r['jsonUrl'], True) for r in transcript_index}
        rows = [r for r in rows if r['slug'] in available]
    selected = ranked(rows, topics, limit)
    records = []
    for row in selected:
        content, evidence, published, segments = row['summary'], index, None, []
        coverage = 'secondary curated summary'
        if source == 'aietalks':
            content, evidence = get(row['url']+'.md')
            original = re.search(r'^Source: (https://www.youtube.com/watch\?v=([A-Za-z0-9_-]{11}))\s*$', content, re.M)
            publication = re.search(r'^Published: (\d{4}-\d{2}-\d{2})\s*$', content, re.M)
            if not original:
                raise ValueError('AIETalks recording identity missing')
            row.update(original_url=original[1], video_id=original[2])
            if publication:
                published = date.fromisoformat(publication[1]).isoformat()
            coverage = 'secondary AIETalks write-up; not a transcript'
        elif source == 'ai-engineer':
            text, evidence = get(available[row['slug']])
            segments = json.loads(text)
            if (not isinstance(segments, list) or not segments
                    or any(type(s.get('startMs')) is not int or s['startMs'] < 0 or not isinstance(s.get('text'), str) for s in segments)):
                raise ValueError('AI Engineer transcript schema changed')
            # Retain whole timestamped passages; truncate only at passage boundaries.
            retained, size = [], 0
            for segment in segments:
                if size+len(segment['text']) > 6000:
                    break
                retained.append({'startMs': segment['startMs'], 'text': segment['text'],
                                 'citation_url': row['original_url']+'&t='+str(segment['startMs']//1000)})
                size += len(segment['text'])
            if not retained:
                raise ValueError('First transcript passage exceeds evidence budget')
            content = '\n\n'.join(s['text'] for s in retained)
            segments = retained
            coverage = 'official automated transcript; selected opening passages; visuals uninspected'
        records.append({'schema': 'research-source/v1', 'provider': source, 'url': row['url'],
                        'title': row['title'], 'original_url': row['original_url'], 'topics': row['topics'],
                        'published_at': published, 'retrieved_at': evidence['retrieved_at'],
                        'content': content[:6000] if source != 'ai-engineer' else content, 'coverage': coverage,
                        'evidence_kind': 'primary-transcript' if source == 'ai-engineer' else 'secondary-summary',
                        'provenance': [{'provider': source, 'catalog_url': index['url'], 'catalog_sha256': index['sha256'],
                                        'evidence_url': evidence['url'], 'evidence_sha256': evidence['sha256'],
                                        'publication_date_basis': 'AIETalks Published field' if published else 'unknown',
                                        'published_at': published,
                                        'catalog_added_at': row.get('added_at'), 'reported_year': row.get('reported_year'),
                                        'video_id': row.get('video_id'), 'segments': segments}]})
    records.append({'schema': 'research-coverage/v1', 'provider': source, 'results': len(rows),
                    'selected': len(selected), 'warning': 'Bounded lexical metadata discovery; not exhaustive. Missing dates remain unknown.'})
    return records


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', choices=['zenml', 'aietalks', 'ai-engineer'])
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--limit', type=int, default=3)
    a = p.parse_args()
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError('Research request exceeds 64 KiB')
        records = acquire(a.source, json.loads(raw), a.work, a.limit)
        sys.stdout.write(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records))
    except (ValueError, KeyError, TypeError, OSError) as e:
        print('ERROR: '+str(e), file=sys.stderr)
        sys.exit(1)
