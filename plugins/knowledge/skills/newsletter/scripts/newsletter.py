#!/usr/bin/env python3
"""Local newsletter publication, reader rendering and manifest-bound retention."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

ASSETS = Path(__file__).resolve().parent.parent/'assets'
FILES = ('issue.json', 'research.json', 'editorial-review.json', 'issue.md', 'issue.html')
PROSE = ('summary', 'technical_detail', 'why_it_matters', 'relevance', 'limitations')
REFERENCE = re.compile(r'\[([^\]\n]+)\]')
# Extraction debris: a passage that runs past a blank line into a section heading supports no claim.
# Level-one '#' lines are left alone because code comments use the same marker.
TRAILING_HEADING = re.compile(r'\n\s*\n {0,3}#{2,6}\s[^\n]*\s*$')


def resolve(inside, numbers):
    """Bracketed source IDs as ascending reference numbers, or None for ordinary bracketed text."""
    found = [numbers.get(part.strip()) for part in re.split('[;,]', inside)]
    return sorted(set(found)) if all(found) else None


def checksum(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('Expected a bounded regular JSON file')
    return json.loads(path.read_text())


def atomic(path, raw):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Refusing a symlink destination')
    fd, name = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path, value):
    atomic(path, json.dumps(value, ensure_ascii=False, indent=2).encode())


def store(root, create=True):
    root = Path(root).expanduser().absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('Newsletter root must not pass through a symlink')
    if create:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = root/'.newsletter-store.json'
    if not marker.exists():
        if not create:
            raise ValueError('Expected an owned newsletter directory')
        if any(root.iterdir()):
            raise ValueError('Refusing to adopt a nonempty unowned newsletter directory')
        write_json(marker, {'schema': 'newsletter-store/v1', 'id': str(uuid.uuid4())})
    identity = read(marker)
    if identity.get('schema') != 'newsletter-store/v1' or not isinstance(identity.get('id'), str):
        raise ValueError('Invalid newsletter ownership marker')
    for name in ('issues', '.work'):
        path = root/name
        if path.is_symlink():
            raise ValueError('Refusing a symlink store directory')
        if create:
            path.mkdir(exist_ok=True, mode=0o700)
        elif not path.is_dir():
            raise ValueError('Incomplete newsletter store')
    return root, identity['id']


@contextmanager
def locked(root):
    fd = os.open(root/'.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def validate(issue, research, review):
    if research.get('schema') != 'newsletter-research/v1' or not isinstance(research.get('sources'), list):
        raise ValueError('Expected newsletter-research/v1')
    sources = {s['id']: s for s in research['sources']}
    if len(sources) > 60 or sum(len(s['content']) for s in sources.values()) > 400000 or len(json.dumps(issue)) > 150000:
        raise ValueError('Edition exceeds source or editorial size bounds')
    if len(sources) != len(research['sources']):
        raise ValueError('Duplicate source identities')
    for source in sources.values():
        p = urlsplit(source['url'])
        if p.scheme != 'https' or not p.hostname or p.username or p.password:
            raise ValueError('Citations require credential-free HTTPS source URLs')
        if not isinstance(source['content'], str):
            raise ValueError('Source content must be text')
    for field in ('title', 'standfirst', 'editorial'):
        if not isinstance(issue.get(field), str) or not issue[field].strip() or len(issue[field]) > 12000:
            raise ValueError('Missing or oversized editorial text')
    stories = issue.get('stories')
    if not isinstance(stories, list) or not 6 <= len(stories) <= 32:
        raise ValueError('An edition needs 6–32 evidence-backed stories')
    ids, topics, deep = set(), set(), 0
    for story in stories:
        sid = story.get('id', '')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', sid) or sid in ids or len(sid) > 100:
            raise ValueError('Story IDs must be distinct short slugs')
        ids.add(sid)
        if story.get('topic') not in research['topics']:
            raise ValueError('Unknown topic')
        topics.add(story['topic'])
        for field in ('headline', 'summary', 'technical_detail', 'why_it_matters', 'relevance', 'limitations'):
            if not isinstance(story.get(field), str) or not story[field].strip() or len(story[field]) > 16000:
                raise ValueError('Story fields must be bounded nonempty text')
        if story.get('kind') not in ('deep_dive', 'brief'):
            raise ValueError('Unknown story kind')
        if story['kind'] == 'deep_dive':
            deep += 1
            if len(story['technical_detail'].split()) < 180:
                raise ValueError('Deep dives require substantive technical detail')
        elif len(story['summary'].split()) > 100:
            raise ValueError('Brief summaries must fit within 100 words')
        if story.get('event_date'):
            datetime.strptime(story['event_date'], '%Y-%m-%d')
        citations = story.get('citations')
        if not isinstance(citations, list) or not citations:
            raise ValueError('Every story needs evidence')
        for citation in citations:
            source = sources.get(citation.get('source_id'))
            quote = citation.get('quote')
            if not source or not isinstance(quote, str) or not 40 <= len(quote) <= 400:
                raise ValueError('Missing source or bounded exact quotation')
            if quote not in source['content']:
                raise ValueError('Quotation not present in frozen source text')
            if TRAILING_HEADING.search(quote):
                raise ValueError('Quotation runs into an extracted heading; choose a clean passage')
    if deep < 2 or len(topics) < 3:
        raise ValueError('Need two deep dives and at least three topic categories')
    if review.get('approved') is not True or review.get('problems') != []:
        raise ValueError('Editorial review has not approved the issue')
    if (review.get('schema') != 'newsletter-review/v1'
            or review.get('issue_sha256') != checksum(json.dumps(issue, ensure_ascii=False, sort_keys=True).encode())
            or review.get('research_sha256') != checksum(json.dumps(research, ensure_ascii=False, sort_keys=True).encode())):
        raise ValueError('Editorial approval does not match this issue and research revision')
    return sources


def reading(issue, research):
    """One presentation order and source identity for HTML and Markdown."""
    sources = {s['id']: s for s in research['sources']}
    start, end = (datetime.fromisoformat(research[k]) for k in ('window_start', 'window_end'))
    current, background = [], []
    for story in issue['stories']:
        date = story.get('event_date', '')
        timely = bool(date and start.date().isoformat() < date <= end.date().isoformat())
        # A date-only item on the opening day cannot establish freshness by itself.
        if date == start.date().isoformat():
            for citation in story['citations']:
                published = sources[citation['source_id']].get('published_at')
                if published:
                    timestamp = datetime.fromisoformat(published.replace('Z', '+00:00'))
                    if timestamp.tzinfo and timestamp.date().isoformat() == date and start <= timestamp <= end:
                        timely = True
        (current if timely else background).append(story)
    ordered = current + [s for s in background if s['kind'] == 'deep_dive'] + [s for s in background if s['kind'] == 'brief']
    references, by_url, numbers = [], {}, {}
    for story in ordered:
        for citation in story['citations']:
            source = sources[citation['source_id']]
            if source['url'] not in by_url:
                by_url[source['url']] = len(references) + 1
                references.append({**source, 'number': len(references) + 1})
            numbers[source['id']] = by_url[source['url']]
    texts = [issue['standfirst'], issue['editorial'], *(s[f] for s in ordered for f in PROSE)]
    referenced = {part.strip() for text in texts for match in REFERENCE.findall(text)
                  for part in re.split('[;,]', match)}
    for source in research['sources']:
        if source['id'] not in numbers:
            if source['id'] in referenced and source['url'] not in by_url:
                by_url[source['url']] = len(references) + 1
                references.append({**source, 'number': len(references) + 1})
            numbers[source['id']] = by_url.get(source['url'])
    for source in references:
        # LaTeXML can leak internal control sequences into a page's own title.
        if '\\__' in source['title']:
            source['title'] = source['url']
    return {'current': current, 'background': background, 'references': references, 'numbers': numbers}


def markdown(issue, research):
    view = reading(issue, research)
    sources = {s['id']: s for s in research['sources']}
    numbers = view['numbers']
    def linked(refs):
        return '['+'; '.join(f'[{x}](#source-{x})' for x in refs)+']'
    def prose(text):
        return REFERENCE.sub(lambda match: linked(refs) if (refs := resolve(match[1], numbers)) else match[0], text)
    text = [f"# {prose(issue['title'])}", prose(issue['standfirst']),
            f"{len(view['current'])} current stories · {len(view['background'])} background reads",
            '## Today in 60 seconds' if view['current'] else '## Reading shortlist']
    shortlist = view['current'] or view['background']
    text += [f"- [{prose(s['headline'])}](#{s['id']})" for s in shortlist[:6]]
    text += ['## The thread', prose(issue['editorial'])]
    for label, stories in [('Current news', view['current']),
                           ('Background analysis', [s for s in view['background'] if s['kind'] == 'deep_dive']),
                           ('Also worth reading · earlier or undated', [s for s in view['background'] if s['kind'] == 'brief'])]:
        if not stories:
            continue
        text.append(f'## {label}')
        for story in stories:
            shown = PROSE if story['kind'] == 'deep_dive' else ('summary', 'limitations')
            inline = {x for field in shown for match in REFERENCE.findall(story[field])
                      for x in resolve(match, numbers) or []}
            # Cited sources without an inline reference keep one visible link row.
            missing = sorted({numbers[c['source_id']] for c in story['citations']} - inline)
            text += [f'<a id="{story["id"]}"></a>', f"### {prose(story['headline'])}",
                     f"{story['topic']} · {story.get('event_date') or 'Date unconfirmed'}", prose(story['summary'])]
            if story['kind'] == 'deep_dive':
                for heading, field in [('Under the hood', 'technical_detail'), ('Why it matters', 'why_it_matters'),
                                       ('For your work', 'relevance'), ('Limits & unknowns', 'limitations')]:
                    text += [f'#### {heading}', prose(story[field])]
            elif story['limitations']:
                text.append(prose(story['limitations']))
            if missing:
                text.append('Sources: '+linked(missing))
    text += ['## Sources & evidence', '<details>', '<summary>Open source notes and exact supporting passages</summary>']
    for source in view['references']:
        number = source['number']
        text += [f'<a id="source-{number}"></a>', f"### [{number}: {source['title']}]({source['url']})",
                 f"{source.get('published_at') or 'Date unconfirmed'} · {source['coverage']}"]
        quotes = dict.fromkeys(c['quote'] for s in issue['stories'] for c in s['citations']
                              if sources[c['source_id']]['url'] == source['url'])
        for quote in quotes:
            text.append('\n'.join('  > '+line for line in quote.splitlines()))
    text.append('</details>')
    text += ['---', f"Research window: {research['window_start']} to {research['window_end']}. "
             'This newsletter is an editorial synthesis. Source claims and implications need independent evaluation before use.']
    return '\n\n'.join(text)+'\n'


def page(editions):
    editions = [{**edition, 'reading': reading(edition['issue'], edition['research'])} for edition in editions]
    data = json.dumps(editions, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (ASSETS/'reader.html').read_text()
    return template.replace('<!--STYLE-->', (ASSETS/'reader.css').read_text()).replace('/*DATA*/', data).replace('/*SCRIPT*/', (ASSETS/'reader.js').read_text())


def checked_entry(path, owner):
    if path.is_symlink() or not path.is_dir():
        raise ValueError('Edition must be a real directory')
    manifest = read(path/'manifest.json')
    if manifest.get('schema') != 'newsletter-edition/v1' or manifest.get('store_id') != owner:
        raise ValueError('Unowned edition; refusing mutation')
    if set(manifest.get('files', {})) != set(FILES) or {p.name for p in path.iterdir()} != {*FILES, 'manifest.json'}:
        raise ValueError('Edition file inventory changed; refusing mutation')
    for name, digest in manifest['files'].items():
        file = path/name
        if file.is_symlink() or not file.is_file() or checksum(file.read_bytes()) != digest:
            raise ValueError('Edition evidence changed; refusing mutation')
    timestamp = datetime.fromisoformat(manifest['published_at'])
    if timestamp.tzinfo is None:
        raise ValueError('Publication time must include timezone')
    return manifest


def refresh(root, owner):
    editions = []
    for path in sorted((root/'issues').iterdir(), reverse=True):
        if path.name.startswith('.'):
            continue
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', path.name):
            continue
        manifest = checked_entry(path, owner)
        issue, research = read(path/'issue.json'), read(path/'research.json')
        editions.append({'date': path.name, 'issue': issue, 'research': research,
                         'published_at': manifest['published_at'], 'markdown': f"issues/{path.name}/issue.md"})
    atomic(root/'index.html', page(editions).encode())
    atomic(root/'latest.md', (markdown(editions[0]['issue'], editions[0]['research']) if editions else '# Fieldnotes / AI\n\nNo editions in the current archive.\n').encode())


def publish(root, work, date=None, at=None):
    root, owner = store(root)
    with locked(root):
        issue, research, review = (read(work/n) for n in ('issue.json', 'research.json', 'editorial-review.json'))
        validate(issue, research, review)
        date = date or datetime.fromisoformat(research['window_end']).astimezone(ZoneInfo('America/Detroit')).date().isoformat()
        datetime.strptime(date, '%Y-%m-%d')
        destination = root/'issues'/date
        inputs = {n: (work/n).read_bytes() for n in ('issue.json', 'research.json', 'editorial-review.json')}
        if destination.exists():
            old = checked_entry(destination, owner)
            if any(old['files'][n] != checksum(raw) for n, raw in inputs.items()):
                raise ValueError('An edition already exists for this date with different evidence')
            refresh(root, owner)
            return destination
        stage = Path(tempfile.mkdtemp(prefix='.stage-', dir=root/'issues'))
        try:
            for name, raw in inputs.items():
                atomic(stage/name, raw)
            atomic(stage/'issue.md', markdown(issue, research).encode())
            edition = {'date': date, 'issue': issue, 'research': research,
                       'published_at': at or datetime.now(timezone.utc).isoformat(), 'markdown': 'issue.md'}
            atomic(stage/'issue.html', page([edition]).encode())
            write_json(stage/'manifest.json', {'schema': 'newsletter-edition/v1', 'store_id': owner,
                       'published_at': edition['published_at'], 'files': {n: checksum((stage/n).read_bytes()) for n in FILES}})
            stage.rename(destination)
            fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        refresh(root, owner)
        return destination


def cleanup(root, apply=False, at=None):
    root, owner = store(root, create=False)
    cutoff = (at or datetime.now(timezone.utc)) - timedelta(days=7)
    with locked(root):
        journal = root/'.retention.json'
        if journal.exists():
            if not apply:
                return {'apply': False, 'pending': read(journal)}
            resume_retention(root, owner, journal)
        targets = []
        for path in sorted((root/'issues').iterdir()):
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', path.name):
                manifest = checked_entry(path, owner)
                if datetime.fromisoformat(manifest['published_at']) < cutoff:
                    targets.append(path)
        works = []
        for path in (root/'.work').iterdir():
            marker = path/'.newsletter-work.json'
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', path.name):
                continue
            if path.is_symlink():
                raise ValueError('Refusing symlink work directory')
            if not marker.exists():
                continue
            info = read(marker)
            if info.get('store_id') != owner or info.get('schema') != 'newsletter-work/v1':
                raise ValueError('Work ownership mismatch')
            if datetime.fromisoformat(info['created_at']) < cutoff:
                if any(p.is_symlink() for p in path.rglob('*')):
                    raise ValueError('Refusing symlink within expired work')
                works.append(path)
        if apply:
            records = [{'parent': p.parent.name, 'name': p.name, 'trash': '.expired-'+uuid.uuid4().hex}
                       for p in [*targets, *works]]
            write_json(journal, {'schema': 'newsletter-retention/v1', 'store_id': owner, 'paths': records})
            resume_retention(root, owner, journal)
        return {'apply': apply, 'cutoff': cutoff.isoformat(), 'editions': [p.name for p in targets],
                'work_directories': [p.name for p in works]}


def resume_retention(root, owner, journal):
    state = read(journal)
    if state.get('schema') != 'newsletter-retention/v1' or state.get('store_id') != owner:
        raise ValueError('Retention journal ownership mismatch')
    pairs = []
    for row in state['paths']:
        if (row['parent'] not in ('issues', '.work') or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', row['name'])
                or not re.fullmatch(r'\.expired-[a-f0-9]{32}', row['trash'])):
            raise ValueError('Unsafe retention journal path')
        source, trash = root/row['parent']/row['name'], root/row['parent']/row['trash']
        for path in (source, trash):
            if path.is_symlink() or path.exists() and any(p.is_symlink() for p in path.rglob('*')):
                raise ValueError('Refusing a symlink retention target')
        if source.exists() and trash.exists():
            raise ValueError('Ambiguous retention transaction')
        pairs.append((source, trash))
    for source, trash in pairs:
        if source.exists():
            source.rename(trash)
    refresh(root, owner)
    for source, trash in pairs:
        if trash.exists():
            shutil.rmtree(trash)
    journal.unlink()


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['collect', 'draft', 'review', 'validate', 'publish', 'cleanup', 'refresh'])
    p.add_argument('--root', type=Path, default=Path(os.environ.get('NEWSLETTER_ROOT', '~/.agents/newsletters')).expanduser())
    p.add_argument('--work', type=Path)
    p.add_argument('--config', type=Path, default=Path(os.environ.get('NEWSLETTER_CONFIG', 'newsletter.json')))
    p.add_argument('--apply', action='store_true', help='Apply seven-day cleanup; default is dry run')
    a = p.parse_args()
    a.config = a.config.expanduser()
    if a.stage == 'cleanup':
        print(json.dumps(cleanup(a.root, a.apply)))
        return
    root, owner = store(a.root)
    today = datetime.now(ZoneInfo('America/Detroit')).date().isoformat()
    work = a.work or (Path(os.environ['NEWSLETTER_WORK']) if os.environ.get('NEWSLETTER_WORK') else
                     root/'.work'/today)
    work = work.expanduser()
    completed = root/'issues'/today
    if not a.work and not os.environ.get('NEWSLETTER_WORK') and completed.exists():
        checked_entry(completed, owner)
        work = completed
        if a.stage in ('collect', 'draft', 'review'):
            print(f'Edition already published; reusing {completed}')
            return
    if a.stage in ('collect', 'draft', 'review'):
        work.mkdir(parents=True, exist_ok=True)
        if work.is_symlink():
            raise ValueError('Refusing symlink work directory')
        if work.parent == root/'.work':
            marker = work/'.newsletter-work.json'
            if not marker.exists():
                write_json(marker, {'schema': 'newsletter-work/v1', 'store_id': owner,
                                   'created_at': datetime.now(timezone.utc).isoformat()})
            elif read(marker).get('store_id') != owner:
                raise ValueError('Work ownership mismatch')
        if a.stage == 'collect':
            command = [sys.executable, str(Path(__file__).with_name('research.py')), '--config', str(a.config.resolve()), '--work', str(work.resolve())]
        else:
            command = [sys.executable, str(Path(__file__).with_name('draft.py')), a.stage, '--work', str(work.resolve())]
        result = subprocess.run(command, stdout=subprocess.DEVNULL, timeout=1200)
        if result.returncode:
            raise RuntimeError(f'{a.stage} failed; retained work: {work}')
        print(work)
    elif a.stage == 'validate':
        validate(read(work/'issue.json'), read(work/'research.json'), read(work/'editorial-review.json'))
        print(json.dumps({'status': 'valid', 'meaning': 'Local newsletter gate; no insight publication'}))
    elif a.stage == 'publish':
        print(publish(root, work))
    elif a.stage == 'cleanup':
        print(json.dumps(cleanup(root, a.apply)))
    else:
        with locked(root):
            refresh(root, owner)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
