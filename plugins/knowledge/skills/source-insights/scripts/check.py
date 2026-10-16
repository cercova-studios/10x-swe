#!/usr/bin/env python3
"""Disposable integration check: extraction, evidence validation and publication."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import tempfile

SCRIPT = Path(__file__).with_name('sources.py')


def cli(*args, ok=True):
    result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)
    assert (result.returncode == 0) == ok, (result.stdout, result.stderr)
    return result.stdout.strip()


def main():
    with tempfile.TemporaryDirectory(prefix='source-insights-check-') as tmp:
        root = Path(tmp)
        original = root / 'original.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=64x64:r=5',
                        '-t', '2', '-c:v', 'libx264', str(original)], check=True)
        before = original.read_bytes()
        work, library = root / 'work', root / 'library'
        command = ('prepare', original, '--work', work, '--backend', 'none', '--frames', '2')
        cli(*command)
        cli(*command)  # completed preparation reuses evidence
        manifest = json.loads((work / 'manifest.json').read_text())
        assert manifest['ready'] and len(manifest['frames']) == 2
        cli('frame', work, '1.0')
        analysis = {'title': 'Blue test frame', 'summary': 'Synthetic test, not knowledge.',
                    'tags': ['fixture'], 'coverage': {'transcript': 'none', 'frames': [1.0],
                    'limitations': ['Synthetic, one inspected frame.']},
                    'insights': [{'claim': 'The frame is blue.', 'status': 'source-claim',
                    'why_it_matters': 'Checks visual provenance.', 'application': 'Only this fixture.',
                    'caveats': 'No real-world inference.',
                    'evidence': [{'start': 1.0, 'end': 1.0, 'kind': 'frame'}]}]}
        doc = work / 'analysis.json'
        doc.write_text(json.dumps(analysis))
        first = cli('publish', work, doc, '--library', library)
        assert first == cli('publish', work, doc, '--library', library)
        assert len(list((library / 'entries').iterdir())) == 1
        assert 'Blue test frame' in cli('search', 'fixture blue', '--library', library)
        invalid = json.loads(json.dumps(analysis))
        invalid['insights'][0]['evidence'][0]['end'] = 100
        bad = work / 'bad.json'
        bad.write_text(json.dumps(invalid))
        cli('publish', work, bad, '--library', library, ok=False)
        invalid['insights'][0]['evidence'][0]['end'] = float('nan')
        bad.write_text(json.dumps(invalid))
        cli('publish', work, bad, '--library', library, ok=False)
        invalid = json.loads(json.dumps(analysis))
        invalid['insights'][0]['evidence'][0]['kind'] = 'transcript'
        bad.write_text(json.dumps(invalid))
        cli('publish', work, bad, '--library', library, ok=False)
        second = dict(analysis, title='Second revision')
        other = work / 'other.json'
        other.write_text(json.dumps(second))
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda p: cli('publish', work, p, '--library', library), [doc, other]))
        assert len(set(results)) == 2
        assert len(list((library / 'entries').iterdir())) == 2
        (library / 'INDEX.md').unlink()
        cli('reindex', '--library', library)
        index = (library / 'INDEX.md').read_text()
        assert 'Blue test frame' in index and 'Second revision' in index
        assert original.read_bytes() == before
        # A malicious evidence path in a local manifest must never be copied.
        manifest = json.loads((work / 'manifest.json').read_text())
        manifest['frames'] = [{'seconds': 1.0, 'path': '../original.mp4'}]
        (work / 'manifest.json').write_text(json.dumps(manifest))
        cli('publish', work, doc, '--library', library, ok=False)
        # Native text PDF: two pages with distinct evidence, no external fixture.
        pdf = root / 'fixture.pdf'
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
                   b'<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>']
        for stream in (6, 7):
            objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents {stream} 0 R >>'.encode())
        objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
        for phrase in ('First page evidence.', 'Second page evidence.'):
            content = f'BT /F1 24 Tf 72 720 Td ({phrase}) Tj ET'.encode()
            objects.append(b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream')
        data, offsets = b'%PDF-1.4\n', [0]
        for n, obj in enumerate(objects, 1):
            offsets.append(len(data))
            data += f'{n} 0 obj\n'.encode() + obj + b'\nendobj\n'
        xref = len(data)
        data += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
        data += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
        data += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
        pdf.write_bytes(data)
        for kind, source in [('pdf', pdf), ('article', root / 'article.html')]:
            if kind == 'article':
                source.write_text('<html><body><article><h1>Example</h1><p>First page evidence.</p></article></body></html>')
            prepared = root / kind
            cli('prepare-' + kind, source, '--work', prepared)
            cli('prepare-' + kind, source, '--work', prepared)
            a = json.loads(json.dumps(analysis))
            a['title'] = kind + ' fixture'
            if kind == 'pdf':
                a['coverage'] = {'text_pages': [1, 2], 'visual_pages': [], 'limitations': ['Fixture only.']}
                evidence = {'page': 1, 'kind': 'text', 'quote': 'First page evidence.'}
                cli('page', prepared, '1')
                assert (prepared / 'pages/0001.png').stat().st_size > 100
            else:
                lines = (prepared / 'document.md').read_text().splitlines()
                line = next(i for i, text in enumerate(lines, 1) if 'First page evidence.' in text)
                a['coverage'] = {'line_ranges': [[1, len(lines)]], 'limitations': ['Text only.']}
                evidence = {'line_start': line, 'line_end': line, 'quote': 'First page evidence.'}
            a['insights'][0]['evidence'] = [evidence]
            document = prepared / 'analysis.json'
            document.write_text(json.dumps(a))
            published = cli('publish', prepared, document, '--library', library)
            assert published == cli('publish', prepared, document, '--library', library)
            assert kind + ' fixture' in cli('search', kind + ' fixture', '--library', library)
            evidence['quote'] = 'Invented evidence.'
            document.write_text(json.dumps(a))
            cli('publish', prepared, document, '--library', library, ok=False)
            evidence['quote'] = 'First page evidence.'
            if kind == 'pdf':
                evidence['page'] = 2
                document.write_text(json.dumps(a))
                cli('publish', prepared, document, '--library', library, ok=False)
                evidence['page'] = 1
            document.write_text(json.dumps(a))
            retained = prepared / ('pages/0001.md' if kind == 'pdf' else 'document.md')
            retained.write_text('Altered evidence.')
            cli('publish', prepared, document, '--library', library, ok=False)
        assert len(list((library / 'entries').iterdir())) == 4
    print('PASS: extraction, reuse, frame selection, timestamps, provenance, deduplication, concurrent publication, index recovery, and path containment')


if __name__ == '__main__':
    main()
    subprocess.run([str(Path.home() / '.agents/runtimes/source-insights/bin/python'),
                    str(Path(__file__).with_name('check_search.py'))], check=True)
