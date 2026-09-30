"""PDF support for the OCR pipeline.

A PDF reaches us in one of two shapes:
  * text PDF    - has a real text layer (e-Aadhaar / DigiLocker downloads, "print to PDF"). Read directly.
  * scanned PDF - just page images (phone scanner apps, flatbed scans). Rasterised here, then OCR'd page by page.

Everything that parses untrusted PDF bytes lives in this module so the limits (page count, render size,
encryption) are enforced in one place.
"""
from __future__ import annotations

import io
import math
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings

MIN_TEXT_CHARS = 40            # fewer alphanumerics than this in the text layer => treat as scanned
MAX_RENDER_PIXELS = 25_000_000  # caps memory for oversized pages (a 40x40 inch "page" must not exhaust RAM)

PDF_MESSAGES = {
    "pdf_encrypted": "This PDF is password-protected, so I can't open it. Please remove the password "
                     "(or upload a photo or screenshot of the document instead).",
    "pdf_too_many_pages": "This PDF has too many pages. Please upload only the pages that show the document "
                          "(up to {max_pages}).",
    "pdf_unreadable": "I couldn't open that PDF. It may be damaged. Please upload it again, or use a photo instead.",
    "pdf_empty": "That PDF has no pages.",
}


class PdfProblem(ValueError):
    """The PDF can't be processed. `code` is a key of PDF_MESSAGES."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def message_for(code: str) -> str:
    return PDF_MESSAGES[code].format(max_pages=get_settings().max_pdf_pages)


@dataclass
class PdfInfo:
    pages: int
    lines: list[tuple[str, float]] = field(default_factory=list)  # text-layer lines (empty for scanned PDFs)

    @property
    def kind(self) -> str:
        return "text" if self.lines else "scanned"


def inspect(path: str) -> PdfInfo:
    """Open the PDF, enforce limits, and pull the text layer if there is a usable one."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")  # some PDFs are 'encrypted' with an empty user password
            except Exception:
                ok = 0
            if not ok:
                raise PdfProblem("pdf_encrypted")
        n = len(reader.pages)
        if n == 0:
            raise PdfProblem("pdf_empty")
        if n > get_settings().max_pdf_pages:
            raise PdfProblem("pdf_too_many_pages")
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except PdfProblem:
        raise
    except (PyPdfError, ValueError, KeyError, IndexError, RecursionError, OSError, NotImplementedError):
        raise PdfProblem("pdf_unreadable")

    lines = [(ln.strip(), 0.99) for ln in text.splitlines() if ln.strip()]
    if sum(c.isalnum() for ln, _ in lines for c in ln) < MIN_TEXT_CHARS:
        lines = []  # a stray page number or watermark is not a text layer
    return PdfInfo(pages=n, lines=lines)


def _pdfium():
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
        raise RuntimeError("Scanned-PDF support needs pypdfium2:  pip install pypdfium2") from exc
    return pdfium


def render_page(path: str, index: int, dpi: int | None = None):
    """Rasterise one page to an RGB PIL image, with the pixel count capped."""
    pdfium = _pdfium()
    dpi = dpi or get_settings().pdf_render_dpi
    try:
        pdf = pdfium.PdfDocument(path)
    except Exception:
        raise PdfProblem("pdf_unreadable")
    try:
        if not 0 <= index < len(pdf):
            raise IndexError(index)
        page = pdf[index]
        w, h = page.get_size()  # PDF points (1/72 inch)
        scale = dpi / 72
        if w * h * scale * scale > MAX_RENDER_PIXELS:
            scale = math.sqrt(MAX_RENDER_PIXELS / (w * h))
        return page.render(scale=scale).to_pil().convert("RGB")
    except IndexError:
        raise
    except Exception:
        raise PdfProblem("pdf_unreadable")
    finally:
        pdf.close()


def render_page_png(path: str, index: int, dpi: int = 130) -> bytes:
    """PNG bytes of one page. Used by the analyst viewer so the browser never has to open an uploaded PDF."""
    buf = io.BytesIO()
    render_page(path, index, dpi).save(buf, format="PNG")
    return buf.getvalue()


@contextmanager
def rendered_pages(path: str):
    """Yield temp PNG paths, one per page, and delete them afterwards (they hold plaintext ID images)."""
    n = _page_count(path)
    with tempfile.TemporaryDirectory(prefix="ocr-pdf-") as tmp:
        paths = []
        for i in range(n):
            out = os.path.join(tmp, f"page-{i + 1}.png")
            render_page(path, i).save(out, format="PNG")
            paths.append(out)
        yield paths


def _page_count(path: str) -> int:
    pdfium = _pdfium()
    try:
        pdf = pdfium.PdfDocument(path)
        try:
            n = len(pdf)
        finally:
            pdf.close()
    except Exception:
        raise PdfProblem("pdf_unreadable")
    if n == 0:
        raise PdfProblem("pdf_empty")
    if n > get_settings().max_pdf_pages:
        raise PdfProblem("pdf_too_many_pages")
    return n
