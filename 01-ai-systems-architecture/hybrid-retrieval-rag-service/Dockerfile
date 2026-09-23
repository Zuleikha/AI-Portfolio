FROM python:3.12-slim

WORKDIR /app

RUN pip install --upgrade pip --quiet

# Dependency layer first so source edits don't invalidate the pip cache.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir .

COPY . .

RUN mkdir -p data/raw data/processed

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
