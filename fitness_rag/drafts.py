from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DRAFT_ID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27}$")


class DraftNotFoundError(KeyError):
    pass


class DraftNotApprovedError(RuntimeError):
    pass


class DraftStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, draft_id: str) -> Path:
        if not DRAFT_ID_PATTERN.fullmatch(draft_id):
            raise DraftNotFoundError(draft_id)
        return self.root / f"{draft_id}.json"

    def save(self, draft: dict[str, Any]) -> dict[str, Any]:
        path = self._path_for(str(draft["id"]))
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)
        return draft

    def get(self, draft_id: str) -> dict[str, Any]:
        path = self._path_for(draft_id)
        if not path.exists():
            raise DraftNotFoundError(draft_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def approve(self, draft_id: str) -> dict[str, Any]:
        draft = self.get(draft_id)
        timestamp = datetime.now(timezone.utc).isoformat()
        draft["status"] = "approved"
        draft["updated_at"] = timestamp
        draft["review"]["approved_at"] = timestamp
        return self.save(draft)

    def export_text(self, draft_id: str) -> str:
        draft = self.get(draft_id)
        if draft["status"] != "approved":
            raise DraftNotApprovedError(
                "Draft must be approved before it can be exported."
            )
        content = draft["content"]
        hashtags = " ".join(f"#{tag}" for tag in content["hashtags"])
        sources = "\n".join(
            f"[S{index}] {source['title']} — {source['url']}"
            for index, source in enumerate(draft["research"]["sources"], 1)
        )
        if draft.get("language") == "en":
            cards = "\n\n".join(
                f"{index}. {card['heading']}\n{card['copy']}"
                for index, card in enumerate(content["carousel"], 1)
            )
            community_url = draft.get("community_source_url")
            provenance = f"\nCommunity topic source\n{community_url}\n" if community_url else ""
            explanation = "\n\n".join(
                f"{item['text']}\n" + " ".join(f"[S{index}]" for index in item["sources"])
                for item in content.get("explanation", [])
            )
            return (
                f"{content['title']}\n\n{content['body']}\n\n{hashtags}\n\n"
                f"Review status: {draft['status']}\n{provenance}\n"
                f"Five-card carousel script\n{cards}\n\n"
                f"Detailed explanation draft\n{explanation}\n\nResearch sources\n{sources}\n"
            )
        return (
            f"{content['title']}\n\n{content['body']}\n\n{hashtags}\n\n"
            f"审核状态：{draft['status']}\n\n来源（发布前请逐条打开核对）：\n{sources}\n"
        )
