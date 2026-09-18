from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Sequence


SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


@dataclass(frozen=True)
class OcrPageMetrics:
    character_count: int
    line_count: int
    mean_confidence: float
    low_confidence_ratio: float
    native_text_characters: int
    status: str

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "character_count": self.character_count,
            "line_count": self.line_count,
            "mean_confidence": self.mean_confidence,
            "low_confidence_ratio": self.low_confidence_ratio,
            "native_text_characters": self.native_text_characters,
            "status": self.status,
        }


@dataclass(frozen=True)
class OcrContentAssessment:
    page_type: str
    layout: str
    rag_action: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, str | list[str]]:
        return {
            "page_type": self.page_type,
            "layout": self.layout,
            "rag_action": self.rag_action,
            "reasons": list(self.reasons),
        }


def validate_source_id(source_id: str) -> str:
    normalized = source_id.strip().casefold()
    if not SOURCE_ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            "source-id must be 2-64 lowercase letters, digits, hyphens, or underscores."
        )
    return normalized


def select_even_pages(
    page_count: int,
    sample_count: int,
    *,
    start_page: int | None = None,
    end_page: int | None = None,
) -> list[int]:
    """Return deterministic 1-based page numbers spanning the requested body range."""

    if page_count < 1:
        raise ValueError("PDF must contain at least one page.")
    if sample_count < 1:
        raise ValueError("sample-count must be positive.")
    start = start_page or max(1, math.ceil(page_count * 0.05))
    end = end_page or min(page_count, math.floor(page_count * 0.95))
    if start < 1 or end > page_count or start > end:
        raise ValueError("Invalid page range.")
    available = end - start + 1
    count = min(sample_count, available)
    if count == 1:
        return [start]
    pages = {
        round(start + index * (end - start) / (count - 1))
        for index in range(count)
    }
    return sorted(pages)


def evaluate_ocr_page(
    lines: Iterable[str],
    scores: Iterable[float],
    *,
    native_text_characters: int = 0,
) -> OcrPageMetrics:
    line_list = [" ".join(str(line).split()) for line in lines if str(line).strip()]
    score_list = [max(0.0, min(1.0, float(score))) for score in scores]
    character_count = sum(len(line.replace(" ", "")) for line in line_list)
    mean_confidence = sum(score_list) / len(score_list) if score_list else 0.0
    low_confidence_ratio = (
        sum(score < 0.80 for score in score_list) / len(score_list)
        if score_list
        else 1.0
    )
    if character_count < 80 or len(line_list) < 3:
        status = "insufficient_text"
    elif mean_confidence < 0.85 or low_confidence_ratio > 0.25:
        status = "needs_review"
    else:
        status = "ocr_readable"
    return OcrPageMetrics(
        character_count=character_count,
        line_count=len(line_list),
        mean_confidence=round(mean_confidence, 5),
        low_confidence_ratio=round(low_confidence_ratio, 5),
        native_text_characters=max(0, native_text_characters),
        status=status,
    )


def detect_page_layout(
    boxes: Iterable[Sequence[Sequence[float]]],
    *,
    image_width: int | float | None,
) -> str:
    """Flag pages whose OCR lines occupy distinct left and right columns."""

    if not image_width or image_width <= 0:
        return "unknown"
    normalized_boxes = []
    for box in boxes:
        points = list(box)
        if not points:
            continue
        x_values = [float(point[0]) for point in points if len(point) >= 2]
        if x_values:
            normalized_boxes.append((min(x_values), max(x_values)))
    if len(normalized_boxes) < 8:
        return "single_or_mixed"

    left_lines = sum(x_max <= image_width * 0.60 for _, x_max in normalized_boxes)
    right_lines = sum(x_min >= image_width * 0.40 for x_min, _ in normalized_boxes)
    split_lines = left_lines + right_lines
    minimum_column_lines = max(4, math.ceil(len(normalized_boxes) * 0.12))
    if (
        left_lines >= minimum_column_lines
        and right_lines >= minimum_column_lines
        and split_lines / len(normalized_boxes) >= 0.45
    ):
        return "two_column_or_split"
    return "single_or_mixed"


def assess_ocr_content(
    metrics: OcrPageMetrics,
    lines: Iterable[str],
    *,
    boxes: Iterable[Sequence[Sequence[float]]] = (),
    image_width: int | float | None = None,
) -> OcrContentAssessment:
    """Assign a conservative RAG disposition independent of OCR confidence."""

    line_list = [" ".join(str(line).split()) for line in lines if str(line).strip()]
    joined = " ".join(line_list)
    opening = " ".join(line_list[:12]).casefold()
    layout = detect_page_layout(boxes, image_width=image_width)

    if metrics.status == "insufficient_text":
        return OcrContentAssessment(
            page_type="image_or_blank",
            layout=layout,
            rag_action="exclude",
            reasons=("too_little_searchable_text",),
        )

    reference_markers = ("参考文献", "references", "bibliography")
    numbered_references = sum(
        bool(re.match(r"^\d{1,3}\.\s+[A-Z]", line)) for line in line_list
    )
    dated_reference_lines = sum(
        bool(re.search(r"\b(?:19|20)\d{2}\b", line)) for line in line_list
    )
    if any(marker in opening for marker in reference_markers) or (
        numbered_references >= 3 and dated_reference_lines >= 4
    ):
        return OcrContentAssessment(
            page_type="reference_page",
            layout=layout,
            rag_action="exclude",
            reasons=("bibliography_not_primary_knowledge_chunk",),
        )

    line_count = max(1, len(line_list))
    numeric_ratio = sum(any(char.isdigit() for char in line) for line in line_list) / line_count
    short_ratio = sum(len(line.replace(" ", "")) <= 12 for line in line_list) / line_count
    if numeric_ratio >= 0.65 and short_ratio >= 0.75:
        return OcrContentAssessment(
            page_type="table_heavy",
            layout=layout,
            rag_action="manual_table_review",
            reasons=("dense_numeric_cells", "row_and_column_structure_not_verified"),
        )
    if numeric_ratio >= 0.45 and short_ratio >= 0.45:
        return OcrContentAssessment(
            page_type="mixed_prose_table",
            layout=layout,
            rag_action="manual_table_review",
            reasons=("prose_and_table_content_mixed", "table_order_not_verified"),
        )
    if metrics.status == "needs_review":
        return OcrContentAssessment(
            page_type="low_confidence_or_complex",
            layout=layout,
            rag_action="manual_review",
            reasons=("ocr_quality_threshold_not_met",),
        )
    if layout == "two_column_or_split":
        return OcrContentAssessment(
            page_type="prose_or_mixed",
            layout=layout,
            rag_action="manual_layout_review",
            reasons=("reading_order_not_verified",),
        )
    return OcrContentAssessment(
        page_type="prose_candidate",
        layout=layout,
        rag_action="stage_for_review",
        reasons=("terminology_and_citation_review_required",),
    )
