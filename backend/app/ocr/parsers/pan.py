from __future__ import annotations

from ..utils import find_pan
from .common import Label, canon_name, extract_labeled, is_namelike, norm_date, prepare

LABELS = [
    Label("father_name", r"father'?s?\s+name", "name"),
    Label("name", r"name", "name"),
    Label("dob", r"date\s+of\s+birth|dob|d\.o\.b", "dob"),
    Label("_sig", r"signature", "ignore"),
]


def parse(lines: list[str], scores: list[float] | None = None) -> dict[str, str]:
    lines, scores = prepare(lines, scores)
    text = "\n".join(lines)
    out: dict[str, str] = {}
    if pan := find_pan(text):
        out["pan_number"] = pan
    out.update(extract_labeled(lines, scores, LABELS))

    if "dob" not in out and (d := norm_date(text)):
        out["dob"] = d
    # Positional fallback: on a PAN card the holder name, then the father's name, follow the PAN number.
    if "name" not in out:
        start = next((i for i, t in enumerate(lines) if pan and pan in t.replace(" ", "")), -1) + 1
        names = [canon_name(t) for t, s in zip(lines[start:], scores[start:]) if is_namelike(t, s)]
        if names:
            out["name"] = names[0]
            if "father_name" not in out and len(names) > 1:
                out["father_name"] = names[1]
    return out
