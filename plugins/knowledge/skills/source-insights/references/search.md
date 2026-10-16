# Local search operations

The portable bootstrap uses `SOURCE_INSIGHTS_INDEX_MODE=keyword`: FTS5 only,
without a model or SQLite extension loading. Use `source-insights search QUERY`
and `source-insights reindex --rebuild`. Semantic/hybrid queries fail explicitly in
this profile. `AGENT_KNOWLEDGE_HOME` locates its runtime and
`SOURCE_INSIGHTS_LIBRARY` selects the independent library.

The neural profile below is optional. It additionally requires Python built with
SQLite extension loading, sqlite-vec, the pinned model and `llama-embedding`.
Explicitly set `SOURCE_INSIGHTS_INDEX_MODE=hybrid`, configure
`KNOWLEDGE_EMBED_MODEL=/absolute/model.gguf`, and rebuild before switching profiles.
These steps never download a model automatically. Historical `~/.agents` examples
below describe the standalone default; use your owned prefix in a portable setup.

Entry JSON, notes and evidence remain authoritative. `INDEX.md` and `search.sqlite`
are disposable derivatives. No graph database or graph extraction is installed.

Search uses SQLite FTS5 (Porter stemming), sqlite-vec 0.1.9 exact cosine search,
and equal-weight reciprocal-rank fusion. FTS covers title, summary, tags, source
identity and insight text; vectors cover claim, rationale and application.
Results retain source citations, coverage, caveats and the readable note path.
The top 50 keyword documents and 100 vector chunks supply candidates. Semantic
matches can be irrelevant; neither fusion scores nor distance establish truth.

## Runtime

The launcher automatically uses `~/.agents/runtimes/source-insights/bin/python`
for search, publish and reindex. This installation uses Python 3.12 and
`sqlite-vec==0.1.9`. To create a missing runtime (do not replace an existing one):

```sh
uv venv --python 3.12 ~/.agents/runtimes/source-insights
uv pip install --python ~/.agents/runtimes/source-insights/bin/python sqlite-vec==0.1.9
```

`llama-embedding` must be on PATH. The tested installation is llama.cpp 0.5.0.
The binary is an installed dependency, not vendored or hash-pinned by this skill.
No embedding server runs. The existing cached model is reused:

- Repository: `unsloth/bge-small-en-v1.5-GGUF`
- Revision: `395309658a295cc893b3aa279136ce84f472fc62`
- File: `bge-small-en-v1.5-f16.gguf` (67,582,560 bytes)
- SHA256: `c5d2302edc429f679642433b9f96dd217799727a06e675abef3b40a79f5e1589`
- Expected location: the standard Hugging Face cache snapshot for that revision,
  under `~/.cache/huggingface/hub/`; see `scripts/search_index.py` for the exact path.

Missing or changed model bytes cause an explicit failure. Search never downloads
models. The model produces 384-dimensional normalized vectors with CLS pooling.
It is an English model with a 512-token context; conservative 480-byte chunks avoid
a tokenizer dependency but can split words or ideas. Queries are limited to 400
UTF-8 bytes, with the BGE retrieval instruction added internally.

## Use and recovery

```sh
python3 ~/.agents/skills/source-insights/scripts/sources.py search 'prevent scope drift'
python3 ~/.agents/skills/source-insights/scripts/sources.py search '2609.24974' --mode keyword
python3 ~/.agents/skills/source-insights/scripts/sources.py reindex --rebuild
python3 ~/.agents/skills/source-insights/scripts/check.py
```

Unchanged entries reuse embeddings. New/changed entries are embedded before the
SQLite transaction; deleted entries are removed from the derived index. Full
rebuilds replace the database atomically. Search and publication share a lock, so
parallel callers wait. Metadata is scanned on each query: suitable for a personal
library, with a change journal as the upgrade if this becomes measurable overhead.

A missing database is rebuilt automatically. For corruption or incompatible
model/schema, run `reindex --rebuild`. A publication can succeed while indexing
fails: the error reports the saved note path, and reindex recovers without another
publication. Authoritative entries are never deleted by index recovery. Existing
unchanged keyword searches do not need an embedding process; initial indexing does.

Restore the archived skill bundle to roll back code. Preserve entries and rebuild
derived indexes using the selected version; the database is not a backup format.
