from app.embeddings import compute_embedding
from app.vector_index import add_vector, search_vectors, get_index_size
from app.db import SessionLocal
from app.models import CodeChunk
from evaluation.dataset import test_snippets, test_queries

db = SessionLocal()

# Clear old data and re-index
db.query(CodeChunk).delete()
db.commit()

for snippet in test_snippets:
    code_chunk = CodeChunk(
        text=snippet["text"],
        file_path=snippet.get("file_path"),
        language=snippet.get("language"),
        function_name=snippet.get("function_name"),
    )
    db.add(code_chunk)
    db.commit()
    db.refresh(code_chunk)
    vector = compute_embedding(code_chunk.text)
    add_vector(vector, code_chunk.id)

print(f"Indexed {get_index_size()} documents\n")

# Now search
for test in test_queries:
    query_vector = compute_embedding(test["query"])
    results = search_vectors(query_vector, k=3)
    top_functions = []
    for r in results:
        chunk = db.query(CodeChunk).filter(CodeChunk.id == r["id"]).first()
        if chunk:
            top_functions.append(chunk.function_name)
    expected = test["expected_function"]
    hit = "HIT" if expected in top_functions else "MISS"
    print(f"{hit} | Query: {test['query']:<45} | Expected: {expected:<25} | Got: {top_functions}")

db.close()
