from __future__ import annotations

import re

from ..utils import valid_aadhaar
from .common import (AADHAAR_LINE_RE, Label, canon_name, collect_address, extract_labeled, find_label_index,
                     is_namelike, prepare)

LABELS = [
    Label("father_name", r"father'?s?\s+name|s/o|d/o|w/o|c/o", "name"),
    Label("dob", r"date\s+of\s+birth|dob|d\.o\.b|year\s+of\s+birth|yob", "dob"),
]


def parse(lines: list[str], scores: list[float] | None = None) -> dict[str, str]:
    lines, scores = prepare(lines, scores)
    text = "\n".join(lines)
    out: dict[str, str] = {}

    numbers = [re.sub(r"\s", "", m.group(0)) for m in AADHAAR_LINE_RE.finditer(text)]
    valid = [n for n in numbers if valid_aadhaar(n)]
    if valid or numbers:
        out["aadhaar_number"] = (valid or numbers)[0]  # a checksum-failed number is flagged downstream

    out.update(extract_labeled(lines, scores, LABELS))
    dob_idx = find_label_index(lines, r"date\s+of\s+birth|dob|d\.o\.b|year\s+of\s+birth|yob")
    father_idx = find_label_index(lines, r"father'?s?\s+name|s/o|d/o|w/o|c/o")

    # The holder's English name is printed ABOVE the father's name / DOB lines, with no label of its own.
    limit = min(i for i in (dob_idx, father_idx, len(lines)) if i is not None)
    for t, s in zip(lines[:limit], scores[:limit]):
        if is_namelike(t, s, min_score=0.6):
            out["name"] = canon_name(t)
            break

    gender_idx = next((i for i, t in enumerate(lines) if re.fullmatch(r"(male|female|transgender)", t, re.I)), None)
    if gender_idx is not None:
        out["gender"] = lines[gender_idx].capitalize()

    # Address: the back page has an 'Address:' label; the front page prints it unlabelled above the number.
    addr_idx = find_label_index(lines, r"address")
    if addr_idx is not None:
        inline = re.sub(r"^address\s*:?\s*", "", lines[addr_idx], flags=re.I).strip()
        out["address"] = collect_address(([inline] if inline else []) + lines[addr_idx + 1:],
                                         ([1.0] if inline else []) + scores[addr_idx + 1:], 0) or ""
    if not out.get("address"):
        anchor = gender_idx if gender_idx is not None else dob_idx
        if anchor is not None:
            out["address"] = collect_address(lines, scores, anchor + 1) or ""
    if not out.get("address"):
        out.pop("address", None)
    return out
