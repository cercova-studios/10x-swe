"""Derived SQLite FTS5 + sqlite-vec index. Caller holds the library flock."""
import array
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile

LEXICAL_ONLY = os.environ.get('SOURCE_INSIGHTS_INDEX_MODE') == 'keyword'
MODEL = Path(os.environ.get('KNOWLEDGE_EMBED_MODEL', Path.home() / '.cache/huggingface/hub/models--unsloth--bge-small-en-v1.5-GGUF/snapshots/395309658a295cc893b3aa279136ce84f472fc62/bge-small-en-v1.5-f16.gguf'))
MODEL_SHA = 'c5d2302edc429f679642433b9f96dd217799727a06e675abef3b40a79f5e1589'
SPEC = 'bge-small-en-v1.5-f16:' + MODEL_SHA + ':cls:384:l2-normalized:480-byte-chunks:v1'
if LEXICAL_ONLY:
    SPEC = 'keyword-fts5-porter-unicode61:v1'
DIM = 384


def chunks(text):
    # ponytail: byte-bounded chunks avoid a tokenizer dependency; semantic boundaries may split.
    parts, current, length = [], [], 0
    for char in ' '.join(text.split()):
        width = len(char.encode('utf-8'))
        if length + width > 480:
            parts.append(''.join(current)); current, length = [], 0
        current.append(char); length += width
    if current:
        parts.append(''.join(current))
    return parts


from local_embeddings import embed


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    if LEXICAL_ONLY:
        return db
    if not hasattr(db, 'enable_load_extension'):
        db.close()
        raise RuntimeError('Neural profile requires Python SQLite extension loading; the keyword profile does not')
    import sqlite_vec
    db.enable_load_extension(True)
    try:
        sqlite_vec.load(db)
    finally:
        db.enable_load_extension(False)
    return db


def initialize(db):
    db.executescript('''
        CREATE TABLE settings(spec TEXT NOT NULL);
        CREATE TABLE entries(entry TEXT PRIMARY KEY, fingerprint TEXT NOT NULL);
        CREATE TABLE docs(id INTEGER PRIMARY KEY, entry TEXT NOT NULL, ordinal INTEGER NOT NULL,
                          payload TEXT NOT NULL, body TEXT NOT NULL);
        CREATE INDEX docs_entry ON docs(entry);
        CREATE VIRTUAL TABLE words USING fts5(body, tokenize='porter unicode61');
        CREATE TABLE chunks(id INTEGER PRIMARY KEY, doc INTEGER NOT NULL);
        CREATE INDEX chunks_doc ON chunks(doc);
    ''')
    if not LEXICAL_ONLY:
        db.execute('CREATE VIRTUAL TABLE vectors USING vec0(embedding float[384] distance_metric=cosine)')
    db.execute('INSERT INTO settings VALUES (?)', (SPEC,))
    db.commit()


def entries(library):
    found = {}
    for path in sorted((library / 'entries').glob('*/analysis.json')):
        if not path.parent.resolve().is_relative_to(library):
            raise ValueError('Entry path escaped library')
        manifest = path.parent / 'manifest.json'
        if not path.resolve().is_relative_to(library) or not manifest.resolve().is_relative_to(library):
            raise ValueError('Entry metadata escaped library')
        # Immutable entry metadata is small; hash it so edits cannot silently stale the index.
        raw, meta = path.read_bytes(), manifest.read_bytes()
        found[path.parent.name] = (hashlib.sha256(raw+b'\0'+meta).hexdigest(), raw, meta)
    return found


