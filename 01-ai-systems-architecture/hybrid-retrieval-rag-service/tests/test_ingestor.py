"""Unit tests for DocumentIngestor — PDF extraction, file ingestion, directory ingestion."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.ingest import DocumentIngestor, IngestionResult


@pytest.fixture
def mock_pipeline():
    p = MagicMock()
    p.ingest_chunks = AsyncMock(return_value=3)
    return p


@pytest.fixture
def ingestor(mock_pipeline):
    return DocumentIngestor(mock_pipeline)


# ── _extract_pdf (static) ─────────────────────────────────────────────────────


class TestExtractPdf:
    def test_text_from_each_page_is_included(self):
        page_1 = MagicMock()
        page_1.extract_text.return_value = "Page one text."
        page_2 = MagicMock()
        page_2.extract_text.return_value = "Page two text."

        with patch("src.ingestion.ingest.pypdf.PdfReader") as MockReader:
            MockReader.return_value.pages = [page_1, page_2]
            result = DocumentIngestor._extract_pdf(b"fake pdf")

        assert "Page one text." in result
        assert "Page two text." in result

    def test_blank_pages_are_skipped(self):
        blank = MagicMock()
        blank.extract_text.return_value = ""
        real = MagicMock()
        real.extract_text.return_value = "Real content."

        with patch("src.ingestion.ingest.pypdf.PdfReader") as MockReader:
            MockReader.return_value.pages = [blank, real]
            result = DocumentIngestor._extract_pdf(b"fake pdf")

        assert result.strip() == "Real content."

    def test_none_page_text_is_skipped(self):
        page = MagicMock()
        page.extract_text.return_value = None

        with patch("src.ingestion.ingest.pypdf.PdfReader") as MockReader:
            MockReader.return_value.pages = [page]
            result = DocumentIngestor._extract_pdf(b"fake pdf")

        assert result == ""

    def test_pages_are_joined_by_double_newline(self):
        page_a = MagicMock()
        page_a.extract_text.return_value = "Alpha."
        page_b = MagicMock()
        page_b.extract_text.return_value = "Beta."

        with patch("src.ingestion.ingest.pypdf.PdfReader") as MockReader:
            MockReader.return_value.pages = [page_a, page_b]
            result = DocumentIngestor._extract_pdf(b"fake pdf")

        assert "\n\n" in result


# ── ingest_pdf_bytes ──────────────────────────────────────────────────────────


class TestIngestPdfBytes:
    @pytest.mark.asyncio
    async def test_returns_ingestion_result(self, ingestor):
        with patch.object(
            DocumentIngestor, "_extract_pdf", return_value="Extracted text from PDF."
        ):
            result = await ingestor.ingest_pdf_bytes(b"pdf bytes", "report.pdf")

        assert isinstance(result, IngestionResult)

    @pytest.mark.asyncio
    async def test_source_is_the_provided_filename(self, ingestor):
        with patch.object(DocumentIngestor, "_extract_pdf", return_value="text"):
            result = await ingestor.ingest_pdf_bytes(b"pdf", "annual_report.pdf")

        assert result.source == "annual_report.pdf"

    @pytest.mark.asyncio
    async def test_characters_processed_matches_extracted_text_length(self, ingestor):
        extracted = "Extracted text from PDF."
        with patch.object(DocumentIngestor, "_extract_pdf", return_value=extracted):
            result = await ingestor.ingest_pdf_bytes(b"pdf", "doc.pdf")

        assert result.characters_processed == len(extracted)

    @pytest.mark.asyncio
    async def test_pipeline_ingest_chunks_is_awaited(self, ingestor, mock_pipeline):
        with patch.object(DocumentIngestor, "_extract_pdf", return_value="Enough text to chunk."):
            await ingestor.ingest_pdf_bytes(b"pdf", "doc.pdf")

        mock_pipeline.ingest_chunks.assert_awaited_once()


# ── ingest_file ───────────────────────────────────────────────────────────────


class TestIngestFile:
    @pytest.mark.asyncio
    async def test_txt_file_returns_ingestion_result(self, ingestor, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello world. This is a sentence.")
        result = await ingestor.ingest_file(f)
        assert isinstance(result, IngestionResult)

    @pytest.mark.asyncio
    async def test_txt_source_name_is_filename_only(self, ingestor, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("Some notes here.")
        result = await ingestor.ingest_file(f)
        assert result.source == "notes.txt"

    @pytest.mark.asyncio
    async def test_md_file_is_accepted(self, ingestor, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Title\n\nSome content.")
        result = await ingestor.ingest_file(f)
        assert result.source == "readme.md"

    @pytest.mark.asyncio
    async def test_unsupported_extension_raises_value_error(self, ingestor, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b,c")
        with pytest.raises(ValueError, match="Unsupported"):
            await ingestor.ingest_file(f)

    @pytest.mark.asyncio
    async def test_txt_chunk_metadata_has_correct_file_type(
        self, ingestor, tmp_path, mock_pipeline
    ):
        f = tmp_path / "article.txt"
        f.write_text("A full sentence about something interesting.")
        await ingestor.ingest_file(f)

        mock_pipeline.ingest_chunks.assert_awaited_once()
        chunks = mock_pipeline.ingest_chunks.call_args[0][0]
        assert chunks, "expected at least one chunk"
        assert all(c.metadata["file_type"] == "txt" for c in chunks)

    @pytest.mark.asyncio
    async def test_md_chunk_metadata_has_correct_file_type(self, ingestor, tmp_path, mock_pipeline):
        f = tmp_path / "notes.md"
        f.write_text("A markdown sentence. Another sentence.")
        await ingestor.ingest_file(f)

        chunks = mock_pipeline.ingest_chunks.call_args[0][0]
        assert all(c.metadata["file_type"] == "md" for c in chunks)


# ── ingest_directory ──────────────────────────────────────────────────────────


class TestIngestDirectory:
    @pytest.mark.asyncio
    async def test_empty_directory_returns_empty_list(self, ingestor, tmp_path):
        result = await ingestor.ingest_directory(tmp_path)
        assert result == []

    @pytest.mark.asyncio
    async def test_only_supported_extensions_are_ingested(self, ingestor, tmp_path):
        (tmp_path / "a.txt").write_text("Content A.")
        (tmp_path / "b.md").write_text("Content B.")
        (tmp_path / "ignore.csv").write_text("1,2,3")
        (tmp_path / "skip.json").write_text("{}")

        results = await ingestor.ingest_directory(tmp_path)

        sources = {r.source for r in results}
        assert "a.txt" in sources
        assert "b.md" in sources
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_failed_files_are_excluded_from_results(self, ingestor, tmp_path):
        (tmp_path / "good.txt").write_text("Good content.")
        (tmp_path / "bad.txt").write_text("Bad content.")

        original_ingest_file = ingestor.ingest_file

        async def sometimes_fail(path: Path) -> IngestionResult:
            if "bad" in path.name:
                raise RuntimeError("Simulated failure")
            return await original_ingest_file(path)

        ingestor.ingest_file = sometimes_fail
        results = await ingestor.ingest_directory(tmp_path)

        assert len(results) == 1
        assert results[0].source == "good.txt"

    @pytest.mark.asyncio
    async def test_all_files_succeed_returns_all_results(self, ingestor, tmp_path):
        for i in range(3):
            (tmp_path / f"doc{i}.txt").write_text(f"Document number {i}.")

        results = await ingestor.ingest_directory(tmp_path)
        assert len(results) == 3
