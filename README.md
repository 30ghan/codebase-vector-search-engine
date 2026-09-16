# codebase-vector-search-engine

Semantic code search engine built with FastAPI, FAISS, and sentence transformers.
It supports vector-based search over code snippets for fast, relevant retrieval,
with a focus on a developer-friendly workflow and lightweight embeddings for quick
experimentation.

## Overview

The project turns code snippets into dense vector embeddings and stores them in a
FAISS index so they can be searched by meaning rather than exact keywords. A query
is embedded with the same model and compared against the index to return the most
similar snippets.

## Tech stack

- **FastAPI** – HTTP API layer
- **sentence-transformers** (`all-MiniLM-L6-v2`) – 384-dimensional text embeddings
- **FAISS** (`faiss-cpu`) – vector index and similarity search
- **NumPy** – array handling for index operations
- **SQLAlchemy** + **SQLite** – document store for code chunk metadata
- **Uvicorn** – ASGI server

## Project structure

```
app/
  __init__.py
  main.py           # FastAPI app and /health endpoint
  embeddings.py     # embedding + similarity helpers
  vector_index.py   # FAISS index: add and search vectors
  db.py             # SQLAlchemy engine/session setup
  models.py         # CodeChunk ORM model
requirements.txt
```

## Progress log

### Day 1 — FastAPI framework with `/health` endpoint

- Set up the project skeleton and virtual environment.
- Added the `app` package and created the FastAPI application in `app/main.py`
  with title, description, and version metadata.
- Added a `/health` endpoint that returns `{"status": "healthy"}` as a basic
  liveness check.
- Captured the environment in `requirements.txt`.

### Day 2 — Embedding system with sentence-transformers

- Added `app/embeddings.py`.
- Loaded the `all-MiniLM-L6-v2` sentence-transformers model.
- Implemented `compute_embedding(text)` to encode text into a normalized
  384-dimensional vector and return it as a list of floats.
- Implemented `cosine_similarity(vec1, vec2)` as a dot product, which is
  equivalent to cosine similarity for normalized embeddings.
- Updated `requirements.txt` with the sentence-transformers dependencies.

### Day 3 — FAISS vector index with add and search

- Added `app/vector_index.py`.
- Created a FAISS `IndexFlatIP` index sized to the 384-dimensional embeddings,
  using inner product as the similarity metric.
- Implemented `add_vector(vector, doc_id)` to append a vector to the index.
- Implemented `search_vectors(query_vector, k=5)` to return the top-`k` matches
  as `{"id", "score"}` entries, skipping empty (`-1`) slots.
- Implemented `get_index_size()` to report the number of vectors in the index.
- Updated `requirements.txt` with `faiss-cpu` and `numpy`.

### Day 4 — Document store with SQLite and SQLAlchemy

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

## Running the API

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then check the health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

## Day 5: /index Endpoint (Write Path)

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

## Day 6: /search Endpoint (Read Path)

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

## Day 7: Evaluation + Metrics

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
