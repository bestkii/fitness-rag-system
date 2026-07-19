from __future__ import annotations

import json
import math
import sys
from collections import Counter
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chromadb
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer

from fitness_rag.config import (
    COLLECTION_NAME,
    DB_PATH,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    METRICS_PATH,
    RANDOM_SEED,
    SPLIT_VERSION,
    TOP_K,
)
from fitness_rag.data import (
    create_or_load_split,
    document_text,
    load_records,
    normalized_rumor,
    records_fingerprint,
    split_diagnostics,
    topic_pair,
)


def evaluate_rankings(
    rankings: list[list[int]],
    records: list[dict],
    test_indices: list[int],
    train_indices: list[int],
) -> dict[str, float]:
    precision = []
    hit = []
    reciprocal_rank = []
    expert_hit = []
    ndcg = []
    recall = []
    for test_index, retrieved in zip(test_indices, rankings):
        expected_pair = topic_pair(records[test_index])
        expected_expert = records[test_index]["expert"]
        relevant = [topic_pair(records[index]) == expected_pair for index in retrieved]
        precision.append(sum(relevant) / len(retrieved))
        relevant_train_count = sum(
            topic_pair(records[index]) == expected_pair for index in train_indices
        )
        recall.append(sum(relevant) / relevant_train_count)
        hit.append(float(any(relevant)))
        expert_hit.append(
            float(any(records[index]["expert"] == expected_expert for index in retrieved))
        )
        first = next((rank for rank, value in enumerate(relevant, 1) if value), None)
        reciprocal_rank.append(0.0 if first is None else 1.0 / first)
        dcg = sum(value / math.log2(rank + 1) for rank, value in enumerate(relevant, 1))
        ideal_relevant = min(
            TOP_K,
            relevant_train_count,
        )
        idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_relevant + 1))
        ndcg.append(dcg / idcg if idcg else 0.0)
    return {
        f"topic_pair_precision_at_{TOP_K}": round(float(np.mean(precision)), 4),
        f"topic_pair_recall_at_{TOP_K}": round(float(np.mean(recall)), 4),
        f"topic_pair_hit_rate_at_{TOP_K}": round(float(np.mean(hit)), 4),
        "mean_reciprocal_rank": round(float(np.mean(reciprocal_rank)), 4),
        f"expert_hit_rate_at_{TOP_K}": round(float(np.mean(expert_hit)), 4),
        f"ndcg_at_{TOP_K}": round(float(np.mean(ndcg)), 4),
    }


def main() -> None:
    records = load_records()
    train_indices, test_indices = create_or_load_split(records)
    train_documents = [document_text(records[index]) for index in train_indices]
    test_claims = [records[index]["rumor"] for index in test_indices]

    model = SentenceTransformer(EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=str(DB_PATH))
    collection = client.get_collection(COLLECTION_NAME)
    indexed_metadata = collection.get(include=["metadatas"])["metadatas"]
    indexed_indices = {int(metadata["dataset_index"]) for metadata in indexed_metadata}
    if indexed_indices != set(train_indices):
        raise RuntimeError("Chroma collection does not exactly match the corrected train split.")
    query_vectors = model.encode(
        test_claims,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).tolist()
    dense_result = collection.query(
        query_embeddings=query_vectors,
        n_results=TOP_K,
        include=["metadatas"],
    )
    dense_rankings = [
        [int(metadata["dataset_index"]) for metadata in row]
        for row in dense_result["metadatas"]
    ]

    vectorizer = TfidfVectorizer(
        lowercase=True,
        analyzer="word",
        ngram_range=(1, 2),
        min_df=2,
        max_features=40000,
        sublinear_tf=True,
    )
    train_matrix = vectorizer.fit_transform(train_documents)
    test_matrix = vectorizer.transform(test_claims)
    similarities = test_matrix @ train_matrix.T
    lexical_rankings = []
    for row in range(similarities.shape[0]):
        dense_row = similarities.getrow(row).toarray().ravel()
        positions = np.argpartition(-dense_row, TOP_K - 1)[:TOP_K]
        positions = positions[np.argsort(-dense_row[positions])]
        lexical_rankings.append([train_indices[position] for position in positions])

    metrics = {
        "evaluation_design": {
            "dataset_records": len(records),
            "indexed_train_records": len(train_indices),
            "held_out_test_records": len(test_indices),
            "split": "deterministic stratified split by unordered topic pair",
            "split_version": SPLIT_VERSION,
            "random_seed": RANDOM_SEED,
            "records_sha256": records_fingerprint(records),
            "leakage_checks": split_diagnostics(records, train_indices, test_indices),
            "test_leakage": (
                "test indices are excluded from Chroma; normalized rumor text does not "
                "cross the train/test boundary"
            ),
            "relevance_definition": "retrieved record has the same unordered topic pair",
            "caveat": "labels and text are synthetic; metrics measure retrieval, not clinical validity",
        },
        "implementation": {
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dimension": EMBEDDING_DIMENSION,
            "vector_store": "ChromaDB",
            "distance": "cosine",
            "top_k": TOP_K,
            "collection_records": collection.count(),
            "library_versions": {
                "chromadb": version("chromadb"),
                "sentence_transformers": version("sentence-transformers"),
                "scikit_learn": version("scikit-learn"),
                "numpy": version("numpy"),
            },
        },
        "dense_rag": evaluate_rankings(
            dense_rankings, records, test_indices, train_indices
        ),
        "lexical_tfidf_baseline": evaluate_rankings(
            lexical_rankings, records, test_indices, train_indices
        ),
        "dataset_profile": {
            "topic_pairs": len(Counter(topic_pair(record) for record in records)),
            "experts": Counter(record["expert"] for record in records),
        },
    }
    for metric in metrics["dense_rag"]:
        metrics.setdefault("absolute_gain", {})[metric] = round(
            metrics["dense_rag"][metric] - metrics["lexical_tfidf_baseline"][metric],
            4,
        )

    train_rumors = {normalized_rumor(records[index]) for index in train_indices}
    test_rumors = {normalized_rumor(records[index]) for index in test_indices}
    assert not train_rumors.intersection(test_rumors)

    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"Saved metrics to {METRICS_PATH}")


if __name__ == "__main__":
    main()
