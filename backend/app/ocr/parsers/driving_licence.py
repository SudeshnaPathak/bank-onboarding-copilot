from __future__ import annotations

import re
from collections import Counter
from datetime import date

from .common import (DATE_RE, Label, canon_name, collect_address, extract_labeled, find_label_index, is_namelike,
                     norm_date, prepare)

_DL_NO = re.compile(r"(?<![A-Z0-9])([A-Z]{2})[\s-]?(\d{2})[\s-]?(\d{4})[\s-]?(\d{7})(?!\d)")

LABELS = [
    Label("father_name", r"father'?s?\s+name|s/o|d/o|w/o|son/daughter/wife\s+of", "name"),
    Label("name", r"name", "name"),
    Label("dob", r"date\s+of\s+birth|dob|d\.o\.b", "date"),
    Label("issue_date", r"date\s+of\s+issue|issue\s+date|issued\s+on|doi", "date"),
    Label("valid_till", r"validity(?:\s*\(?(?:nt|tr)\)?)?|valid\s+(?:till|upto|up\s+to)|date\s+of\s+expiry|expiry(?:\s+date)?", "date"),
    # recognised only so they are never mistaken for a value or an address line
    Label("_blood", r"blood\s+group", "ignore"),
    Label("_endorse_date", r"endorsement\s+date", "ignore"),
    Label("_endorse_no", r"endorsement\s+no\.?", "ignore"),
    Label("_mobile", r"mobile\s+no\.?", "ignore"),
    Label("_authority", r"issuing\s+authority", "ignore"),
    Label("_sig", r"holder'?s?\s+signature", "ignore"),
]


def _d(value: str | None) -> date | None:
    m = DATE_RE.search(value or "")
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
    except ValueError:
        return None


def _repair_dates(out: dict[str, str], all_dates: list[str]) -> None:
    """Sanity layer: DOB < issue < validity must hold. If label pairing broke that (the classic bug: the
    'Validity' label picked up the issue date), fall back to what the dates themselves say."""
    dob, issue, valid = _d(out.get("dob")), _d(out.get("issue_date")), _d(out.get("valid_till"))
    pool = sorted({d for d in map(_d, all_dates) if d})
    if valid is None or (issue and valid <= issue) or (dob and valid <= dob):
        later = [d for d in pool if (not issue or d > issue) and (not dob or d > dob)]
        if later:
            out["valid_till"] = max(later).strftime("%d/%m/%Y")  # validity is the latest date on a licence
        else:
            out.pop("valid_till", None)  # better missing than wrong: the customer is asked / flagged
    if dob is None and pool:
        out["dob"] = pool[0].strftime("%d/%m/%Y")
    elif dob and issue and dob >= issue:
        out["dob"] = pool[0].strftime("%d/%m/%Y")


def parse(lines: list[str], scores: list[float] | None = None) -> dict[str, str]:
    lines, scores = prepare(lines, scores)
    text = "\n".join(lines)
    out: dict[str, str] = {}

    if m := _DL_NO.search(text.upper()):
        out["dl_number"] = "".join(m.groups())
    out.update(extract_labeled(lines, scores, LABELS))
    _repair_dates(out, [norm_date(m.group(0)) for m in DATE_RE.finditer(text)])

    if "name" not in out:  # the holder's name is printed twice on a licence; the father's name only once
        names = [canon_name(t) for t, s in zip(lines, scores) if is_namelike(t, s)]
        names = [n for n in names if n != out.get("father_name")]
        if names:
            out["name"] = Counter(names).most_common(1)[0][0]

    idx = find_label_index(lines, r"(?:present|permanent|current|residential)?\s*address")
    if idx is not None:
        inline = re.sub(r"^(?:(?:present|permanent|current|residential)\s+)?address\s*:?\s*", "", lines[idx], flags=re.I).strip()
        addr = collect_address(([inline] if inline else []) + lines[idx + 1:], ([1.0] if inline else []) + scores[idx + 1:], 0)
        if addr:
            out["address"] = addr
    return out
