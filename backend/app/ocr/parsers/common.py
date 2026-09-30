from __future__ import annotations

import re

DATE_RE = re.compile(r"\b(\d{2})[/\-.](\d{2})[/\-.](\d{4})\b")
# Labels that end a multi-line value such as an address.
STOP_LABELS = re.compile(
    r"^(name|dob|date of birth|d\.o\.b|valid|validity|issue|signature|blood|authori[sz]ed|dl no|"
    r"licen[cs]e|father|gender|sex|male|female|vid|download|help@|www\.)\b", re.I)


def norm_date(text: str) -> str | None:
    m = DATE_RE.search(text or "")
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else None


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip(" :-,")


def value_after(lines: list[str], label_re: str, multiline: bool = False) -> str | None:
    """Value for a printed label: text after 'Label:' on the same line, else the following line(s)."""
    pat = re.compile(rf"^(?:{label_re})\b\s*[:\-]?\s*(.*)$", re.I)
    for i, line in enumerate(lines):
        m = pat.match(line.strip())
        if not m:
            continue
        parts = [m.group(1).strip()] if m.group(1).strip() else []
        j = i + 1
        while j < len(lines) and (multiline or not parts):
            nxt = lines[j].strip()
            if not nxt or STOP_LABELS.match(nxt):
                break
            parts.append(nxt)
            j += 1
            if not multiline:
                break
        value = clean(" ".join(parts))
        return value or None
    return None
