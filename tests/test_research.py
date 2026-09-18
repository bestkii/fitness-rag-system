from __future__ import annotations

import unittest

from fitness_rag.research import (
    ResearchService,
    _academic_topic,
    _matches_required_concepts,
)


class FakeSearchProvider:
    def search(self, query: str, count: int) -> list[dict]:
        del count
        return [
            {
                "title": "Fasted exercise WHO guidance",
                "url": "https://www.who.int/example",
                "description": f"WHO evidence for {query}",
            },
            {
                "title": "Fasted exercise university review",
                "url": "https://research.example.edu/review",
                "description": f"A university evidence review for {query}.",
            },
            {
                "title": "Fasted exercise general article",
                "url": "https://example.com/article",
                "description": f"A general summary for {query}.",
            },
        ]


class ResearchServiceTests(unittest.TestCase):
    def test_research_deduplicates_and_prioritizes_sources(self):
        packet = ResearchService(FakeSearchProvider()).research("空腹有氧是否更减脂")

        self.assertEqual(len(packet.queries), 2)
        self.assertEqual(len(packet.sources), 3)
        self.assertEqual(packet.sources[0].source_tier, "authoritative")
        self.assertEqual(packet.sources[1].source_tier, "academic")
        self.assertEqual(packet.evidence_status, "ready_for_drafting")
        self.assertFalse(packet.review_flags)

    def test_short_topic_is_rejected_before_search(self):
        with self.assertRaises(ValueError):
            ResearchService(FakeSearchProvider()).research("hi")

    def test_common_chinese_fitness_terms_are_expanded_for_academic_search(self):
        expanded = _academic_topic("空腹有氧是否更减脂")

        self.assertIn("fasted aerobic exercise", expanded)
        self.assertIn("fat loss", expanded)
        self.assertEqual(expanded.count("aerobic exercise"), 1)

    def test_fasted_cardio_queries_avoid_broad_nutrition_terms(self):
        queries = ResearchService.plan_queries("空腹有氧真的更减脂吗？")

        self.assertEqual(len(queries), 2)
        self.assertTrue(all("fasted" in query for query in queries))
        self.assertNotIn("nutrition evidence", " ".join(queries))

    def test_fasted_cardio_requires_fasting_and_exercise_concepts(self):
        packet = ResearchService(FakeSearchProvider()).research("空腹有氧是否更减脂")

        relevant = packet.sources[0]
        self.assertTrue(
            _matches_required_concepts(relevant, "空腹有氧是否更减脂")
        )


if __name__ == "__main__":
    unittest.main()
