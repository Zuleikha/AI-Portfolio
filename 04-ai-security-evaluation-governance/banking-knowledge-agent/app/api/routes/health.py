"""Health and readiness endpoints.

``GET /health`` is a pure liveness check: it answers "is this process alive and
how is it configured?" without touching any downstream system.

``GET /ready`` is the readiness check (Stage 13, carried item 12.D): "could
this process answer a question now?" It runs two named checks and returns 200
only when both pass, 503 otherwise, always in the same shape:

* ``vectorstore`` -- the persisted index in ``vectorstore_dir`` has a valid
  manifest, was built by the configured embedding model in the current on-disk
  format, holds at least one chunk, and its vectors file agrees with the
  manifest on row count and width. Only the manifest and the ``.npy`` *header*
  are read: the vectors are not loaded, and the embedding model is never
  loaded -- the configured model id is compared as a string.
* ``llm`` -- the configured provider is one this build knows; ``mock`` is
  always ready; a paid provider is ready only with a non-blank
  ``BKA_LLM_API_KEY`` and its SDK installed. No provider or SDK client is
  constructed and **no request is ever made** -- a probe that called a paid API
  would bill for every poll.

Both checks are cheap on purpose: a container orchestrator polls this often.
Neither consults ``app.state.conversation``: that service is built lazily on
the first question, so its absence says nothing, and the probe must never
build it (that would load the model on a health poll).

A failing check is logged as ``api.ready_check_failed`` with the check name and
the exception *type* only. Exception text can hold filesystem paths or
configuration detail, so it reaches neither the log nor the response.

Both routes are unauthenticated: probes hold no API key (guide §20.50).

Route handlers are intentionally not wrapped in ``@traced``: FastAPI resolves
handler annotations against the decorated function's module globals, which a
wrapper breaks. Request-level tracing is applied as middleware in Stage 10.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.dependencies import SettingsDep
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.tracing import traced
from app.llm.factory import AVAILABLE_PROVIDERS, PAID_PROVIDERS
from app.rag.embeddings import get_embedder
from app.rag.vectorstore import (
    CHUNKS_FILENAME,
    INDEX_FORMAT_VERSION,
    MANIFEST_FILENAME,
    VECTORS_FILENAME,
)

logger = get_logger(__name__)

router = APIRouter(tags=["health"])

CheckStatus = Literal["ok", "failed"]

PROVIDER_SDK_MODULES = {"anthropic": "anthropic", "openai": "openai"}
"""Import name of each paid provider's SDK, checked with ``find_spec`` only."""


class ReadinessError(RuntimeError):
    """A readiness check found the dependency unusable."""


class HealthResponse(BaseModel):
    """Payload returned by ``GET /health``."""

    status: str = Field(description="Overall service status.", examples=["ok"])
    service: str = Field(description="Human readable service name.")
    version: str = Field(description="Running application version.")
    environment: str = Field(description="Active environment profile.")


class ReadinessResponse(BaseModel):
    """Payload returned by ``GET /ready``, with 200 and with 503 alike."""

    status: Literal["ready", "not_ready"] = Field(
        description="'ready' only when every check is 'ok'."
    )
    checks: dict[str, CheckStatus] = Field(
        description="Each named check and its outcome. Never exception text.",
        examples=[{"vectorstore": "ok", "llm": "ok"}],
    )


@traced
def check_vectorstore(settings: Settings) -> None:
    """Validate the persisted index without loading vectors or the model.

    Raises:
        ReadinessError: If the index is absent, stale or inconsistent.
        OSError, ValueError: If a file cannot be read or parsed.
    """
    directory = settings.vectorstore_dir
    manifest_path = directory / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise ReadinessError("manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ReadinessError("manifest is not an object")
    if manifest.get("format_version") != INDEX_FORMAT_VERSION:
        raise ReadinessError("index format version differs")
    # Constructing an embedder is cheap by design; only its id is read.
    if manifest.get("model_id") != get_embedder(settings).model_id:
        raise ReadinessError("index built by a different embedding model")
    dimension = manifest.get("dimension")
    chunk_count = manifest.get("chunk_count")
    if not isinstance(dimension, int) or dimension < 1:
        raise ReadinessError("manifest dimension invalid")
    if not isinstance(chunk_count, int) or chunk_count < 1:
        raise ReadinessError("index is empty")
    if not (directory / CHUNKS_FILENAME).is_file():
        raise ReadinessError("chunks file missing")
    if _vectors_shape(directory / VECTORS_FILENAME) != (chunk_count, dimension):
        raise ReadinessError("vectors disagree with manifest")


@traced
def _vectors_shape(path: Path) -> tuple[int, ...]:
    """Read an ``.npy`` file's shape from its header, not its data."""
    if not path.is_file():
        raise ReadinessError("vectors file missing")
    with path.open("rb") as handle:
        version = np.lib.format.read_magic(handle)
        if version == (1, 0):
            shape, _, _ = np.lib.format.read_array_header_1_0(handle)
        elif version == (2, 0):
            shape, _, _ = np.lib.format.read_array_header_2_0(handle)
        else:
            raise ReadinessError("unsupported .npy version")
    return tuple(int(size) for size in shape)


@traced
def check_llm(settings: Settings) -> None:
    """Check the configured provider could be built, without building it.

    Raises:
        ReadinessError: If the provider is unknown, a paid provider has no
            key, or its SDK is not installed.
    """
    provider = settings.llm_provider
    if provider not in AVAILABLE_PROVIDERS:
        raise ReadinessError("unknown provider")
    if provider not in PAID_PROVIDERS:
        return
    key = settings.llm_api_key
    if key is None or not key.get_secret_value().strip():
        raise ReadinessError("paid provider without a key")
    if importlib.util.find_spec(PROVIDER_SDK_MODULES[provider]) is None:
        raise ReadinessError("provider SDK not installed")


@traced
def run_readiness_checks(settings: Settings) -> dict[str, CheckStatus]:
    """Run every check; a failure is logged by name and type, never by text."""
    # Built per call from the module names, so one check can be swapped in tests.
    checks: tuple[tuple[str, Callable[[Settings], None]], ...] = (
        ("vectorstore", check_vectorstore),
        ("llm", check_llm),
    )
    results: dict[str, CheckStatus] = {}
    for name, check in checks:
        try:
            check(settings)
        except Exception as exc:  # any failure at all means "not ready"
            logger.warning(
                "api.ready_check_failed", check=name, error_type=type(exc).__name__
            )
            results[name] = "failed"
        else:
            results[name] = "ok"
    return results


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health(settings: SettingsDep) -> HealthResponse:
    """Report that the service is running and how it is configured."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness check",
    responses={503: {"model": ReadinessResponse, "description": "Not ready."}},
)
def ready(settings: SettingsDep) -> JSONResponse:
    """Report whether the index and the LLM provider are usable. Offline."""
    checks = run_readiness_checks(settings)
    healthy = all(value == "ok" for value in checks.values())
    body = ReadinessResponse(status="ready" if healthy else "not_ready", checks=checks)
    return JSONResponse(
        status_code=200 if healthy else 503, content=body.model_dump(mode="json")
    )
