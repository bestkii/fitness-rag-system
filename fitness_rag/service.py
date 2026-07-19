from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import chromadb
from openai import OpenAI
from sentence_transformers import SentenceTransformer

from .config import (
    COLLECTION_NAME,
    DB_PATH,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    EXPERT_LABELS,
    INDEXED_RECORDS,
    METRICS_PATH,
    TOP_K,
)


@dataclass
class RetrievedEvidence:
    rank: int
    score: float
    expert: str
    topics: list[str]
    rumor: str
    truth: str
    source_id: str


class RagService:
    def __init__(self) -> None:
        if not DB_PATH.exists():
            raise RuntimeError("Final knowledge base is missing. Run scripts/build_knowledge_base.py.")
        self.model = SentenceTransformer(EMBEDDING_MODEL)
        self.client = chromadb.PersistentClient(path=str(DB_PATH))
        self.collection = self.client.get_collection(COLLECTION_NAME)

    @property
    def generation_mode(self) -> str:
        return "deepseek" if os.environ.get("DEEPSEEK_API_KEY") else "extractive"

    def retrieve(self, claim: str, top_k: int = TOP_K) -> list[RetrievedEvidence]:
        vector = self.model.encode(
            [claim],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0].tolist()
        result = self.collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        evidence: list[RetrievedEvidence] = []
        for index, (metadata, distance, source_id) in enumerate(
            zip(result["metadatas"][0], result["distances"][0], result["ids"][0]),
            1,
        ):
            evidence.append(
                RetrievedEvidence(
                    rank=index,
                    score=max(0.0, min(1.0, 1.0 - float(distance))),
                    expert=metadata["expert"],
                    topics=json.loads(metadata["topics"]),
                    rumor=metadata["rumor"],
                    truth=metadata["truth"],
                    source_id=source_id,
                )
            )
        return evidence

    def analyze(self, claim: str) -> dict[str, Any]:
        claim = re.sub(r"\s+", " ", claim).strip()
        if len(claim) < 8:
            raise ValueError("Please enter a claim of at least 8 characters.")
        if len(claim) > 1000:
            raise ValueError("Claim must be 1,000 characters or fewer.")

        evidence = self.retrieve(claim)
        expert = Counter(item.expert for item in evidence).most_common(1)[0][0]
        risk = self._risk_level(claim)
        if self.generation_mode == "deepseek":
            synthesis = self._deepseek_synthesis(claim, evidence, expert, risk)
        else:
            synthesis = {
                "verdict": "Related synthetic rebuttal retrieved",
                "summary": evidence[0].truth,
                "reasoning": (
                    "Offline extractive mode returns the highest-similarity synthetic "
                    "rebuttal. It does not independently establish whether the claim is true."
                ),
            }

        return {
            "claim": claim,
            "verdict": synthesis["verdict"],
            "risk": risk,
            "expert": expert,
            "expert_label": EXPERT_LABELS.get(expert, expert.replace("_", " ").title()),
            "summary": synthesis["summary"],
            "reasoning": synthesis["reasoning"],
            "generation_mode": self.generation_mode,
            "evidence": [
                {
                    "rank": item.rank,
                    "similarity": round(item.score, 4),
                    "expert": item.expert,
                    "expert_label": EXPERT_LABELS.get(
                        item.expert, item.expert.replace("_", " ").title()
                    ),
                    "topics": item.topics,
                    "matched_claim": item.rumor,
                    "truth": item.truth,
                    "source_id": item.source_id,
                    "provenance": "DeepSeek-generated synthetic evidence record",
                }
                for item in evidence
            ],
        }

    @staticmethod
    def _risk_level(claim: str) -> str:
        lowered = claim.lower()
        critical = ("pregnan", "insulin", "steroid", "dehydrat", "injury", "pain")
        high = ("never", "always", "zero carb", "detox", "7 day", "extreme", "cure")
        if any(token in lowered for token in critical):
            return "Critical"
        if any(token in lowered for token in high):
            return "High"
        return "Moderate"

    @staticmethod
    def _deepseek_synthesis(
        claim: str,
        evidence: list[RetrievedEvidence],
        expert: str,
        risk: str,
    ) -> dict[str, str]:
        context = "\n\n".join(
            f"[Evidence {item.rank}] {item.truth}" for item in evidence
        )
        prompt = f"""
Analyze the fitness claim using only the supplied evidence.
Claim: {claim}
Routed expert: {expert}
Risk level: {risk}
Evidence:
{context}

Return JSON with exactly these string fields:
verdict, summary, reasoning.
Do not cite knowledge outside the evidence. State uncertainty when evidence is insufficient.
"""
        client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com",
            timeout=30.0,
        )
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "You are an evidence-grounded fitness fact-checker.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return json.loads(response.choices[0].message.content)


def load_metrics() -> dict[str, Any]:
    if not METRICS_PATH.exists():
        return {}
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


def system_facts() -> dict[str, Any]:
    return {
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimension": EMBEDDING_DIMENSION,
        "indexed_records": INDEXED_RECORDS,
        "held_out_records": 300,
        "top_k": TOP_K,
        "distance": "cosine",
    }
