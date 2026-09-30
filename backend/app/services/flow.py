"""Pure functions that decide what the conversation needs next. Deterministic and unit-tested."""
from __future__ import annotations

from ..rules.engine import threshold
from ..rules.matchers import compatible
from .form_schema import FIELD_BY_KEY, FIELDS, PRODUCTS

CONFIRM_FIELDS = ("name", "dob", "address")
DOC_PRIORITY = {"pan": 0, "aadhaar": 1, "driving_licence": 2}


def required_docs(product: str) -> list[str]:
    return PRODUCTS[product]["documents"]


def missing_docs(product: str, uploaded: set[str]) -> list[str]:
    return [d for d in required_docs(product) if d not in uploaded]


def needs_confirmation(field: str, candidates: list[dict]) -> str | None:
    """Returns the reason a field must be confirmed by the customer, or None."""
    if any(c["confidence"] < threshold("low_confidence") for c in candidates):
        return "low_confidence"
    if any(c["source"] in ("llm_fallback", "ocr_checksum_failed") for c in candidates):
        return "low_confidence"
    vals = [c["value"] for c in candidates]
    if any(not compatible(field, vals[0], v, threshold("address_ratio")) for v in vals[1:]):
        return "conflict"
    return None


def pending_confirmations(extracted: dict, form: dict) -> list[str]:
    done = form.get("confirmations", {})
    return [f for f in CONFIRM_FIELDS if f in extracted and f not in done and needs_confirmation(f, extracted[f])]


def resolved(extracted: dict, form: dict, field: str) -> str | None:
    confirmed = form.get("confirmations", {}).get(field)
    if confirmed:
        return confirmed
    cands = extracted.get(field, [])
    if not cands:
        return None
    return sorted(cands, key=lambda c: (-c["confidence"], DOC_PRIORITY.get(c["source_doc"], 9)))[0]["value"]


def applicable_fields(form: dict):
    for f in FIELDS:
        if f.key == "nominee_relation" and not form.get("nominee_name"):
            continue  # only ask the relationship when a nominee was actually named
        yield f


def missing_fields(form: dict):
    return [f for f in applicable_fields(form) if f.key not in form]


def next_step(product: str, uploaded: set[str], extracted: dict, form: dict) -> dict:
    if md := missing_docs(product, uploaded):
        return {"kind": "upload", "doc_type": md[0]}
    if pc := pending_confirmations(extracted, form):
        return {"kind": "confirm", "field": pc[0]}
    if mf := missing_fields(form):
        return {"kind": "field", "field": mf[0].key}
    if form.get("consent") is not True:
        return {"kind": "blocked", "reason": "consent_declined"}
    return {"kind": "ready"}


def progress(product: str, uploaded: set[str], extracted: dict, form: dict, status: str) -> list[dict]:
    step = next_step(product, uploaded, extracted, form)
    docs_done = not missing_docs(product, uploaded)
    confirm_done = docs_done and not pending_confirmations(extracted, form)
    details_done = confirm_done and not missing_fields(form)
    submitted = status != "draft" and status != "info_requested"
    steps = [
        ("documents", "Upload documents", docs_done),
        ("confirm", "Confirm what we read", confirm_done),
        ("details", "Your details", details_done),
        ("review", "Submit for review", submitted),
    ]
    out, current_set = [], False
    for key, label, done in steps:
        state = "done" if done else ("current" if not current_set else "todo")
        current_set = current_set or not done
        out.append({"key": key, "label": label, "status": state})
    out.append({"key": "decision", "label": "Reviewer decision",
                "status": "done" if status in ("approved", "rejected") else "todo"})
    return out
