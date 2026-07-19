from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 20 * 1024 * 1024
FORBIDDEN_NAMES = {"api-key.txt", ".env"}
FORBIDDEN_SUFFIXES = {".pdf", ".mp4", ".mov", ".zip"}
IGNORED_DIRECTORIES = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".txt",
    ".yml",
    ".yaml",
}
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
PERSONAL_PATH_PATTERN = re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE)


def main() -> int:
    errors: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue
        if any(part.startswith("fitness_vector_db") for part in path.parts):
            continue
        relative = path.relative_to(ROOT)
        lowered_name = path.name.casefold()
        if lowered_name in FORBIDDEN_NAMES:
            errors.append(f"forbidden filename: {relative.as_posix()}")
        if path.suffix.casefold() in FORBIDDEN_SUFFIXES:
            errors.append(f"forbidden artifact: {relative.as_posix()}")
        if path.stat().st_size > MAX_FILE_BYTES:
            errors.append(f"oversized file: {relative.as_posix()}")
        if path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SECRET_PATTERN.search(text):
            errors.append(f"credential-like token: {relative.as_posix()}")
        if PERSONAL_PATH_PATTERN.search(text):
            errors.append(f"personal absolute path: {relative.as_posix()}")

    print(f"Release guard checked {ROOT}")
    for error in errors:
        print(f"ERROR: {error}")
    print("PASS" if not errors else "FAIL")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
