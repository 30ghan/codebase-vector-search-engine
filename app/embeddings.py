from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

def compute_embedding(text: str) -> list[float]:
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()

def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot_product = sum(a*b for a, b in zip(vec1, vec2))
    return dot_product
