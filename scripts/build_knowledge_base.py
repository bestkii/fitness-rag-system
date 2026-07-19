from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chromadb
from sentence_transformers import SentenceTransformer

from fitness_rag.config import COLLECTION_NAME, DB_PATH, EMBEDDING_MODEL
from fitness_rag.data import (
    create_or_load_split,
    document_text,
    load_records,
    records_fingerprint,
)


def main() -> None:
    records = load_records()
    train_indices, test_indices = create_or_load_split(records)
    print(f"Validated {len(records)} records: {len(train_indices)} train / {len(test_indices)} test")

    if DB_PATH.exists():
        resolved = DB_PATH.resolve()
        if resolved.parent != ROOT.resolve():
            raise RuntimeError(f"Refusing to replace database outside workspace: {resolved}")
        shutil.rmtree(resolved)

    model = SentenceTransformer(EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=str(DB_PATH))
    collection = client.create_collection(
        COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": EMBEDDING_MODEL,
            "split": "2,700 train records only",
            "records_sha256": records_fingerprint(records),
        },
    )

    batch_size = 128
    for start in range(0, len(train_indices), batch_size):
        batch_indices = train_indices[start : start + batch_size]
        batch = [records[index] for index in batch_indices]
        documents = [document_text(record) for record in batch]
        vectors = model.encode(
            documents,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()
        collection.add(
            ids=[f"fitness-{index:04d}" for index in batch_indices],
            embeddings=vectors,
            documents=documents,
            metadatas=[
                {
                    "dataset_index": index,
                    "expert": record["expert"],
                    "topics": __import__("json").dumps(record["topics"]),
                    "rumor": record["rumor"],
                    "truth": record["truth"],
                    "source_type": "synthetic_deepseek",
                }
                for index, record in zip(batch_indices, batch)
            ],
        )
        print(f"Indexed {min(start + batch_size, len(train_indices))}/{len(train_indices)}")

    print(f"Knowledge base ready: {collection.count()} records at {DB_PATH}")


if __name__ == "__main__":
    main()
