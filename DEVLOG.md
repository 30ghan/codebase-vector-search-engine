# Development Log

A day-by-day record of how this project was built: what was added each day, the
bugs hit, how each was diagnosed, and the measurements at each stage. For an
overview of the project, results, and how to run it, see [README.md](README.md).

## Day 1 — FastAPI framework with `/health` endpoint

- Set up the project skeleton and virtual environment.
- Added the `app` package and created the FastAPI application in `app/main.py`
  with title, description, and version metadata.
- Added a `/health` endpoint that returns `{"status": "healthy"}` as a basic
  liveness check.
- Captured the environment in `requirements.txt`.

## Day 2 — Embedding system with sentence-transformers

- Added `app/embeddings.py`.
- Loaded the `all-MiniLM-L6-v2` sentence-transformers model.
- Implemented `compute_embedding(text)` to encode text into a normalized
  384-dimensional vector and return it as a list of floats.
- Implemented `cosine_similarity(vec1, vec2)` as a dot product, which is
  equivalent to cosine similarity for normalized embeddings.
- Updated `requirements.txt` with the sentence-transformers dependencies.

## Day 3 — FAISS vector index with add and search

- Added `app/vector_index.py`.
- Created a FAISS `IndexFlatIP` index sized to the 384-dimensional embeddings,
  using inner product as the similarity metric.
- Implemented `add_vector(vector, doc_id)` to append a vector to the index.
- Implemented `search_vectors(query_vector, k=5)` to return the top-`k` matches
  as `{"id", "score"}` entries, skipping empty (`-1`) slots.
- Implemented `get_index_size()` to report the number of vectors in the index.
- Updated `requirements.txt` with `faiss-cpu` and `numpy`.

## Day 4 — Document store with SQLite and SQLAlchemy

- Added `app/db.py`.
- Configured a SQLAlchemy engine and session (`SessionLocal`) against a local
  SQLite database (`codebase_search.db`).
- Declared the SQLAlchemy `Base` and created all tables on startup via
  `Base.metadata.create_all`.
- Added `app/models.py`.
- Defined the `CodeChunk` ORM model (`code_chunks` table) with `id`, `text`,
  `file_path`, `language`, and `function_name` columns to store code snippet
  metadata alongside their vector embeddings.
- Updated `requirements.txt` with the SQLAlchemy dependency.

## Day 5 — /index Endpoint (Write Path)

**What was built:** The `/index` POST endpoint, which wires together the embedding
system, FAISS vector index, and SQLite document store into a single API call.

**How the pipeline works:**

- A user sends a POST request to `/index` with code text and metadata.
- The text and metadata are saved to SQLite, generating an auto-incrementing ID.
- The text is converted into a 384-dimensional vector using sentence-transformers.
- The vector is stored in FAISS under that same SQLite ID.
- The matching ID is the critical link between the two systems — it's what lets a
  FAISS search result later be resolved back to its stored code chunk.

**Files changed:**

- `app/main.py` — added the `/index` endpoint, the `IndexRequest` Pydantic model,
  and a database session dependency (`get_db`).

**Testing done:**

- Tested via the FastAPI `/docs` interactive page.
- Indexed three code snippets:
  - `def load_config()` from `src/utils.py` → id: 8
  - `def connect_to_database()` from `src/db.py` → id: 9
  - `def calculate_tax()` from `src/finance.py` → id: 10
- All three returned `200` with `"Indexed successfully"`.

**Errors encountered:**

- Copilot auto-inserted an unnecessary `from torch import chunk` import — removed it.
- Passed the wrong argument to `add_vector` (`code_chunk.id` twice instead of
  `vector, code_chunk.id`) — fixed.

## Day 6 — /search Endpoint (Read Path)

**What was built:** The `/search` POST endpoint, which completes the core search
engine. Users can now index code through `/index` and search it by meaning through
`/search`.

**How the search pipeline works:**

