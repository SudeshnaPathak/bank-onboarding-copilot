from __future__ import annotations

from ..utils import find_pan
from .common import clean, norm_date, value_after


def parse(lines: list[str]) -> dict[str, str]:
    text = "\n".join(lines)
    out: dict[str, str] = {}
    if pan := find_pan(text):
        out["pan_number"] = pan
    name = value_after(lines, r"name")
    if name:
        out["name"] = clean(name).upper()
    if father := value_after(lines, r"father'?s?\s+name"):
        out["father_name"] = clean(father).upper()
    dob_line = value_after(lines, r"date\s+of\s+birth|dob")
    dob = norm_date(dob_line or "") or norm_date(text)
    if dob:
        out["dob"] = dob
    return out
