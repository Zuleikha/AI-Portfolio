FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV DAGSTER_HOME=/app/dagster_home

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer first so source edits don't invalidate the pip cache.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY . .

# Model bundles and datasets are produced by a training run, not baked into the image.
RUN mkdir -p data/raw data/processed data/external models dagster_home

EXPOSE 8000 3000

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
