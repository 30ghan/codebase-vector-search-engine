from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app import db
from app.db import SessionLocal
from app.models import CodeChunk
from app.embeddings import compute_embedding, compute_embeddings
from app.vector_index import (
    add_vector,
    add_vectors,
    remove_vectors,
    search_vectors,
    get_index_size,
    reset_index,
    save_index,
    load_index,
)
import os
import time
from fastapi import HTTPException
from app.code_parser import chunk_directory

# SQLite caps the number of bound parameters per statement, so IN (...) clauses
# built from indexed file paths have to be chunked.
SQL_PARAM_BATCH = 500


def rebuild_index_from_db() -> int:
    """Recompute every embedding in SQLite and repopulate FAISS from scratch."""
    session = SessionLocal()
    try:
        chunks = session.query(CodeChunk).all()
        reset_index()
        if not chunks:
            return 0
        vectors = compute_embeddings([chunk.text for chunk in chunks])
        add_vectors(vectors, [chunk.id for chunk in chunks])
        save_index()
        return len(chunks)
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The FAISS index lives in memory, so every uvicorn --reload restart dropped
    # it while SQLite kept its rows - leaving /search silently returning [].
    session = SessionLocal()
    try:
        row_count = session.query(CodeChunk).count()
    finally:
        session.close()

    if load_index() and get_index_size() == row_count:
        print(f"[startup] loaded FAISS index from disk ({get_index_size()} vectors)")
    else:
        count = rebuild_index_from_db()
        print(f"[startup] rebuilt FAISS index from SQLite ({count} vectors)")
    yield


app = FastAPI(
    title = "Codebase Semantic Search Engine",
    description = "A Semantic code search engine using FastAPI, FAISS and sentence transformers for vector based code retrieval",
    version = "1.0.0",
    lifespan = lifespan,
)

@app.get("/health")
def health_check():
    session = SessionLocal()
    try:
        row_count = session.query(CodeChunk).count()
    finally:
        session.close()

    vectors_indexed = get_index_size()
    return {
        "status": "healthy" if vectors_indexed == row_count else "degraded",
        "vectors_indexed": vectors_indexed,
        "chunks_in_database": row_count,
    }

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def store_code_chunk (db: Session, text: str, file_path: str = None, language: str = None,
                      function_name : str = None) -> int :
    code_chunk = CodeChunk(
        text=text,
        file_path=file_path,
        language=language,
        function_name=function_name,
    )
    db.add(code_chunk)
    db.commit()
    db.refresh(code_chunk)

    vector = compute_embedding(code_chunk.text)
    add_vector(vector, code_chunk.id)

    return code_chunk.id

class IndexRequest(BaseModel):
    text: str
    file_path: str = None
    language: str = None
    function_name: str = None

class SearchRequest(BaseModel):
    query: str
    k: int = 5
    language: str = None
    file_path_contains: str = None

class SearchResult(BaseModel):
    id: int
    text: str
    file_path: str = None
    language: str = None
    function_name: str = None
    score: float

class IndexDirectoryRequest(BaseModel):
    directory_path: str

@app.post("/index")
def index_code(request: IndexRequest, db: Session = Depends(get_db)):
    doc_id = store_code_chunk(
        db,
        text=request.text,
        file_path=request.file_path,
        language=request.language,
        function_name=request.function_name,
    )
    save_index()
    return {"id": doc_id, "message": "Indexed successfully"}

@app.post("/index-directory")
def index_directory(request: IndexDirectoryRequest, db: Session = Depends(get_db)):
    if not os.path.isdir(request.directory_path):
        raise HTTPException(status_code=400, detail="Directory not found")

    start_time = time.time()
    chunks = chunk_directory(request.directory_path)

    if not chunks:
        return {
            "chunks_indexed": 0,
            "chunks_replaced": 0,
            "time_seconds": round(time.time() - start_time, 2),
            "message": "No indexable code found in directory",
        }

    # Re-indexing the same directory used to append a second copy of every chunk.
    # Drop the previous rows (and their vectors) so indexing is idempotent.
    file_paths = sorted({chunk["file_path"] for chunk in chunks})
    replaced = 0
    for start in range(0, len(file_paths), SQL_PARAM_BATCH):
        batch = file_paths[start:start + SQL_PARAM_BATCH]
        stale_ids = [
            row.id for row in
            db.query(CodeChunk.id).filter(CodeChunk.file_path.in_(batch)).all()
        ]
        if not stale_ids:
            continue
        remove_vectors(stale_ids)
        db.query(CodeChunk).filter(CodeChunk.id.in_(stale_ids)).delete(synchronize_session=False)
        replaced += len(stale_ids)
    if replaced:
        db.commit()

    rows = [
        CodeChunk(
            text=chunk["text"],
            file_path=chunk["file_path"],
            language=chunk["language"],
            function_name=chunk["function_name"],
        )
        for chunk in chunks
    ]
    db.add_all(rows)
    db.commit()

    # One batched encode instead of one model call per chunk.
    vectors = compute_embeddings([row.text for row in rows])
    add_vectors(vectors, [row.id for row in rows])
    save_index()

    time_elapsed = time.time() - start_time

    return {
        "chunks_indexed": len(rows),
        "chunks_replaced": replaced,
        "time_seconds": round(time_elapsed, 2),
        "message": "Directory indexed successfully",
    }


def _matches_filters(code_chunk: CodeChunk, request: SearchRequest) -> bool:
    if request.language:
        # Stored languages are lowercase ("python"), so an exact compare made
        # language="Python" match nothing.
        if (code_chunk.language or "").lower() != request.language.lower():
            return False

    if request.file_path_contains:
        stored_path = (code_chunk.file_path or "").replace("\\", "/").lower()
        wanted = request.file_path_contains.replace("\\", "/").lower()
        if wanted not in stored_path:
            return False

    return True


@app.post("/search")
def search_code(request: SearchRequest, db: Session = Depends(get_db)):
    if request.k <= 0:
        raise HTTPException(status_code=400, detail="k must be greater than 0")

    index_size = get_index_size()
    if index_size == 0:
        raise HTTPException(
            status_code=503,
            detail="Search index is empty - index code via /index or /index-directory first.",
        )

    query_vector = compute_embedding(request.query)

    has_filters = bool(request.language or request.file_path_contains)
    fetch_k = min(request.k * 5 if has_filters else request.k, index_size)

    # Filters are applied after the vector search, so a narrow filter can starve
    # a fixed fetch_k. Widen the candidate window until k results are found or
    # the whole index has been scanned.
    while True:
        results = search_vectors(query_vector, k=fetch_k)

        chunks_by_id = {
            code_chunk.id: code_chunk
            for code_chunk in db.query(CodeChunk).filter(
                CodeChunk.id.in_([result["id"] for result in results])
            ).all()
        }

        search_results = []
        for result in results:
            code_chunk = chunks_by_id.get(result["id"])
            if code_chunk is None or not _matches_filters(code_chunk, request):
                continue

            search_results.append(SearchResult(
                id=code_chunk.id,
                text=code_chunk.text,
                file_path=code_chunk.file_path,
                language=code_chunk.language,
                function_name=code_chunk.function_name,
                score=round(result["score"], 3),
            ))

            if len(search_results) >= request.k:
                break

        if len(search_results) >= request.k or fetch_k >= index_size:
            return search_results

        fetch_k = min(fetch_k * 4, index_size)
