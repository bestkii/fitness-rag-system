from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


PAGE_NUMBER_PATTERN = re.compile(r"^(?:\d{1,4}|[ivxlcdm]{1,8})$", re.IGNORECASE)


@dataclass(frozen=True)
class OrderedLine:
    text: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    @property
    def x_center(self) -> float:
        return (self.x_min + self.x_max) / 2

    @property
    def y_center(self) -> float:
        return (self.y_min + self.y_max) / 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _line_geometry(text: str, box: Sequence[Sequence[float]]) -> OrderedLine | None:
    normalized = " ".join(str(text).split())
    if not normalized:
        return None
    points = [point for point in box if len(point) >= 2]
    if not points:
        return None
    x_values = [float(point[0]) for point in points]
    y_values = [float(point[1]) for point in points]
    return OrderedLine(
        text=normalized,
        x_min=min(x_values),
        x_max=max(x_values),
        y_min=min(y_values),
        y_max=max(y_values),
    )


def reconstruct_reading_order(
    texts: Iterable[str],
    boxes: Iterable[Sequence[Sequence[float]]],
    *,
    image_width: int | float,
    layout: str,
) -> list[str]:
    """Return deterministic lines, reading a detected split page left then right."""

    records = [
        record
        for text, box in zip(texts, boxes, strict=False)
        if (record := _line_geometry(text, box)) is not None
        and not PAGE_NUMBER_PATTERN.fullmatch(record.text)
    ]
    if not records:
        return []
    if layout != "two_column_or_split" or image_width <= 0:
        return [record.text for record in sorted(records, key=lambda item: (item.y_min, item.x_min))]

    spanning = [
        record
        for record in records
        if record.x_max - record.x_min >= image_width * 0.60
        or (record.x_min <= image_width * 0.35 and record.x_max >= image_width * 0.65)
    ]
    column_lines = [record for record in records if record not in spanning]
    if not column_lines:
        return [record.text for record in sorted(spanning, key=lambda item: (item.y_min, item.x_min))]

    def order_column_band(band: list[OrderedLine]) -> list[OrderedLine]:
        left = [record for record in band if record.x_center < image_width / 2]
        right = [record for record in band if record.x_center >= image_width / 2]
        return sorted(left, key=lambda item: (item.y_min, item.x_min)) + sorted(
            right, key=lambda item: (item.y_min, item.x_min)
        )

    ordered: list[OrderedLine] = []
    remaining = list(column_lines)
    for separator in sorted(spanning, key=lambda item: (item.y_min, item.x_min)):
        band = [record for record in remaining if record.y_center < separator.y_center]
        ordered.extend(order_column_band(band))
        remaining = [record for record in remaining if record not in band]
        ordered.append(separator)
    ordered.extend(order_column_band(remaining))
    return [record.text for record in ordered]


def chunk_lines(
    lines: Iterable[str],
    *,
    target_characters: int = 650,
    overlap_characters: int = 100,
    minimum_characters: int = 120,
) -> list[str]:
    """Create deterministic line-aware chunks with a small trailing overlap."""

    if target_characters < 100:
        raise ValueError("target_characters must be at least 100")
    if overlap_characters < 0 or overlap_characters >= target_characters:
        raise ValueError("overlap_characters must be non-negative and smaller than target")
    clean_lines = [" ".join(str(line).split()) for line in lines if str(line).strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for line in clean_lines:
        addition = len(line) + (1 if current else 0)
        if current and current_length + addition > target_characters:
            chunks.append("\n".join(current))
            overlap: list[str] = []
            overlap_length = 0
            for prior_line in reversed(current):
                if overlap and overlap_length + len(prior_line) + 1 > overlap_characters:
                    break
                overlap.insert(0, prior_line)
                overlap_length += len(prior_line) + (1 if overlap_length else 0)
            current = overlap
            current_length = len("\n".join(current))
        current.append(line)
        current_length += len(line) + (1 if current_length else 0)
    if current:
        final = "\n".join(current)
        if len(final) >= minimum_characters or not chunks:
            chunks.append(final)
        else:
            chunks[-1] = f"{chunks[-1]}\n{final}"
    return chunks
