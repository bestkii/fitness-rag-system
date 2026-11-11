from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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

    def test_english_template_and_export_keep_topic_provenance_separate(self):
        from fitness_rag.drafts import DraftNotApprovedError

        legacy_analyzer = Mock()
        agent = ContentAgent(ResearchService(FakeSearchProvider()), legacy_analyzer)
        community_url = "https://mastodon.social/@example/123"
        draft = agent.create_draft(
            "How often should beginners strength train?",
            language="en",
            community_source_url=community_url,
        )
        self.assertEqual(draft["language"], "en")
        self.assertEqual(draft["audience"], "Fitness beginners")
        self.assertEqual(draft["tone"], "Clear, measured and friendly")
        self.assertEqual(draft["generation_mode"], "template")
        self.assertEqual(len(draft["content"]["explanation"]), 3)
        self.assertEqual(draft["community_source_url"], community_url)
        self.assertNotIn(community_url, str(draft["research"]))
        self.assertIn("[S1]", draft["content"]["body"])
        self.assertEqual(len(draft["content"]["carousel"]), 5)
        self.assertIsNone(draft["legacy_rag_context"])
        legacy_analyzer.assert_not_called()

        with tempfile.TemporaryDirectory() as directory:
            store = DraftStore(Path(directory))
            store.save(draft)
            with self.assertRaises(DraftNotApprovedError):
                store.export_text(draft["id"])
            store.approve(draft["id"])
            exported = store.export_text(draft["id"])

        self.assertIn("Review status: approved", exported)
        self.assertIn("Five-card carousel script", exported)
        self.assertIn(f"Community topic source\n{community_url}", exported)
        self.assertNotIn(community_url, exported.split("Research sources\n")[1])

    def test_english_model_rejects_an_explanation_with_an_unknown_source(self):
        payload = {
            "title": "A fitness question",
            "body": "A finding [S1].",
            "hashtags": ["Fitness"],
            "carousel": [{"heading": "Question", "copy": "Check the evidence."}] * 5,
            "explanation": [{"text": "A finding", "sources": [99]}] * 3,
        }
        client = Mock()
        client.chat.completions.create.return_value.choices = [
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))
        ]
        fake_openai = SimpleNamespace(OpenAI=Mock(return_value=client))
        agent = ContentAgent(ResearchService(FakeSearchProvider()))
        with patch.dict(os.environ, {"CONTENT_API_KEY": "test-key"}), patch.dict(
            sys.modules, {"openai": fake_openai}
        ):
            with self.assertRaisesRegex(ValueError, "valid source numbers"):
                agent.create_draft("How often should beginners train?", language="en")

    def test_english_model_prompt_uses_only_research_evidence(self):
        model_payload = {
            "title": "How often should beginners strength train?",
            "body": "A measured summary [S1].",
            "hashtags": ["Fitness", "Research", "Training"],
            "carousel": [{"heading": "Review", "copy": "Check the evidence."}] * 5,
            "explanation": [{"text": "Check the study population and its limitations.", "sources": [1]}] * 3,
        }
        client = Mock()
        completion = client.chat.completions.create
        completion.return_value.choices = [
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(model_payload)))
        ]
        fake_openai = SimpleNamespace(OpenAI=Mock(return_value=client))
        legacy_analyzer = Mock(return_value={"summary": "Synthetic context"})
        agent = ContentAgent(ResearchService(FakeSearchProvider()), legacy_analyzer)
        with patch.dict(os.environ, {"CONTENT_API_KEY": "test-key"}), patch.dict(
            sys.modules, {"openai": fake_openai}
        ):
            draft = agent.create_draft(
                "How often should beginners strength train?",
                language="en",
                community_source_url="https://mastodon.social/@example/123",
            )
        self.assertEqual(draft["content"]["title"], model_payload["title"])
        self.assertEqual(draft["content"]["carousel"], model_payload["carousel"])
        self.assertEqual(draft["content"]["explanation"], model_payload["explanation"])
        messages = completion.call_args.kwargs["messages"]
        self.assertIn("English fitness content editor", messages[0]["content"])
        self.assertIn("Write every field in English.", messages[1]["content"])
        self.assertIn("[S1]", messages[1]["content"])
        self.assertNotIn("Synthetic", messages[1]["content"])
        self.assertNotIn("mastodon.social", messages[1]["content"])
        legacy_analyzer.assert_not_called()

    def test_legacy_saved_draft_without_language_still_exports_in_chinese(self):
        agent = ContentAgent(ResearchService(FakeSearchProvider()))
        draft = agent.create_draft("力量训练后的恢复策略")
        del draft["language"]
        del draft["community_source_url"]
        with tempfile.TemporaryDirectory() as directory:
            store = DraftStore(Path(directory))
            store.save(draft)
            store.approve(draft["id"])
            self.assertIn("审核状态：approved", store.export_text(draft["id"]))

if __name__ == "__main__":
    unittest.main()
