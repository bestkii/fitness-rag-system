from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fitness_rag.config import PRIVATE_SOURCE_REGISTRY_PATH
from fitness_rag.ocr_quality import validate_source_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register local PDF paths for private review previews."
    )
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="source_id=C:\\absolute\\path\\book.pdf",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources: dict[str, str] = {}
    for value in args.source:
        if "=" not in value:
            raise SystemExit("Each --source must use source_id=absolute_pdf_path")
        raw_id, raw_path = value.split("=", 1)
        source_id = validate_source_id(raw_id)
        source = Path(raw_path).resolve()
        if not source.is_file() or source.suffix.casefold() != ".pdf":
            raise SystemExit(f"Registered source is not an existing PDF: {source_id}")
        sources[source_id] = str(source)
    payload = {
        "privacy": "local_only_not_for_repository",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
    }
    PRIVATE_SOURCE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_SOURCE_REGISTRY_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"registered_source_ids": sorted(sources)}))


if __name__ == "__main__":
    main()
