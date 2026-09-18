from __future__ import annotations

import argparse
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
    PRIVATE_CORPUS_DIR,
    PRIVATE_TEXTBOOK_COLLECTION,
    PRIVATE_TEXTBOOK_DB_PATH,
)
from fitness_rag.ocr_quality import validate_source_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local-only staged textbook index")
    parser.add_argument("--source-id", action="append", required=True)
    return parser.parse_args()


def load_chunks(source_ids: list[str]) -> tuple[list[dict], list[dict]]:
    chunks: list[dict] = []
    manifests: list[dict] = []
    for source_id in source_ids:
        corpus_dir = PRIVATE_CORPUS_DIR / source_id / "corpus"
        manifest_path = corpus_dir / "manifest.json"
        chunks_path = corpus_dir / "chunks.jsonl"
        if not manifest_path.is_file() or not chunks_path.is_file():
            raise SystemExit(f"Extracted corpus not found for {source_id}")
        manifests.append(json.loads(manifest_path.read_text(encoding="utf-8")))
        chunks.extend(
            json.loads(line)
            for line in chunks_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    if len({chunk["chunk_id"] for chunk in chunks}) != len(chunks):
        raise RuntimeError("Duplicate private-corpus chunk IDs")
    return chunks, manifests


def main() -> None:
    args = parse_args()
    source_ids = [validate_source_id(value) for value in args.source_id]
    chunks, manifests = load_chunks(source_ids)
    if not chunks:
        raise SystemExit("No staged chunks are available to index")

    resolved_db = PRIVATE_TEXTBOOK_DB_PATH.resolve()
    resolved_root = PRIVATE_CORPUS_DIR.resolve()
    if resolved_db.parent != resolved_root:
        raise RuntimeError(f"Refusing to replace database outside private runtime: {resolved_db}")
    if resolved_db.exists():
        shutil.rmtree(resolved_db)

    model = SentenceTransformer(EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=str(resolved_db))
    collection = client.create_collection(
        PRIVATE_TEXTBOOK_COLLECTION,
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": EMBEDDING_MODEL,
            "privacy": "local_only",
            "review_state": "staging",
        },
    )
    batch_size = 64
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = model.encode(
            [chunk["text"] for chunk in batch],
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()
        collection.add(
            ids=[chunk["chunk_id"] for chunk in batch],
            documents=[chunk["text"] for chunk in batch],
            embeddings=vectors,
            metadatas=[
                {
                    "source_id": chunk["source_id"],
                    "title": chunk["title"],
                    "section_id": chunk["section_id"],
                    "section_title": chunk["section_title"],
                    "pdf_page": int(chunk["pdf_page"]),
                    "printed_page": int(chunk["printed_page"]),
                    "review_status": chunk["review_status"],
                }
                for chunk in batch
            ],
        )
        print(f"indexed={min(start + batch_size, len(chunks))}/{len(chunks)}")

    index_manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "privacy": "local_only_not_for_repository",
        "collection": PRIVATE_TEXTBOOK_COLLECTION,
        "embedding_model": EMBEDDING_MODEL,
        "distance": "cosine",
        "review_state": "staging_not_generation_approved",
        "chunk_count": collection.count(),
        "sources": manifests,
    }
    (PRIVATE_CORPUS_DIR / "index_manifest.json").write_text(
        json.dumps(index_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"chunk_count": collection.count(), "source_ids": source_ids}))


if __name__ == "__main__":
    main()