- A user sends a POST request to `/search` with a plain English query and an
  optional `k` parameter (defaults to 5).
- The query is converted into a 384-dimensional vector using the same embedding
  model used for indexing.
- FAISS searches its index for the `k` nearest vectors and returns their IDs and
  similarity scores.
- Each ID is looked up in SQLite to retrieve the actual code text, file path,
  language, and function name.
- Results are returned ranked by similarity score, best match first.
- Scores are rounded to 3 decimal places for readability.

**Files changed:**

- `app/main.py` — added the `/search` POST endpoint, the `SearchRequest` model
  (query + configurable `k`), and the `SearchResult` response model.

**Testing done:**

- Indexed three code snippets: `load_config` (`src/utils.py`),
  `connect_to_database` (`src/db.py`), and `calculate_tax` (`src/finance.py`).
- Searched with query: `"open a database connection"` (`k=3`).
- Results: `connect_to_database` ranked #1 (score 0.466) despite sharing almost no
  words with the query — confirming the search is matching by meaning, not
  keywords.

## Day 7 — Evaluation + Metrics

**What was built:** An evaluation system that measures four key metrics —
indexing speed, query latency, Recall@K, and throughput. This turns a subjective
"it works" into quantifiable numbers, and on its first run it caught a retrieval
bug that manual spot-checking had missed entirely.

**Files created:**

- `evaluation/dataset.py` — 8 labelled test pairs: code snippets paired with
  natural language queries that should match them. The queries are deliberately
  phrased differently from the code (e.g. "encrypt a user password" should match
  `hash_password`) to test genuine semantic understanding rather than keyword
  overlap.
- `evaluation/evaluate.py` — the evaluation runner. It resets the database,
  indexes the test data, runs every query, and prints a full metrics report:
  indexing speed (docs/sec), query latency (avg/min/max/p50/p95), Recall@K, and
  throughput (queries/sec).
- `debugging_recall.py` — a diagnostic script that prints a per-query HIT/MISS
  breakdown showing exactly what was returned versus what was expected.

**First evaluation run:**

- Indexing speed: 36 docs/sec (8 documents in 0.222s)
- Query latency: 8ms average, 11.2ms p95
- Throughput: 148.7 queries/sec
- Recall@3: **25%** (2/8 queries found the correct function in the top 3)

**Debugging the low recall:**

A 25% recall looked like a model quality problem, so the obvious conclusion was
that `all-MiniLM-L6-v2` — a general-purpose sentence model — simply couldn't
bridge code-specific synonyms like "encrypt" → "hash". Running
`debugging_recall.py` showed something different:

```
MISS | Query: encrypt a user password         | Expected: hash_password     | Got: ['connect_to_postgres', ...]
MISS | Query: send a notification email       | Expected: send_email        | Got: ['hash_password', ...]
MISS | Query: compute the mean of a list      | Expected: calculate_average | Got: ['send_email', ...]
MISS | Query: scale an image to dimensions    | Expected: resize_image      | Got: ['calculate_average', ...]
```

Every miss returned the snippet indexed *immediately before* the expected one.
That is an off-by-one pattern, not a semantic failure. Two other clues pointed
the same way: some `k=3` searches returned only 2 results, and the mistakes were
perfectly consistent rather than fuzzy.

**Root cause:** `add_vector(vector, doc_id)` accepted a `doc_id` but never used
it. `IndexFlatIP.add()` assigns its own sequential positions (0, 1, 2, …), and
`search_vectors` returned those positions. `/search` then looked them up as
SQLite IDs, which start at 1 — so every result was shifted by one, and FAISS
position 0 matched no database row at all. The ID link described back on Day 5
was silently broken.

Interpreting one raw FAISS result both ways makes it unambiguous:

```
Query: 'encrypt a user password'  (expected hash_password)
  FAISS returned 2  score=0.448  | as POSITION -> hash_password  | as SQLite ID -> connect_to_postgres
```

