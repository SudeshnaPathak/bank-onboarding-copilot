"""Deterministic OCR helpers: checksums, OCR-confusion repair, per-field confidence."""
from __future__ import annotations

import unicodedata

import re

_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_valid(number: str) -> bool:
    if not number.isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(base: str) -> str:
    """Used by the synthetic-document generator to mint checksum-valid demo Aadhaar numbers."""
    c = 0
    for i, ch in enumerate(reversed(base)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def valid_aadhaar(number: str) -> bool:
    d = re.sub(r"\s", "", number)
    return len(d) == 12 and d[0] not in "01" and verhoeff_valid(d)


PAN_RE = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
_TO_LETTER = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"}
_TO_DIGIT = {"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2", "G": "6", "D": "0"}


def repair_pan(token: str) -> str | None:
    """Fix positional OCR confusions (O/0, I/1, S/5, B/8...) then validate the PAN layout."""
    tok = re.sub(r"[^A-Z0-9]", "", token.upper())
    if len(tok) != 10:
        return None
    out = "".join((_TO_LETTER if (i < 5 or i == 9) else _TO_DIGIT).get(c, c) for i, c in enumerate(tok))
    return out if PAN_RE.fullmatch(out) else None


def find_pan(text: str) -> str | None:
    for line in text.splitlines():
        cleaned = re.sub(r"[^A-Za-z0-9]", "", line)
        if len(cleaned) < 10:
            continue
        for start in range(0, len(cleaned) - 9):
            hit = repair_pan(cleaned[start:start + 10])
            if hit:
                return hit
    return None


def _tok(text: str) -> set[str]:
    return set(re.findall(r"[A-Z0-9]+", text.upper()))


def field_confidence(value: str, lines: list[tuple[str, float]]) -> float | None:
    """Weakest OCR score among the lines that contain this value's tokens."""
    vt = _tok(value)
    compact = re.sub(r"[^A-Z0-9]", "", value.upper())
    scores = [
        s for text, s in lines
        if vt & _tok(text) or (len(compact) >= 6 and compact in re.sub(r"[^A-Z0-9]", "", text.upper()))
    ]  # the compact form handles numbers printed in groups, e.g. "2345 6789 0124"
    return round(min(scores), 3) if scores else None


_PUNCT = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u02bc": "'", "\u0060": "'", "\u00b4": "'",   # curly / modifier apostrophes
    "\u201c": '"', "\u201d": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-",  # dashes, minus
    "\u00a0": " ", "\u2009": " ", "\u202f": " ",                                    # non-breaking / thin spaces
    "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "", "\u00ad": "",           # zero-width, soft hyphen
})


def normalize_text(text: str) -> str:
    """Make text-layer and OCR output look the same to the parsers: NFKC (ligatures, full-width forms) plus
    typographic quotes, dashes and odd spaces folded to ASCII. Real PDFs use \u2019 in "Father\u2019s Name"."""
    return unicodedata.normalize("NFKC", text).translate(_PUNCT)
