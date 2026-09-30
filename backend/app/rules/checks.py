from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from .matchers import dobs_compatible, name_tokens, parse_date

_DL_RE = re.compile(r"^[A-Z]{2}\d{2}\d{4}\d{7}$")


def normalize_dl(number: str) -> str:
    return re.sub(r"[\s-]", "", (number or "").upper())


def dl_number_valid(number: str) -> bool:
    """State code + RTO code + year + 7-digit serial. Very old licences may use other layouts."""
    return bool(_DL_RE.fullmatch(normalize_dl(number)))


def expiry_status(valid_till: str, today: date, soon_days: int = 90) -> tuple[str, int | None]:
    d = parse_date(valid_till)
    if d is None:
        return "unknown", None
    days = (d - today).days
    if days < 0:
        return "expired", days
    return ("expiring_soon" if days <= soon_days else "valid"), days


def age_years(dob: str, today: date) -> int | None:
    d = parse_date(dob)
    if d is None:
        return None
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


@lru_cache
def _watchlist() -> list[dict]:
    path = Path(__file__).with_name("watchlist.json")
    return json.loads(path.read_text())["entries"]


def watchlist_screen(name: str, dob: str | None, min_ratio: int = 90) -> list[dict]:
    """Fuzzy name screen. Returns candidates with context; a human decides. Never auto-rejects."""
    norm = " ".join(sorted(name_tokens(name)))
    hits = []
    for e in _watchlist():
        ratio = int(fuzz.token_sort_ratio(norm, " ".join(sorted(name_tokens(e["name"])))))
        if ratio >= min_ratio:
            dob_match = None if not (e.get("dob") and dob) else dobs_compatible(e["dob"], dob)
            hits.append({"list": e["list"], "matched_name": e["name"], "ratio": ratio,
                         "dob_match": dob_match, "reason": e.get("reason", "")})
    return hits
