#!/usr/bin/env python3
"""Disposable pipe journey: extraction, provenance, citations, publication, retrieval."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SCRIPT = Path(__file__).with_name('sources.py')
DISTILLER = os.environ.get('DISTILLER_BINARY', 'distiller')
SOURCE = 'https://example.invalid/article?edition=1#code'
HTML = b'<article><h1>Prepared stream fixture</h1><p>Original evidence preserves exact numerical constants.</p><pre><code>let n = 970;\n    n &gt;&gt; 52</code></pre><a href="/source">Source</a></article>'


def cli(*args, data=None, ok=True, env=None):
    result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                            input=data, capture_output=True, timeout=180, env=env)
    assert (result.returncode == 0) == ok, (result.stdout, result.stderr)
    return result.stdout.decode().strip()


def main():
    with tempfile.TemporaryDirectory(prefix='prepared-evidence-check-') as tmp:
        root = Path(tmp)
        snapshot = root / 'original.html'
        snapshot.write_bytes(HTML)
        work, library = root / 'work', root / 'library'
        producer = subprocess.Popen([DISTILLER, '--stdin', '--base-url', SOURCE, '--mode', 'json'],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        producer.stdin.write(HTML)
        producer.stdin.close()
        # No companion tool is available to the consumer's preparation process.
        env = dict(os.environ, PATH=str(root / 'no-executables'), PYTHONDONTWRITEBYTECODE='1')
        consumer = subprocess.run([sys.executable, str(SCRIPT), 'prepare-article', SOURCE,
                                  '--prepared', '-', '--snapshot', str(snapshot), '--work', str(work)],
                                  stdin=producer.stdout, capture_output=True, timeout=45, env=env)
        producer.stdout.close()
        producer.wait(timeout=45)
        assert producer.returncode == 0, producer.stderr.read()
        producer.stderr.close()
        assert consumer.returncode == 0, consumer.stderr
        original_files = {p.name: p.read_bytes() for p in work.iterdir()}
        manifest = json.loads(original_files['manifest.json'])
        packet = original_files['extraction.json']
        record = json.loads(packet)
        assert manifest['source'] == SOURCE
        assert manifest['source_id'] == 'article:' + hashlib.sha256(HTML).hexdigest()
        assert (work / 'source.html').read_bytes() == HTML
        assert (work / 'document.md').read_text() == record['document']['markdown']
        assert 'let n = 970;\n    n >> 52' in record['document']['markdown']
        assert 'https://example.invalid/source' in record['document']['markdown']
        assert manifest['extraction']['name'] == 'distiller'
        assert manifest['extraction']['version'] and manifest['extraction']['method'] == 'deterministic-html'
        for name, checksum in manifest['prepared_sha256'].items():
            assert hashlib.sha256((work / name).read_bytes()).hexdigest() == checksum
        args = ('prepare-article', SOURCE, '--prepared', '-', '--snapshot', snapshot, '--work', work)
        cli(*args, data=packet, env=env)
        assert {p.name: p.read_bytes() for p in work.iterdir()} == original_files
        bad_records = [b'', b'{', packet + b'{}']
        for key, value in [('schema', 'unknown'), ('source', dict(record['source'], url=SOURCE + 'changed')),
                           ('source', dict(record['source'], sha256='0' * 64)),
                           ('document', {'title': 'Empty', 'markdown': ''}),
                           ('extractor', {'name': 'unknown'})]:
            bad_records.append(json.dumps(dict(record, **{key: value})).encode())
        for i, data in enumerate(bad_records):
            badwork = root / f'bad-{i}'
            cli('prepare-article', SOURCE, '--prepared', '-', '--snapshot', snapshot, '--work', badwork,
                data=data, ok=False, env=env)
            assert not badwork.exists()
            cli(*args, data=data, ok=False, env=env)
            assert {p.name: p.read_bytes() for p in work.iterdir()} == original_files
        cli('prepare-article', SOURCE, '--prepared', '-', '--work', root / 'missing-snapshot',
            data=packet, ok=False, env=env)
        # Any producer may emit the published schema; no distiller-specific branch.
        other = dict(record, extractor={'name': 'uninstalled-producer', 'version': '1',
                                       'method': 'fixture', 'options': {'opaque': 'not executable'}})
        cli('prepare-article', SOURCE, '--prepared', '-', '--snapshot', snapshot, '--work', root / 'generic',
            data=json.dumps(other).encode(), env=env)
        lines = (work / 'document.md').read_text().splitlines()
        line = next(i for i, text in enumerate(lines, 1) if 'Original evidence' in text)
        analysis = {'title': 'Prepared stream fixture', 'summary': 'Synthetic pipe acceptance, not real knowledge.',
                    'tags': ['prepared-fixture'], 'coverage': {'line_ranges': [[1, len(lines)]],
                    'limitations': ['Synthetic text only; no independent claim verification.']},
                    'insights': [{'claim': 'The fixture preserves numerical constants.', 'status': 'source-claim',
                    'why_it_matters': 'Exercises the reviewed evidence handoff.', 'application': 'Only this fixture.',
                    'caveats': 'Synthetic acceptance evidence.', 'evidence': [{'line_start': line, 'line_end': line,
                    'quote': 'Original evidence preserves exact numerical constants.'}]}]}
        doc = root / 'analysis.json'
        doc.write_text(json.dumps(analysis))
        first = Path(cli('publish', work, doc, '--library', library))
        assert first == Path(cli('publish', work, doc, '--library', library))
        saved = json.loads((first.parent / 'manifest.json').read_text())
        assert saved['source'] == SOURCE and saved['extraction'] == manifest['extraction']
        for name, checksum in saved['evidence_sha256'].items():
            assert hashlib.sha256((first.parent / name).read_bytes()).hexdigest() == checksum
        hits = [json.loads(row) for row in cli('search', 'numerical constants', '--mode', 'keyword',
                                             '--library', library).splitlines()]
        assert hits and hits[0]['source'] == SOURCE and hits[0]['evidence'][0]['line_start'] == line
        assert 'Original evidence preserves exact numerical constants.' in first.read_text()
        for evidence in [{'line_start': line, 'line_end': line, 'quote': 'Invented evidence.'},
                         {'line_start': 0, 'line_end': line, 'quote': 'Original evidence'}]:
            invalid = json.loads(json.dumps(analysis))
            invalid['insights'][0]['evidence'] = [evidence]
            doc.write_text(json.dumps(invalid))
            cli('publish', work, doc, '--library', library, ok=False)
        doc.write_text(json.dumps(analysis))
        # Equal bytes at a different exact URL must not collapse its source identity.
        second_url = SOURCE + '2'
        second = dict(record, source=dict(record['source'], url=second_url))
        second_work = root / 'second-url'
        cli('prepare-article', second_url, '--prepared', '-', '--snapshot', snapshot, '--work', second_work,
            data=json.dumps(second).encode(), env=env)
        assert first != Path(cli('publish', second_work, doc, '--library', library))
        assert len(list((library / 'entries').iterdir())) == 2
        retained = first.parent / 'document.md'
        before = retained.read_bytes()
        retained.write_text('Corrupt published evidence.')
        cli('publish', work, doc, '--library', library, ok=False)
        retained.write_bytes(before)
        assert first == Path(cli('publish', work, doc, '--library', library))
        metadata = first.parent / 'manifest.json'
        original = metadata.read_bytes()
        metadata.write_text(json.dumps(dict(saved, source=SOURCE + '-corrupt')))
        cli('publish', work, doc, '--library', library, ok=False)
        metadata.write_bytes(original)
        for key, value in [('version', 'changed'), ('method', 'changed'), ('source_url', SOURCE + '-changed')]:
            corrupt = dict(saved, extraction=dict(saved['extraction'], **{key: value}))
            metadata.write_text(json.dumps(corrupt))
            cli('publish', work, doc, '--library', library, ok=False)
        metadata.write_bytes(original)
        fault = '''
import sys
from argparse import Namespace
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import sources
copy = sources.shutil.copyfile
def corrupt(src, dst):
    copy(src, dst)
    if Path(dst).name == 'document.md': Path(dst).write_text('Copy fault')
sources.shutil.copyfile = corrupt
try:
    sources.publish(Namespace(work=Path(sys.argv[2]), analysis=Path(sys.argv[3]), library=Path(sys.argv[4])))
except ValueError as exc:
    assert 'Evidence changed during publication' in str(exc), str(exc)
else:
    raise AssertionError('Corrupt publication copy was accepted')
'''
        fault_library = root / 'fault-library'
        subprocess.run([sys.executable, '-c', fault, str(SCRIPT.parent), str(work), str(doc), str(fault_library)],
                       capture_output=True, timeout=30, check=True)
        assert list((fault_library / 'entries').iterdir()) == []
        (work / 'document.md').write_text('Altered evidence.')
        cli('publish', work, doc, '--library', library, ok=False)
        assert snapshot.read_bytes() == HTML
    print('PASS: real pipe, independent producers, exact source/snapshot/Markdown hashes, reuse, malformed and mismatched input, retained citations, deduplication, distinct URL identity, keyword retrieval and tamper rejection; disposable library removed')


if __name__ == '__main__':
    main()