def update(db, found):
    if db.execute('SELECT spec FROM settings').fetchall() != [(SPEC,)]:
        raise RuntimeError('Search model/schema changed; run reindex --rebuild')
    previous = dict(db.execute('SELECT entry,fingerprint FROM entries'))
    changed = {key for key, value in found.items() if previous.get(key) != value[0]}
    removed = set(previous) - set(found)
    pending = []
    for key in sorted(changed):
        fingerprint, raw, meta = found[key]
        a, m = json.loads(raw), json.loads(meta)
        for ordinal, insight in enumerate(a['insights']):
            body = '\n'.join([a['title'], a['summary'], ' '.join(a['tags']), m['source'],
                              m['source_id'], insight['claim'], insight['why_it_matters'],
                              insight['application'], insight['caveats']])
            payload = dict(title=a['title'], summary=a['summary'], claim=insight['claim'],
                           status=insight['status'], application=insight['application'],
                           caveats=insight['caveats'], evidence=insight['evidence'],
                           source=m['source'], kind=m['kind'], published=m.get('published'),
                           coverage=a['coverage'], insight=ordinal+1)
            semantic = [] if LEXICAL_ONLY else chunks(insight['claim'] + ' ' + insight['why_it_matters'] + ' ' + insight['application'])
            pending.append((key, ordinal, body, payload, semantic))
    all_vectors = iter(embed([part for item in pending for part in item[4]]))
    with db:
        for key in sorted(changed | removed):
            for (doc,) in db.execute('SELECT id FROM docs WHERE entry=?', (key,)).fetchall():
                ids = db.execute('SELECT id FROM chunks WHERE doc=?', (doc,)).fetchall()
                if not LEXICAL_ONLY:
                    db.executemany('DELETE FROM vectors WHERE rowid=?', ids)
                db.execute('DELETE FROM chunks WHERE doc=?', (doc,))
                db.execute('DELETE FROM words WHERE rowid=?', (doc,))
            db.execute('DELETE FROM docs WHERE entry=?', (key,))
            db.execute('DELETE FROM entries WHERE entry=?', (key,))
        for key, ordinal, body, payload, parts in pending:
            doc = db.execute('INSERT INTO docs(entry,ordinal,payload,body) VALUES (?,?,?,?)',
                             (key, ordinal, json.dumps(payload), body)).lastrowid
            db.execute('INSERT INTO words(rowid,body) VALUES (?,?)', (doc, body))
            for part in parts:
                chunk = db.execute('INSERT INTO chunks(doc) VALUES (?)', (doc,)).lastrowid
                db.execute('INSERT INTO vectors(rowid,embedding) VALUES (?,?)', (chunk, next(all_vectors)))
        db.executemany('INSERT INTO entries VALUES (?,?)', [(key,found[key][0]) for key in changed])


def sync(library, rebuild=False):
    library = library.resolve()
    path = library / 'search.sqlite'
    found = entries(library)
    if rebuild or not path.exists():
        fd, name = tempfile.mkstemp(prefix='.search-', suffix='.sqlite', dir=library)
        os.close(fd)
        try:
            db = connect(name)
            try:
                initialize(db); update(db, found)
            finally:
                db.close()
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
    else:
        db = connect(path)
        try:
            update(db, found)
        finally:
            db.close()


def search(library, query, mode='hybrid', limit=5):
    if LEXICAL_ONLY and mode != 'keyword':
        raise RuntimeError('This index uses the explicit keyword profile; configure local embeddings and rebuild before hybrid/semantic retrieval')
    query = ' '.join(query.split())
    if not query or len(query.encode()) > 400:
        raise ValueError('Search query must contain 1–400 UTF-8 bytes')
    sync(library)
    db = connect(library / 'search.sqlite')
    try:
        keyword, semantic, distances = [], [], {}
        if mode in ('hybrid','keyword'):
            terms = list(dict.fromkeys(re.findall(r'\w+',query)))
            if terms:
                expression = ' OR '.join('"'+term+'"' for term in terms)
                keyword = [r[0] for r in db.execute('SELECT rowid FROM words WHERE words MATCH ? ORDER BY rank LIMIT 50', (expression,))]
        count = db.execute('SELECT count(*) FROM chunks').fetchone()[0]
        if count and mode in ('hybrid','semantic'):
            vector = embed([query], query=True)[0]
            rows = db.execute('SELECT rowid,distance FROM vectors WHERE embedding MATCH ? AND k=? ORDER BY distance', (vector,min(count,100))).fetchall()
            for chunk, distance in rows:
                doc = db.execute('SELECT doc FROM chunks WHERE id=?', (chunk,)).fetchone()[0]
                if doc not in distances:
                    distances[doc]=distance; semantic.append(doc)
        scores = {}
        # Reciprocal-rank fusion avoids treating BM25 and cosine as comparable units.
        for ranking in (keyword, semantic):
            for rank, doc in enumerate(ranking,1):
                scores[doc] = scores.get(doc,0) + 1/(60+rank)
        for doc in sorted(scores,key=lambda d:(-scores[d],d))[:limit]:
            key, payload = db.execute('SELECT entry,payload FROM docs WHERE id=?',(doc,)).fetchone()
            result=json.loads(payload)
            result.update(note=str(library/'entries'/key/'note.md'),score=scores[doc],mode=mode,
                          matched_by=[name for name,ranking in [('keyword',keyword),('semantic',semantic)] if doc in ranking])
            if doc in distances:
                result['cosine_distance']=distances[doc]
            yield result
    finally:
        db.close()
