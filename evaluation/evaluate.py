import time 
from app.embeddings import compute_embedding
from app.vector_index import add_vector, search_vectors, get_index_size
from app.db import SessionLocal
from app.models import CodeChunk
from evaluation.dataset import test_snippets, test_queries

def reset_database():
    db = SessionLocal()
    db.query(CodeChunk).delete()
    db.commit()
    db.close()

def index_test_snippets():
    db = SessionLocal()
    start_time = time.time()

    for snippet in test_snippets:
        code_chunk = CodeChunk(
            text=snippet["text"], 
            file_path=snippet.get("file_path"),
            language=snippet.get("language"),
            function_name=snippet.get("function_name") 
        )
        db.add(code_chunk)
        db.commit()
        db.refresh(code_chunk)

        vector = compute_embedding(code_chunk.text)
        add_vector(vector, code_chunk.id)

    time_elapsed = time.time() - start_time
    db.close()
    return time_elapsed
        
def evaluate_search(k: int = 3):
    db = SessionLocal()
    latencies = []
    hits = 0

    for test in test_queries:
        start_time = time.time()
        query_vector = compute_embedding(test["query"])
        results = search_vectors(query_vector, k=k)
        latencies.append((time.time() - start_time) * 1000)

        returned_functions = []
        for result in results:
            code_chunk = db.query(CodeChunk).filter(CodeChunk.id == result["id"]).first()
            if code_chunk:
                returned_functions.append(code_chunk.function_name)

        if test["expected_function"] in returned_functions:
            hits += 1

    db.close()
    recall = hits / len(test_queries)
    return latencies, recall


def run_evaluation():
    print("=" * 50)
    print("EVALUATION REPORT")
    print("=" * 50)

    reset_database()

    index_time = index_test_snippets()
    num_docs = len(test_snippets)
    docs_per_sec = num_docs / index_time
    print(f"\n--- Indexing Speed ---")
    print(f"Documents indexed: {num_docs}")
    print(f"Total time: {index_time:.3f}s")
    print(f"Speed: {docs_per_sec:.1f} docs/sec")

    k = 3
    latencies, recall = evaluate_search(k=k)

    avg_latency = sum(latencies) / len(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)
    sorted_latencies = sorted(latencies)
    p50 = sorted_latencies[len(sorted_latencies) // 2]
    p95_index = int(len(sorted_latencies) * 0.95)
    p95 = sorted_latencies[min(p95_index, len(sorted_latencies) - 1)]

    print(f"\n--- Query Latency ---")
    print(f"Average: {avg_latency:.1f}ms")
    print(f"Min: {min_latency:.1f}ms")
    print(f"Max: {max_latency:.1f}ms")
    print(f"P50: {p50:.1f}ms")
    print(f"P95: {p95:.1f}ms")

    print(f"\n--- Recall@{k} ---")
    print(f"Recall: {recall:.1%} ({int(recall * len(test_queries))}/{len(test_queries)} queries)")

    num_throughput_queries = 50
    start_time = time.time()
    for test in test_queries * (num_throughput_queries // len(test_queries)):
        query_vector = compute_embedding(test["query"])
        search_vectors(query_vector, k=k)
    throughput_time = time.time() - start_time
    actual_queries = len(test_queries) * (num_throughput_queries // len(test_queries))
    qps = actual_queries / throughput_time

    print(f"\n--- Throughput ---")
    print(f"Queries: {num_throughput_queries}")
    print(f"Total time: {throughput_time:.3f}s")
    print(f"Throughput: {qps:.1f} queries/sec")

    print(f"\n--- Index Info ---")
    print(f"Vectors in index: {get_index_size()}")
    print("=" * 50)


if __name__ == "__main__":
    run_evaluation()
