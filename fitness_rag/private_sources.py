from __future__ import annotations

import json
from pathlib import Path

from .config import PRIVATE_PAGE_PREVIEW_DIR, PRIVATE_SOURCE_REGISTRY_PATH
from .ocr_quality import validate_source_id


class PrivateSourceRegistry:
    """Resolve explicitly registered local PDFs and render bounded page previews."""

    def __init__(self, path: Path = PRIVATE_SOURCE_REGISTRY_PATH) -> None:
        self.path = path

    def load(self) -> dict[str, Path]:
        if not self.path.is_file():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            validate_source_id(source_id): Path(value).resolve()
            for source_id, value in payload.get("sources", {}).items()
        }

    def source_path(self, source_id: str) -> Path:
        normalized = validate_source_id(source_id)
        source = self.load().get(normalized)
        if source is None or not source.is_file() or source.suffix.casefold() != ".pdf":
            raise FileNotFoundError(normalized)
        return source

    def render_page(self, source_id: str, pdf_page: int, *, scale: float = 1.35) -> Path:
        if pdf_page < 1:
            raise ValueError("PDF page must be positive")
        source = self.source_path(source_id)
        normalized = validate_source_id(source_id)
        output_dir = PRIVATE_PAGE_PREVIEW_DIR / normalized
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"page_{pdf_page:04d}.png"
        if output.is_file():
            return output
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for private page previews") from exc
        document = fitz.open(source)
        try:
            if pdf_page > document.page_count:
                raise ValueError("PDF page exceeds source length")
            pixmap = document.load_page(pdf_page - 1).get_pixmap(
                matrix=fitz.Matrix(scale, scale), alpha=False
            )
            pixmap.save(output)
        finally:
            document.close()
        return output
