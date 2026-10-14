# Codebase Semantic Search Engine

A search engine for Python source code that matches on meaning rather than
keywords. Files are parsed with Python's `ast` module and split at function and
class boundaries, so each indexed unit is a complete definition rather than an
arbitrary line window. Each chunk is embedded with `all-MiniLM-L6-v2` into a
384-dimensional vector and stored in a FAISS index, while its text and metadata
live in SQLite. A query is embedded with the same model and compared against the
index, so `"measure how alike two vectors are"` returns `cosine_similarity`
without sharing a single word with it. Exposed as a FastAPI service with
endpoints for indexing a snippet, bulk-indexing a directory, and searching with
optional language and file-path filters.

## Results

Benchmark: **16 natural-language queries over this project's own 29 functions and
classes** in `app/`. Each query names a target function, and the metric is where
that function appears in the ranked results. Figures below are from a single run
on CPU (second consecutive run, so the model and its files are warm).

| Metric | Result |
| --- | --- |
| Recall@1 | 75.0% |
| Recall@3 | 81.2% |
| Recall@5 | 93.8% |
| MRR | 0.812 |
| Query latency (average) | 16.9 ms |
| Query latency (p95) | 18.3 ms |
| Indexing speed | 41.9 chunks/sec (29 chunks in 0.69 s) |

