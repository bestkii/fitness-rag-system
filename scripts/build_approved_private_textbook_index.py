from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chromadb
from sentence_transformers import SentenceTransformer

from fitness_rag.config import (
    EMBEDDING_MODEL,
    PRIVATE_APPROVED_COLLECTION,
    PRIVATE_APPROVED_DB_PATH,
    PRIVATE_CORPUS_DIR,
)
from fitness_rag.private_reviews import PrivateReviewStore


def load_staged_chunks() -> list[dict]:
    manifest_path = PRIVATE_CORPUS_DIR / "index_manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("Build the private staging index first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks: list[dict] = []
    for source in manifest.get("sources", []):
        path = PRIVATE_CORPUS_DIR / source["source_id"] / "corpus" / "chunks.jsonl"
        chunks.extend(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return chunks


def main() -> None:
    chunks = load_staged_chunks()
    reviews = PrivateReviewStore().get_many(chunk["chunk_id"] for chunk in chunks)
    approved = [
        chunk
        for chunk in chunks
        if reviews.get(chunk["chunk_id"], {}).get("decision") == "approved"
    ]
    if not approved:
        raise SystemExit("No human-approved textbook chunks are available")

    resolved_db = PRIVATE_APPROVED_DB_PATH.resolve()
    if resolved_db.parent != PRIVATE_CORPUS_DIR.resolve():
        raise RuntimeError(f"Refusing to replace database outside private runtime: {resolved_db}")
    if resolved_db.exists():
        shutil.rmtree(resolved_db)

    model = SentenceTransformer(EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=str(resolved_db))
    collection = client.create_collection(
        PRIVATE_APPROVED_COLLECTION,
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": EMBEDDING_MODEL,
            "privacy": "local_only",
            "review_state": "human_approved_only",
        },
    )
    vectors = model.encode(
        [chunk["text"] for chunk in approved],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).tolist()
    collection.add(
        ids=[chunk["chunk_id"] for chunk in approved],
        documents=[chunk["text"] for chunk in approved],
        embeddings=vectors,
        metadatas=[
            {
                "source_id": chunk["source_id"],
                "title": chunk["title"],
                "section_id": chunk["section_id"],
                "section_title": chunk["section_title"],
                "pdf_page": int(chunk["pdf_page"]),
                "printed_page": int(chunk["printed_page"]),
                "review_state": "human_approved",
            }
            for chunk in approved
        ],
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "privacy": "local_only_not_for_repository",
        "collection": PRIVATE_APPROVED_COLLECTION,
        "embedding_model": EMBEDDING_MODEL,
        "approved_chunk_count": collection.count(),
        "gate": "human_approved_only",
    }
    (PRIVATE_CORPUS_DIR / "approved_index_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
