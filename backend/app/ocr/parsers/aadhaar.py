from __future__ import annotations

import re

from ..utils import valid_aadhaar
from .common import clean, norm_date, value_after

_HEADER_WORDS = re.compile(r"government|india|aadhaar|unique|authority|enrol|address|help|www|vid|male|female|dob|year", re.I)


def parse(lines: list[str]) -> dict[str, str]:
    text = "\n".join(lines)
    out: dict[str, str] = {}

    candidates = [re.sub(r"\s", "", m.group(0)) for m in re.finditer(r"\b\d{4}\s?\d{4}\s?\d{4}\b", text)]
    valid = [c for c in candidates if valid_aadhaar(c)]
    if valid or candidates:
        out["aadhaar_number"] = (valid or candidates)[0]  # checksum-failed numbers are flagged later

    dob_idx = None
    for i, line in enumerate(lines):
        d = norm_date(line)
        if d and re.search(r"dob|date of birth|birth", line, re.I):
            out["dob"], dob_idx = d, i
            break
        y = re.search(r"(?:year\s+of\s+birth|\byob\b)\D{0,6}((?:19|20)\d{2})", line, re.I)
        if y:
            out["dob"], dob_idx = y.group(1), i  # year-only birth date
            break
    if "dob" not in out and (d := norm_date(text)):
        out["dob"] = d

    # Name is printed just above the DOB / year-of-birth line on Aadhaar cards.
    if dob_idx is not None:
        for k in range(dob_idx - 1, -1, -1):
            cand = lines[k].strip()
            if re.fullmatch(r"[A-Za-z .']{3,}", cand) and len(cand.split()) >= 2 and not _HEADER_WORDS.search(cand):
                out["name"] = clean(cand).upper()
                break

    if g := re.search(r"\b(male|female|transgender)\b", text, re.I):
        out["gender"] = g.group(1).capitalize()
    if addr := value_after(lines, r"address", multiline=True):
        out["address"] = addr
    return out
