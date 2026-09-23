# Banking Knowledge Agent -- container image (Stage 12).
# Decisions: docs/HANDOVER.md §12.A-§12.G, guide §20.43-§20.48.
#
#   docker compose up --build                      # run (target: runtime)
#   docker build --target test -t bka-test .       # full test suite image
#   docker run --rm bka-test

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

# 12.F: an unprivileged user owns only what the app writes.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app

# 12.B: CPU-only PyTorch first, at the version pinned in requirements.txt, so
# the second install finds torch already satisfied and pulls no CUDA wheels.
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        "$(grep -E '^torch==' requirements.txt)" \
    && pip install -r requirements.txt

COPY pyproject.toml .
COPY app ./app
COPY data ./data

RUN mkdir -p logs data/vectorstore "$HF_HOME" \
    && chown app:app logs data/vectorstore "$HF_HOME"

USER app

# 12.A: download the embedding model and build the index now, so the running
# container needs no network. No log files are left in the image.
RUN BKA_LOG_TO_FILE=false python -m app.rag build

# 15.A: JSON logs by default -- one object per line for a log collector to
# parse into fields. Overridable: -e BKA_LOG_FORMAT=console for a human.
ENV HF_HUB_OFFLINE=1 \
    BKA_HOST=0.0.0.0 \
    BKA_PORT=8000 \
    BKA_LOG_FORMAT=json

EXPOSE 8000

# 12.D: liveness via Python -- the slim image has no curl. 13.G: stays on
# /health; /ready is for orchestrators that route traffic, not for restarts.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['BKA_PORT'] + '/health', timeout=4)"

# 14.A: python -m app reads BKA_HOST / BKA_PORT through the validated settings.
# 13.H: --no-access-log -- uvicorn's access log prints client IP and path and
# bypasses log redaction; the request middleware already logs every request.
CMD ["python", "-m", "app", "--no-access-log"]

# ---------------------------------------------------------------------------
# 12.E: the runtime image plus dev tools and tests. Never deployed.
FROM runtime AS test

USER root
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY tests ./tests
# Read by tests/test_container_config.py; not present in the runtime image.
COPY Dockerfile compose.yaml .dockerignore ./
# pytest writes .pytest_tmp and .pytest_cache at the repository root.
RUN chown app:app /app
USER app

CMD ["python", "-m", "pytest"]
