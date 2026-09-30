"""Builds realistic extraction state from the synthetic scenarios, with no database and no network."""
from __future__ import annotations

import asyncio
import tempfile
from functools import lru_cache

from app.config import get_settings
from app.ocr.candidates import merge_candidates
from app.ocr.pipeline import extract_document
from app.synthetic import generate_all


@lru_cache
def _samples() -> tuple[str, dict]:
    d = tempfile.mkdtemp()
    return d, generate_all(d, get_settings().fixture_dir)


def scenario(key: str) -> tuple[dict, dict]:
    """Returns (extracted candidates, per-document data in the same shape validation reads from the database)."""
    d, manifest = _samples()
    extracted, data = {}, {}
    for doc_type in manifest[key]["documents"]:
        if doc_type.endswith("_retake"):
            continue
        res = asyncio.run(extract_document(f"{d}/{key}/{doc_type}.png", doc_type, None))
        extracted = merge_candidates(extracted, doc_type, res)
        data[doc_type] = {"fields": res.fields, "field_confidence": res.field_confidence, "field_source": res.field_source}
    return extracted, data


def base_state(extracted: dict, **over) -> dict:
    st = {"case_id": "c1", "user_id": "u1", "user_name": "Priya Sharma", "product": "basic_savings", "status": "draft",
          "form": {}, "extracted": extracted, "uploaded": ["aadhaar", "driving_licence", "pan"], "text": None, "action": None,
          "pending_upload": None, "user_display": "", "passive": False, "last_upload": None, "upload_feedback": [], "gate_errors": []}
    st.update(over)
    return st