The embedding model had ranked the correct function **#1 with a strong score**
the whole time. The retrieval was working; the lookup was not.

**The fix:** Wrapped the flat index in a FAISS `IndexIDMap` and switched to
`add_with_ids`, so FAISS stores the real SQLite IDs instead of its own positions:

```python
index = faiss.IndexIDMap(faiss.IndexFlatIP(embedding_dim))

def add_vector(vector: list[float], doc_id: int) -> None:
    vec_array = np.array([vector], dtype=np.float32)
    id_array = np.array([doc_id], dtype=np.int64)
    index.add_with_ids(vec_array, id_array)
```

**Results after the fix:**

- Recall@1: **100%** (8/8)
- Recall@3: **100%** (8/8)
- Indexing speed: 73.0 docs/sec (8 documents in 0.110s)
- Query latency: 10.2ms average, 11.4ms p95
- Throughput: 96.8 queries/sec

Every query now returns its expected function as the top result, including the
ones that looked like model failures — `all-MiniLM-L6-v2` bridges "encrypt" →
"hash" and "scale" → "resize" without trouble. Only recall changed
meaningfully here; the latency and throughput differences are run-to-run noise
on a dataset this small.

**Improvement paths identified for Days 8-10:**

- Recall is saturated at 100% on 8 well-separated snippets, so the metric can't
  discriminate yet. The priority is a larger, harder dataset with near-duplicate
  and adjacent functions before drawing any conclusions about model quality.
- Enrich indexed text with docstrings, comments, or function signatures to give
  the model more context than a single line.
- Re-test a code-trained embedding model (CodeBERT, CodeT5) once the dataset is
  hard enough for the comparison to mean something.
- Add hybrid search combining vector similarity with keyword matching as a
  fallback for exact identifier lookups.

**Why this matters:** Without evaluation, this project was a demo that "seemed to
work" — the Day 6 manual test passed because the one query tried happened to be
among the cases the off-by-one didn't visibly break. The first automated run
exposed a broken ID mapping sitting in the core read path. The lesson wasn't that
the model was weak; it was that an unmeasured system hides its own bugs, and that
a suspicious metric deserves a diagnostic before it deserves an explanation.

## Day 8 — Code Parsing with Python's `ast`

**What was built:** A code parser that reads `.py` files and extracts each
function and class as its own chunk. Until now every indexed snippet had to be
pasted in by hand through `/index`; this is the piece that makes indexing a real
codebase possible.

**How the parser works:**

- `extract_functions(source_code, file_path)` parses the source into an abstract
  syntax tree with `ast.parse`, then walks it with `ast.walk` looking for
  `FunctionDef`, `AsyncFunctionDef`, and `ClassDef` nodes.
- Each node carries `lineno` and `end_lineno`, so the original source lines are
  sliced out verbatim rather than reconstructed — the indexed text is exactly what
  sits in the file, comments and formatting included.
- `ast.get_docstring(node)` pulls the docstring out alongside the code.
- Each chunk is returned as a dict with `text`, `function_name`, `file_path`,
  `language`, `start_line`, `end_line`, and `docstring` — the same shape the
  `CodeChunk` model already expects.
- `chunk_file(path)` handles one file; `chunk_directory(path)` walks a tree with
  `os.walk` and aggregates every `.py` file it finds.

**Files created:**

- `app/code_parser.py` — the three functions above.

**Design decisions:**

- Parsing with `ast` rather than regex or fixed line windows means chunks always
  align with real syntactic boundaries. A regex split cuts mid-function on nested
  defs and multi-line signatures.
- `SyntaxError` is caught and returns an empty list, so one unparseable file
  cannot abort a whole directory walk. `IOError` and `UnicodeDecodeError` are
  handled the same way in `chunk_file`.
- `chunk_directory` prunes `venv`, `.git`, `__pycache__`, `node_modules`, and
  `.venv` in place (`dirs[:] = ...`), so `os.walk` never descends into dependency
  trees. Without this, indexing the project root would pull in thousands of
  library files.

