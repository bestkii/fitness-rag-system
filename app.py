from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fitness_rag.config import APP_NAME, ROOT
from fitness_rag.service import RagService, load_metrics, system_facts

STATIC_DIR = ROOT / "web"
service: RagService | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global service
    service = RagService()
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ClaimRequest(BaseModel):
    claim: str = Field(min_length=8, max_length=1000)


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ready", **system_facts()}


@app.get("/api/metrics")
def metrics() -> dict:
    return load_metrics()


@app.post("/api/analyze")
def analyze(request: ClaimRequest) -> dict:
    if service is None:
        raise HTTPException(status_code=503, detail="Knowledge base is still loading.")
    try:
        return service.analyze(request.claim)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
