from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fitness_rag.xiaohongshu import (
    XiaohongshuTopicStore,
    normalize_note_url,
    normalize_notes,
    parse_visible_count,
)


class XiaohongshuCollectorTests(unittest.TestCase):
    def test_url_normalization_keeps_only_public_note_identity(self):
        normalized = normalize_note_url(
            "https://www.xiaohongshu.com/explore/abc123?xsec_token=private#comments"
        )

        self.assertEqual(normalized, "https://www.xiaohongshu.com/explore/abc123")
        self.assertIsNone(normalize_note_url("https://example.com/explore/abc123"))

    def test_visible_counts_are_parsed_without_guessing(self):
        self.assertEqual(parse_visible_count("1.2万"), 12_000)
        self.assertEqual(parse_visible_count("3K"), 3_000)
        self.assertEqual(parse_visible_count("10万+"), 100_000)
        self.assertEqual(parse_visible_count("87"), 87)
        self.assertIsNone(parse_visible_count("赞"))

    def test_notes_are_deduplicated_and_persisted_locally(self):
        notes = normalize_notes(
            "空腹有氧",
            [
                {
                    "url": "/explore/abc123?tracking=discarded",
                    "title": "空腹有氧测试",
                    "author": "公开作者名",
                    "visible_text": "空腹有氧测试 公开作者名 1.2万",
                    "like_text": "1.2万",
                },
                {
                    "url": "https://www.xiaohongshu.com/explore/abc123",
                    "title": "重复卡片",
                },
            ],
        )

        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].like_count, 12_000)
        self.assertEqual(notes[0].author, "公开作者名")
        with tempfile.TemporaryDirectory() as directory:
            store = XiaohongshuTopicStore(Path(directory) / "topics.sqlite3")
            self.assertEqual(store.save(notes), 1)
            saved = store.list("空腹有氧")

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["note_id"], "abc123")
        self.assertNotIn("tracking", saved[0]["url"])


if __name__ == "__main__":
    unittest.main()
