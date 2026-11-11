from __future__ import annotations

import io
import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from fitness_rag.community import load_community_questions


def public_post(identifier: str, **changes) -> dict:
    return {
        "uri": f"https://example.org/users/editor/statuses/{identifier}",
        "url": f"https://example.org/@editor/{identifier}",
        "created_at": "2026-11-11T01:00:00Z",
        "language": "en",
        "visibility": "public",
        "reblog": None,
        "content": "<p>How often should I train&#63;</p>",
        **changes,
    }


class CommunityQuestionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_filters_sorts_and_deduplicates_without_returning_post_text(self):
        first = public_post("first")
        latest = public_post("latest", created_at="2026-11-11T02:00:00Z", language="en-US")
        feeds = {
            "strengthtraining": [
                first,
                public_post("language", language="fr"),
                public_post("boost", reblog=first),
                public_post("private", visibility="unlisted"),
                public_post("link", content='<a href="https://example.org/?x=1">Workout</a>'),
                public_post(
                    "tracking-link",
                    content='<a href="https://example.org/?x=1"><span>https://</span>example.org/?x=1</a>',
                ),
                public_post("bad-url", url="javascript:alert(1)"),
                public_post("bad-date", created_at="unknown"),
                public_post("bad-timezone", created_at="2026-11-11T01:00:00"),
                None,
            ],
            "fitness": [{**first, "url": "https://another.example/@editor/first"}, latest],
        }

        def open_timeline(request, *, timeout):
            self.assertEqual(timeout, 5)
            tag, query = request.full_url.rsplit("/", 1)[1].split("?")
            self.assertEqual(query, "limit=20")
            return io.BytesIO(json.dumps(feeds[tag]).encode())

        with patch("fitness_rag.community.urlopen", side_effect=open_timeline):
            response = await load_community_questions()

        self.assertEqual(response["unavailable_tags"], [])
        self.assertEqual(
            response["questions"],
            [
                {"url": latest["url"], "tag": "Fitness", "created_at": latest["created_at"]},
                {"url": first["url"], "tag": "StrengthTraining", "created_at": first["created_at"]},
            ],
        )

    async def test_empty_feeds_are_available(self):
        with patch("fitness_rag.community.urlopen", side_effect=lambda *a, **kw: io.BytesIO(b"[]")):
            self.assertEqual(await load_community_questions(), {"questions": [], "unavailable_tags": []})

    async def test_partial_failure_preserves_the_available_feed(self):
        post = public_post("first")

        def open_timeline(request, **kwargs):
            if "/fitness?" in request.full_url:
                raise HTTPError(request.full_url, 429, "Too Many Requests", {}, None)
            return io.BytesIO(json.dumps([post]).encode())

        with patch("fitness_rag.community.urlopen", side_effect=open_timeline):
            response = await load_community_questions()

        self.assertEqual(response["unavailable_tags"], ["Fitness"])
        self.assertEqual([item["url"] for item in response["questions"]], [post["url"]])

    async def test_reports_unavailable_feeds_for_timeout_and_malformed_responses(self):
        def open_timeline(request, **kwargs):
            if "/fitness?" in request.full_url:
                raise URLError(TimeoutError("timed out"))
            return io.BytesIO(b'{"unexpected": "object"}')

        with patch("fitness_rag.community.urlopen", side_effect=open_timeline):
            response = await load_community_questions()
        self.assertEqual(response, {"questions": [], "unavailable_tags": ["StrengthTraining", "Fitness"]})

        with patch("fitness_rag.community.urlopen", side_effect=lambda *a, **kw: io.BytesIO(b"invalid json")):
            self.assertEqual(await load_community_questions(), response)
