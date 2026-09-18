from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .evidence import (
    CompositeEvidenceProvider,
    CrossrefSearchProvider,
    EvidenceProviderError,
    PubMedSearchProvider,
)


BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_TRUSTED_DOMAINS = (
    "who.int",
    "nih.gov",
    "ncbi.nlm.nih.gov",
    "cdc.gov",
    "nhs.uk",
    "gov.cn",
    "acsm.org",
    "nsca.com",
    "cochrane.org",
)


class ResearchError(RuntimeError):
    """Raised when the configured research provider cannot return evidence."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    domain: str
    source_tier: str
    query: str
    published_at: str | None = None


@dataclass(frozen=True)
class ResearchPacket:
    topic: str
    queries: list[str]
    sources: list[SearchResult]
    generated_at: str
    evidence_status: str
    review_flags: list[str]

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "queries": self.queries,
            "sources": [asdict(source) for source in self.sources],
            "generated_at": self.generated_at,
            "evidence_status": self.evidence_status,
            "review_flags": self.review_flags,
        }


class SearchProvider(Protocol):
    def search(self, query: str, count: int) -> list[dict]: ...


def _domain_for(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return (parsed.hostname or "").casefold().removeprefix("www.")


def _trusted_domains() -> tuple[str, ...]:
    configured = os.environ.get("TRUSTED_SOURCE_DOMAINS", "")
    additions = tuple(
        item.strip().casefold().removeprefix("www.")
        for item in configured.split(",")
        if item.strip()
    )
    return tuple(dict.fromkeys((*DEFAULT_TRUSTED_DOMAINS, *additions)))


def _source_tier(domain: str) -> str:
    if any(domain == trusted or domain.endswith(f".{trusted}") for trusted in _trusted_domains()):
        return "authoritative"
    if domain.endswith(".edu") or domain.endswith(".ac.uk") or domain.endswith(".edu.cn"):
        return "academic"
    return "general"


class BraveSearchProvider:
    """Small dependency-free adapter for Brave Web Search."""

    def __init__(self, api_key: str | None = None, timeout_seconds: float = 20.0):
        self.api_key = api_key or os.environ.get("BRAVE_SEARCH_API_KEY", "")
        self.timeout_seconds = timeout_seconds

    name = "brave"

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, count: int) -> list[dict]:
        if not self.api_key:
            raise ResearchError(
                "Web research is not configured. Set BRAVE_SEARCH_API_KEY in the environment."
            )
        params = urlencode(
            {
                "q": query,
                "count": max(1, min(count, 20)),
                "safesearch": "strict",
                "extra_snippets": "true",
            }
        )
        request = Request(
            f"{BRAVE_SEARCH_URL}?{params}",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
                "User-Agent": "fitness-rag-agent/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ResearchError(f"Search provider returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            raise ResearchError("Search provider could not be reached.") from exc
        except json.JSONDecodeError as exc:
            raise ResearchError("Search provider returned invalid JSON.") from exc
        return payload.get("web", {}).get("results", [])


FITNESS_TERM_MAP = {
    "空腹有氧": "fasted aerobic exercise",
    "有氧": "aerobic exercise",
    "减脂": "fat loss",
    "燃脂": "fat oxidation",
    "力量训练": "resistance training",
    "增肌": "muscle hypertrophy",
    "蛋白质": "dietary protein",
    "碳水": "carbohydrate intake",
    "睡眠": "sleep",
    "恢复": "exercise recovery",
    "拉伸": "stretching",
    "深蹲": "squat",
    "膝盖": "knee",
    "补剂": "dietary supplement",
    "肌酸": "creatine",
    "高强度间歇": "high intensity interval training",
}


def _matched_academic_terms(topic: str) -> list[str]:
    """Expand the most specific non-overlapping Chinese fitness terms."""

    matches: list[tuple[int, int, str]] = []
    occupied: set[int] = set()
    for chinese, english in sorted(
        FITNESS_TERM_MAP.items(), key=lambda item: len(item[0]), reverse=True
    ):
        for found in re.finditer(re.escape(chinese), topic):
            positions = set(range(found.start(), found.end()))
            if positions.intersection(occupied):
                continue
            matches.append((found.start(), found.end(), english))
            occupied.update(positions)
    return [english for _, _, english in sorted(matches)]


def _academic_topic(topic: str) -> str:
    matched = _matched_academic_terms(topic)
    return " ".join(dict.fromkeys(matched)) or topic


def _required_concept_groups(topic: str) -> tuple[tuple[str, ...], ...]:
    """Return strict concept groups only for topics with known ambiguity."""

    if "空腹有氧" in topic:
        return (("fasted", "fasting"), ("exercise", "aerobic", "cardio"))
    return ()


def _source_relevance(source: SearchResult, topic: str) -> int:
    text = f"{source.title} {source.snippet}".casefold()
    title = source.title.casefold()
    academic_topic = _academic_topic(topic).casefold()
    terms = {
        term
        for term in re.findall(r"[a-z0-9]+", academic_topic)
        if len(term) > 2
    }
    score = sum(1 for term in terms if term in text)
    phrases = [value.casefold() for value in _matched_academic_terms(topic)]
    score += 3 * sum(1 for phrase in phrases if phrase in text)
    for group in _required_concept_groups(topic):
        if any(term in text for term in group):
            score += 4
    required_groups = _required_concept_groups(topic)
    if required_groups and all(
        any(term in title for term in group) for group in required_groups
    ):
        score += 12
    return score


def _matches_required_concepts(source: SearchResult, topic: str) -> bool:
    text = f"{source.title} {source.snippet}".casefold()
    groups = _required_concept_groups(topic)
    matches_all = all(
        any(term in text for term in group)
        for group in groups
    )
    if not matches_all:
        return False
    if "空腹有氧" in topic:
        title = source.title.casefold()
        return any(term in title for term in groups[0])
    return True


def default_search_provider() -> SearchProvider:
    """Use free scholarly APIs by default; Brave is an explicit opt-in."""

    mode = os.environ.get("RESEARCH_PROVIDER", "academic").strip().casefold()
    if mode == "brave":
        return BraveSearchProvider()
    return CompositeEvidenceProvider([PubMedSearchProvider(), CrossrefSearchProvider()])


class ResearchService:
    def __init__(self, provider: SearchProvider, max_sources: int = 6):
        self.provider = provider
        self.max_sources = max_sources

    @staticmethod
    def plan_queries(topic: str) -> list[str]:
        normalized = " ".join(topic.split())
        if "空腹有氧" in normalized:
            return [
                "fasted exercise versus fed exercise body composition systematic review meta-analysis",
                "fasted aerobic exercise fat oxidation fat loss randomized trial",
            ]
        academic_topic = _academic_topic(normalized)
        return [
            f"{academic_topic} systematic review meta-analysis",
            f"{academic_topic} guideline consensus randomized trial",
        ]

    def research(self, topic: str) -> ResearchPacket:
        topic = " ".join(topic.split()).strip()
        if len(topic) < 4:
            raise ValueError("Topic must contain at least 4 characters.")
        if len(topic) > 300:
            raise ValueError("Topic must contain at most 300 characters.")

        queries = self.plan_queries(topic)
        seen_urls: set[str] = set()
        sources: list[SearchResult] = []
        for query in queries:
            try:
                raw_results = self.provider.search(query, count=self.max_sources)
            except EvidenceProviderError as exc:
                raise ResearchError(str(exc)) from exc
            for item in raw_results:
                url = str(item.get("url", "")).strip()
                domain = _domain_for(url)
                canonical = url.rstrip("/")
                if not domain or canonical in seen_urls:
                    continue
                title = " ".join(str(item.get("title", "Untitled source")).split())
                snippets = [str(item.get("description", ""))]
                snippets.extend(str(value) for value in item.get("extra_snippets", []))
                snippet = " ".join(" ".join(snippets).split())[:1200]
                if not snippet:
                    continue
                seen_urls.add(canonical)
                sources.append(
                    SearchResult(
                        title=title[:300],
                        url=url,
                        snippet=snippet,
                        domain=domain,
                        source_tier=(
                            item.get("source_tier")
                            if item.get("source_tier")
                            in {"authoritative", "academic", "general"}
                            else _source_tier(domain)
                        ),
                        query=query,
                        published_at=item.get("page_age") or item.get("age"),
                    )
                )

        flags: list[str] = []
        required_groups = _required_concept_groups(topic)
        if required_groups:
            topic_specific = [
                source for source in sources if _matches_required_concepts(source, topic)
            ]
            if len(topic_specific) >= 3:
                sources = topic_specific
            else:
                flags.append(
                    "Fewer than three sources matched every required topic concept."
                )

        tier_rank = {"authoritative": 0, "academic": 1, "general": 2}
        sources.sort(
            key=lambda item: (
                -_source_relevance(item, topic),
                tier_rank[item.source_tier],
                item.domain,
                item.title,
            )
        )
        sources = sources[: self.max_sources]
        trusted_count = sum(
            item.source_tier in {"authoritative", "academic"} for item in sources
        )
        if len(sources) < 3:
            flags.append("Fewer than three usable web sources were found.")
        if trusted_count < 2:
            flags.append("Fewer than two authoritative or academic sources were found.")
        status = "ready_for_drafting" if not flags else "needs_review"
        return ResearchPacket(
            topic=topic,
            queries=queries,
            sources=sources,
            generated_at=datetime.now(timezone.utc).isoformat(),
            evidence_status=status,
            review_flags=flags,
        )