**Verified output:** `chunk_directory("app")` yielded 16 chunks at this point,
each with its own `function_name` and line range — 7 from `main.py`, 3 each from
`code_parser.py` and `vector_index.py`, 2 from `embeddings.py`, and 1 from
`models.py`. `db.py` contributes none: it is module-level configuration with no
functions or classes, which is a useful reminder that the parser indexes
definitions, not files. The same call returns 29 chunks today — Day 9 added
persistence, filters, and helper functions to `main.py` and `vector_index.py`.

**Limitation identified:** The parser is Python-only — it hardcodes
`language: "python"` and filters on `.endswith(".py")`. Other languages would need
a different parser, tree-sitter being the usual choice.

## Day 9 — Bulk Indexing, Search Filters, and Persistence

Shipped in two parts.

### Part 1 — `/index-directory`

**What was built:** A POST endpoint that takes a directory path, runs the Day 8
parser over it, and indexes every function and class it finds in a single call.

**Files changed:**

- `app/main.py` — added the `/index-directory` endpoint and the
  `IndexDirectoryRequest` model. The per-chunk write logic was pulled out of
  `/index` into a shared `store_code_chunk()` helper, so both endpoints go through
  the same path: save to SQLite, embed, add to FAISS under the SQLite ID.
- Returns `chunks_indexed` and `time_seconds`, and rejects a bad path with a 400.

### Part 2 — Filters, persistence, and three silent-failure bugs

**What was built:** Optional `language` and `file_path_contains` filters on
`/search`, FAISS persistence to disk, and fixes for three separate bugs that all
presented identically: `/search` returning `[]` with a `200` and no error.

**Bug 1 — the in-memory index vanished on restart.** FAISS lived only in a
module-level variable while SQLite persisted to disk. Every `uvicorn --reload`
restart — which fires on every `.py` save — left the database full and the index
empty:

```
SQLite rows persisted: 19
health: {'vectors_indexed': 0}
search -> 200 []
```

`search_vectors` on an empty index gets all `-1` back, skips every one, and
returns an empty list under a success status.

*Fix:* `save_index()` and `load_index()` persist the index to `faiss_index.bin`,
and a FastAPI `lifespan` hook loads it at startup. If the file is missing or its
vector count disagrees with the row count, the index is rebuilt from SQLite —
SQLite stays the source of truth, so a stale snapshot cannot wedge the service.

**Bug 2 — the language filter was case-sensitive.** The parser stores
`language: "python"` in lowercase, and the filter compared with `!=`:

```
language='python' -> 3 results
language='Python' -> 0 results    # same query
```

*Fix:* compare both sides lowercased.

**Bug 3 — post-filter starvation.** Filters were applied after the vector search,
over a fixed `k * 5` candidate window. A match ranked below that window was never
reached:

```
k=1 (fetch_k=5)  file_path_contains=models.py -> 0 results
k=2 (fetch_k=10) file_path_contains=models.py -> 1 result    # it existed all along
```

*Fix:* widen the window (×4 per round, capped at the index size) until `k` results
are found or the whole index has been scanned.

**Also fixed:**

- `/index-directory` appended a duplicate row for every chunk on each run (19 rows
  became 38, with `extract_functions` at both id 1 and id 20). It now deletes prior
  rows for the same files first, and reports `chunks_replaced`.
- `DATABASE_URL` was a relative `sqlite:///codebase_search.db`, which resolves
  against the process working directory — starting uvicorn from anywhere but the
  project root silently created a second, empty database. Both the database and
  index paths are now absolute, overridable via `DATABASE_PATH` and
  `FAISS_INDEX_PATH`.
- Embedding is batched through `compute_embeddings` instead of one model call per
  chunk.
- An empty index now returns a `503` with an explanatory message instead of `[]`,
  and `/health` reports `chunks_in_database` alongside `vectors_indexed`, flagging
  `degraded` when the two disagree.
