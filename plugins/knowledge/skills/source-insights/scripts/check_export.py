"""Public export acceptance against an isolated copy of retained evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

helper = Path(__file__).with_name('sources.py')
original = Path(sys.argv[1])
with tempfile.TemporaryDirectory(prefix='insight-export-') as tmp:
    library = Path(tmp) / 'library'
    shutil.copytree(original, library)
    def export(*args, ok=True):
        p = subprocess.run([sys.executable, str(helper), 'export', '--library', str(library), *args],
                           capture_output=True, env=dict(os.environ, PATH='/no-external-executables'))
        assert (p.returncode == 0) == ok, p.stderr.decode()
        if not ok:
            assert not p.stdout, 'Failed export emitted partial data'
            return
        assert len(p.stdout.splitlines()) == 1
        return json.loads(p.stdout)
    packet = export()
    assert packet['schema'] == 'knowledge-snapshot/v1' and packet['hits'] == []
    for entry in (library / 'entries').iterdir():
        mh = hashlib.sha256((entry/'manifest.json').read_bytes()).hexdigest()
        ah = hashlib.sha256((entry/'analysis.json').read_bytes()).hexdigest()
        assert packet['versions']['entry:'+entry.name] == hashlib.sha256(f'{mh}:{ah}'.encode()).hexdigest()
    for node in packet['nodes']:
        if node['kind'] == 'insight':
            assert node['details']['coverage'] and node['details']['evidence']
    entry = next((library/'entries').iterdir())
    manifest_path=entry/'manifest.json';original_manifest=manifest_path.read_bytes()
    data=json.loads(original_manifest);data['extraction']=None
    manifest_path.write_text(json.dumps(data))
    assert export(), 'Legacy entries with null extraction must remain exportable'
    manifest_path.write_bytes(original_manifest)
    evidence = next(iter(json.loads((entry/'manifest.json').read_text())['evidence_sha256']))
    path = entry/evidence
    old = path.read_bytes()
    path.write_bytes(old+b'\nchanged bytes\n')
    export(ok=False)
    path.write_bytes(old)
    analysis = entry/'analysis.json'
    old = analysis.read_bytes()
    data = json.loads(old)
    data['insights'][0]['evidence'][0]['quote'] = 'This quote does not occur in retained evidence.'
    analysis.write_text(json.dumps(data))
    export(ok=False)
    analysis.write_bytes(old)
    assert export() == packet
print('PASS: stdlib-only export, exact revision hashes, citations/coverage, corruption and invalid citation rejection, no partial output')
