from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fitness_rag.private_reviews import PrivateReviewStore


class PrivateReviewStoreTests(unittest.TestCase):
    def test_review_is_persisted_and_can_be_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PrivateReviewStore(Path(directory) / "reviews.sqlite3")
            first = store.save("book-section-p0001-c01", "approved", "checked page")
            second = store.save("book-section-p0001-c01", "rejected", "column order")

            self.assertEqual(first["decision"], "approved")
            self.assertEqual(second["decision"], "rejected")
            self.assertEqual(store.get("book-section-p0001-c01")["note"], "column order")
            self.assertEqual(store.summary()["reviewed"], 1)

    def test_invalid_decision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PrivateReviewStore(Path(directory) / "reviews.sqlite3")
            with self.assertRaises(ValueError):
                store.save("book-section-p0001-c01", "pending")


if __name__ == "__main__":
    unittest.main()
