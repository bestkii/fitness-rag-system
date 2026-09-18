from __future__ import annotations

import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PUBMED_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
USER_AGENT = "fitness-evidence-studio/0.2 (portfolio research prototype)"


class EvidenceProviderError(RuntimeError):
    """Raised when a free evidence provider cannot be reached or parsed."""


class EvidenceProvider(Protocol):
    def search(self, query: str, count: int) -> list[dict]: ...


def _request_text(url: str, timeout_seconds: float) -> str:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        raise EvidenceProviderError(f"Evidence provider returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise EvidenceProviderError("Evidence provider could not be reached.") from exc


def _request_json(url: str, timeout_seconds: float) -> dict:
    try:
        return json.loads(_request_text(url, timeout_seconds))
    except json.JSONDecodeError as exc:
        raise EvidenceProviderError("Evidence provider returned invalid JSON.") from exc


def _strip_markup(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return " ".join(text.split())


def _first_text(node: ET.Element | None, path: str) -> str:
    if node is None:
        return ""
    found = node.find(path)
    if found is None:
        return ""
    return " ".join("".join(found.itertext()).split())


class PubMedSearchProvider:
    """Free PubMed E-utilities adapter using only public article metadata/abstracts."""

    name = "pubmed"
    available = True

    def __init__(self, timeout_seconds: float = 20.0, min_interval_seconds: float = 0.36):
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at = 0.0

    def _throttled_text(self, url: str) -> str:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)
        result = _request_text(url, self.timeout_seconds)
        self._last_request_at = time.monotonic()
        return result

    @staticmethod
    def _common_params() -> dict[str, str]:
        params = {"tool": "fitness_evidence_studio"}
        contact = os.environ.get("NCBI_CONTACT_EMAIL", "").strip()
        if contact:
            params["email"] = contact
        return params

    def search(self, query: str, count: int) -> list[dict]:
        search_params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": str(max(1, min(count, 20))),
            "sort": "relevance",
            **self._common_params(),
        }
        search_url = f"{PUBMED_BASE_URL}/esearch.fcgi?{urlencode(search_params)}"
        try:
            search_payload = json.loads(self._throttled_text(search_url))
        except json.JSONDecodeError as exc:
            raise EvidenceProviderError("PubMed returned invalid JSON.") from exc
        identifiers = search_payload.get("esearchresult", {}).get("idlist", [])
        if not identifiers:
            return []

        fetch_params = {
            "db": "pubmed",
            "id": ",".join(identifiers),
            "retmode": "xml",
            **self._common_params(),
        }
        fetch_url = f"{PUBMED_BASE_URL}/efetch.fcgi?{urlencode(fetch_params)}"
        try:
            root = ET.fromstring(self._throttled_text(fetch_url))
        except ET.ParseError as exc:
            raise EvidenceProviderError("PubMed returned invalid XML.") from exc

        results: list[dict] = []
        for article in root.findall(".//PubmedArticle"):
            citation = article.find("MedlineCitation")
            pmid = _first_text(citation, "PMID")
            article_node = citation.find("Article") if citation is not None else None
            title = _first_text(article_node, "ArticleTitle")
            abstract_parts = [
                " ".join("".join(part.itertext()).split())
                for part in article.findall(".//Abstract/AbstractText")
            ]
            journal = _first_text(article_node, "Journal/Title")
            year = _first_text(article_node, "Journal/JournalIssue/PubDate/Year")
            description = " ".join(part for part in abstract_parts if part)
            if not description:
                description = " · ".join(part for part in (journal, year) if part)
            if not pmid or not title or not description:
                continue
            results.append(
                {
                    "title": title,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "description": description,
                    "page_age": year or None,
                    "source_tier": "authoritative",
                    "provider": self.name,
                }
            )
        return results


class CrossrefSearchProvider:
    """Free Crossref REST API adapter for scholarly metadata discovery."""

    name = "crossref"
    available = True

    def __init__(self, timeout_seconds: float = 20.0):
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, count: int) -> list[dict]:
        params = {
            "query.bibliographic": query,
            "rows": str(max(1, min(count, 20))),
            "select": "DOI,title,URL,author,published,abstract,publisher,type",
        }
        contact = os.environ.get("CROSSREF_CONTACT_EMAIL", "").strip()
        if contact:
            params["mailto"] = contact
        payload = _request_json(
            f"{CROSSREF_WORKS_URL}?{urlencode(params)}", self.timeout_seconds
        )
        results: list[dict] = []
        for item in payload.get("message", {}).get("items", []):
            titles = item.get("title") or []
            title = _strip_markup(str(titles[0])) if titles else ""
            doi = str(item.get("DOI", "")).strip()
            url = str(item.get("URL", "")).strip() or (
                f"https://doi.org/{doi}" if doi else ""
            )
            abstract = _strip_markup(str(item.get("abstract", "")))
            publisher = _strip_markup(str(item.get("publisher", "")))
            authors = item.get("author") or []
            author_names = ", ".join(
                " ".join(
                    part
                    for part in (
                        str(author.get("given", "")).strip(),
                        str(author.get("family", "")).strip(),
                    )
                    if part
                )
                for author in authors[:3]
            )
            description = abstract or " · ".join(
                part for part in (author_names, publisher, str(item.get("type", ""))) if part
            )
            date_parts = item.get("published", {}).get("date-parts", [])
            published = "-".join(str(value) for value in date_parts[0]) if date_parts else None
            if not title or not url or not description:
                continue
            results.append(
                {
                    "title": title,
                    "url": url,
                    "description": description,
                    "page_age": published,
                    "source_tier": "academic",
                    "provider": self.name,
                }
            )
        return results


class CompositeEvidenceProvider:
    """Combines providers while allowing one public service to be temporarily unavailable."""

    name = "pubmed+crossref"
    available = True

    def __init__(self, providers: list[EvidenceProvider]):
        if not providers:
            raise ValueError("At least one evidence provider is required.")
        self.providers = providers

    def search(self, query: str, count: int) -> list[dict]:
        results: list[dict] = []
        failures: list[str] = []
        successful_calls = 0
        for provider in self.providers:
            try:
                results.extend(provider.search(query, count))
                successful_calls += 1
            except EvidenceProviderError as exc:
                failures.append(str(exc))
        if not successful_calls:
            detail = "; ".join(dict.fromkeys(failures)) or "No provider completed."
            raise EvidenceProviderError(detail)
        return results