Retrieval figures are deterministic and reproduce exactly between runs; the
latency numbers vary by a millisecond or two. This is a small benchmark written
by the same person who wrote the code being searched — see
[Limitations](#limitations--future-work).

Reproduce with `python -m evaluation.evaluate_codebase`.

## Architecture

Two paths through the same embedding model. The write path turns source files
into vectors; the read path turns a query into the same kind of vector and looks
for neighbours.

```
WRITE PATH   POST /index-directory
=====================================================================

  app/*.py
     |
     v
  code_parser.py          ast.walk -> FunctionDef, AsyncFunctionDef,
     |                    ClassDef; source sliced by lineno/end_lineno
     v
  SQLite  code_chunks     INSERT -> auto-increment id
     |                    (text, file_path, language, function_name)
     v
  embeddings.py           all-MiniLM-L6-v2 -> normalised 384-d vector
     |
     v
  FAISS IndexIDMap        add_with_ids(vector, sqlite_id)
                          <- the id is the only link between the two


READ PATH    POST /search
=====================================================================

  "measure how alike two vectors are"
     |
     v
  embeddings.py           same model -> 384-d query vector
     |
     v
  FAISS .search(k)        inner product on normalised vectors
     |                    = cosine similarity -> [(id, score), ...]
     v
  SQLite lookup by id     -> text, file_path, language, function_name
     |
     v
  optional filters        language, file_path_contains
     |
     v
  ranked results          highest score first
```

**SQLite is the source of truth.** FAISS stores only vectors keyed by SQLite row
id — never any text — so the index is a derived cache rather than primary data.
On startup the service loads `faiss_index.bin` from disk, but if that file is
missing or its vector count disagrees with the row count, the index is rebuilt by
re-embedding every row in SQLite. A deleted or stale index file is therefore a
recoverable condition, not data loss.

## Tech stack

- **FastAPI** / **Uvicorn** — HTTP API and ASGI server
- **sentence-transformers** (`all-MiniLM-L6-v2`) — 384-dimensional embeddings
- **FAISS** (`faiss-cpu`) — `IndexIDMap` over `IndexFlatIP` for vector search
- **SQLAlchemy** + **SQLite** — chunk text and metadata
- **NumPy** — array handling at the FAISS boundary
- **Python `ast`** (standard library) — function- and class-level chunking

## API

| Method | Endpoint | Body | Returns |
| --- | --- | --- | --- |
| `GET` | `/health` | — | `status`, `vectors_indexed`, `chunks_in_database` |
| `POST` | `/index` | `text`, optional `file_path`, `language`, `function_name` | `id`, `message` |
| `POST` | `/index-directory` | `directory_path` | `chunks_indexed`, `chunks_replaced`, `time_seconds`, `message` |
| `POST` | `/search` | `query`, `k` (default 5), optional `language`, `file_path_contains` | ranked list of matches with `score` |

`/health` reports `degraded` when the FAISS vector count and the SQLite row count
disagree. `/search` returns `503` on an empty index rather than an empty list, and
`400` when `k <= 0`. `/index-directory` is idempotent: re-running it on the same
directory replaces the previous chunks for those files instead of duplicating them.

Search filters are applied after the vector search, and the candidate window
widens automatically until `k` matches are found or the whole index has been
scanned. `language` matching is case-insensitive; `file_path_contains` is a
case-insensitive substring test that normalises path separators, so `app/db.py`
matches a stored `app\db.py`.

**Example request**

```bash
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "measure how alike two vectors are", "k": 2}'
```

**Actual response** (against this repo's own `app/` folder, `text` of the second
result abbreviated):

```json
[
  {
    "id": 6,
    "text": "def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:\n    dot_product = sum(a*b for a, b in zip(vec1, vec2))\n    return dot_product",
    "file_path": "app\\embeddings.py",
    "language": "python",
    "function_name": "cosine_similarity",
    "score": 0.571
  },
  {
    "id": 25,
    "text": "def search_vectors(query_vector: list[float], k: int = 5) -> list[dict]:\n    if k <= 0 or index.ntotal == 0:\n        return []\n    ...",
    "file_path": "app\\vector_index.py",
    "language": "python",
    "function_name": "search_vectors",
    "score": 0.407
  }
]
```

Neither result shares a word with the query. With filters applied —
`{"query": "write the index to disk", "k": 1, "language": "python",
"file_path_contains": "vector_index"}` — the top hit is `save_index` at `0.567`.

## Quickstart

```bash
python -m venv venv
venv\Scripts\activate              # Windows; use source venv/bin/activate on Unix
pip install -r requirements.txt
uvicorn app.main:app --reload      # serves on http://127.0.0.1:8000
```

Index this project's own source, then search it:

```bash
curl -X POST http://127.0.0.1:8000/index-directory \
  -H "Content-Type: application/json" \
  -d '{"directory_path": "app"}'
# {"chunks_indexed":29,"chunks_replaced":0,"time_seconds":1.05,"message":"Directory indexed successfully"}
# running it again returns "chunks_replaced":29 - the same 29 chunks, not 58

curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "parse python source into functions", "k": 3}'
```

Confirm what is loaded at any point with `curl http://127.0.0.1:8000/health`.
Interactive docs are at `http://127.0.0.1:8000/docs`.

The first run downloads the embedding model (~88 MB on disk) and takes noticeably
longer than later ones.

## Evaluation

Two harnesses, both runnable without a server:

```bash
python -m evaluation.evaluate            # 8 hand-written snippets, Recall@3 + throughput
python -m evaluation.evaluate_codebase   # 16 queries over app/, Recall@1/3/5 + MRR
```

- **Recall@K** — the fraction of queries whose target function appears anywhere in
  the top K results. Measures whether the right answer was retrieved at all.
- **MRR** (mean reciprocal rank) — the average of `1/rank` of the target across
  queries, so rank 1 scores 1.0 and rank 2 scores 0.5. Measures how highly the
  right answer was ranked, not just whether it was found.

Both harnesses redirect `DATABASE_PATH` and `FAISS_INDEX_PATH` to their own
scratch files before importing anything from `app`, because both delete every row
before indexing. Those paths are read at import time, so the redirect has to
happen first. The same guard is in `debugging_recall.py`, a per-query HIT/MISS
diagnostic. Running any of them leaves `codebase_search.db` and `faiss_index.bin`
byte-identical.

## Engineering highlights

- **A broken ID mapping held recall at 25%.** `add_vector` accepted a `doc_id` and
  silently ignored it: `IndexFlatIP.add()` assigns its own sequential positions,
  so every search result was looked up in SQLite under the wrong key — off by one,
  with position 0 matching no row at all. The numbers looked like a weak embedding
  model. A per-query diagnostic showed every miss returning the snippet indexed
  immediately *before* the expected one, which is an off-by-one signature, not a
  semantic failure. Switching to `IndexIDMap` with `add_with_ids` took Recall@3
  from 25% to 100%; the model had been ranking the right answer first all along.
- **Three separate bugs all returned `200 []`.** The in-memory FAISS index was
  lost on every `uvicorn --reload` restart while SQLite kept its rows; a
  case-sensitive filter made `language="Python"` match nothing where `"python"`
  matched three; and post-filter starvation (next bullet) hid real matches.
  Fixes: persist the index to disk with a startup rebuild from SQLite whenever
  the vector and row counts disagree, compare languages case-insensitively, and
  return `503` on an empty index instead of `[]`, so a broken index can no
  longer look like "no matches".
- **Post-filter starvation.** Filters ran after the vector search over a fixed
  `k * 5` candidate window, so a match ranked below that window was unreachable:
  `k=1` returned nothing while `k=2` returned the result that had existed all
  along. The window now widens until `k` matches are found or the index is
  exhausted.
- **Evaluation could destroy the data it measured.** Both harnesses call
  `reset_database()`; once the index was persisted to disk, a single evaluation run
  would have wiped the real indexed codebase and left the server rebuilding from 8
  test snippets. Each harness now runs against its own database and index file,
  set before the first `app` import.

Most of these were found by measuring rather than by reading the code — the full
investigation for each is in [DEVLOG.md](DEVLOG.md).

## Limitations & future work

- **Python only.** The parser is built on Python's `ast`, hardcodes
  `language: "python"`, and filters on `.py`. Other languages would need a
  different front end — tree-sitter being the usual choice.
- **Weak on very short and near-symmetric functions.** `save_index` and
  `load_index` swap ranks for each other's queries: both are short wrappers around
  `faiss.write_index` / `faiss.read_index`, so their embeddings nearly coincide.
  `get_index_size` is a one-line `return index.ntotal` and misses the top 10
  entirely — there is not enough text to embed. The failures cluster on the
  shortest definitions, not the semantically hardest ones.
- **The benchmark is small and self-written.** 16 queries over 29 functions,
  authored by the same person as the code. Enough to catch regressions and
  localise weaknesses, not enough to support a general claim about retrieval
  quality.
- **Next steps**, in the order the results suggest: embed the function name,
  signature, and docstring alongside the body, since the current failures are all
  cases of too little text; add hybrid keyword-plus-vector search for exact
  identifier lookups, which vector search handles poorly; and re-test a
  code-trained embedding model (CodeBERT, CodeT5) now that the benchmark is hard
  enough for the comparison to mean something.

## Development log

[DEVLOG.md](DEVLOG.md) has the day-by-day build log, Days 1–10 — what was built
each day, the bugs hit, how each was diagnosed, and the measurements at each stage.
