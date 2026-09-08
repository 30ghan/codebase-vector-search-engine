from fastapi import FastAPI

app = FastAPI(
    title = "Codebase Semantic Search Engine", 
    description = "A Semantic code search engine using FastAPI, FAISS and sentence transformers for vector based code retrieval", 
    version = "1.0.0",
)

@app.get("/health")
def health_check():
    return {"status": "healthy"}
