from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import PRIVATE_REVIEW_DB_PATH


CHUNK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,160}$")
VALID_DECISIONS = {"approved", "rejected"}


class PrivateReviewStore:
    """Persist human OCR review decisions in a local-only SQLite database."""

    def __init__(self, path: Path = PRIVATE_REVIEW_DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS private_chunk_reviews (
                    chunk_id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL CHECK(decision IN ('approved', 'rejected')),
                    note TEXT NOT NULL DEFAULT '',
                    reviewed_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    @staticmethod
    def validate_chunk_id(chunk_id: str) -> str:
        normalized = chunk_id.strip().casefold()
        if not CHUNK_ID_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid private-corpus chunk ID")
        return normalized

    def save(self, chunk_id: str, decision: str, note: str = "") -> dict:
        normalized_id = self.validate_chunk_id(chunk_id)
        normalized_decision = decision.strip().casefold()
        if normalized_decision not in VALID_DECISIONS:
            raise ValueError("Decision must be approved or rejected")
        normalized_note = " ".join(note.split())[:500]
        reviewed_at = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO private_chunk_reviews (chunk_id, decision, note, reviewed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    decision = excluded.decision,
                    note = excluded.note,
                    reviewed_at = excluded.reviewed_at
                """,
                (normalized_id, normalized_decision, normalized_note, reviewed_at),
            )
            connection.commit()
        return {
            "chunk_id": normalized_id,
            "decision": normalized_decision,
            "note": normalized_note,
            "reviewed_at": reviewed_at,
        }

    def get(self, chunk_id: str) -> dict | None:
        normalized_id = self.validate_chunk_id(chunk_id)
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT chunk_id, decision, note, reviewed_at FROM private_chunk_reviews WHERE chunk_id = ?",
                (normalized_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_many(self, chunk_ids: Iterable[str]) -> dict[str, dict]:
        normalized = [self.validate_chunk_id(value) for value in chunk_ids]
        if not normalized:
            return {}
        placeholders = ",".join("?" for _ in normalized)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT chunk_id, decision, note, reviewed_at FROM private_chunk_reviews WHERE chunk_id IN ({placeholders})",
                normalized,
            ).fetchall()
        return {str(row["chunk_id"]): dict(row) for row in rows}

    def summary(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT decision, COUNT(*) AS count FROM private_chunk_reviews GROUP BY decision"
            ).fetchall()
        counts = {"approved": 0, "rejected": 0}
        counts.update({str(row["decision"]): int(row["count"]) for row in rows})
        counts["reviewed"] = counts["approved"] + counts["rejected"]
        return counts
