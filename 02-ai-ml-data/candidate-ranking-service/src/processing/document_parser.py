"""Extract plain text from uploaded resume documents."""

from __future__ import annotations

import io
import logging

import pypdf

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF"


class DocumentParseError(ValueError):
    """Raised when a document cannot be read as text."""


def looks_like_pdf(content: bytes) -> bool:
    """Whether the bytes begin with the PDF magic number.

    Content sniffing beats trusting the filename or the client-supplied
    content type, either of which can be wrong or absent.
    """
    return content.startswith(PDF_MAGIC)


def extract_pdf_text(content: bytes) -> str:
    """Return the concatenated text of every page in a PDF.

    Args:
        content: Raw PDF bytes.

    Returns:
        Plain text, stripped.

    Raises:
        DocumentParseError: If the bytes are not a readable PDF.
    """
    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise DocumentParseError(f"Could not read PDF: {exc}") from exc
    return "\n".join(pages).strip()


def extract_text(content: bytes) -> str:
    """Return the text of a resume upload, PDF or plain text.

    Args:
        content: Raw uploaded bytes.

    Returns:
        Extracted text, stripped.

    Raises:
        DocumentParseError: If the content is empty, is an unreadable PDF, or
            is not valid UTF-8 text.
    """
    if not content:
        raise DocumentParseError("Uploaded file is empty")

    if looks_like_pdf(content):
        text = extract_pdf_text(content)
        if not text:
            raise DocumentParseError(
                "PDF contained no extractable text. Scanned documents need OCR, "
                "which this service does not perform."
            )
        return text

    try:
        text = content.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise DocumentParseError(
            "File is neither a PDF nor UTF-8 text. Supported: .pdf, .txt, .md"
        ) from exc

    if not text:
        raise DocumentParseError("Uploaded file contains no text")
    return text
