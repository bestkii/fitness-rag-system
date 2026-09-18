from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fitness_rag.content import ContentAgent
from fitness_rag.drafts import DraftStore
from fitness_rag.research import ResearchService


class FakeSearchProvider:
    def search(self, query: str, count: int) -> list[dict]:
        del query, count
        return [
            {
                "title": "WHO source",
                "url": "https://www.who.int/health-topic",
                "description": "Public-health guidance emphasizes context and safe progression.",
            },
            {
                "title": "NIH source",
                "url": "https://www.ncbi.nlm.nih.gov/example",
                "description": "A review reports mixed evidence and important limitations.",
            },
            {
                "title": "Background source",
                "url": "https://example.org/background",
                "description": "A plain-language background article.",
            },
        ]


class ContentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.previous_content_key = os.environ.pop("CONTENT_API_KEY", None)
        self.previous_deepseek_key = os.environ.pop("DEEPSEEK_API_KEY", None)

    def tearDown(self):
        if self.previous_content_key is not None:
            os.environ["CONTENT_API_KEY"] = self.previous_content_key
        if self.previous_deepseek_key is not None:
            os.environ["DEEPSEEK_API_KEY"] = self.previous_deepseek_key

    def test_template_draft_requires_review_and_uses_source_markers(self):
        agent = ContentAgent(ResearchService(FakeSearchProvider()))
        draft = agent.create_draft("空腹有氧是否更减脂")

        self.assertEqual(draft["status"], "draft")
        self.assertEqual(draft["generation_mode"], "template")
        self.assertTrue(draft["review"]["required"])
        self.assertIn("[S1]", draft["content"]["body"])
        self.assertEqual(len(draft["content"]["carousel"]), 5)
        self.assertEqual(draft["publishing"]["mode"], "export_only")

    def test_approval_is_persisted_and_exported(self):
        agent = ContentAgent(ResearchService(FakeSearchProvider()))
        draft = agent.create_draft("力量训练后的恢复策略")
        with tempfile.TemporaryDirectory() as directory:
            store = DraftStore(Path(directory))
            store.save(draft)
            approved = store.approve(draft["id"])
            exported = store.export_text(draft["id"])

        self.assertEqual(approved["status"], "approved")
        self.assertIsNotNone(approved["review"]["approved_at"])
        self.assertIn("审核状态：approved", exported)
        self.assertIn("https://www.who.int/health-topic", exported)

    def test_unapproved_draft_cannot_be_exported(self):
        from fitness_rag.drafts import DraftNotApprovedError

        agent = ContentAgent(ResearchService(FakeSearchProvider()))
        draft = agent.create_draft("力量训练后的恢复策略")
        with tempfile.TemporaryDirectory() as directory:
            store = DraftStore(Path(directory))
            store.save(draft)
            with self.assertRaises(DraftNotApprovedError):
                store.export_text(draft["id"])


if __name__ == "__main__":
    unittest.main()
