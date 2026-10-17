#!/usr/bin/env python3
"""Prepare source evidence and publish agent-written insights; stdlib only."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
import re
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen, Request

ROOT = Path(os.environ.get('AGENT_KNOWLEDGE_HOME', Path.home() / '.agents'))
sys.path.insert(0, str(ROOT / 'lib'))
LIBRARY = Path(os.environ.get('SOURCE_INSIGHTS_LIBRARY', ROOT / 'knowledge/sources'))
DEFAULT_SEARCH_MODE = 'keyword' if os.environ.get('SOURCE_INSIGHTS_INDEX_MODE') == 'keyword' else 'hybrid'
MODELS = {'whisper': 'mlx-community/whisper-large-v3-turbo',
          'parakeet': 'mlx-community/parakeet-tdt-0.6b-v3'}


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, text):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def write_json(path, data):
    atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as src:
        for block in iter(lambda: src.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(args, work, timeout=3600):
    """Capture stdout with a time limit; keep diagnostics in a tool log."""
    with (work / 'tools.log').open('a') as log:
        log.write('\nTOOL: ' + str(args[0]) + '\n')
        log.flush()
        try:
            return subprocess.check_output([str(x) for x in args], stderr=log,
                                           text=True, timeout=timeout)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f'{args[0]} failed; see {work / "tools.log"}') from exc


def frame(work, seconds, width=1280):
    manifest = read(work / 'manifest.json')
    if not math.isfinite(seconds) or not 0 <= seconds < manifest['duration']:
        raise ValueError('frame timestamp must be within the video')
    name = f'frames/{seconds:.3f}.jpg'
    run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', f'{seconds:.3f}',
         '-i', manifest['media'], '-frames:v', '1', '-vf', f'scale={width}:-2',
         '-q:v', '3', work / name], work)
    if not (work / name).is_file():
        raise RuntimeError(f'No frame decoded at {seconds}')
    manifest['frames'] = [x for x in manifest['frames'] if x['path'] != name]
    manifest['frames'].append({'seconds': round(seconds, 3), 'path': name})
    manifest['frames'].sort(key=lambda x: x['seconds'])
    write_json(work / 'manifest.json', manifest)
    return name


def prepare(args):
    work = args.work.expanduser().resolve()
    source_path = Path(args.source).expanduser()
    source = str(source_path.resolve()) if source_path.is_file() else args.source
    request = {'source': source, 'backend': args.backend, 'model': args.model,
               'language': args.language, 'frames': args.frames}
    if (work / 'manifest.json').exists():
        old = read(work / 'manifest.json')
        if old.get('ready') and old['request'] == request:
            required = [f['path'] for f in old['frames']]
            if old['transcription'] != 'none':
                required.append('transcript.vtt')
            for name in required:
                if not (work / name).is_file():
                    raise ValueError('Cached evidence is missing; use a new work directory')
            if source_path.is_file() and old['source_id'] != 'file:' + digest(source_path):
                raise ValueError('Local source changed; use a new work directory')
            print(work / 'manifest.json')
            return
        raise ValueError('Work directory differs or is incomplete; use a new directory')
    work.mkdir(parents=True, exist_ok=False)
    work.chmod(0o700)
    (work / 'frames').mkdir()
    title = source_path.stem
    published = None
    captions = []
    if source_path.is_file():
        media = source_path.resolve()
        source_id = 'file:' + digest(media)
    else:
        parsed = urlsplit(source)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Use a local file or an HTTP(S) URL without credentials')
        base = ['yt-dlp', '--ignore-config', '--no-playlist', '--socket-timeout', '30',
                '--retries', '2', '--fragment-retries', '2']
        info = json.loads(run(base + ['--dump-single-json', '--skip-download', '--', source], work, 120))
        if info.get('_type') in ('playlist', 'multi_video') or info.get('is_live'):
            raise ValueError('Use one non-live video')
        duration = info.get('duration')
        if not duration or duration > 14400:
            raise ValueError('URL must have a known duration of at most four hours')
        title = info.get('title') or 'Untitled video'
        published = info.get('upload_date')
        source_id = f'{info.get("extractor_key", "url")}:{info["id"]}'
        opts = ['-f', 'bv*[height<=720]+ba/b[height<=720]/b', '--max-filesize', '4G',
                '--merge-output-format', 'mkv', '-o', str(work / 'source.%(ext)s'),
                '--print', 'after_move:filepath']
        # Captions are evidence; auto-generated captions are not verified speech.
        if args.backend in ('auto', 'captions'):
            opts += ['--write-subs', '--write-auto-subs', '--sub-langs', args.language,
                     '--sub-format', 'vtt']
        result = run(base + opts + ['--', source], work)
        paths = [Path(x) for x in result.splitlines() if x.strip()]
        if len(paths) != 1 or not paths[0].is_file():
            raise RuntimeError('Download did not produce exactly one media file')
        media = paths[0].resolve()
        if media.parent != work:
            raise ValueError('Downloaded media escaped the work directory')
        captions = sorted(work.glob('source.*.vtt'))
    probe = json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                            '-of', 'json', media], work, 60))
    duration = float(probe['format']['duration'])
    if not math.isfinite(duration) or duration <= 0 or duration > 14400:
        raise ValueError('Media duration must be positive and at most four hours')
    has_video = any(s['codec_type'] == 'video' for s in probe['streams'])
    has_audio = any(s['codec_type'] == 'audio' for s in probe['streams'])
    backend = args.backend
    model = None
    if captions:
        shutil.copyfile(captions[0], work / 'transcript.vtt')
        backend = 'platform captions (may be automatic)'
    elif backend == 'captions':
        raise ValueError('No captions found; choose whisper or parakeet')
    elif backend != 'none':
        if not has_audio:
            raise ValueError('No audio stream; use --backend none for visual-only analysis')
        backend = 'whisper' if backend == 'auto' else backend
        model = args.model or MODELS[backend]
        run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', media, '-vn', '-ac', '1',
             '-ar', '16000', work / 'audio.wav'], work)
        if backend == 'whisper':
            command = ['mlx_whisper', str(work / 'audio.wav'), '--model', model,
                       '--output-dir', str(work), '--output-name', 'transcript',
                       '--output-format', 'vtt', '--verbose', 'False']
            if args.language != 'auto':
                command += ['--language', args.language]
        else:
            command = ['parakeet-mlx', str(work / 'audio.wav'), '--model', model,
                       '--output-dir', str(work), '--output-template', 'transcript',
                       '--output-format', 'vtt', '--chunk-duration', '120']
        run(command, work)
        if not (work / 'transcript.vtt').is_file():
            raise RuntimeError('Transcriber produced no VTT; inspect tools.log')
    manifest = {'schema': 2, 'kind': 'video', 'ready': False, 'request': request, 'source': source,
                'source_id': source_id, 'title': title, 'published': published,
                'analyzed_at': datetime.now(timezone.utc).isoformat(),
                'media': str(media), 'duration': duration, 'transcription': backend,
                'model': model, 'frames': []}
    write_json(work / 'manifest.json', manifest)
    if has_video:
        # ponytail: sparse overview; targeted frame commands fill visual gaps.
        for i in range(args.frames):
            frame(work, round(duration * (i + 0.5) / args.frames, 3), 960)
    manifest = read(work / 'manifest.json')
    manifest['ready'] = True
    write_json(work / 'manifest.json', manifest)
    print(work / 'manifest.json')


def prepare_pdf(args):
    work = args.work.expanduser().resolve()
    paper = args.command == 'prepare-paper'
    if paper:
        if not re.fullmatch(r'(?:\d{4}\.\d{4,5}|[A-Za-z.-]+/\d{7})(?:v[1-9]\d*)?', args.source):
            raise ValueError('prepare-paper needs an arXiv ID, optionally with version')
        source = 'https://arxiv.org/pdf/' + args.source
    else:
        local = Path(args.source).expanduser()
        source = str(local.resolve()) if local.is_file() else args.source
    request = {'source': source, 'paper': paper, 'ocr': args.ocr, 'language': args.language, 'title': args.title}
    if (work / 'manifest.json').exists():
        previous = read(work / 'manifest.json')
        if previous.get('ready') and previous['request'] == request:
            if digest(work / 'source.pdf') != previous['pdf_sha256']:
                raise ValueError('Cached PDF changed; use a new work directory')
            if Path(source).is_file() and digest(source) != previous['pdf_sha256']:
                raise ValueError('Local PDF changed; use a new work directory')
            for name in previous['retained']:
                if digest(work / name) != previous['prepared_sha256'][name]:
                    raise ValueError('Cached PDF evidence changed; use a new work directory')
            print(work / 'manifest.json')
            return
        raise ValueError('Work directory differs or is incomplete; use a new directory')
    work.mkdir(parents=True, exist_ok=False)
    work.chmod(0o700)
    pdf = work / 'source.pdf'
    maximum = 100 * 1024 * 1024
    if Path(source).is_file():
        if Path(source).stat().st_size > maximum:
            raise ValueError('PDF exceeds 100 MiB limit')
        shutil.copyfile(source, pdf)
    else:
        parsed = urlsplit(source)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Use a local PDF or HTTP(S) URL without credentials')
        with urlopen(Request(source, headers={'User-Agent': 'source-insights/1'}), timeout=60) as response, pdf.open('wb') as out:
            if urlsplit(response.url).scheme not in ('http', 'https'):
                raise ValueError('Unsupported redirect scheme')
            total = 0
            for block in iter(lambda: response.read(1024 * 1024), b''):
                total += len(block)
                if total > maximum:
                    raise ValueError('PDF exceeds 100 MiB limit')
                out.write(block)
    with pdf.open('rb') as src:
        if b'%PDF-' not in src.read(1024):
            raise ValueError('Source is not a PDF')
    retained = ['source.pdf', 'extraction.json']
    discovery_errors = []
    title = args.title or (args.source if paper else Path(source).stem)
    published = None
    if paper:
        for command, name in [('info', 'paper-info.json'), ('read', 'paper.md')]:
            try:
                flags = ['--json'] if command == 'info' else []
                output = run(['hf', 'papers', command, args.source, *flags], work, 120)
                if command == 'info':
                    metadata = json.loads(output)
                    title = args.title or metadata.get('title') or title
                    published = metadata.get('published_at')
                atomic(work / name, output)
                retained.append(name)
            except (RuntimeError, ValueError, OSError) as exc:
                warning = f'HF {command} unavailable; original PDF remains primary: {exc}'
                discovery_errors.append(warning)
                print(warning, file=sys.stderr)
    command = ['xberg', 'extract', str(pdf), '--no-config-discovery', '--format', 'json',
               '--content-format', 'markdown', '--extract-pages', 'true', '--page-markers', 'true',
               '--extract-images', 'false', '--no-cache', 'true', '--max-threads', '2',
               '--ocr', 'true' if args.ocr else 'false']
    if args.ocr:
        command += ['--ocr-backend', 'tesseract', '--ocr-language', args.language,
                    '--ocr-scanned-pages']
    raw = run(command, work, 600)
    extracted = json.loads(raw)['result']
    warnings = extracted.get('processing_warnings', [])
    for warning in warnings:
        print('WARNING: ' + json.dumps(warning), file=sys.stderr)
    if args.ocr and any(w.get('source') == 'ocr' for w in warnings):
        raise ValueError('OCR reported incomplete extraction; see tools.log and retry in a new directory')
    if extracted.get('mime_type') != 'application/pdf':
        raise ValueError('xberg did not return PDF evidence')
    pages = extracted.get('pages')
    count = extracted['metadata']['pages']['total_count']
    if not isinstance(pages, list) or not pages or [p['page_number'] for p in pages] != list(range(1, count + 1)):
        raise ValueError('Incomplete page mapping from xberg; refusing invented page citations')
    atomic(work / 'extraction.json', raw)
    (work / 'pages').mkdir()
    page_records = []
    for page in pages:
        number = page['page_number']
        name = f'pages/{number:04d}.md'
        atomic(work / name, page['content'])
        retained.append(name)
        page_records.append({'number': number, 'path': name, 'empty': not page['content'].strip()})
    checksum = digest(pdf)
    manifest = {'schema': 2, 'kind': 'pdf', 'ready': True, 'request': request,
                'source': source, 'source_id': 'pdf:' + checksum, 'title': title,
                'published': published, 'analyzed_at': datetime.now(timezone.utc).isoformat(),
                'pdf_sha256': checksum, 'page_count': count, 'pages': page_records,
                'renders': [], 'retained': retained, 'discovery_errors': discovery_errors,
                'prepared_sha256': {name: digest(work / name) for name in retained},
                'paper_id': args.source if paper else None,
                'extraction': {'tool': run(['xberg', 'version'], work, 30).strip(),
                               'method': extracted.get('extraction_method'),
                               'warnings': warnings,
                               'ocr_requested': args.ocr, 'ocr_language': args.language if args.ocr else None}}
    write_json(work / 'manifest.json', manifest)
    if any(p['empty'] for p in page_records):
        print('WARNING: some pages have no extracted text; inspect them visually or retry with --ocr.', file=sys.stderr)
    print(work / 'manifest.json')


def render_page(work, number):
    manifest = read(work / 'manifest.json')
    if manifest['kind'] != 'pdf' or not 1 <= number <= manifest['page_count']:
        raise ValueError('Page must be within the prepared PDF, starting at 1')
    if digest(work / 'source.pdf') != manifest['pdf_sha256']:
        raise ValueError('Prepared PDF changed')
    name = f'pages/{number:04d}.png'
    run(['swift', Path(__file__).with_name('render_pdf.swift'), work / 'source.pdf',
         str(number), work / name], work, 120)
    if not (work / name).is_file():
        raise RuntimeError('Renderer produced no page image')
    manifest['renders'] = [r for r in manifest['renders'] if r['page'] != number]
    manifest['renders'].append({'page': number, 'path': name})
    manifest['renders'].sort(key=lambda r: r['page'])
    write_json(work / 'manifest.json', manifest)
    return work / name


def validate_pdf(analysis, manifest, work):
    for name, checksum in manifest['prepared_sha256'].items():
        path = (work / name).resolve()
        if not path.is_relative_to(work) or digest(path) != checksum:
            raise ValueError('Prepared PDF evidence changed or escaped work directory')
    coverage = analysis['coverage']
    for key in ('text_pages', 'visual_pages'):
        numbers = coverage[key]
        if not isinstance(numbers, list) or any(type(n) is not int or not 1 <= n <= manifest['page_count'] for n in numbers):
            raise ValueError(f'{key} must contain physical page numbers within the PDF')
    rendered = {p['page'] for p in manifest['renders']}
    if not set(coverage['visual_pages']) <= rendered:
        raise ValueError('Visual coverage requires rendered pages')
    contents = {p['page_number']: p['content'] for p in read(work / 'extraction.json')['result']['pages']}
    for insight in analysis['insights']:
        for evidence in insight['evidence']:
            page, kind = evidence['page'], evidence['kind']
            if type(page) is not int or not 1 <= page <= manifest['page_count']:
                raise ValueError('Evidence page outside PDF')
            if kind not in ('text', 'visual', 'both'):
                raise ValueError('PDF evidence kind must be text, visual, or both')
            if kind in ('text', 'both'):
                quote = evidence.get('quote', '')
                if not isinstance(quote, str) or not quote.strip() or len(quote) > 500:
                    raise ValueError('Text evidence needs a short exact quote (1–500 characters)')
                if page not in coverage['text_pages'] or ' '.join(quote.split()) not in ' '.join(contents[page].split()):
                    raise ValueError('Quote not found on a reviewed page')
            if kind in ('visual', 'both') and page not in coverage['visual_pages']:
                raise ValueError('Visual evidence must reference an inspected page')


def prepare_article(args):
    if args.prepared is not None:
        return prepare_article_evidence(args)
    work = args.work.expanduser().resolve()
    local = Path(args.source).expanduser()
    source = str(local.resolve()) if local.is_file() else args.source
    if (work / 'manifest.json').exists():
        old = read(work / 'manifest.json')
        if old.get('ready') and old['kind'] == 'article' and old['source'] == source and old['request_title'] == args.title:
            for name, checksum in old['prepared_sha256'].items():
                if digest(work / name) != checksum:
                    raise ValueError('Cached article evidence changed')
            if local.is_file() and digest(local) != old['source_id'].removeprefix('article:'):
                raise ValueError('Local article changed; use a new work directory')
            print(work / 'manifest.json')
            return
        raise ValueError('Work directory differs or is incomplete; use a new directory')
    work.mkdir(parents=True, exist_ok=False)
    work.chmod(0o700)
    suffix = local.suffix.lower() if local.is_file() else '.html'
    if suffix not in ('.html', '.htm', '.md', '.txt'):
        raise ValueError('Local articles must be HTML, Markdown, or plain text')
    raw = work / ('source' + suffix)
    limit = 10 * 1024 * 1024
    if local.is_file():
        if local.stat().st_size > limit:
            raise ValueError('Article exceeds 10 MiB limit')
        shutil.copyfile(local, raw)
    else:
        parsed = urlsplit(source)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Use an HTTP(S) article URL without credentials')
        with urlopen(Request(source, headers={'User-Agent': 'source-insights/1'}), timeout=60) as response:
            if urlsplit(response.url).scheme not in ('http', 'https'):
                raise ValueError('Unsupported redirect scheme')
            mime = response.headers.get_content_type()
            suffixes = {'text/html': '.html', 'application/xhtml+xml': '.html',
                        'text/plain': '.txt', 'text/markdown': '.md'}
            if mime not in suffixes:
                raise ValueError(f'URL returned {mime}; use the appropriate source preparation command')
            raw = work / ('source' + suffixes[mime])
            total = 0
            with raw.open('wb') as out:
                for block in iter(lambda: response.read(1024 * 1024), b''):
                    total += len(block)
                    if total > limit:
                        raise ValueError('Article exceeds 10 MiB limit')
                    out.write(block)
    extracted_raw = run(['xberg', 'extract', raw, '--no-config-discovery', '--format', 'json',
                         '--content-format', 'markdown', '--ocr', 'false', '--no-cache', 'true',
                         '--extract-images', 'false', '--max-threads', '2'], work, 120)
    result = json.loads(extracted_raw)['result']
    content = result['content']
    if not content.strip():
        raise ValueError('No article text extracted; use a browser-accessible copy')
    atomic(work / 'extraction.json', extracted_raw)
    atomic(work / 'document.md', content)
    retained = [raw.name, 'extraction.json', 'document.md']
    manifest = {'schema': 2, 'kind': 'article', 'ready': True, 'source': source,
                'source_id': 'article:' + digest(raw), 'request_title': args.title,
                'title': args.title or result.get('metadata', {}).get('title') or source,
                'published': None, 'analyzed_at': datetime.now(timezone.utc).isoformat(),
                'line_count': len(content.splitlines()), 'retained': retained,
                'prepared_sha256': {name: digest(work / name) for name in retained},
                'extraction': {'tool': run(['xberg', 'version'], work, 30).strip(),
                               'method': result.get('extraction_method')}}
    write_json(work / 'manifest.json', manifest)
    print(work / 'manifest.json')


def prepare_article_evidence(args):
    """Import a public article-extraction/v1 record; never invoke its producer."""
    source = args.source
    if len(source.encode('utf-8')) > 8192 or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in source):
        raise ValueError('Prepared source URL must be at most 8192 bytes without whitespace or controls')
    parsed = urlsplit(source)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Prepared evidence needs its original HTTP(S) URL without credentials')
    if args.snapshot is None:
        raise ValueError('Prepared evidence needs --snapshot with original UTF-8 HTML')
    with args.snapshot.expanduser().open('rb') as stream:
        snapshot = stream.read(5 * 1024 * 1024 + 1)
    if len(snapshot) > 5 * 1024 * 1024:
        raise ValueError('Original HTML exceeds 5 MiB limit')
    snapshot.decode('utf-8')
    if args.prepared == '-':
        raw = sys.stdin.buffer.read(32 * 1024 * 1024 + 1)
    else:
        with Path(args.prepared).expanduser().open('rb') as stream:
            raw = stream.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError('Prepared record exceeds 32 MiB limit')
    record = json.loads(raw)
    if not isinstance(record, dict) or record.get('schema') != 'article-extraction/v1':
        raise ValueError('Expected article-extraction/v1 JSON record')
    origin, extractor, document = (record.get(key) for key in ('source', 'extractor', 'document'))
    if not all(isinstance(value, dict) for value in (origin, extractor, document)):
        raise ValueError('Prepared source, extractor and document must be objects')
    checksum = hashlib.sha256(snapshot).hexdigest()
    if origin != {'url': source, 'sha256': checksum, 'media_type': 'text/html', 'encoding': 'utf-8'}:
        raise ValueError('Prepared source URL, encoding or SHA256 does not match original snapshot')
    for key in ('name', 'version', 'method'):
        value = extractor.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError('Prepared extractor needs bounded name, version and method strings')
    if not isinstance(extractor.get('options'), dict):
        raise ValueError('Prepared extractor options must be an object')
    content, title = document.get('markdown'), document.get('title')
    if not isinstance(content, str) or not content.strip() or len(content.encode('utf-8')) > 10 * 1024 * 1024:
        raise ValueError('Prepared Markdown must be nonempty and at most 10 MiB')
    if not isinstance(title, str) or len(title) > 4096:
        raise ValueError('Prepared title must be a string of at most 4096 characters')
    work = args.work.expanduser().resolve()
    provenance = dict(extractor, source_url=source, schema=record['schema'])
    files = {'source.html': snapshot, 'extraction.json': raw, 'document.md': content.encode('utf-8')}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    if (work / 'manifest.json').exists():
        old = read(work / 'manifest.json')
        if not (old.get('ready') and old['kind'] == 'article' and old['source'] == source
                and old['request_title'] == args.title and old['prepared_sha256'] == hashes
                and old['extraction'] == provenance):
            raise ValueError('Prepared evidence differs; use a new work directory')
        for name, checksum in hashes.items():
            if digest(work / name) != checksum:
                raise ValueError('Cached article evidence changed')
        print(work / 'manifest.json')
        return
    # Validate the entire stream before creating a publishable work directory.
    work.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.article-', dir=work.parent))
    try:
        for name, data in files.items():
            (stage / name).write_bytes(data)
        write_json(stage / 'manifest.json', {
            'schema': 2, 'kind': 'article', 'ready': True, 'source': source,
            'source_id': 'article:' + hashlib.sha256(snapshot).hexdigest(),
            'request_title': args.title, 'title': args.title or title or source,
            'published': None, 'analyzed_at': datetime.now(timezone.utc).isoformat(),
            'line_count': len(content.splitlines()), 'retained': list(files),
            'prepared_sha256': hashes, 'extraction': provenance})
        if work.exists():
            raise ValueError('Work directory already exists; use a new directory')
        stage.rename(work)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(work / 'manifest.json')


def validate_article(analysis, manifest, work):
    ranges = analysis['coverage']['line_ranges']
    if not isinstance(ranges, list) or not ranges:
        raise ValueError('Article coverage needs reviewed line ranges')
    for span in ranges:
        if not isinstance(span, list) or len(span) != 2 or any(type(n) is not int for n in span) or not 1 <= span[0] <= span[1] <= manifest['line_count']:
            raise ValueError('Coverage line range outside article')
    for name, checksum in manifest['prepared_sha256'].items():
        path = (work / name).resolve()
        if not path.is_relative_to(work) or digest(path) != checksum:
            raise ValueError('Prepared article evidence changed or escaped work directory')
    lines = (work / 'document.md').read_text().splitlines()
    for insight in analysis['insights']:
        for evidence in insight['evidence']:
            start, end, quote = evidence['line_start'], evidence['line_end'], evidence['quote']
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= manifest['line_count']:
                raise ValueError('Evidence line range outside article')
            if not any(a <= start <= end <= b for a, b in ranges):
                raise ValueError('Evidence must be within a reviewed line range')
            if not isinstance(quote, str) or not quote.strip() or len(quote) > 500 or ' '.join(quote.split()) not in ' '.join(' '.join(lines[start-1:end]).split()):
                raise ValueError('A short exact quote must occur in the cited lines')


def validate(analysis, manifest, work):
    if manifest.get('schema') != 2 or manifest.get('kind') not in ('video', 'pdf', 'article'):
        raise ValueError('Unsupported source manifest')
    for key in ('title', 'summary'):
        if not isinstance(analysis.get(key), str) or not analysis[key].strip():
            raise ValueError(f'Missing {key}')
    if not isinstance(analysis.get('tags'), list) or not all(isinstance(x, str) for x in analysis['tags']):
        raise ValueError('tags must be a list of strings')
    coverage = analysis['coverage']
    if not isinstance(coverage.get('limitations'), list) or not all(isinstance(x, str) for x in coverage['limitations']):
        raise ValueError('coverage.limitations must be a list of strings')
    if not isinstance(analysis.get('insights'), list) or not analysis['insights']:
        raise ValueError('At least one evidence-backed insight is required')
    for insight in analysis['insights']:
        for key in ('claim', 'why_it_matters', 'application', 'caveats'):
            if not isinstance(insight.get(key), str) or not insight[key].strip():
                raise ValueError(f'Each insight needs {key}')
        if insight['status'] not in ('source-claim', 'inference'):
            raise ValueError('status must distinguish source-claim from inference')
        if not insight.get('evidence'):
            raise ValueError('Each insight needs source-specific evidence')
    if manifest['kind'] == 'pdf':
        validate_pdf(analysis, manifest, work)
        return
    if manifest['kind'] == 'article':
        validate_article(analysis, manifest, work)
        return
    if coverage['transcript'] not in ('full', 'partial', 'none'):
        raise ValueError('coverage.transcript must be full, partial, or none')
    if manifest['transcription'] == 'none' and coverage['transcript'] != 'none':
        raise ValueError('Cannot claim transcript review without a transcript')
    available = {f['seconds'] for f in manifest['frames']}
    if not isinstance(coverage['frames'], list) or not set(coverage['frames']) <= available:
        raise ValueError('Inspected frame times must be present in manifest')
    for insight in analysis['insights']:
        for evidence in insight['evidence']:
            start, end = evidence['start'], evidence['end']
            if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) for t in (start, end)):
                raise ValueError('Evidence times must be finite numbers')
            if not 0 <= start <= end <= manifest['duration']:
                raise ValueError('Evidence timestamp outside video')
            kind = evidence['kind']
            if kind not in ('transcript', 'frame', 'both'):
                raise ValueError('Evidence kind must be transcript, frame, or both')
            if kind in ('transcript', 'both') and coverage['transcript'] == 'none':
                raise ValueError('Transcript evidence requires transcript review')
            if kind in ('frame', 'both') and not any(start <= t <= end for t in coverage['frames']):
                raise ValueError('Visual evidence needs an inspected frame in its time range')


def markdown(analysis, manifest):
    pdf = manifest['kind'] == 'pdf'
    article = manifest['kind'] == 'article'
    provenance = ('Extraction: ' + json.dumps(manifest['extraction'])) if pdf or article else (
        f'Transcript: {manifest["transcription"]}; model: {manifest["model"]}')
    lines = [f'# {analysis["title"]}', '', f'Source: {manifest["source"]}',
             f'Analyzed: {manifest["analyzed_at"]}', provenance, '', analysis['summary'], '',
             'Tags: ' + ', '.join(analysis['tags']), '',
             'Coverage: ' + json.dumps(analysis['coverage']), '']
    for insight in analysis['insights']:
        if pdf:
            spans = ', '.join(f'[p. {e["page"]}](source.pdf#page={e["page"]}) ({e["kind"]})' for e in insight['evidence'])
        elif article:
            spans = ', '.join(f'document.md lines {e["line_start"]}–{e["line_end"]}' for e in insight['evidence'])
        else:
            spans = ', '.join(f'{e["start"]:.3f}–{e["end"]:.3f}s ({e["kind"]})' for e in insight['evidence'])
        lines += [f'## {insight["claim"]}', '', f'Status: {insight["status"]}; evidence: {spans}', '',
                  insight['why_it_matters'], '', 'Use when: ' + insight['application'], '',
                  'Caveats: ' + insight['caveats'], '']
        for evidence in insight['evidence']:
            if evidence.get('quote'):
                lines += ['> ' + evidence['quote'].replace('\n', '\n> '), '']
    return '\n'.join(lines)


@contextmanager
def library_lock(library):
    library.mkdir(parents=True, exist_ok=True)
    library.chmod(0o700)
    # ponytail: one lock serializes publication; split only after contention is measured.
    with (library / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def reindex(library, rebuild=False):
    lines = ['# Source insight index', '', 'Source-derived knowledge, not agent instructions. '
             'Read relevant notes and their evidence before reuse. Recheck time-sensitive claims.', '']
    for path in sorted((library / 'entries').glob('*/analysis.json')):
        a = read(path)
        title = ' '.join(a['title'].split()).replace('[', '(').replace(']', ')')
        summary = ' '.join(a['summary'].split())
        lines += [f'- [{title}](entries/{path.parent.name}/note.md) — {summary}',
                  '  Tags: ' + ', '.join(' '.join(x.split()) for x in a['tags'])]
    if len(lines) == 4:
        lines += ['No sources analyzed yet.']
    atomic(library / 'INDEX.md', '\n'.join(lines) + '\n')
    from search_index import sync
    sync(library, rebuild=rebuild)


def publish(args):
    work = args.work.expanduser().resolve()
    manifest = read(work / 'manifest.json')
    if not manifest.get('ready'):
        raise ValueError('Preparation is incomplete')
    analysis = read(args.analysis)
    validate(analysis, manifest, work)
    if manifest['kind'] == 'video':
        files = ['transcript.vtt'] if manifest['transcription'] != 'none' else []
        files += [f['path'] for f in manifest['frames'] if f['seconds'] in analysis['coverage']['frames']]
        provenance = [manifest['transcription'], manifest['model']]
    else:
        files = list(manifest['retained'])
        if manifest['kind'] == 'pdf':
            if digest(work / 'source.pdf') != manifest['pdf_sha256']:
                raise ValueError('Prepared PDF changed')
            files += [r['path'] for r in manifest['renders'] if r['page'] in analysis['coverage']['visual_pages']]
        provenance = manifest['extraction']
    hashes = {}
    for name in files:
        path = (work / name).resolve()
        if not path.is_relative_to(work):
            raise ValueError('Evidence escaped work directory')
        hashes[name] = digest(path)
    identity = json.dumps([manifest['source_id'], provenance, analysis, hashes], sort_keys=True)
    entry_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
    library = args.library.expanduser().resolve()
    with library_lock(library):
        entries = library / 'entries'
        entries.mkdir(exist_ok=True)
        destination = entries / entry_id
        if not destination.exists():
            stage = Path(tempfile.mkdtemp(prefix='.publish-', dir=library))
            try:
                write_json(stage / 'analysis.json', analysis)
                durable = dict(manifest, evidence_sha256=hashes)
                durable.pop('media', None)
                if manifest['kind'] == 'video':
                    durable['frames'] = [f for f in manifest['frames'] if f['path'] in hashes]
                elif manifest['kind'] == 'pdf':
                    durable['renders'] = [r for r in manifest['renders'] if r['path'] in hashes]
                write_json(stage / 'manifest.json', durable)
                atomic(stage / 'note.md', markdown(analysis, manifest))
                for name in files:
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(work / name, target)
                    if digest(target) != hashes[name]:
                        raise ValueError('Evidence changed during publication')
                validate(analysis, durable, stage)
                stage.rename(destination)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        else:
            saved = read(destination / 'manifest.json')
            fields = ('schema', 'kind', 'source', 'source_id', 'extraction', 'line_count',
                      'prepared_sha256', 'retained', 'transcription', 'model', 'duration')
            if (any(saved.get(key) != manifest.get(key) for key in fields)
                    or saved.get('evidence_sha256') != hashes or read(destination / 'analysis.json') != analysis):
                raise ValueError('Existing publication metadata differs')
            for name, checksum in hashes.items():
                if digest(destination / name) != checksum:
                    raise ValueError('Existing published evidence changed')
            validate(analysis, manifest, destination)
        try:
            reindex(library)
        except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f'Entry saved at {destination / "note.md"}, but indexing failed: {exc}. Run reindex after fixing the cause.') from exc
    print(destination / 'note.md')


def export_records(args):
    """Portable metadata snapshot; evidence validation stays with its owner."""
    library = args.library.expanduser().resolve()
    with library_lock(library):
        rows = []
        if args.query is not None:
            if not args.query.strip() or len(args.query.encode()) > 400 or not 1 <= args.limit <= 50:
                raise ValueError('Export query must be 1–400 bytes and limit 1–50')
            from search_index import search
            rows = list(search(library, args.query, args.mode, args.limit))
        packet = dict(schema='knowledge-snapshot/v1', corpus='insights', query=args.query,
                      nodes=[], edges=[], versions={}, hits=[])
        entries = sorted((library / 'entries').iterdir())
        if len(entries) > 10000:
            raise ValueError('Export exceeds 10000 entries')
        for entry in entries:
            if entry.name.startswith('.'):
                continue
            if (len(entry.name) != 24 or any(c not in '0123456789abcdef' for c in entry.name)
                    or not entry.is_dir() or entry.is_symlink()):
                raise ValueError('Invalid published entry')
            manifest, analysis = read(entry / 'manifest.json'), read(entry / 'analysis.json')
            validate(analysis, manifest, entry)
            for name, checksum in manifest['evidence_sha256'].items():
                path = (entry / name).resolve()
                if not path.is_relative_to(entry) or digest(path) != checksum:
                    raise ValueError('Published evidence changed')
            mh, ah = digest(entry / 'manifest.json'), digest(entry / 'analysis.json')
            version = hashlib.sha256(f'{mh}:{ah}'.encode()).hexdigest()
            eid = 'entry:' + entry.name
            source = manifest['source']
            url = source if urlsplit(source).scheme in ('http', 'https') else None
            details = dict(source=source, source_id=manifest['source_id'], source_kind=manifest['kind'],
                           analyzed_at=manifest.get('analyzed_at'), coverage=analysis['coverage'],
                           version=version, manifest_sha256=mh, analysis_sha256=ah,
                           evidence_sha256=manifest['evidence_sha256'], note=str(entry / 'note.md'),
                           open_with=['insights', '--library', str(library), 'view', entry.name, '--json'],
                           insights=analysis['insights'], extraction=manifest.get('extraction'),
                           integrity='Producer validated retained evidence hashes and citations; claims and coverage are recorded assessments.')
            extraction = manifest.get('extraction')
            if isinstance(extraction, dict) and extraction.get('tool') == 'session-evidence/v1':
                details['session_provenance'] = extraction
            request = manifest.get('request')
            request = request.get('source') if isinstance(request, dict) else request
            if isinstance(request, str) and urlsplit(request).scheme in ('http', 'https'):
                details['request_url'] = request
            packet['nodes'].append(dict(id=eid, label=analysis['title'], kind='source_entry',
                                        url=url, bookmark_kind=None, details=details))
            packet['versions'][eid] = version
            for ordinal, insight in enumerate(analysis['insights'], 1):
                iid = f'insight:{entry.name}:{ordinal}'
                detail = dict(details, **insight, title=analysis['title'], insight=ordinal)
                detail['open_with'] = ['insights', '--library', str(library), 'view', entry.name, str(ordinal), '--json']
                packet['nodes'].append(dict(id=iid, label=insight['claim'], kind='insight',
                                            url=url, bookmark_kind=None, details=detail))
                packet['versions'][iid] = version
                packet['edges'].append(dict(a=iid, b=eid, kind='derived_from', status='recorded',
                                            evidence=dict(version=version, citations=insight['evidence'], coverage=analysis['coverage'])))
            if digest(entry / 'manifest.json') != mh or digest(entry / 'analysis.json') != ah:
                raise ValueError('Published metadata changed during export')
        for rank, row in enumerate(rows, 1):
            eid = Path(row['note']).parent.name
            iid = f'insight:{eid}:{row["insight"]}'
            node = next((n for n in packet['nodes'] if n['id'] == iid), None)
            if node is None or any(row[k] != node['details'][k] for k in ('claim', 'coverage', 'evidence')):
                raise ValueError('Retrieved insight revision changed')
            packet['hits'].append(dict(id=iid, rank=rank, method=row['mode'], matched_by=row['matched_by']))
        raw = json.dumps(packet, ensure_ascii=False)
        if len(raw.encode()) > 16 * 1024 * 1024 or len(packet['nodes']) > 10000:
            raise ValueError('Export exceeds snapshot limits')
        print(raw)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('source')
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--backend', choices=['auto', 'captions', 'whisper', 'parakeet', 'none'], default='auto')
    p.add_argument('--model')
    p.add_argument('--language', default='en')
    p.add_argument('--frames', type=int, default=24)
    for name in ('prepare-pdf', 'prepare-paper'):
        p = sub.add_parser(name)
        p.add_argument('source')
        p.add_argument('--work', type=Path, required=True)
        p.add_argument('--title')
        p.add_argument('--ocr', action='store_true')
        p.add_argument('--language', default='eng')
    p = sub.add_parser('prepare-article')
    p.add_argument('source')
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--title')
    p.add_argument('--prepared', help='article-extraction/v1 JSON file, or - for stdin; no extractor is invoked')
    p.add_argument('--snapshot', type=Path, help='Original UTF-8 HTML matching the prepared record SHA256')
    p = sub.add_parser('prepare-session', help='Import selected public session excerpts from neutral records; no producer invoked')
    p.add_argument('session', help='Explicit session:AGENT:ID from the producer output')
    p.add_argument('--records', required=True, help='Sessions knowledge-snapshot/v1 file or - for stdin')
    p.add_argument('--work', type=Path, required=True)
    p = sub.add_parser('page')
    p.add_argument('work', type=Path)
    p.add_argument('number', type=int)
    p = sub.add_parser('frame')
    p.add_argument('work', type=Path)
    p.add_argument('seconds', type=float)
    p.add_argument('--width', type=int, default=1280)
    p = sub.add_parser('publish')
    p.add_argument('work', type=Path)
    p.add_argument('analysis', type=Path)
    p.add_argument('--library', type=Path, default=LIBRARY)
    p = sub.add_parser('validate', help='Check analysis, coverage, citations and prepared hashes without publication')
    p.add_argument('work', type=Path)
    p.add_argument('analysis', type=Path)
    p = sub.add_parser('reindex')
    p.add_argument('--library', type=Path, default=LIBRARY)
    p.add_argument('--rebuild', action='store_true', help='Atomically rebuild the derived search database')
    p = sub.add_parser('search')
    p.add_argument('query')
    p.add_argument('--library', type=Path, default=LIBRARY)
    p.add_argument('--mode', choices=['hybrid', 'keyword', 'semantic'], default=DEFAULT_SEARCH_MODE)
    p.add_argument('--limit', type=int, default=5)
    sub.add_parser('doctor')
    p = sub.add_parser('export', help='Emit one complete knowledge-snapshot/v1 JSONL record; no consumer invoked')
    p.add_argument('--library', type=Path, default=LIBRARY)
    p.add_argument('--query')
    p.add_argument('--mode', choices=['hybrid', 'keyword', 'semantic'], default=DEFAULT_SEARCH_MODE)
    p.add_argument('--limit', type=int, default=5)
    args = parser.parse_args()
    if args.command in ('search', 'publish', 'reindex') or args.command == 'export' and args.query is not None:
        runtime = ROOT / 'runtimes/source-insights/bin/python'
        if Path(sys.prefix) != runtime.parent.parent:
            if not runtime.is_file():
                raise RuntimeError('Search runtime missing; see references/search.md')
            os.execv(str(runtime), [str(runtime), str(Path(__file__).resolve()), *sys.argv[1:]])
    if args.command == 'prepare':
        if not 0 <= args.frames <= 100:
            raise ValueError('--frames must be 0–100')
        prepare(args)
    elif args.command in ('prepare-pdf', 'prepare-paper'):
        prepare_pdf(args)
    elif args.command == 'prepare-article':
        if args.snapshot is not None and args.prepared is None:
            raise ValueError('--snapshot requires --prepared')
        prepare_article(args)
    elif args.command == 'prepare-session':
        from session_records import prepare as prepare_session
        prepare_session(args, dict(read=read,digest=digest,atomic=atomic,write_json=write_json,
                                   now=lambda: datetime.now(timezone.utc).isoformat()))
    elif args.command == 'page':
        print(render_page(args.work.resolve(), args.number))
    elif args.command == 'frame':
        if not 128 <= args.width <= 3840:
            raise ValueError('--width must be 128–3840')
        print(frame(args.work.resolve(), args.seconds, args.width))
    elif args.command == 'publish':
        publish(args)
    elif args.command == 'validate':
        work = args.work.expanduser().resolve()
        manifest = read(work / 'manifest.json')
        if not isinstance(manifest, dict) or not manifest.get('ready'):
            raise ValueError('Preparation is incomplete')
        if not isinstance(manifest.get('source_id'), str) or not manifest['source_id'].strip():
            raise ValueError('Source manifest needs an explicit source identity')
        analysis = read(args.analysis.expanduser())
        if not isinstance(analysis, dict):
            raise ValueError('Analysis must be a JSON object')
        try:
            validate(analysis, manifest, work)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f'Malformed analysis or source manifest: {exc}') from exc
        print(json.dumps(dict(status='valid', source_id=manifest['source_id'], work=str(work),
                              meaning='Citation integrity checked; not claim verification or publication approval.')))
    elif args.command == 'reindex':
        library = args.library.expanduser().resolve()
        with library_lock(library):
            reindex(library, rebuild=args.rebuild)
    elif args.command == 'search':
        if not 1 <= args.limit <= 50:
            raise ValueError('--limit must be 1–50')
        from search_index import search
        library = args.library.expanduser().resolve()
        with library_lock(library):
            for result in search(library, args.query, args.mode, args.limit):
                print(json.dumps(result, ensure_ascii=False))
    elif args.command == 'export':
        export_records(args)
    else:
        missing = False
        for name in ('yt-dlp', 'ffmpeg', 'ffprobe', 'mlx_whisper', 'parakeet-mlx', 'hf', 'xberg', 'llama-embedding'):
            path = shutil.which(name)
            print(f'{name}: {path or "MISSING"}')
            missing |= path is None
        if missing:
            raise RuntimeError('Missing dependencies; see SKILL.md')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, RuntimeError, sqlite3.Error, subprocess.TimeoutExpired) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
