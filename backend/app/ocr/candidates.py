"""Merges one document's extraction into the per-field candidate lists (masked identifiers only)."""
from __future__ import annotations

from ..security.masking import mask_field

CANDIDATE_FIELDS = ("name", "dob", "address", "pan_number", "aadhaar_number", "dl_number", "valid_till")


def merge_candidates(extracted: dict, doc_type: str, res) -> dict:
    merged = {k: [c for c in v if c["source_doc"] != doc_type] for k, v in extracted.items()}  # re-upload replaces
    for key in CANDIDATE_FIELDS:
        if value := res.fields.get(key):
            merged.setdefault(key, []).append({
                "value": mask_field(key, value), "source_doc": doc_type,
                "confidence": res.field_confidence.get(key, res.mean_confidence),
                "source": res.field_source.get(key, "ocr")})
    return {k: v for k, v in merged.items() if v}
