"""Local pinned BGE invocation; no library, storage or producer dependencies."""
import array
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

MODEL = Path(os.environ.get('KNOWLEDGE_EMBED_MODEL', Path.home() / '.cache/huggingface/hub/models--unsloth--bge-small-en-v1.5-GGUF/snapshots/395309658a295cc893b3aa279136ce84f472fc62/bge-small-en-v1.5-f16.gguf'))
MODEL_SHA = 'c5d2302edc429f679642433b9f96dd217799727a06e675abef3b40a79f5e1589'
DIM = 384
SPEC = 'bge-small-en-v1.5-f16:' + MODEL_SHA + ':cls:384:l2-normalized:480-byte-chunks:v1'

def embed(texts, query=False):
    if not texts:
        return []
    if not MODEL.is_file() or hashlib.sha256(MODEL.read_bytes()).hexdigest() != MODEL_SHA:
        raise RuntimeError('Pinned BGE model missing or changed; see references/search.md')
    texts = [('Represent this sentence for searching relevant passages: ' if query else '') + t for t in texts]
    if any(not t.strip() or '\n' in t or len(t.encode()) > 480 for t in texts):
        raise ValueError('Embedding text must be nonempty, single-line, and at most 480 UTF-8 bytes')
    vectors = []
    with tempfile.TemporaryDirectory(prefix='source-insights-embed-') as tmp:
        tmp = Path(tmp)
        for offset in range(0, len(texts), 16):
            batch = texts[offset:offset+16]
            prompt = tmp / 'input.txt'; prompt.write_text('\n'.join(batch))
            with (tmp / 'output.json').open('w') as output, (tmp / 'stderr.log').open('w') as log:
                result = subprocess.run(['llama-embedding', '-m', str(MODEL), '-f', str(prompt),
                                         '--pooling', 'cls', '--embd-normalize', '2',
                                         '--embd-output-format', 'json', '-ngl', '0',
                                         '-c', '512', '-b', '512', '-ub', '512', '-t', '4'],
                                        stdout=output, stderr=log, timeout=120)
            if result.returncode:
                raise RuntimeError('Local embedding failed: ' + (tmp / 'stderr.log').read_text()[-2000:])
            rows = json.loads((tmp / 'output.json').read_text())['data']
            if len(rows) != len(batch) or [r['index'] for r in rows] != list(range(len(batch))):
                raise RuntimeError('Embedding output count/order mismatch')
            for row in rows:
                v = row['embedding']
                if len(v) != DIM or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in v):
                    raise RuntimeError('Invalid embedding dimensions or values')
                norm = math.sqrt(sum(x*x for x in v))
                if norm < 0.001:
                    raise RuntimeError('Empty embedding')
                vectors.append(array.array('f', (x/norm for x in v)).tobytes())
    return vectors