- A `threading.Lock` guards index mutations, since uvicorn runs sync endpoints in
  a thread pool.

**Results, cold-started with nothing indexed in the process:**

```
health: {"status":"healthy","vectors_indexed":29,"chunks_in_database":29}
search unfiltered       -> 3 results (extract_functions, app\code_parser.py, 0.708)
search language=Python  -> 3 results   (was 0)
search k=1 + models.py  -> 1 result    (was 0)
```

Re-indexing the same directory holds steady at 29 rows and 29 vectors.
`language="javascript"` still returns `[]` — a genuine no-match, now
distinguishable from a broken index.

**Why this matters:** All three bugs returned `200 []`. None raised, none logged,
and two of them were introduced by the very change that made them hard to spot —
from the client, a wrong filter and an empty index look the same. The Day 7
pattern repeated: the system was silently wrong in its core read path, and only
reproducing each case separately separated the three causes.

## Day 10 — Real-Codebase Evaluation

**What was built:** A second evaluation harness that measures retrieval against
this project's own source instead of hand-written snippets, reporting Recall@1/3/5
and MRR. Day 7's evaluation had saturated at 100% on 8 well-separated snippets and
could no longer discriminate — this is the harder dataset Day 7 flagged as the
priority.

**Files created:**

- `evaluation/codebase_queries.py` — 16 natural language queries paired with the
  function or class in `app/` that should answer them, phrased the way a developer
  would ask ("write the vector index to a file on disk" → `save_index`).
- `evaluation/evaluate_codebase.py` — indexes all 29 functions and classes parsed
  from `app/`, then records the rank of the expected function for each query,
  printing that rank and the actual top hit so misses stay traceable.

**Evaluation isolation — the bug this prevented:** `evaluation/evaluate.py` calls
`reset_database()`, which deletes every row. Once FAISS was persisted on Day 9,
running the evaluation would have wiped the real indexed codebase and left the
server to rebuild its index from the 8 test snippets on next start. Both harnesses
now redirect `DATABASE_PATH` and `FAISS_INDEX_PATH` to their own files
(`eval_search.db`, `eval_codebase.db`) *before* importing anything from `app` —
those paths are read at import time, so setting them afterwards has no effect.
`reset_index()` now runs alongside `reset_database()` too, so vectors from a
previous run cannot point at deleted rows and inflate recall.

**First real-codebase run (29 chunks, 16 queries):**

- Recall@1: **75.0%**
- Recall@3: **81.2%**
- Recall@5: **93.8%**
- MRR: **0.812**
- Query latency: 19.0ms average, 47.5ms p95

The recall and MRR figures are deterministic and reproduce exactly. The latency
numbers are not: a later run of the same 16 queries gave 16.6ms average and
19.3ms p95, so that first p95 was mostly model warm-up on the opening query
rather than a representative tail.

**What the metrics exposed:** Unlike Day 7's flat 100%, these numbers
discriminate. Three queries show where the embedding model struggles:

```
#2    | write the vector index to a file on disk     | expected save_index     | top: load_index
#4    | restore a previously saved index from a file | expected load_index     | top: save_index
MISS  | count how many vectors are stored            | expected get_index_size | top: add_vectors
```

`save_index` and `load_index` swap ranks for each other's queries — their bodies
are nearly identical wrappers around `faiss.write_index` and `faiss.read_index`,
so their embeddings sit almost on top of each other. `get_index_size` is a
one-line `return index.ntotal` and misses the top 10 entirely; there is simply not
enough text to embed. That is direct evidence for Day 7's "enrich indexed text
with docstrings and signatures" improvement path — the failures cluster on the
shortest functions, not the semantically hardest ones.

**Why this matters:** A metric reading 100% is a metric that has stopped working.
Re-pointing the same evaluation at real code dropped Recall@1 to 75% and
immediately localised the weakness to short, structurally similar functions —
something no amount of additional synthetic snippets would have surfaced.
