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
