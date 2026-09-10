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
- **Uvicorn** – ASGI server

## Project structure

```
app/
  __init__.py
  main.py           # FastAPI app and /health endpoint
  embeddings.py     # embedding + similarity helpers
  vector_index.py   # FAISS index: add and search vectors
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
