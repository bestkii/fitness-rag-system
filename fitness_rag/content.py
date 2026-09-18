from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from .research import ResearchPacket, ResearchService


HIGH_RISK_TERMS = (
    "pregnan",
    "怀孕",
    "insulin",
    "胰岛素",
    "steroid",
    "类固醇",
    "injury",
    "受伤",
    "pain",
    "疼痛",
    "cure",
    "治愈",
)


def _compact(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


def _source_context(packet: ResearchPacket) -> str:
    return "\n\n".join(
        f"[S{index}] {source.title}\nURL: {source.url}\nExcerpt: {source.snippet}"
        for index, source in enumerate(packet.sources, 1)
    )


class ContentAgent:
    """Research-to-draft workflow with an explicit human approval boundary."""

    def __init__(
        self,
        research_service: ResearchService,
        rag_analyzer: Callable[[str], dict[str, Any]] | None = None,
    ):
        self.research_service = research_service
        self.rag_analyzer = rag_analyzer

    @property
    def generation_mode(self) -> str:
        return "llm" if os.environ.get("CONTENT_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") else "template"

    def create_draft(
        self,
        topic: str,
        audience: str = "健身初学者",
        tone: str = "清晰、克制、友好",
    ) -> dict[str, Any]:
        packet = self.research_service.research(topic)
        legacy_context = self._legacy_rag_context(topic)
        if self.generation_mode == "llm":
            content = self._llm_draft(packet, audience, tone, legacy_context)
        else:
            content = self._template_draft(packet, audience, tone)

        review_flags = list(packet.review_flags)
        if any(term in topic.casefold() for term in HIGH_RISK_TERMS):
            review_flags.append("High-risk health topic requires qualified human review.")
        cited_markers = set(re.findall(r"\[S(\d+)\]", content["body"]))
        valid_markers = {str(index) for index in range(1, len(packet.sources) + 1)}
        if not cited_markers:
            review_flags.append("Draft body contains no source markers.")
        if not cited_markers.issubset(valid_markers):
            review_flags.append("Draft contains a citation marker without a matching source.")

        return {
            "id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "draft",
            "topic": packet.topic,
            "audience": _compact(audience, 120),
            "tone": _compact(tone, 120),
            "generation_mode": self.generation_mode,
            "research": packet.to_dict(),
            "legacy_rag_context": legacy_context,
            "content": content,
            "review": {
                "required": True,
                "flags": list(dict.fromkeys(review_flags)),
                "approved_at": None,
            },
            "publishing": {
                "mode": "export_only",
                "platform": "xiaohongshu",
                "note": "No content is posted automatically. Approval and export are separate actions.",
            },
        }

    def _legacy_rag_context(self, topic: str) -> dict[str, Any] | None:
        if self.rag_analyzer is None:
            return None
        try:
            result = self.rag_analyzer(topic)
        except (RuntimeError, ValueError):
            return None
        return {
            "verdict": result.get("verdict"),
            "summary": result.get("summary"),
            "risk": result.get("risk"),
            "provenance": "synthetic_corpus_context_not_a_publication_source",
        }

    @staticmethod
    def _template_draft(
        packet: ResearchPacket, audience: str, tone: str
    ) -> dict[str, Any]:
        source_lines = []
        for index, source in enumerate(packet.sources[:4], 1):
            source_lines.append(
                f"[S{index}] {_compact(source.snippet, 180)}"
            )
        evidence_section = "\n\n".join(source_lines) or "尚未获得可用的联网来源。"
        body = (
            f"这次我们不凭感觉讨论“{packet.topic}”，先看公开证据。\n\n"
            f"{evidence_section}\n\n"
            "目前这是一份待审核草稿：搜索摘要可能缺少原文上下文，发布前需要打开来源核对。"
            "如果问题涉及疼痛、疾病、药物或特殊人群，请咨询合格专业人士。"
        )
        slides = [
            {"heading": "问题是什么？", "copy": _compact(packet.topic, 90)},
            {"heading": "证据怎么说？", "copy": _compact(packet.sources[0].snippet, 120) if packet.sources else "等待补充来源"},
            {"heading": "别急着下结论", "copy": "相关性、适用人群和证据等级都需要核对。"},
            {"heading": "怎么行动？", "copy": "先采用风险较低、可持续、可观察反馈的做法。"},
            {"heading": "来源与边界", "copy": "打开原始链接复核；本内容不替代医疗建议。"},
        ]
        return {
            "title": _compact(f"{packet.topic}：先看证据，再做决定", 40),
            "body": body,
            "hashtags": ["健身科普", "循证健身", "拒绝健身谣言"],
            "carousel": slides,
            "audience_note": _compact(audience, 120),
            "tone_note": _compact(tone, 120),
        }

    @staticmethod
    def _llm_draft(
        packet: ResearchPacket,
        audience: str,
        tone: str,
        legacy_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        from openai import OpenAI

        api_key = os.environ.get("CONTENT_API_KEY") or os.environ["DEEPSEEK_API_KEY"]
        base_url = os.environ.get("CONTENT_API_BASE", "https://api.deepseek.com")
        model = os.environ.get("CONTENT_MODEL", "deepseek-chat")
        prompt = f"""
Create a Chinese Xiaohongshu draft about: {packet.topic}
Audience: {audience}
Tone: {tone}

Use only the web excerpts below for factual claims. Every factual paragraph must include
one or more source markers such as [S1]. Do not treat search snippets as complete papers;
state uncertainty and ask the reviewer to open the original URLs. Never turn the synthetic
legacy RAG context into a citation or authoritative claim.

Web evidence:
{_source_context(packet)}

Synthetic legacy RAG context (orientation only):
{json.dumps(legacy_context, ensure_ascii=False)}

Return JSON with exactly these fields:
title (string, <= 40 Chinese characters), body (string), hashtags (array of 3-6 strings),
carousel (array of exactly 5 objects with string fields heading and copy).
Avoid medical diagnosis, guaranteed outcomes, fear-based language, and invented statistics.
"""
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=45.0)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a cautious evidence-grounded Chinese fitness content editor.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        payload = json.loads(response.choices[0].message.content)
        required = {"title", "body", "hashtags", "carousel"}
        if required.difference(payload):
            raise ValueError("Content model returned an incomplete draft.")
        if not isinstance(payload["carousel"], list) or len(payload["carousel"]) != 5:
            raise ValueError("Content model must return exactly five carousel cards.")
        return {
            "title": _compact(str(payload["title"]), 40),
            "body": str(payload["body"]).strip(),
            "hashtags": [
                _compact(str(value).lstrip("#"), 30)
                for value in payload["hashtags"][:6]
            ],
            "carousel": [
                {
                    "heading": _compact(str(item.get("heading", "")), 50),
                    "copy": _compact(str(item.get("copy", "")), 220),
                }
                for item in payload["carousel"]
            ],
            "audience_note": _compact(audience, 120),
            "tone_note": _compact(tone, 120),
        }
