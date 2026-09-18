from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fitness_rag.config import PRIVATE_CORPUS_DIR
from fitness_rag.ocr_quality import assess_ocr_content, evaluate_ocr_page, validate_source_id
from fitness_rag.private_corpus import chunk_lines, reconstruct_reading_order, sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract a local-only, page-cited textbook section into staged RAG chunks."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--section-id", required=True)
    parser.add_argument("--section-title", required=True)
    parser.add_argument("--start-page", type=int, required=True, help="First PDF page, 1-based")
    parser.add_argument("--end-page", type=int, required=True, help="Last PDF page, inclusive")
    parser.add_argument(
        "--printed-page-offset",
        type=int,
        default=0,
        help="PDF page minus printed page, for page citations",
    )
    parser.add_argument("--scale", type=float, default=1.6)
    parser.add_argument("--target-characters", type=int, default=650)
    parser.add_argument("--overlap-characters", type=int, default=100)
    return parser.parse_args()


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    if not source.is_file() or source.suffix.casefold() != ".pdf":
        raise SystemExit("--source must be an existing PDF")
    source_id = validate_source_id(args.source_id)
    section_id = validate_source_id(args.section_id)
    if args.start_page < 1 or args.end_page < args.start_page:
        raise SystemExit("Invalid page range")
    if not 1.0 <= args.scale <= 2.5:
        raise SystemExit("--scale must be between 1.0 and 2.5")

    try:
        import fitz
        import numpy as np
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise SystemExit("Install the local OCR dependencies from requirements-ocr.txt") from exc

    output_dir = PRIVATE_CORPUS_DIR / source_id / "corpus"
    output_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(source)
    if args.end_page > document.page_count:
        document.close()
        raise SystemExit(f"Page range exceeds PDF length ({document.page_count})")

    engine = RapidOCR()
    page_records: list[dict] = []
    chunks: list[dict] = []
    try:
        for pdf_page in range(args.start_page, args.end_page + 1):
            page = document.load_page(pdf_page - 1)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(args.scale, args.scale), alpha=False)
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height, pixmap.width, pixmap.n
            )
            result = engine(image)
            texts = list(result.txts or ())
            scores = [float(score) for score in (result.scores or ())]
            boxes = [] if result.boxes is None else list(result.boxes)
            metrics = evaluate_ocr_page(
                texts,
                scores,
                native_text_characters=len((page.get_text("text") or "").strip()),
            )
            assessment = assess_ocr_content(
                metrics, texts, boxes=boxes, image_width=pixmap.width
            )
            include_page = assessment.rag_action in {
                "stage_for_review",
                "manual_layout_review",
            }
            ordered_lines = (
                reconstruct_reading_order(
                    texts,
                    boxes,
                    image_width=pixmap.width,
                    layout=assessment.layout,
                )
                if include_page
                else []
            )
            printed_page = pdf_page - args.printed_page_offset
            page_record = {
                "source_id": source_id,
                "title": args.title,
                "section_id": section_id,
                "section_title": args.section_title,
                "pdf_page": pdf_page,
                "printed_page": printed_page,
                "metrics": metrics.to_dict(),
                "content_assessment": assessment.to_dict(),
                "corpus_action": "staged" if include_page else "excluded",
                "review_status": (
                    "machine_reconstructed_needs_review"
                    if assessment.rag_action == "manual_layout_review"
                    else "ocr_needs_terminology_review"
                    if include_page
                    else "excluded_by_quality_gate"
                ),
                "text": "\n".join(ordered_lines),
            }
            page_records.append(page_record)
            if include_page:
                for chunk_number, text in enumerate(
                    chunk_lines(
                        ordered_lines,
                        target_characters=args.target_characters,
                        overlap_characters=args.overlap_characters,
                    ),
                    1,
                ):
                    chunks.append(
                        {
                            "chunk_id": f"{source_id}-{section_id}-p{pdf_page:04d}-c{chunk_number:02d}",
                            "source_id": source_id,
                            "title": args.title,
                            "section_id": section_id,
                            "section_title": args.section_title,
                            "pdf_page": pdf_page,
                            "printed_page": printed_page,
                            "review_status": page_record["review_status"],
                            "text": text,
                        }
                    )
            print(
                f"page={pdf_page} action={page_record['corpus_action']} "
                f"type={assessment.page_type} chunks={sum(c['pdf_page'] == pdf_page for c in chunks)}"
            )
    finally:
        document.close()

    write_jsonl(output_dir / "pages.jsonl", page_records)
    write_jsonl(output_dir / "chunks.jsonl", chunks)
    action_counts = Counter(record["corpus_action"] for record in page_records)
    review_counts = Counter(record["review_status"] for record in page_records)
    manifest = {
        "source_id": source_id,
        "title": args.title,
        "section_id": section_id,
        "section_title": args.section_title,
        "privacy": "local_only_not_for_repository",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_filename": source.name,
        "source_sha256": sha256_file(source),
        "pdf_page_range": [args.start_page, args.end_page],
        "printed_page_range": [
            args.start_page - args.printed_page_offset,
            args.end_page - args.printed_page_offset,
        ],
        "render_scale": args.scale,
        "chunking": {
            "unit": "page-local OCR lines",
            "target_characters": args.target_characters,
            "overlap_characters": args.overlap_characters,
            "table_policy": "excluded from first text index",
            "layout_policy": "detected split pages reordered left column then right column",
        },
        "page_count": len(page_records),
        "chunk_count": len(chunks),
        "action_counts": dict(action_counts),
        "review_status_counts": dict(review_counts),
        "generation_eligibility": "retrieval_staging_only_until_human_review",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
