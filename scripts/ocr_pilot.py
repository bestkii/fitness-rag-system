from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fitness_rag.config import RUNTIME_DIR
from fitness_rag.ocr_quality import (
    assess_ocr_content,
    evaluate_ocr_page,
    select_even_pages,
    validate_source_id,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local-only OCR quality pilot on representative PDF pages."
    )
    parser.add_argument("--source", type=Path, required=True, help="Local PDF path")
    parser.add_argument("--source-id", required=True, help="Safe local corpus identifier")
    parser.add_argument("--sample-count", type=int, default=20)
    parser.add_argument("--start-page", type=int)
    parser.add_argument("--end-page", type=int)
    parser.add_argument("--scale", type=float, default=1.6)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    if not source.is_file() or source.suffix.casefold() != ".pdf":
        raise SystemExit("--source must point to an existing PDF.")
    if not 1.0 <= args.scale <= 2.5:
        raise SystemExit("--scale must be between 1.0 and 2.5.")
    source_id = validate_source_id(args.source_id)

    try:
        import fitz
        import numpy as np
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise SystemExit(
            "OCR dependencies are missing. Install: pip install -r requirements-ocr.txt"
        ) from exc

    output_dir = RUNTIME_DIR / "private_corpus" / source_id / "pilot"
    page_dir = output_dir / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(source)
    total_page_count = document.page_count
    page_numbers = select_even_pages(
        total_page_count,
        args.sample_count,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    engine = RapidOCR()
    page_reports: list[dict] = []
    try:
        for page_number in page_numbers:
            page = document.load_page(page_number - 1)
            native_text = page.get_text("text") or ""
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(args.scale, args.scale), alpha=False
            )
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height, pixmap.width, pixmap.n
            )
            result = engine(image)
            lines = list(result.txts or ())
            scores = [float(score) for score in (result.scores or ())]
            boxes = [] if result.boxes is None else list(result.boxes)
            metrics = evaluate_ocr_page(
                lines,
                scores,
                native_text_characters=len(native_text.strip()),
            )
            assessment = assess_ocr_content(
                metrics,
                lines,
                boxes=boxes,
                image_width=pixmap.width,
            )
            page_report = {
                "page_number": page_number,
                "metrics": metrics.to_dict(),
                "content_assessment": assessment.to_dict(),
                "ocr_lines": [
                    {
                        "text": line,
                        "confidence": round(score, 5),
                        "box": [[round(float(value), 2) for value in point] for point in box],
                    }
                    for line, score, box in zip(lines, scores, boxes, strict=False)
                ],
            }
            (page_dir / f"page_{page_number:04d}.json").write_text(
                json.dumps(page_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            page_reports.append(page_report)
            print(
                f"page={page_number} status={metrics.status} "
                f"type={assessment.page_type} action={assessment.rag_action} "
                f"chars={metrics.character_count} confidence={metrics.mean_confidence:.3f}"
            )
    finally:
        document.close()

    statuses = [report["metrics"]["status"] for report in page_reports]
    character_counts = [report["metrics"]["character_count"] for report in page_reports]
    confidences = [report["metrics"]["mean_confidence"] for report in page_reports]
    readable_count = statuses.count("ocr_readable")
    rag_actions = [
        report["content_assessment"]["rag_action"] for report in page_reports
    ]
    page_types = [
        report["content_assessment"]["page_type"] for report in page_reports
    ]
    summary = {
        "source_id": source_id,
        "source_filename": source.name,
        "source_sha256": sha256_file(source),
        "privacy": "local_only_not_for_repository",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "page_count": total_page_count,
        "sampled_pages": page_numbers,
        "render_scale": args.scale,
        "ocr_engine": "rapidocr-3.9.2/onnxruntime",
        "quality_policy": {
            "ocr_readable": "at least 80 non-space characters, at least 3 lines, mean confidence >= 0.85, low-confidence ratio <= 0.25",
            "rag_gate": "No page is auto-ingested. References and image-only pages are excluded; tables, split layouts, terminology, and citations require their stated review action.",
            "limitation": "OCR confidence is not ground-truth character accuracy or proof of correct reading order.",
        },
        "results": {
            "sample_count": len(page_reports),
            "ocr_readable_pages": readable_count,
            "ocr_readable_rate": round(readable_count / len(page_reports), 4),
            "median_character_count": statistics.median(character_counts),
            "mean_confidence": round(statistics.mean(confidences), 5),
            "status_counts": {status: statuses.count(status) for status in sorted(set(statuses))},
            "page_type_counts": {
                page_type: page_types.count(page_type)
                for page_type in sorted(set(page_types))
            },
            "rag_action_counts": {
                action: rag_actions.count(action)
                for action in sorted(set(rag_actions))
            },
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary["results"], ensure_ascii=False, indent=2))
    print(f"Local-only report: {report_path}")


if __name__ == "__main__":
    main()
