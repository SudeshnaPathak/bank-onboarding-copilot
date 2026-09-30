"""Cross-document validation. Pure function: no database, no LLM. Every flag comes from a rule in rules.yaml.

`data` maps doc_type -> {"fields": {...}, "field_confidence": {...}, "field_source": {...}}.
Evidence never contains full ID numbers; only names, dates and addresses that a reviewer needs to compare.
"""
from __future__ import annotations

from datetime import date
from itertools import combinations

from ..ocr.utils import valid_aadhaar
from ..security.masking import mask_aadhaar
from ..services.form_schema import DOC_LABELS
from .checks import age_years, dl_number_valid, expiry_status, watchlist_screen
from .engine import make_flag, threshold
from .matchers import compatible

MISMATCH_CODES = {"name": "NAME_MISMATCH", "dob": "DOB_MISMATCH", "address": "ADDRESS_MISMATCH"}
FIELD_WORDS = {"name": "Name", "dob": "Date of birth", "address": "Address"}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
CONFIRMABLE = ("name", "dob", "address")


def _label(doc_type: str) -> str:
    return DOC_LABELS.get(doc_type, doc_type)


def _first_value(field: str, data: dict) -> str | None:
    for dt in ("pan", "aadhaar", "driving_licence"):
        if v := data.get(dt, {}).get("fields", {}).get(field):
            return v
    return None


def run_validation(required: list[str], confirmations: dict, data: dict, today: date) -> list[dict]:
    flags: list[dict] = []
    ratio = threshold("address_ratio")

    for dt in required:
        if dt not in data:
            flags.append(make_flag("MISSING_DOCUMENT", f"{_label(dt)} was not provided.", {"doc_type": dt}))

    for field, code in MISMATCH_CODES.items():
        values = {dt: d["fields"][field] for dt, d in data.items() if d["fields"].get(field)}
        if len(values) < 2:
            continue
        if all(compatible(field, a, b, ratio) for a, b in combinations(values.values(), 2)):
            continue
        detail = "; ".join(f"{_label(dt)}: {v}" for dt, v in values.items())
        confirmed = confirmations.get(field)
        msg = f"{FIELD_WORDS[field]} differs across documents ({detail})."
        if confirmed:
            msg += f" The customer confirmed \"{confirmed}\" during the chat."
        flags.append(make_flag(code, msg, {"values": values, "customer_confirmed": confirmed},
                               confirmed_by_customer=bool(confirmed)))

    aad = data.get("aadhaar", {})
    number = aad.get("fields", {}).get("aadhaar_number")
    if number and (aad.get("field_source", {}).get("aadhaar_number") == "ocr_checksum_failed" or not valid_aadhaar(number)):
        flags.append(make_flag("AADHAAR_CHECKSUM_FAILED",
                               "The Aadhaar number does not pass its built-in check digit. This is often an OCR misread.",
                               {"aadhaar": mask_aadhaar(number)}))

    dl = data.get("driving_licence", {}).get("fields", {})
    if dl.get("dl_number") and not dl_number_valid(dl["dl_number"]):
        flags.append(make_flag("DL_FORMAT_INVALID", "The licence number does not match the expected format.",
                               {"doc_type": "driving_licence"}))
    if dl.get("valid_till"):
        status, days = expiry_status(dl["valid_till"], today, threshold("expiring_days"))
        if status == "expired":
            flags.append(make_flag("DOC_EXPIRED", f"The driving licence expired on {dl['valid_till']} ({-days} days ago).",
                                   {"doc_type": "driving_licence", "valid_till": dl["valid_till"]}))
        elif status == "expiring_soon":
            flags.append(make_flag("DOC_EXPIRING_SOON", f"The driving licence expires on {dl['valid_till']} ({days} days).",
                                   {"doc_type": "driving_licence", "valid_till": dl["valid_till"]}))

    dob = confirmations.get("dob") or _first_value("dob", data)
    name = confirmations.get("name") or _first_value("name", data)
    age = age_years(dob, today) if dob else None
    if age is not None and age < threshold("min_age"):
        flags.append(make_flag("UNDERAGE", f"The date of birth {dob} gives an age of {age}.", {"dob": dob, "age": age}))
    if name:
        for hit in watchlist_screen(name, dob, threshold("watchlist_ratio")):
            dob_note = {True: "date of birth is compatible", False: "date of birth differs", None: "no date of birth to compare"}[hit["dob_match"]]
            flags.append(make_flag("WATCHLIST_HIT",
                                   f"Name resembles an entry on the {hit['list']} (similarity {hit['ratio']}%, {dob_note}). "
                                   "This is a screening lead for a human, not a determination.", hit))

    low_thr = threshold("low_confidence")
    for dt, d in data.items():
        fb = sorted(k for k, s in d.get("field_source", {}).items() if s == "llm_fallback")
        low = sorted(k for k, c in d.get("field_confidence", {}).items()
                     if c < low_thr and k not in fb and not (k in CONFIRMABLE and confirmations.get(k)))
        if low:
            flags.append(make_flag("LOW_CONFIDENCE_FIELD", f"{_label(dt)}: low OCR confidence for {', '.join(low)}.",
                                   {"doc_type": dt, "fields": low}))
        if fb:
            flags.append(make_flag("LLM_FALLBACK_USED", f"{_label(dt)}: {', '.join(fb)} filled by the AI fallback after the parser missed it.",
                                   {"doc_type": dt, "fields": fb}))

    return sorted(flags, key=lambda f: SEVERITY_ORDER[f["severity"]])
