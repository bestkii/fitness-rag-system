from __future__ import annotations

import asyncio
import json
from datetime import datetime
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


TAGS = {"strengthtraining": "StrengthTraining", "fitness": "Fitness"}
TIMELINE_URL = "https://mastodon.social/api/v1/timelines/tag"
POST_LIMIT = 20
TIMEOUT_SECONDS = 5


class QuestionTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.has_question_mark = False
        self.link_text: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "a":
            self.link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.link_text is not None:
            text = "".join(self.link_text).strip()
            if not text.startswith(("http://", "https://")):
                self.has_question_mark |= "?" in text
            self.link_text = None

    def handle_data(self, data: str) -> None:
        if self.link_text is None:
            self.has_question_mark |= "?" in data
        else:
            self.link_text.append(data)


def _read_timeline(tag: str) -> list:
    request = Request(
        f"{TIMELINE_URL}/{tag}?limit={POST_LIMIT}",
        headers={"Accept": "application/json", "User-Agent": "FitnessEvidenceStudio/1.0"},
    )
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        posts = json.load(response)
    if not isinstance(posts, list):
        raise ValueError("Expected a list of Mastodon posts.")
    return posts[:POST_LIMIT]


def _candidate(post: object, tag: str) -> tuple[str, datetime, dict[str, str]] | None:
    if not isinstance(post, dict):
        return None
    if post.get("visibility") != "public" or post.get("reblog") is not None:
        return None
    language = post.get("language")
    if not isinstance(language, str) or language.lower().split("-", 1)[0] != "en":
        return None
    uri, url, created_at, content = (
        post.get("uri"), post.get("url"), post.get("created_at"), post.get("content")
    )
    if not all(isinstance(value, str) and value for value in (uri, url, created_at, content)):
        return None
    try:
        timestamp = datetime.fromisoformat(created_at)
        source = urlsplit(url)
    except ValueError:
        return None
    if (
        timestamp.tzinfo is None
        or source.scheme != "https"
        or not source.hostname
        or source.username is not None
    ):
        return None
    parser = QuestionTextParser()
    parser.feed(content)
    parser.close()
    if not parser.has_question_mark:
        return None
    return uri, timestamp, {"url": url, "tag": TAGS[tag], "created_at": created_at}


async def load_community_questions() -> dict:
    async def fetch(tag: str) -> list | None:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_read_timeline, tag), timeout=TIMEOUT_SECONDS
            )
        except (OSError, HTTPException, ValueError):
            return None

    feeds = await asyncio.gather(*(fetch(tag) for tag in TAGS))
    by_uri: dict[str, tuple[datetime, dict[str, str]]] = {}
    unavailable = []
    for tag, posts in zip(TAGS, feeds):
        if posts is None:
            unavailable.append(TAGS[tag])
            continue
        for post in posts:
            candidate = _candidate(post, tag)
            if candidate is not None:
                uri, timestamp, item = candidate
                by_uri.setdefault(uri, (timestamp, item))

    return {
        "questions": [
            item for _, item in sorted(by_uri.values(), key=lambda entry: entry[0], reverse=True)
        ],
        "unavailable_tags": unavailable,
    }
