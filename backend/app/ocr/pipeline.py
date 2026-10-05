"""OCR -> parse -> (optional) verified LLM fallback -> per-field confidence and provenance."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import pdf
from .engine import get_engine
from .parsers import PARSERS
from .utils import field_confidence, normalize_text, valid_aadhaar

REQUIRED_FIELDS = {
    "pan": ["pan_number", "name", "dob"],
    "aadhaar": ["aadhaar_number", "name", "dob", "address"],
    "driving_licence": ["dl_number", "name", "dob", "valid_till", "address"],
}


@dataclass
class ExtractionResult:
    doc_type: str
    raw_text: str
    fields: dict[str, str]
    field_confidence: dict[str, float]
    field_source: dict[str, str]
    missing: list[str]
    mean_confidence: float
    lines: list[tuple[str, float]] = field(default_factory=list)


class UnsupportedDocument(ValueError):
    pass


log = logging.getLogger(__name__)
ENGINE_FAILED = ("Sorry, our document reader ran into a problem. Please try again in a moment. "
                 "If it keeps happening, contact support.")


def _engine_call(fn, path: str):
    """Run an OCR engine call. A crash inside the engine (bad install, model download failure, inference error)
    must not kill the customer's chat turn: log the real cause for the operator and show a plain message."""
    try:
        return fn(path)
    except pdf.PdfProblem:
        raise  # a specific, customer-actionable PDF problem; handled by the caller
    except Exception:
        log.exception("OCR engine %s failed on an uploaded document", getattr(get_engine(), "name", "?"))
        raise UnsupportedDocument(ENGINE_FAILED)


def _read_lines(path: str) -> tuple[list[tuple[str, float]], str]:
    if Path(path).suffix.lower() == ".pdf":
        try:
            info = pdf.inspect(path)
            if info.lines:  # real text layer: no OCR needed
                return info.lines, "pdf_text"
            lines = _engine_call(get_engine().read_pdf, path)  # scanned PDF: rasterise + OCR every page
        except pdf.PdfProblem as exc:
            raise UnsupportedDocument(pdf.message_for(exc.code))
        if not lines:
            raise UnsupportedDocument(
                "I couldn't read any text from this PDF. Please upload a clearer scan, or a photo of the document.")
        return lines, "ocr"
    return _engine_call(get_engine().read, path), "ocr"


def _grounded(value: str, raw_text: str) -> bool:
    """Reject LLM-fallback values that do not literally appear in the OCR text."""
    norm = lambda s: re.sub(r"[^A-Z0-9]", "", s.upper())
    return bool(norm(value)) and norm(value) in norm(raw_text)


async def extract_document(path: str, doc_type: str, llm=None) -> ExtractionResult:
    lines, base_source = await asyncio.to_thread(_read_lines, path)
    lines = [(t, c) for t, c in ((normalize_text(t).strip(), c) for t, c in lines) if t]
    texts = [t for t, _ in lines]
    raw_text = "\n".join(texts)
    fields = PARSERS[doc_type](texts, [score for _, score in lines]) if texts else {}
    source = {k: base_source for k in fields}
    if fields.get("aadhaar_number") and not valid_aadhaar(fields["aadhaar_number"]):
        source["aadhaar_number"] = "ocr_checksum_failed"

    missing = [f for f in REQUIRED_FIELDS[doc_type] if not fields.get(f)]
    if missing and llm is not None and raw_text:
        filled = await llm.fallback_extract(doc_type, raw_text, missing)
        for k, v in filled.items():
            if k in missing and v and _grounded(v, raw_text):
                fields[k], source[k] = v.strip(), "llm_fallback"
        missing = [f for f in REQUIRED_FIELDS[doc_type] if not fields.get(f)]

    mean = round(sum(s for _, s in lines) / len(lines), 3) if lines else 0.0
    conf: dict[str, float] = {}
    for k, v in fields.items():
        if source.get(k) == "llm_fallback":
            conf[k] = 0.6
        else:
            fc = field_confidence(v, lines)
            conf[k] = fc if fc is not None else min(mean, 0.5)
    return ExtractionResult(doc_type, raw_text, fields, conf, source, missing, mean, lines)
