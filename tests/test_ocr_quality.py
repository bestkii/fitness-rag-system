from __future__ import annotations

import unittest

from fitness_rag.ocr_quality import (
    assess_ocr_content,
    detect_page_layout,
    evaluate_ocr_page,
    select_even_pages,
    validate_source_id,
)


class OcrQualityTests(unittest.TestCase):
    def test_even_page_selection_is_deterministic_and_bounded(self):
        pages = select_even_pages(100, 5, start_page=11, end_page=91)

        self.assertEqual(pages, [11, 31, 51, 71, 91])

    def test_sample_count_is_capped_by_available_pages(self):
        self.assertEqual(
            select_even_pages(5, 20, start_page=2, end_page=4), [2, 3, 4]
        )

    def test_readable_page_requires_text_and_confidence(self):
        metrics = evaluate_ocr_page(
            ["力量训练适应与动作技术" * 8, "训练计划设计" * 8, "恢复与营养" * 8],
            [0.96, 0.94, 0.92],
            native_text_characters=0,
        )

        self.assertEqual(metrics.status, "ocr_readable")
        self.assertGreater(metrics.character_count, 80)

    def test_low_confidence_page_is_flagged(self):
        metrics = evaluate_ocr_page(
            ["文本" * 50, "更多文本" * 30, "结论" * 20], [0.70, 0.74, 0.78]
        )

        self.assertEqual(metrics.status, "needs_review")

    def test_source_id_rejects_paths(self):
        self.assertEqual(validate_source_id("cscs_2021"), "cscs_2021")
        with self.assertRaises(ValueError):
            validate_source_id("../private")

    def test_reference_page_is_excluded_even_when_ocr_is_readable(self):
        lines = ["参考文献", "1. Example 2020"] + ["Journal entry 12: 1-10"] * 8
        metrics = evaluate_ocr_page(lines, [0.99] * len(lines))

        assessment = assess_ocr_content(metrics, lines)

        self.assertEqual(metrics.status, "ocr_readable")
        self.assertEqual(assessment.page_type, "reference_page")
        self.assertEqual(assessment.rag_action, "exclude")

    def test_continuation_reference_page_is_excluded_without_heading(self):
        lines = [
            f"{index}. Author, A. Journal study. 12: 1-10, 20{index:02d}."
            for index in range(1, 8)
        ]
        metrics = evaluate_ocr_page(lines, [0.99] * len(lines))

        assessment = assess_ocr_content(metrics, lines)

        self.assertEqual(assessment.page_type, "reference_page")
        self.assertEqual(assessment.rag_action, "exclude")

    def test_dense_numeric_table_requires_table_review(self):
        lines = [f"{index} 20 30" for index in range(20)]
        metrics = evaluate_ocr_page(lines, [0.97] * len(lines))

        assessment = assess_ocr_content(metrics, lines)

        self.assertEqual(assessment.page_type, "table_heavy")
        self.assertEqual(assessment.rag_action, "manual_table_review")

    def test_two_column_layout_requires_layout_review(self):
        lines = ["足够长的训练正文内容" * 5 for _ in range(10)]
        boxes = [
            [[10, index], [58, index], [58, index + 1], [10, index + 1]]
            for index in range(5)
        ] + [
            [[42, index], [90, index], [90, index + 1], [42, index + 1]]
            for index in range(5)
        ]
        metrics = evaluate_ocr_page(lines, [0.98] * len(lines))

        self.assertEqual(detect_page_layout(boxes, image_width=100), "two_column_or_split")
        self.assertEqual(
            assess_ocr_content(
                metrics, lines, boxes=boxes, image_width=100
            ).rag_action,
            "manual_layout_review",
        )


if __name__ == "__main__":
    unittest.main()
