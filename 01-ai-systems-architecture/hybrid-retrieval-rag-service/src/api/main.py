"""
FastAPI application — HTTP surface for the retrieval pipeline.

- Async lifespan context builds the pipeline once at startup
- Request-timing middleware records latency for every route
- Pydantic v2 request/response models with field-level validation
- /metrics exposes request counts, latency and token usage
- /ingest accepts both PDF and plain-text uploads
- 503 while the pipeline is not ready, 400 for malformed input
- data/raw/ is auto-ingested on startup
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field

from config.settings import settings
from src.ingestion.ingest import DocumentIngestor
from src.monitoring.metrics import configure_logging, get_metrics
from src.rag.pipeline import RAGPipeline

logger = logging.getLogger(__name__)

pipeline: RAGPipeline | None = None
ingestor: DocumentIngestor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, ingestor
    configure_logging(settings.log_level)
    logger.info("Starting retrieval service v%s", settings.app_version)

    pipeline = RAGPipeline()
    ingestor = DocumentIngestor(pipeline)

    raw_dir = Path("data/raw")
    if raw_dir.exists():
        try:
            results = await ingestor.ingest_directory(raw_dir)
            if results:
                total = sum(r.chunks_created for r in results)
                logger.info("Auto-ingested %d file(s) → %d chunks", len(results), total)
        except Exception as exc:
            logger.warning("Auto-ingestion failed: %s", exc)

    logger.info("Pipeline ready. Documents indexed: %d", pipeline.document_count)
    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Hybrid retrieval + cross-encoder reranking RAG system",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _patched_openapi() -> dict:
    """Return the OpenAPI schema with format:binary on UploadFile items.

    FastAPI 0.115+ emits contentMediaType (OAS 3.1) for UploadFile, but
    Swagger UI needs format:binary (OAS 3.0) to render file-picker buttons.
    Without this patch the files field renders as a plain text-array input
    and any content typed into it arrives on the server as garbled bytes.
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    body = (
        schema.get("components", {}).get("schemas", {}).get("Body_ingest_documents_ingest_post", {})
    )
    items = body.get("properties", {}).get("files", {}).get("items", {})
    if items:
        items.pop("contentMediaType", None)
        items["format"] = "binary"
    app.openapi_schema = schema
    return schema


app.openapi = _patched_openapi  # type: ignore[method-assign]


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    logger.debug(
        "%s %s → %s (%.0f ms)",
        request.method,
        request.url.path,
        response.status_code,
        ms,
    )
    return response


# ── Schemas ───────────────────────────────────────────────────────────────────


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str = Field(default="default", max_length=64)
    retrieval_k: int | None = Field(default=None, ge=1, le=50)
    rerank_k: int | None = Field(default=None, ge=1, le=20)


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    tokens_used: int
    latency_ms: float
    retrieval_latency_ms: float
    rerank_latency_ms: float
    chunks_retrieved: int
    chunks_after_rerank: int


class UploadResponse(BaseModel):
    filename: str
    chunks_created: int
    characters_processed: int


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    try:
        doc_count = pipeline.document_count if pipeline else 0
    except Exception:
        doc_count = -1
    return {
        "status": "ok",
        "version": settings.app_version,
        "embedding_model": settings.embedding_model,
        "llm_model": settings.llm_model,
        "documents_indexed": doc_count,
    }


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    if pipeline is None:
        raise HTTPException(503, "Pipeline not initialised")
    try:
        result = await pipeline.query(
            req.question,
            conversation_id=req.conversation_id,
            retrieval_k=req.retrieval_k,
            rerank_k=req.rerank_k,
        )
        get_metrics().record(result.tokens_used, result.latency_ms)
        return QueryResponse(**dict(result))
    except Exception as exc:
        get_metrics().errors += 1
        logger.exception("Query failed")
        raise HTTPException(500, str(exc)) from exc


@app.post("/ingest", response_model=list[UploadResponse])
async def ingest_documents(
    files: Annotated[
        list[UploadFile],
        File(description="One or more .pdf, .txt, or .md files to ingest"),
    ],
):
    if ingestor is None:
        raise HTTPException(503, "Pipeline not initialised")

    supported = {".pdf", ".txt", ".md"}
    results = []
    for file in files:
        data = await file.read()
        filename = file.filename or "upload"
        suffix = Path(filename).suffix.lower()

        if suffix not in supported:
            raise HTTPException(
                400,
                f"Unsupported file type '{suffix}'. Supported: {', '.join(sorted(supported))}",
            )

        try:
            if suffix == ".pdf":
                result = await ingestor.ingest_pdf_bytes(data, filename)
            else:
                text = data.decode("utf-8", errors="ignore")
                result = await ingestor._ingest(text, source=filename, file_type=suffix.lstrip("."))

            results.append(
                UploadResponse(
                    filename=result.source,
                    chunks_created=result.chunks_created,
                    characters_processed=result.characters_processed,
                )
            )
        except Exception as exc:
            logger.exception("Ingestion failed for %s", filename)
            raise HTTPException(500, f"Ingestion failed for {filename}: {exc}") from exc

    return results


@app.get("/documents")
async def list_documents():
    if pipeline is None:
        raise HTTPException(503, "Pipeline not initialised")
    try:
        docs = pipeline.store.get_all_documents()
    except Exception as exc:
        logger.exception("Failed to fetch documents from store")
        raise HTTPException(503, f"Store unavailable: {exc}") from exc
    counts: dict[str, int] = {}
    for doc in docs:
        source = doc["metadata"].get("source", "unknown")
        counts[source] = counts.get(source, 0) + 1
    return [{"name": name, "chunks": count} for name, count in sorted(counts.items())]


@app.get("/metrics")
async def metrics():
    return get_metrics().to_dict()


@app.delete("/conversation/{conversation_id}", status_code=204)
async def clear_conversation(conversation_id: str):
    if pipeline:
        pipeline.clear_conversation(conversation_id)


@app.get("/")
async def root():
    return {"message": f"{settings.app_name} v{settings.app_version}", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
