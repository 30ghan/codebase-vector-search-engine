from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app import db
from app.db import SessionLocal
from app.models import CodeChunk
from app.embeddings import compute_embedding
from app.vector_index import add_vector, search_vectors
import os
import time
from fastapi import HTTPException
from app.code_parser import chunk_directory

app = FastAPI(
    title = "Codebase Semantic Search Engine", 
    description = "A Semantic code search engine using FastAPI, FAISS and sentence transformers for vector based code retrieval", 
    version = "1.0.0",
)

@app.get("/health")
def health_check():
    return {"status": "healthy"}

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
    return {"id": doc_id, "message": "Indexed successfully"}

@app.post("/index-directory")
def index_directory(request: IndexDirectoryRequest, db: Session = Depends(get_db)):
    if not os.path.isdir(request.directory_path):
        raise HTTPException(status_code=400, detail="Directory not found")

    start_time = time.time()
    chunks = chunk_directory(request.directory_path)

    for chunk in chunks:
        store_code_chunk(
            db,
            text=chunk["text"],
            file_path=chunk["file_path"],
            language=chunk["language"],
            function_name=chunk["function_name"],
        )

    time_elapsed = time.time() - start_time

    return {
        "chunks_indexed": len(chunks),
        "time_seconds": round(time_elapsed, 2),
        "message": "Directory indexed successfully",
    }

@app.post("/search")
def search_code(request: SearchRequest, db: Session = Depends(get_db)):
    query_vector = compute_embedding(request.query)
    results = search_vectors(query_vector, k=request.k)
    search_results = []
    for result in results:
        code_chunk = db.query(CodeChunk).filter(CodeChunk.id == result["id"]).first()
        if code_chunk:
            search_results.append(SearchResult(
                id=code_chunk.id,
                text=code_chunk.text,
                file_path=code_chunk.file_path,
                language=code_chunk.language,
                function_name=code_chunk.function_name,
                score=round(result["score"], 3)
            ))
    return search_results