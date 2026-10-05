"""Layout-tolerant helpers shared by the PAN, Aadhaar and driving-licence parsers.

Why this exists: real Indian ID cards are bilingual ("<Hindi> / <English>"), photographed with QR-code noise,
and laid out in columns, so OCR lines arrive garbled and out of order. The old approach of 'take the line after
the label' breaks on all three. These helpers instead:
  1. reduce every line to its English part (drops Hindi / garbage left of ' / ', drops non-ASCII),
  2. pair labels with values by TYPE (a date label only accepts a date), using a queue so both
     row-major ("Issue, Validity, <d1>, <d2>") and column-major ("Issue, <d1>, Validity, <d2>") orders work,
  3. skip junk lines (QR noise, endorsement numbers) when collecting multi-line addresses.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

DATE_RE = re.compile(r"(?<!\d)(\d{2})[/\-.](\d{2})[/\-.](\d{4})(?!\d)")
PIN_RE = re.compile(r"(?<!\d)\d{6}(?!\d)")
AADHAAR_LINE_RE = re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)")

_ASCII_MAP = str.maketrans({"\u2019": "'", "\u2018": "'", "\u00b4": "'", "`": "'", "\u201c": '"', "\u201d": '"',
                            "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00a0": " "})

HEADER_WORDS = {
    "income", "tax", "department", "govt", "government", "india", "indian", "permanent", "account", "number", "card",
    "signature", "licence", "license", "driving", "union", "authority", "unique", "identification", "aadhaar",
    "address", "date", "birth", "blood", "group", "validity", "issue", "issued", "father", "name", "mobile",
    "endorsement", "holder", "holders", "issuing", "valid", "copy", "reference", "only", "male", "female",
    "transgender", "year", "dob", "yob", "main", "of", "the", "front", "side",
}


def english_part(line: str) -> str:
    """'<Hindi or OCR garbage> / <English>'  ->  '<English>'. Also strips non-ASCII and stray symbols."""
    s = unicodedata.normalize("NFKC", line or "").translate(_ASCII_MAP).strip()
    if not PIN_RE.search(s):  # an address line with a PIN is not bilingual
        parts = re.split(r"\s+/\s+|\s+/$|^/\s+", s)
        if len(parts) > 1:
            s = parts[-1]
    s = re.sub(r"[^\x00-\x7F]+", " ", s)
    s = re.sub(r"[|~_=\u00ab\u00bb*]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" /\"'")


def prepare(lines: list[str], scores: list[float] | None = None) -> tuple[list[str], list[float]]:
    """English-only lines (empty ones dropped) with their OCR scores kept aligned."""
    scores = scores or [1.0] * len(lines)
    out, out_scores = [], []
    for text, sc in zip(lines, scores):
        e = english_part(text)
        if e:
            out.append(e)
            out_scores.append(sc)
    return out, out_scores


# ---------------------------------------------------------------- value helpers
def norm_date(text: str) -> str | None:
    m = DATE_RE.search(text or "")
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else None


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip(" :-,;")


def canon_name(text: str) -> str:
    """Single canonical spelling/case so 'PRIYA SHARMA' and 'Priya Sharma' are the same value everywhere."""
    t = re.sub(r"[^A-Za-z .'-]", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip(" .-'")
    return t.title() if (t.isupper() or t.islower()) else t


def is_namelike(text: str, score: float | None = None, min_score: float = 0.4) -> bool:
    """A printed person name: 2+ capitalised alphabetic tokens, no digits, not a header/label phrase."""
    if score is not None and score < min_score:
        return False
    if re.search(r"[\d:@/]", text):
        return False
    tokens = re.findall(r"[A-Za-z][A-Za-z.'-]*", text)
    if len(tokens) < 2 or len(tokens) > 6:
        return False
    if any(t.lower().strip(".'-") in HEADER_WORDS for t in tokens):
        return False
    return all(t[0].isupper() for t in tokens)  # Hindi-OCR garbage ("far raf") is lowercase


def is_address_like(text: str, score: float | None = None) -> bool:
    if score is not None and score < 0.5:
        return False
    if not re.search(r"[A-Za-z0-9]", text):
        return False
    if " " not in text.strip():  # single token: endorsement codes, QR noise, '1947'...
        return bool(PIN_RE.search(text)) or text.strip().endswith(",")
    alpha = [t for t in re.findall(r"[A-Za-z]+", text) if len(t) >= 3]
    has_digit = bool(re.search(r"\d", text))
    return (has_digit and len(alpha) >= 1) or len(alpha) >= 2


# ---------------------------------------------------------------- label / value pairing
@dataclass(frozen=True)
class Label:
    key: str
    pattern: str
    kind: str  # date | dob | name | ignore


def _compile(label: Label) -> re.Pattern:
    return re.compile(rf"^(?:{label.pattern})(?=\s|[:\-]|$)\s*(?:[:\-]\s*)?(?P<v>.*)$", re.I)


def _accepts(kind: str, text: str, score: float | None) -> str | None:
    """Returns the normalised value if `text` is a valid value for this kind of label."""
    if kind == "date":
        return norm_date(text)
    if kind == "dob":
        return norm_date(text) or (m.group(0) if (m := re.fullmatch(r"(?:19|20)\d{2}", text.strip())) else None)
    if kind == "name":
        return canon_name(text) if is_namelike(text, score) else None
    return None


def extract_labeled(lines: list[str], scores: list[float], labels: list[Label], expiry: int = 8) -> dict[str, str]:
    """Pair labels with values by type using a FIFO queue. Noise lines are skipped; a pending label expires
    after `expiry` lines so a missing value cannot swallow an unrelated one later in the document."""
    compiled = [(l, _compile(l)) for l in labels]
    out: dict[str, str] = {}
    pending: list[tuple[Label, int]] = []  # (label, line index where it appeared)
    for i, text in enumerate(lines):
        hit = next(((l, m) for l, p in compiled if (m := p.match(text))), None)
        pending = [(l, at) for l, at in pending if i - at <= expiry]
        if hit:
            label, m = hit
            if label.kind == "ignore":
                continue
            inline = _accepts(label.kind, m.group("v"), scores[i]) if m.group("v").strip() else None
            if inline:
                out.setdefault(label.key, inline)
            elif label.key not in out:
                pending = [(l, at) for l, at in pending if l.key != label.key] + [(label, i)]
            continue
        for j, (label, _) in enumerate(pending):  # earliest pending label this line can satisfy
            if (value := _accepts(label.kind, text, scores[i])) is not None:
                out.setdefault(label.key, value)
                pending.pop(j)
                break
    return out


# ---------------------------------------------------------------- multi-line address
_ADDR_STOP = re.compile(
    r"^(valid\s+only|this\s+is\s+a|holder|issuing|signature|form\s*\d|mobile|endorsement|date\s+of|blood|name\b|"
    r"father|dob|validity|support|www\.|help)", re.I)


def collect_address(lines: list[str], scores: list[float], start: int, end: int | None = None, max_lines: int = 6) -> str | None:
    """Lines from `start` while they look like an address. Skips junk, ends at a stop phrase, and after the PIN
    line allows one trailing state/country line (e.g. 'Delhi, India.')."""
    end = len(lines) if end is None else end
    got: list[str] = []
    after_pin = False
    for k in range(start, end):
        text, sc = lines[k], scores[k]
        if _ADDR_STOP.match(text) or (got and AADHAAR_LINE_RE.fullmatch(text.strip())):
            break
        if after_pin:
            if re.fullmatch(r"[A-Za-z ,.]+", text) and is_address_like(text, sc):
                got.append(text)
            break
        if not is_address_like(text, sc):
            continue
        got.append(text)
        if PIN_RE.search(text):
            after_pin = True
        if len(got) >= max_lines:
            break
    if not got:
        return None
    return clean(", ".join(g.strip(" ,.;") for g in got)) or None


def find_label_index(lines: list[str], pattern: str) -> int | None:
    pat = re.compile(rf"^(?:{pattern})(?=\s|[:\-]|$)", re.I)
    for i, t in enumerate(lines):
        if pat.match(t):
            return i
    return None
