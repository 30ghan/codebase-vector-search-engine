import os 

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["DATABASE_PATH"] = os.path.join(EVAL_DIR, "eval_codebase.db")
os.environ["FAISS_INDEX_PATH"] = os.path.join(EVAL_DIR, "eval_codebase_index.bin")

import time 
from app.db import SessionLocal
from app.models import CodeChunk
from app.embeddings import compute_embedding
from app.vector_index import add_vector, search_vectors, get_index_size, reset_index
from app.code_parser import chunk_directory
from evaluation.codebase_queries import codebase_queries

PROJECT_ROOT = os.path.dirname(EVAL_DIR)
APP_DIR = os.path.join(PROJECT_ROOT, "app")


def index_codebase():
    db = SessionLocal()
    db.query(CodeChunk).delete()
    db.commit()
    reset_index()

    chunks = chunk_directory(APP_DIR)
    start_time = time.time()

    for chunk in chunks:
        code_chunk = CodeChunk(
            text=chunk["text"],
            file_path=chunk["file_path"],
            language=chunk["language"],
            function_name=chunk["function_name"],
        )
        db.add(code_chunk)
        db.commit()
        db.refresh(code_chunk)
        add_vector(compute_embedding(code_chunk.text), code_chunk.id)

    time_elapsed = time.time() - start_time
    indexed_names = {chunk["function_name"] for chunk in chunks}
    db.close()
    return len(chunks), time_elapsed, indexed_names


def find_rank(db, query: str, expected: str, max_k: int = 10):
    start_time = time.time()
    query_vector = compute_embedding(query)
    results = search_vectors(query_vector, k=max_k)
    latency_ms = (time.time() - start_time) * 1000

    top_result = None
    for position, result in enumerate(results, start=1):
        code_chunk = db.query(CodeChunk).filter(CodeChunk.id == result["id"]).first()
        if not code_chunk:
            continue
        if position == 1:
            top_result = code_chunk.function_name
        if code_chunk.function_name == expected:
            return position, top_result, latency_ms

    return None, top_result, latency_ms


def run_codebase_evaluation():
    print("=" * 60)
    print("REAL CODEBASE EVALUATION")
    print("=" * 60)

    num_chunks, index_time, indexed_names = index_codebase()
    print(f"\nIndexed {num_chunks} functions/classes from app/ in {index_time:.2f}s "
          f"({num_chunks / index_time:.1f} chunks/sec)")
    print(f"Vectors in index: {get_index_size()}\n")

    db = SessionLocal()
    ranks = []
    latencies = []

    for test in codebase_queries:
        expected = test["expected_function"]
        if expected not in indexed_names:
            print(f"SKIP  | '{expected}' not found in codebase — check the name")
            continue

        rank, top_result, latency_ms = find_rank(db, test["query"], expected)
        ranks.append(rank)
        latencies.append(latency_ms)

        label = f"#{rank}" if rank else "MISS"
        print(f"{label:<5} | {test['query'][:50]:<50} | expected {expected:<18} | top: {top_result}")

    db.close()

    total = len(ranks)
    recall_1 = sum(1 for r in ranks if r and r <= 1) / total
    recall_3 = sum(1 for r in ranks if r and r <= 3) / total
    recall_5 = sum(1 for r in ranks if r and r <= 5) / total
    mrr = sum((1 / r) if r else 0 for r in ranks) / total

    sorted_latencies = sorted(latencies)
    p95 = sorted_latencies[min(int(total * 0.95), total - 1)]

    print(f"\n--- Retrieval Quality ({total} queries) ---")
    print(f"Recall@1: {recall_1:.1%}")
    print(f"Recall@3: {recall_3:.1%}")
    print(f"Recall@5: {recall_5:.1%}")
    print(f"MRR:      {mrr:.3f}")

    print(f"\n--- Query Latency ---")
    print(f"Average: {sum(latencies) / total:.1f}ms")
    print(f"P95:     {p95:.1f}ms")
    print("=" * 60)


if __name__ == "__main__":
    run_codebase_evaluation()