"""Deterministic matching for names, dates of birth and addresses. No LLM involved."""
from __future__ import annotations

import re
from datetime import date

from rapidfuzz import fuzz

_TITLES = {"MR", "MRS", "MS", "MISS", "SMT", "SHRI", "SRI", "DR", "KUMARI"}
_ABBR = {"rd": "road", "st": "street", "apt": "apartment", "apts": "apartment", "ln": "lane",
         "blk": "block", "sec": "sector", "nr": "near", "opp": "opposite", "flr": "floor",
         "bldg": "building", "hno": "house", "no": "number", "ave": "avenue"}


def name_tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z]+", text.upper()) if t not in _TITLES]


def names_compatible(a: str, b: str) -> bool:
    """Order-insensitive; a single-letter initial matches any token starting with it."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return all(any(t == u or (len(t) == 1 and u.startswith(t)) for u in long_) for t in short)


def parse_date(value: str) -> date | None:
    m = re.fullmatch(r"\s*(\d{2})[/\-.](\d{2})[/\-.](\d{4})\s*", value or "")
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.fullmatch(r"\s*(\d{4})-(\d{2})-(\d{2})\s*", value or "")
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _dob_parts(value: str) -> tuple[str | None, str]:
    d = parse_date(value)
    if d:
        return f"{d.day:02d}/{d.month:02d}", str(d.year)
    return None, (value or "").strip()  # year-only (some Aadhaar cards print just the year)


def dobs_compatible(a: str, b: str) -> bool:
    (da, ya), (db, yb) = _dob_parts(a), _dob_parts(b)
    return ya == yb and (da is None or db is None or da == db)


def normalize_address(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"\b(c/o|s/o|d/o|w/o)\b[^,]*,?", " ", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return " ".join(_ABBR.get(w, w) for w in t.split())


def pin_of(text: str) -> str | None:
    found = re.findall(r"\b(\d{6})\b", text or "")
    return found[-1] if found else None


def address_similarity(a: str, b: str) -> int:
    """0-100. Different PIN codes cap the score: a fuzzy match must not paper over a different area."""
    score = int(fuzz.token_set_ratio(normalize_address(a), normalize_address(b)))
    pa, pb = pin_of(a), pin_of(b)
    if pa and pb and pa != pb:
        score = min(score, 60)
    return score


def compatible(field: str, a: str, b: str, address_ratio: int = 80) -> bool:
    if field == "name":
        return names_compatible(a, b)
    if field == "dob":
        return dobs_compatible(a, b)
    if field == "address":
        return address_similarity(a, b) >= address_ratio
    return a.strip().upper() == b.strip().upper()


def canonical_name(text: str) -> str:
    t = re.sub(r"[^A-Za-z .'-]", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip(" .-'")
    return t.title() if (t.isupper() or t.islower()) else t


def same_value(field: str, a: str, b: str) -> bool:
    if field == "name":
        return names_compatible(a, b)
    return re.sub(r"\s+", " ", (a or "").strip()).casefold() == re.sub(r"\s+", " ", (b or "").strip()).casefold()


def dob_plausible(dob: str, today: date) -> bool:
    if re.fullmatch(r"\s*(19|20)\d{2}\s*", dob or ""):
        return today.year - int(dob) <= 110
    d = parse_date(dob)
    if d is None:
        return False
    age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return 0 <= age <= 110