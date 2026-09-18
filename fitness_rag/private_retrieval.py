from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .config import PRIVATE_CORPUS_DIR


class PrivateTextbookRetriever:
    """Local-only lexical retriever for staged, page-cited textbook chunks."""

    def __init__(
        self,
        *,
        corpus_dir: Path = PRIVATE_CORPUS_DIR,
        chunks: list[dict[str, Any]] | None = None,
    ) -> None:
        self.corpus_dir = corpus_dir
        self.chunks = chunks if chunks is not None else self._load_indexed_chunks()
        if not self.chunks:
            raise RuntimeError("Private textbook staging corpus is missing")
        documents = [str(chunk["text"]) for chunk in self.chunks]
        self.vectorizer = TfidfVectorizer(
            analyzer="char", ngram_range=(2, 4), min_df=1, sublinear_tf=True
        )
        self.matrix = self.vectorizer.fit_transform(documents)
        self.by_id = {str(chunk["chunk_id"]): chunk for chunk in self.chunks}

    def _load_indexed_chunks(self) -> list[dict[str, Any]]:
        manifest_path = self.corpus_dir / "index_manifest.json"
        if not manifest_path.is_file():
            return []
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        chunks: list[dict[str, Any]] = []
        for source in manifest.get("sources", []):
            source_id = str(source.get("source_id", ""))
            chunks_path = self.corpus_dir / source_id / "corpus" / "chunks.jsonl"
            if not chunks_path.is_file():
                raise RuntimeError(f"Indexed private corpus is incomplete: {source_id}")
            chunks.extend(
                json.loads(line)
                for line in chunks_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        return chunks

    @staticmethod
    def _format_chunk(
        chunk: dict[str, Any], *, rank: int, score: float | None = None
    ) -> dict[str, Any]:
        return {
            "rank": rank,
            "score": None if score is None else round(score, 4),
            "chunk_id": chunk["chunk_id"],
            "source_id": chunk["source_id"],
            "title": chunk["title"],
            "section_id": chunk["section_id"],
            "section_title": chunk["section_title"],
            "pdf_page": int(chunk["pdf_page"]),
            "printed_page": int(chunk["printed_page"]),
            "review_status": chunk["review_status"],
            "excerpt": " ".join(str(chunk["text"]).split())[:320],
            "privacy": "local_only",
        }

    def has_chunk(self, chunk_id: str) -> bool:
        normalized = chunk_id.strip().casefold()
        return any(key.casefold() == normalized for key in self.by_id)

    @staticmethod
    def _even_sample(
        items: list[dict[str, Any]], count: int
    ) -> list[dict[str, Any]]:
        """Select deterministic samples spanning the full page range."""
        if count >= len(items):
            return list(items)
        if count == 1:
            return [items[len(items) // 2]]
        positions = [
            round(index * (len(items) - 1) / (count - 1))
            for index in range(count)
        ]
        return [items[position] for position in positions]

    def review_queue(
        self, *, reviewed_ids: set[str], limit: int = 12
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 30:
            raise ValueError("Review queue limit must be between 1 and 30")
        first_per_page: dict[tuple[str, int], dict[str, Any]] = {}
        for chunk in sorted(
            self.chunks,
            key=lambda item: (item["source_id"], int(item["pdf_page"]), item["chunk_id"]),
        ):
            if chunk["chunk_id"] in reviewed_ids:
                continue
            first_per_page.setdefault(
                (str(chunk["source_id"]), int(chunk["pdf_page"])), chunk
            )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for chunk in first_per_page.values():
            grouped.setdefault(str(chunk["source_id"]), []).append(chunk)
        selected: list[dict[str, Any]] = []
        source_ids = sorted(grouped)
        per_source_limit = (limit + len(source_ids) - 1) // len(source_ids)
        sampled = {
            source_id: self._even_sample(grouped[source_id], per_source_limit)
            for source_id in source_ids
        }
        while len(selected) < limit and any(sampled.values()):
            for source_id in source_ids:
                if sampled[source_id] and len(selected) < limit:
                    selected.append(sampled[source_id].pop(0))

        if len(selected) < limit:
            selected_ids = {str(chunk["chunk_id"]) for chunk in selected}
            remaining = [
                chunk
                for source_id in source_ids
                for chunk in grouped[source_id]
                if str(chunk["chunk_id"]) not in selected_ids
            ]
            selected.extend(remaining[: limit - len(selected)])
        return [
            self._format_chunk(chunk, rank=rank)
            for rank, chunk in enumerate(selected, 1)
        ]

    def search(self, query: str, *, top_k: int = 3) -> list[dict[str, Any]]:
        normalized = re.sub(r"\s+", " ", query).strip()
        if len(normalized) < 2:
            raise ValueError("Query must contain at least 2 characters")
        if len(normalized) > 300:
            raise ValueError("Query must be 300 characters or fewer")
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be between 1 and 10")
        scores = (self.vectorizer.transform([normalized]) @ self.matrix.T).toarray().ravel()
        result_count = min(top_k, len(self.chunks))
        positions = np.argpartition(-scores, result_count - 1)[:result_count]
        positions = positions[np.argsort(-scores[positions])]
        results = []
        for rank, position in enumerate(positions, 1):
            chunk = self.chunks[int(position)]
            results.append(
                self._format_chunk(
                    chunk, rank=rank, score=float(scores[position])
                )
            )
        return results
