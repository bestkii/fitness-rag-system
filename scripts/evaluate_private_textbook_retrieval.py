from __future__ import annotations

import json
import math
import sys
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chromadb
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer

from fitness_rag.config import (
    EMBEDDING_MODEL,
    PRIVATE_CORPUS_DIR,
    PRIVATE_TEXTBOOK_COLLECTION,
    PRIVATE_TEXTBOOK_DB_PATH,
    PRIVATE_TEXTBOOK_METRICS_PATH,
)

QUERY_PATH = ROOT / "artifacts" / "private_textbook_eval_queries.json"
TOP_K = 3


def is_relevant(metadata: dict, query: dict) -> bool:
    return (
        metadata["source_id"] == query["source_id"]
        and query["printed_page_start"]
        <= int(metadata["printed_page"])
        <= query["printed_page_end"]
    )


def score_rankings(rankings: list[list[dict]], queries: list[dict]) -> dict[str, float]:
    hit, reciprocal_rank, precision, ndcg = [], [], [], []
    for ranking, query in zip(rankings, queries, strict=True):
        relevant = [is_relevant(metadata, query) for metadata in ranking]
        hit.append(float(any(relevant)))
        precision.append(sum(relevant) / TOP_K)
        first = next((rank for rank, value in enumerate(relevant, 1) if value), None)
        reciprocal_rank.append(0.0 if first is None else 1.0 / first)
        dcg = sum(value / math.log2(rank + 1) for rank, value in enumerate(relevant, 1))
        ideal_count = min(TOP_K, sum(relevant))
        idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
        ndcg.append(dcg / idcg if idcg else 0.0)
    return {
        f"page_range_hit_rate_at_{TOP_K}": round(float(np.mean(hit)), 4),
        f"page_range_precision_at_{TOP_K}": round(float(np.mean(precision)), 4),
        "mean_reciprocal_rank": round(float(np.mean(reciprocal_rank)), 4),
        f"ndcg_at_{TOP_K}": round(float(np.mean(ndcg)), 4),
    }


def main() -> None:
    queries = json.loads(QUERY_PATH.read_text(encoding="utf-8"))
    client = chromadb.PersistentClient(path=str(PRIVATE_TEXTBOOK_DB_PATH))
    collection = client.get_collection(PRIVATE_TEXTBOOK_COLLECTION)
    corpus = collection.get(include=["documents", "metadatas"])
    ids = corpus["ids"]
    documents = corpus["documents"]
    metadatas = corpus["metadatas"]
    if not ids or not documents or not metadatas:
        raise RuntimeError("Private textbook collection is empty")

    model = SentenceTransformer(EMBEDDING_MODEL)
    query_vectors = model.encode(
        [query["query"] for query in queries],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).tolist()
    dense_result = collection.query(
        query_embeddings=query_vectors,
        n_results=TOP_K,
        include=["metadatas"],
    )
    dense_rankings = dense_result["metadatas"]

    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=1, sublinear_tf=True)
    corpus_matrix = vectorizer.fit_transform(documents)
    query_matrix = vectorizer.transform([query["query"] for query in queries])
    similarities = query_matrix @ corpus_matrix.T
    lexical_rankings: list[list[dict]] = []
    for row in range(similarities.shape[0]):
        values = similarities.getrow(row).toarray().ravel()
        positions = np.argpartition(-values, TOP_K - 1)[:TOP_K]
        positions = positions[np.argsort(-values[positions])]
        lexical_rankings.append([metadatas[position] for position in positions])

    dense_metrics = score_rankings(dense_rankings, queries)
    lexical_metrics = score_rankings(lexical_rankings, queries)
    failures = []
    for query, ranking in zip(queries, dense_rankings, strict=True):
        if not any(is_relevant(metadata, query) for metadata in ranking):
            failures.append(
                {
                    "query_id": query["id"],
                    "retrieved": [
                        {
                            "source_id": metadata["source_id"],
                            "printed_page": metadata["printed_page"],
                        }
                        for metadata in ranking
                    ],
                }
            )
    metrics = {
        "evaluation_design": {
            "query_count": len(queries),
            "query_source": "predeclared from table-of-contents sections before retrieval inspection",
            "relevance_definition": "matching source and expected printed-page range",
            "top_k": TOP_K,
            "caveat": "OCR staging corpus; metrics measure retrieval location, not factual or medical correctness",
            "status": "pilot development set; future retrieval changes require a new held-out query set",
        },
        "implementation": {
            "collection": PRIVATE_TEXTBOOK_COLLECTION,
            "collection_records": collection.count(),
            "embedding_model": EMBEDDING_MODEL,
            "distance": "cosine",
            "lexical_baseline": "character TF-IDF 2-4 grams",
            "library_versions": {
                "chromadb": version("chromadb"),
                "sentence_transformers": version("sentence-transformers"),
                "scikit_learn": version("scikit-learn"),
                "numpy": version("numpy"),
            },
        },
        "dense_rag": dense_metrics,
        "lexical_tfidf_baseline": lexical_metrics,
        "absolute_gain": {
            key: round(dense_metrics[key] - lexical_metrics[key], 4)
            for key in dense_metrics
        },
        "dense_failures": failures,
        "recommended_staging_retriever": "lexical_tfidf",
    }
    PRIVATE_CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_TEXTBOOK_METRICS_PATH.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
