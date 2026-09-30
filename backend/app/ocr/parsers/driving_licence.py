from __future__ import annotations

import re

from .common import clean, norm_date, value_after

_DL_NO = re.compile(r"\b([A-Z]{2})[\s-]?(\d{2})[\s-]?(\d{4})[\s-]?(\d{7})\b")


def parse(lines: list[str]) -> dict[str, str]:
    text = "\n".join(lines)
    out: dict[str, str] = {}
    if m := _DL_NO.search(text.upper()):
        out["dl_number"] = "".join(m.groups())
    if name := value_after(lines, r"name"):
        out["name"] = clean(name).upper()
    dob = norm_date(value_after(lines, r"dob|date\s+of\s+birth") or "")
    if dob:
        out["dob"] = dob
    valid = value_after(lines, r"valid\s+till|validity(?:\s*\(?nt\)?)?|valid\s+up\s*to|valid\s+upto")
    if valid and (d := norm_date(valid)):
        out["valid_till"] = d
    if issue := norm_date(value_after(lines, r"issue\s+date|date\s+of\s+issue") or ""):
        out["issue_date"] = issue
    if addr := value_after(lines, r"address", multiline=True):
        out["address"] = addr
    return out
