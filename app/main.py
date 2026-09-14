from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import CodeChunk
from app.embeddings import compute_embedding
from app.vector_index import add_vector

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