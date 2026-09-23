"""
Document ingestor: loads, chunks, embeds, and stores documents.

Supported formats: .pdf, .txt, .md
PDF extraction uses pypdf (the maintained successor to deprecated PyPDF2).
"""

from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from pathlib import Path

import pypdf

from src.rag.chunker import SentenceAwareChunker
from src.rag.pipeline import RAGPipeline

logger = logging.getLogger(__name__)

_TEXT_EXTENSIONS = {".txt", ".md"}
_PDF_EXTENSION = ".pdf"
_ALL_EXTENSIONS = {_PDF_EXTENSION} | _TEXT_EXTENSIONS


@dataclass
class IngestionResult:
    source: str
    chunks_created: int
    characters_processed: int


class DocumentIngestor:
    def __init__(self, pipeline: RAGPipeline) -> None:
        self._pipeline = pipeline
        self._chunker = SentenceAwareChunker()

    # ── Public interface ──────────────────────────────────────────────────────

    async def ingest_pdf_bytes(self, data: bytes, filename: str) -> IngestionResult:
        text = self._extract_pdf(data)
        return await self._ingest(text, source=filename, file_type="pdf")

    async def ingest_file(self, path: Path) -> IngestionResult:
        suffix = path.suffix.lower()
        if suffix == _PDF_EXTENSION:
            text = self._extract_pdf(path.read_bytes())
            return await self._ingest(text, source=path.name, file_type="pdf")
        if suffix in _TEXT_EXTENSIONS:
            text = path.read_text(encoding="utf-8", errors="ignore")
            return await self._ingest(text, source=path.name, file_type=suffix.lstrip("."))
        raise ValueError(f"Unsupported file type: {suffix}")

    async def ingest_directory(self, directory: Path) -> list[IngestionResult]:
        paths = [p for p in directory.iterdir() if p.suffix.lower() in _ALL_EXTENSIONS]
        if not paths:
            logger.warning("No supported documents found in %s", directory)
            return []

        results = await asyncio.gather(
            *[self.ingest_file(p) for p in paths],
            return_exceptions=True,
        )
        successes = [r for r in results if isinstance(r, IngestionResult)]
        failures = [r for r in results if isinstance(r, Exception)]
        if failures:
            logger.error("%d documents failed ingestion: %s", len(failures), failures)
        return successes

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _ingest(self, text: str, source: str, file_type: str) -> IngestionResult:
        chunks = self._chunker.chunk(text, metadata={"source": source, "file_type": file_type})
        await self._pipeline.ingest_chunks(chunks)
        logger.info("Ingested %s → %d chunks", source, len(chunks))
        return IngestionResult(
            source=source,
            chunks_created=len(chunks),
            characters_processed=len(text),
        )

    @staticmethod
    def _extract_pdf(data: bytes) -> str:
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages.append(page_text.strip())
        return "\n\n".join(pages)
