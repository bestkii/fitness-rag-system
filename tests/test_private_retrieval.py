from __future__ import annotations

import unittest

from fitness_rag.private_retrieval import PrivateTextbookRetriever


def chunk(
    chunk_id: str, text: str, printed_page: int, source_id: str = "book_one"
) -> dict:
    return {
        "chunk_id": chunk_id,
        "source_id": source_id,
        "title": "Local Book",
        "section_id": "section_one",
        "section_title": "Section One",
        "pdf_page": printed_page + 10,
        "printed_page": printed_page,
        "review_status": "machine_reconstructed_needs_review",
        "text": text,
    }


class PrivateTextbookRetrieverTests(unittest.TestCase):
    def setUp(self):
        self.retriever = PrivateTextbookRetriever(
            chunks=[
                chunk("one", "抗阻训练计划需要安排训练频率和练习顺序", 20),
                chunk("two", "均衡膳食包括多样食物和合理搭配", 30),
                chunk("three", "恢复需要考虑睡眠和训练负荷", 40),
            ]
        )

    def test_search_returns_page_cited_local_result(self):
        results = self.retriever.search("练习顺序怎么安排", top_k=2)

        self.assertEqual(results[0]["chunk_id"], "one")
        self.assertEqual(results[0]["printed_page"], 20)
        self.assertEqual(results[0]["privacy"], "local_only")
        self.assertEqual([result["rank"] for result in results], [1, 2])

    def test_search_validates_limits(self):
        with self.assertRaises(ValueError):
            self.retriever.search("a")
        with self.assertRaises(ValueError):
            self.retriever.search("正常问题", top_k=11)

    def test_review_queue_uses_one_chunk_per_page_and_skips_reviewed(self):
        retriever = PrivateTextbookRetriever(
            chunks=[
                chunk("book-one-p0030-c01", "第一段", 30),
                chunk("book-one-p0030-c02", "第二段", 30),
                chunk("book-one-p0031-c01", "第三段", 31),
            ]
        )

        queue = retriever.review_queue(
            reviewed_ids={"book-one-p0030-c01"}, limit=3
        )

        self.assertEqual(
            [item["chunk_id"] for item in queue],
            ["book-one-p0030-c02", "book-one-p0031-c01"],
        )

    def test_review_queue_spans_both_sources_and_page_ranges(self):
        chunks = [
            chunk(f"a-{page}", f"A {page}", page, "book_a")
            for page in range(1, 11)
        ] + [
            chunk(f"b-{page}", f"B {page}", page, "book_b")
            for page in range(101, 111)
        ]
        retriever = PrivateTextbookRetriever(chunks=chunks)

        queue = retriever.review_queue(reviewed_ids=set(), limit=6)

        self.assertEqual(
            [(item["source_id"], item["printed_page"]) for item in queue],
            [
                ("book_a", 1),
                ("book_b", 101),
                ("book_a", 5),
                ("book_b", 105),
                ("book_a", 10),
                ("book_b", 110),
            ],
        )


if __name__ == "__main__":
    unittest.main()
