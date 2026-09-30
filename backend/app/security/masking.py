"""PII masking. Full identifiers live only in encrypted storage; state, prompts and logs get masked values."""
from __future__ import annotations

import re

_AADHAAR_RE = re.compile(r"\b(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})\b")
_PAN_RE = re.compile(r"\b([A-Z]{5})(\d{4})([A-Z])\b")
_ACCOUNT_RE = re.compile(r"\b\d{9,18}\b")


def mask_aadhaar(number: str) -> str:
    d = re.sub(r"\D", "", number)
    return f"XXXX XXXX {d[-4:]}" if len(d) == 12 else "XXXX XXXX XXXX"


def mask_pan(pan: str) -> str:
    return f"{pan[:5]}****{pan[-1]}" if len(pan) == 10 else "**********"


def mask_dl(number: str) -> str:
    n = re.sub(r"[\s-]", "", number)
    return f"{n[:4]}{'*' * max(len(n) - 8, 0)}{n[-4:]}" if len(n) >= 8 else "****"


def mask_field(key: str, value: str) -> str:
    if key == "aadhaar_number":
        return mask_aadhaar(value)
    if key == "pan_number":
        return mask_pan(value)
    if key == "dl_number":
        return mask_dl(value)
    return value


def redact_text(text: str) -> str:
    """Scrub identifiers from free text before it reaches an LLM prompt or a log line."""
    text = _AADHAAR_RE.sub(lambda m: f"XXXX XXXX {m.group(3)}", text)
    text = _PAN_RE.sub(lambda m: f"{m.group(1)}****{m.group(3)}", text)
    return _ACCOUNT_RE.sub("[REDACTED-NUMBER]", text)
