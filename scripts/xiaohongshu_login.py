from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fitness_rag.xiaohongshu import XiaohongshuCollectorError, open_login_session


if __name__ == "__main__":
    try:
        open_login_session()
    except XiaohongshuCollectorError as exc:
        raise SystemExit(str(exc)) from exc
