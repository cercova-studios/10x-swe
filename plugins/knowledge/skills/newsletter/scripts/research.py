#!/usr/bin/env python3
"""Freeze bounded public research using a caller-selected search command."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import fcntl
import ipaddress
import json
from pathlib import Path
import socket
import subprocess
import sys
import urllib.parse
import urllib.request


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    tmp.replace(path)


def admitted(url, domains):
    p = urllib.parse.urlsplit(url)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.port not in (None, 443) or any(ord(c) < 33 for c in url)):
        raise ValueError('Source must be a public HTTPS URL without credentials')
    if not any(p.hostname == d or p.hostname.endswith('.' + d) for d in domains):
        raise ValueError('Source domain outside configured public corpus')
    return url


def fetch(url, domains):
    def check(url):
        admitted(url, domains)
        for row in socket.getaddrinfo(urllib.parse.urlsplit(url).hostname, 443):
            if not ipaddress.ip_address(row[4][0]).is_global:
                raise ValueError('Source resolved to a non-public address')
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            check(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    check(url)
    req = urllib.request.Request(url, headers={'User-Agent': 'personal-newsletter/1'})
    with urllib.request.build_opener(Redirect()).open(req, timeout=20) as response:
        if response.headers.get_content_type() not in ('text/html', 'application/xhtml+xml'):
            raise ValueError('Not an HTML source; excerpt coverage retained')
        raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('Source exceeds 4 MiB')
        raw.decode('utf-8')
        return raw, response.url


def collect(config, work):
    max_sources = config.get('max_sources', 48)
    source_chars = config.get('source_chars', 6000)
    extracted_chars = config.get('extracted_chars', 12000)
    if (not 1 <= len(config['topics']) <= 24 or not 8 <= max_sources <= 60
            or not 1000 <= source_chars <= 6000 or not 1000 <= extracted_chars <= 12000):
        raise ValueError('Research topics or source bounds outside supported limits')
    work.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    target = work/'research.json'
    if target.exists():
        old = json.loads(target.read_text())
        if old['config_sha256'] != fingerprint:
            raise ValueError('Research configuration changed; use a new work directory')
        return old
    window = work/'window.json'
    if not window.exists():
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=config.get('lookback_hours', 72))
        save(window, {'config_sha256': fingerprint, 'start': start.isoformat(), 'end': end.isoformat()})
    state = json.loads(window.read_text())
    if state['config_sha256'] != fingerprint:
        raise ValueError('Research configuration changed during recovery')
    start, end = datetime.fromisoformat(state['start']), datetime.fromisoformat(state['end'])
    command = [arg.replace('{window_start_date}', start.date().isoformat()) for arg in config['search_command']]
    supplemental, evidence_coverage = evidence_inputs(config, work, start, end)
    sources, coverage = {}, []
    for index, topic in enumerate(config['topics']):
        raw_path = work/f'search-{index}.json'
        query = (f"{topic['query']}. Primary sources published {start.date()} through {end.date()}. "
                 'Prefer official announcements, papers, source repositories and technical engineering blogs.')
        if not raw_path.exists():
            result = subprocess.run([*command, query], capture_output=True, timeout=150)
            if len(result.stdout) > 5 * 1024 * 1024:
                raise ValueError('Search response exceeds 5 MiB')
            parsed = json.loads(result.stdout)
            save(raw_path, {'query': query, 'retrieved_at': now(), 'response': parsed, 'exit_code': result.returncode})
        saved = json.loads(raw_path.read_text())
        if saved.get('exit_code', 0):
            raise RuntimeError(f'Search failed for topic {index}; saved partial response retained; no automatic retry')
        for provider, envelope in saved['response'].items():
            if envelope.get('error'):
                raise RuntimeError(f'{provider} search failed; use a fresh successful response')
            native = envelope['response']
            rows = native.get('results', [])
            coverage.append({'topic': topic['name'], 'provider': provider,
                             'results': len(rows), 'request_id': native.get('requestId') or native.get('search_id'),
                             'warnings': native.get('warnings')})
            accepted = 0
            for row in rows:
                url = row.get('url', '')
                try:
                    admitted(url, config['domains'])
                except ValueError:
                    continue
                if accepted >= config.get('sources_per_topic_provider', 3):
                    break
                sid = hashlib.sha256(url.encode()).hexdigest()[:16]
                excerpts = row.get('highlights') or row.get('excerpts') or []
                if isinstance(excerpts, str):
                    excerpts = [excerpts]
                content = '\n\n'.join(excerpts)[:source_chars]
                if not content.strip():
                    continue
                accepted += 1
                if sid in sources:
                    sources[sid]['topics'] = sorted(set(sources[sid]['topics'] + [topic['name']]))
                    continue
                sources[sid] = {'id': sid, 'url': url, 'title': row.get('title') or url,
                                'published_at': row.get('publishedDate') or row.get('publish_date'),
                                'retrieved_at': saved['retrieved_at'], 'topics': [topic['name']],
                                'content': content, 'coverage': 'search excerpts', 'provider': provider}
    # Give later topics a first source before earlier topics consume the source budget.
    sources = balanced_sources(sources, config['topics'], max_sources-len(supplemental))
    for sid, source in supplemental.items():
        if sid in sources:
            sources[sid]['topics'] = sorted(set(sources[sid]['topics']+source['topics']))
            sources[sid].setdefault('provenance', []).extend(source['provenance'])
            if source['evidence_kind'] == 'primary-transcript':
                sources[sid] = dict(source, topics=sources[sid]['topics'], provenance=sources[sid]['provenance'])
        else:
            sources[sid] = source
    for row in coverage:
        row['retained_sources'] = sum(row['topic'] in s['topics'] and row['provider'] == s['provider'] for s in sources.values())
    coverage.extend(evidence_coverage)
    # A bounded selection gets original snapshots and an independent extractor.
    enriched = 0
    attempted = 0
    for sid, source in sources.items():
        if source.get('provenance'):
            continue  # Explicit evidence producers own their extraction and coverage labels.
        if attempted >= config.get('max_original_pages', 8):
            break
        attempted += 1
        html_path, extracted = work/f'{sid}.html', work/f'{sid}.extraction.json'
        try:
            if not extracted.exists():
                raw, final = fetch(source['url'], config['domains'])
                html_path.write_bytes(raw)
                r = subprocess.run([config['distiller'], '--stdin', '--base-url', source['url'], '--mode', 'json'],
                                   input=raw, capture_output=True, timeout=45)
                if r.returncode:
                    raise RuntimeError('HTML extractor failed')
                record = json.loads(r.stdout)
                if record['source']['sha256'] != hashlib.sha256(raw).hexdigest():
                    raise ValueError('Extractor input hash mismatch')
                save(extracted, {'final_url': final, 'record': record})
            data = json.loads(extracted.read_text())
            text = data['record']['document']['markdown']
            source.update(content=text[:extracted_chars], coverage='extracted HTML; bounded text' if len(text) > extracted_chars else 'extracted HTML',
                          final_url=data['final_url'], snapshot_sha256=data['record']['source']['sha256'])
            enriched += 1
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
            source['extraction_warning'] = type(error).__name__ + ': original-page extraction unavailable; excerpts only'
    result = {'schema': 'newsletter-research/v1', 'config_sha256': fingerprint,
              'window_start': start.isoformat(), 'window_end': end.isoformat(),
              'created_at': now(), 'topics': [t['name'] for t in config['topics']],
              'coverage': coverage, 'sources': list(sources.values()),
              'coverage_notes': config.get('coverage_notes', []),
              'limits': {'search_requests': len(config['topics']) * len(config.get('providers', [])),
                         'original_pages': enriched, 'original_page_attempt_limit': config.get('max_original_pages', 8),
                         'retained_source_limit': max_sources, 'source_chars': source_chars, 'extracted_chars': extracted_chars}}
    if len(result['sources']) < 8 or len({t for s in result['sources'] for t in s['topics']}) < 3:
        raise ValueError('Insufficient source/topic coverage; refusing an empty edition')
    save(target, result)
    return result


def evidence_inputs(config, work, start, end):
    """Invoke independent producers; accept only explicit versioned evidence records."""
    commands = config.get('evidence_commands', [])
    if not isinstance(commands, list) or len(commands) > 6:
        raise ValueError('Evidence command count outside bounds')
    request = {'schema': 'research-request/v1', 'topics': config['topics'],
               'window_start': start.isoformat(), 'window_end': end.isoformat()}
    sources, coverage = {}, []
    for index, command in enumerate(commands):
        if not isinstance(command, list) or not command or not all(isinstance(a, str) for a in command):
            raise ValueError('Evidence command must be an argument list')
        path = work/f'evidence-{index}.json'
        if not path.exists():
            args = [a.replace('{work}', str((work/f'producer-{index}').resolve())) for a in command]
            result = subprocess.run(args, input=json.dumps(request).encode(), capture_output=True, timeout=300)
            (work/f'evidence-{index}.stderr.log').write_bytes(result.stderr or b'')
            if len(result.stdout) > 1024*1024:
                raise ValueError('Evidence response exceeds 1 MiB')
            save(path, {'exit_code': result.returncode, 'records': [json.loads(line) for line in result.stdout.splitlines() if line.strip()]})
        saved = json.loads(path.read_text())
        if saved['exit_code']:
            raise RuntimeError(f'Evidence command {index} failed; inspect producer workspace; no automatic retry')
        for row in saved['records']:
            if row.get('schema') == 'research-coverage/v1':
                coverage.append({**row, 'topic': 'Catalog discovery', 'retained_sources': row.get('selected', 0)})
                continue
            if row.get('schema') != 'research-source/v1':
                raise ValueError('Expected research-source/v1 or research-coverage/v1')
            if any(not isinstance(row.get(k), str) for k in ('url', 'title', 'provider', 'coverage', 'retrieved_at')):
                raise ValueError('Evidence metadata must be text')
            admitted(row['url'], config['domains'])
            original = row.get('original_url', row['url'])
            admitted(original, [urllib.parse.urlsplit(original).hostname or ''])
            if (not isinstance(row.get('content'), str) or not row['content'].strip() or len(row['content']) > 8000
                    or row.get('evidence_kind') not in ('secondary-summary', 'primary-transcript')
                    or not isinstance(row.get('provenance'), list) or not row['provenance']
                    or not isinstance(row.get('topics'), list) or not row['topics']
                    or not all(isinstance(t, str) for t in row['topics'])
                    or not set(row['topics']) <= {t['name'] for t in config['topics']}):
                raise ValueError('Invalid evidence content, provenance or topics')
            for origin in row['provenance']:
                if not isinstance(origin, dict) or any(not isinstance(origin.get(k), str) for k in ('provider', 'catalog_url', 'evidence_url')):
                    raise ValueError('Invalid evidence provenance')
                links = [origin['catalog_url'], origin['evidence_url']]
                segments = origin.get('segments', [])
                if not isinstance(segments, list):
                    raise ValueError('Invalid transcript segments')
                for segment in segments:
                    if (not isinstance(segment, dict) or type(segment.get('startMs')) is not int or segment['startMs'] < 0
                            or not isinstance(segment.get('text'), str) or not isinstance(segment.get('citation_url'), str)):
                        raise ValueError('Invalid transcript segment')
                    links.append(segment['citation_url'])
                for link in links:
                    admitted(link, [urllib.parse.urlsplit(link).hostname or ''])
            if row.get('published_at'):
                datetime.fromisoformat(row['published_at'].replace('Z', '+00:00'))
            sid = hashlib.sha256(original.encode()).hexdigest()[:16]
            if sid in sources:
                old = sources[sid]
                old['topics'] = sorted(set(old['topics']+row['topics']))
                old['provenance'].extend(row['provenance'])
                if row['evidence_kind'] == 'primary-transcript':
                    # One recording is one source; primary transcript replaces a secondary write-up.
                    sources[sid] = dict(row, id=sid, topics=old['topics'], provenance=old['provenance'],
                                        published_at=row.get('published_at') or old.get('published_at'))
            else:
                sources[sid] = dict(row, id=sid)
    if len(sources) > config.get('max_sources', 48)-8:
        raise ValueError('Evidence inputs leave insufficient web-source budget')
    return sources, coverage


def balanced_sources(sources, topics, limit):
    groups = [[sid for sid, source in sources.items() if topic['name'] in source['topics']] for topic in topics]
    selected = {}
    for rank in range(max(map(len, groups), default=0)):
        for group in groups:
            if rank < len(group):
                sid = group[rank]
                selected[sid] = sources[sid]
                if len(selected) == limit:
                    return selected
    return selected


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    a = p.parse_args()
    try:
        a.work.mkdir(parents=True, exist_ok=True)
        with (a.work/'.research.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(json.dumps(collect(json.loads(a.config.read_text()), a.work), ensure_ascii=False))
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
