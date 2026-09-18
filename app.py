from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fitness_rag.config import APP_NAME, DRAFTS_DIR, ROOT
from fitness_rag.content import ContentAgent
from fitness_rag.drafts import DraftNotApprovedError, DraftNotFoundError, DraftStore
from fitness_rag.private_retrieval import PrivateTextbookRetriever
from fitness_rag.private_reviews import PrivateReviewStore
from fitness_rag.private_sources import PrivateSourceRegistry
from fitness_rag.research import ResearchError, ResearchService, default_search_provider
from fitness_rag.service import RagService, load_metrics, system_facts
from fitness_rag.xiaohongshu import XiaohongshuTopicStore

STATIC_DIR = ROOT / "web"
service: RagService | None = None
content_agent: ContentAgent | None = None
private_retriever: PrivateTextbookRetriever | None = None
private_review_store = PrivateReviewStore()
private_source_registry = PrivateSourceRegistry()
draft_store = DraftStore(DRAFTS_DIR)
topic_store = XiaohongshuTopicStore()
search_provider = default_search_provider()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global content_agent, private_retriever, service
    try:
        service = RagService()
    except RuntimeError:
        service = None
    try:
        private_retriever = PrivateTextbookRetriever()
    except RuntimeError:
        private_retriever = None
    research_service = ResearchService(search_provider)
    content_agent = ContentAgent(
        research_service,
        rag_analyzer=service.analyze if service is not None else None,
    )
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ClaimRequest(BaseModel):
    claim: str = Field(min_length=8, max_length=1000)


class DraftRequest(BaseModel):
    topic: str = Field(min_length=4, max_length=300)
    audience: str = Field(default="健身初学者", min_length=2, max_length=120)
    tone: str = Field(default="清晰、克制、友好", min_length=2, max_length=120)


class ApprovalRequest(BaseModel):
    acknowledged_sources: bool


class PrivateReviewRequest(BaseModel):
    chunk_id: str = Field(min_length=2, max_length=180)
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=500)


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ready" if service is not None else "partial",
        "rag_available": service is not None,
        "web_research_available": getattr(search_provider, "available", True),
        "research_provider": getattr(search_provider, "name", "configured"),
        "private_textbook_available": private_retriever is not None,
        "private_textbook_mode": "local_lexical_staging" if private_retriever else "unavailable",
        **system_facts(),
    }


@app.get("/api/metrics")
def metrics() -> dict:
    return load_metrics()


@app.get("/api/trends")
def trends(keyword: str | None = None, limit: int = 20) -> dict:
    notes = topic_store.list(keyword=keyword, limit=limit)
    return {
        "mode": "local_read_only",
        "keyword": keyword,
        "count": len(notes),
        "notes": notes,
    }


@app.get("/api/private-library/search")
def private_library_search(q: str, limit: int = 3) -> dict:
    if private_retriever is None:
        raise HTTPException(status_code=503, detail="Private textbook corpus is not built")
    try:
        results = private_retriever.search(q, top_k=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    reviews = private_review_store.get_many(item["chunk_id"] for item in results)
    for item in results:
        item["review"] = reviews.get(item["chunk_id"])
        item["source_page_url"] = (
            f"/api/private-library/source-page/{item['source_id']}/{item['pdf_page']}"
        )
    return {
        "query": q,
        "mode": "local_only_lexical_staging",
        "generation_approved": False,
        "count": len(results),
        "results": results,
    }


@app.get("/api/private-library/review-queue")
def private_library_review_queue(limit: int = 12) -> dict:
    if private_retriever is None:
        raise HTTPException(status_code=503, detail="Private textbook corpus is not built")
    reviewed = private_review_store.get_many(
        chunk["chunk_id"] for chunk in private_retriever.chunks
    )
    try:
        results = private_retriever.review_queue(
            reviewed_ids=set(reviewed), limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for item in results:
        item["review"] = None
        item["source_page_url"] = (
            f"/api/private-library/source-page/{item['source_id']}/{item['pdf_page']}"
        )
    return {
        "mode": "local_human_review",
        "count": len(results),
        "summary": private_review_store.summary(),
        "results": results,
    }


@app.get("/api/private-library/review-summary")
def private_library_review_summary() -> dict:
    summary = private_review_store.summary()
    total = len(private_retriever.chunks) if private_retriever else 0
    return {**summary, "total_chunks": total, "pending": max(0, total - summary["reviewed"])}


@app.post("/api/private-library/reviews")
def save_private_library_review(request: PrivateReviewRequest) -> dict:
    if private_retriever is None:
        raise HTTPException(status_code=503, detail="Private textbook corpus is not built")
    if not private_retriever.has_chunk(request.chunk_id):
        raise HTTPException(status_code=404, detail="Private textbook chunk not found")
    try:
        review = private_review_store.save(
            request.chunk_id, request.decision, request.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"review": review, "summary": private_review_store.summary()}


@app.get("/api/private-library/source-page/{source_id}/{pdf_page}")
def private_library_source_page(source_id: str, pdf_page: int) -> FileResponse:
    try:
        preview = private_source_registry.render_page(source_id, pdf_page)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Private source is not registered") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(
        preview,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.post("/api/analyze")
def analyze(request: ClaimRequest) -> dict:
    if service is None:
        raise HTTPException(status_code=503, detail="Knowledge base is still loading.")
    try:
        return service.analyze(request.claim)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/content/drafts")
def create_content_draft(request: DraftRequest) -> dict:
    if content_agent is None:
        raise HTTPException(status_code=503, detail="Content workflow is still loading.")
    try:
        draft = content_agent.create_draft(
            request.topic,
            audience=request.audience,
            tone=request.tone,
        )
    except (ResearchError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return draft_store.save(draft)


@app.get("/api/content/drafts/{draft_id}")
def get_content_draft(draft_id: str) -> dict:
    try:
        return draft_store.get(draft_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Draft not found.") from exc


@app.post("/api/content/drafts/{draft_id}/approve")
def approve_content_draft(draft_id: str, request: ApprovalRequest) -> dict:
    if not request.acknowledged_sources:
        raise HTTPException(
            status_code=422,
            detail="Source review must be acknowledged before approval.",
        )
    try:
        return draft_store.approve(draft_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Draft not found.") from exc


@app.get("/api/content/drafts/{draft_id}/export", response_class=PlainTextResponse)
def export_content_draft(draft_id: str) -> str:
    try:
        return draft_store.export_text(draft_id)
    except DraftNotApprovedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Draft not found.") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
