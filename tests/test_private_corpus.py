from __future__ import annotations

import unittest

from fitness_rag.private_corpus import chunk_lines, reconstruct_reading_order


class PrivateCorpusTests(unittest.TestCase):
    def test_two_columns_are_read_left_then_right(self):
        texts = ["右一", "左一", "右二", "左二"]
        boxes = [
            [[60, 10], [90, 10], [90, 20], [60, 20]],
            [[10, 10], [40, 10], [40, 20], [10, 20]],
            [[60, 30], [90, 30], [90, 40], [60, 40]],
            [[10, 30], [40, 30], [40, 40], [10, 40]],
        ]

        ordered = reconstruct_reading_order(
            texts, boxes, image_width=100, layout="two_column_or_split"
        )

        self.assertEqual(ordered, ["左一", "左二", "右一", "右二"])

    def test_page_numbers_are_removed(self):
        ordered = reconstruct_reading_order(
            ["正文", "12"],
            [
                [[10, 10], [90, 10], [90, 20], [10, 20]],
                [[45, 90], [55, 90], [55, 99], [45, 99]],
            ],
            image_width=100,
            layout="single_or_mixed",
        )

        self.assertEqual(ordered, ["正文"])

    def test_spanning_lines_keep_vertical_regions_in_order(self):
        texts = ["页标题", "上方整行一", "上方整行二", "右栏", "左栏"]
        boxes = [
            [[10, 5], [40, 5], [40, 10], [10, 10]],
            [[10, 20], [90, 20], [90, 30], [10, 30]],
            [[10, 35], [90, 35], [90, 45], [10, 45]],
            [[60, 55], [90, 55], [90, 65], [60, 65]],
            [[10, 55], [40, 55], [40, 65], [10, 65]],
        ]

        ordered = reconstruct_reading_order(
            texts, boxes, image_width=100, layout="two_column_or_split"
        )

        self.assertEqual(ordered, ["页标题", "上方整行一", "上方整行二", "左栏", "右栏"])

    def test_chunks_overlap_without_dropping_lines(self):
        lines = [f"第{index}行" + "内容" * 12 for index in range(12)]

        chunks = chunk_lines(
            lines,
            target_characters=160,
            overlap_characters=50,
            minimum_characters=20,
        )

        self.assertGreater(len(chunks), 1)
        combined = "\n".join(chunks)
        for line in lines:
            self.assertIn(line, combined)


if __name__ == "__main__":
    unittest.main()
