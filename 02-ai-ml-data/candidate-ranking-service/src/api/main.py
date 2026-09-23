"""HTTP interface for the candidate ranking service.

The service ranks; it does not decide. Responses carry a score, a band and the
component breakdown behind them, and never a hire/reject recommendation — that
judgement belongs to a person who can see the things a model cannot.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.api.schemas import (
    CandidateListResponse,
    FairnessRequest,
    FairnessResponse,
    HealthResponse,
    InlineRankRequest,
    RankRequest,
    RankResponse,
    UploadResponse,
)
from src.models.domain import Candidate
from src.monitoring.fairness import fairness_report
from src.processing.document_parser import DocumentParseError, extract_text
from src.ranking import Ranker, build_ranker
from src.ranking.features import parse_skills
from src.storage.memory import CandidateStoreFull, InMemoryCandidateStore
from src.utils.config import Settings, get_settings

logger = logging.getLogger(__name__)

API_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build settings, store and ranker once, at startup.

    The embedding backend loads a model here rather than on first request, so
    the cost is paid before the service reports itself ready instead of
    landing on one unlucky caller.
    """
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    app.state.settings = settings
    app.state.store = InMemoryCandidateStore(max_size=settings.max_candidates)
    app.state.ranker = build_ranker(settings)
    logger.info("Ranking backend ready: %s", app.state.ranker.describe())
    yield
    app.state.store.clear()


app = FastAPI(
    title="Candidate Ranking Service",
    version=API_VERSION,
    description=(
        "Ranks candidates against a job description on skill coverage, "
        "experience fit and resume-text similarity."
    ),
    lifespan=lifespan,
)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _store(request: Request) -> InMemoryCandidateStore:
    return request.app.state.store


def _ranker(request: Request) -> Ranker:
    return request.app.state.ranker


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Guard write endpoints when an API key is configured.

    When ``API_KEY`` is unset the service is open — the documented default for
    local use. When it is set, a missing or wrong key is rejected with 401.

    Raises:
        HTTPException: 401 if a key is configured and the header does not match.
    """
    expected = request.app.state.settings.api_key
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health(
    request: Request,
    store: InMemoryCandidateStore = Depends(_store),
    ranker: Ranker = Depends(_ranker),
) -> HealthResponse:
    """Report liveness, the active ranking backend and store occupancy."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC),
        ranking=ranker.describe(),
        candidates_stored=len(store),
        capacity=request.app.state.settings.max_candidates,
    )


@app.post(
    "/candidates",
    response_model=UploadResponse,
    status_code=201,
    tags=["candidates"],
    dependencies=[Depends(require_api_key)],
)
def add_candidate(
    candidate: Candidate,
    store: InMemoryCandidateStore = Depends(_store),
    settings: Settings = Depends(_settings),
) -> UploadResponse:
    """Store a candidate for later ranking.

    Raises:
        HTTPException: 413 if the resume exceeds the configured length cap,
            507 if the store is at capacity.
    """
    if len(candidate.resume_text) > settings.max_resume_chars:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Resume text exceeds the {settings.max_resume_chars} character limit "
                f"({len(candidate.resume_text)} supplied)"
            ),
        )
    try:
        created = store.add(candidate)
    except CandidateStoreFull as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc

    return UploadResponse(
        candidate_id=candidate.candidate_id,
        created=created,
        candidates_stored=len(store),
    )


@app.post(
    "/candidates/upload",
    response_model=UploadResponse,
    status_code=201,
    tags=["candidates"],
    dependencies=[Depends(require_api_key)],
)
async def upload_candidate_document(
    candidate_id: str = Form(...),
    file: UploadFile = File(...),
    skills: str = Form(default=""),
    years_experience: int | None = Form(default=None),
    store: InMemoryCandidateStore = Depends(_store),
    settings: Settings = Depends(_settings),
) -> UploadResponse:
    """Store a candidate from an uploaded PDF or text document.

    Args:
        candidate_id: Identifier for the candidate.
        file: A PDF or UTF-8 text file. The type is detected from content, not
            from the filename.
        skills: Comma-separated skills, or a list literal.
        years_experience: Years of experience, if known.

    Raises:
        HTTPException: 400 if the document cannot be parsed, 413 if it is too
            long, 507 if the store is full.
    """
    content = await file.read()
    try:
        text = extract_text(content)
    except DocumentParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if len(text) > settings.max_resume_chars:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Extracted text exceeds the {settings.max_resume_chars} character "
                f"limit ({len(text)} extracted)"
            ),
        )

    try:
        parsed_skills = parse_skills(skills)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse skills: {exc}") from exc

    candidate = Candidate(
        candidate_id=candidate_id,
        resume_text=text,
        skills=parsed_skills,
        years_experience=years_experience,
    )
    try:
        created = store.add(candidate)
    except CandidateStoreFull as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc

    return UploadResponse(candidate_id=candidate_id, created=created, candidates_stored=len(store))


@app.get("/candidates", response_model=CandidateListResponse, tags=["candidates"])
def list_candidates(
    store: InMemoryCandidateStore = Depends(_store),
) -> CandidateListResponse:
    """List the ids currently held. Resume text is never returned in bulk."""
    ids = store.list_ids()
    return CandidateListResponse(count=len(ids), candidate_ids=ids)


@app.delete(
    "/candidates/{candidate_id}",
    status_code=204,
    tags=["candidates"],
    dependencies=[Depends(require_api_key)],
)
def delete_candidate(candidate_id: str, store: InMemoryCandidateStore = Depends(_store)) -> None:
    """Remove a candidate.

    Raises:
        HTTPException: 404 if no such candidate is stored.
    """
    if not store.delete(candidate_id):
        raise HTTPException(status_code=404, detail=f"No candidate with id {candidate_id!r}")


@app.post("/rank", response_model=RankResponse, tags=["ranking"])
def rank_stored_candidates(
    payload: RankRequest,
    store: InMemoryCandidateStore = Depends(_store),
    ranker: Ranker = Depends(_ranker),
) -> RankResponse:
    """Rank every stored candidate against a job.

    Raises:
        HTTPException: 404 if no candidates have been stored.
    """
    candidates = store.all()
    if not candidates:
        raise HTTPException(
            status_code=404, detail="No candidates stored. Add candidates before ranking."
        )

    results = ranker.rank(payload.job, candidates)
    if payload.top_k is not None:
        results = results[: payload.top_k]

    description = ranker.describe()
    return RankResponse(
        scoring_method=description["method"],
        model=description.get("model"),
        candidates_considered=len(candidates),
        results=results,
    )


@app.post("/rank/inline", response_model=RankResponse, tags=["ranking"])
def rank_inline(payload: InlineRankRequest, ranker: Ranker = Depends(_ranker)) -> RankResponse:
    """Rank candidates supplied in the request, storing nothing."""
    results = ranker.rank(payload.job, payload.candidates)
    if payload.top_k is not None:
        results = results[: payload.top_k]

    description = ranker.describe()
    return RankResponse(
        scoring_method=description["method"],
        model=description.get("model"),
        candidates_considered=len(payload.candidates),
        results=results,
    )


@app.post("/fairness", response_model=FairnessResponse, tags=["monitoring"])
def measure_fairness(payload: FairnessRequest) -> FairnessResponse:
    """Measure selection-rate fairness across caller-supplied groups.

    Raises:
        HTTPException: 422 if the outcome sequences do not line up.
    """
    try:
        report = fairness_report(payload.groups, payload.selected, payload.qualified)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FairnessResponse(report=report)
