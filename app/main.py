from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import CodeChunk
from app.embeddings import compute_embedding
from app.vector_index import add_vector, search_vectors

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


@app.post("/index")
def index_code(request: IndexRequest, db: Session = Depends(get_db)):
    code_chunk = CodeChunk(
        text=request.text,
        file_path=request.file_path,
        language=request.language,
        function_name=request.function_name,
        
    )
    db.add(code_chunk)
    db.commit()
    db.refresh(code_chunk)

    vector = compute_embedding(code_chunk.text)
    add_vector(vector, code_chunk.id)

    return {"id": code_chunk.id, "message": "Indexed successfully"}

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