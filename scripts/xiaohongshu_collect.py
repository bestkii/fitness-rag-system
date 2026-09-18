from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fitness_rag.xiaohongshu import (
    XiaohongshuCollector,
    XiaohongshuCollectorError,
    XiaohongshuTopicStore,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect a small set of visible Xiaohongshu public search cards."
    )
    parser.add_argument("keyword", nargs="?", help="Search keyword, for example: 空腹有氧")
    parser.add_argument(
        "--home-fitness",
        action="store_true",
        help="Filter fitness-related cards from the public home feed",
    )
    parser.add_argument("--limit", type=int, default=20, help="Maximum notes (hard cap: 30)")
    parser.add_argument("--scrolls", type=int, default=3, help="Scrolls (hard cap: 5)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    collector = XiaohongshuCollector()
    store = XiaohongshuTopicStore()
    try:
        if args.home_fitness:
            notes = collector.collect_home_fitness(
                limit=args.limit, max_scrolls=args.scrolls
            )
        elif args.keyword:
            notes = collector.collect(
                args.keyword, limit=args.limit, max_scrolls=args.scrolls
            )
        else:
            raise ValueError("Provide a keyword or use --home-fitness.")
    except (XiaohongshuCollectorError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    store.save(notes)
    print(json.dumps([note.to_dict() for note in notes], ensure_ascii=False, indent=2))
    print(f"已保存 {len(notes)} 条公开搜索卡片到本机趋势库。")
