"""Small BM25 retriever over the product corpus. No embeddings, no tokens, fully deterministic.
Swap in pgvector later behind the same `search` signature."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_STOP = set("a an and are as at be by can do does for from how i if in is it me my of on or so that the this to was we what when where which who why will with you your should would could about".split())
CORPUS_DIR = Path(__file__).with_name("corpus")


@dataclass(frozen=True)
class Passage:
    id: str
    doc: str
    section: str
    text: str


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 1]


def _stem(t: str) -> str:
    for suf in ("ing", "es", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)]
    return t


def _terms(text: str) -> list[str]:
    return [_stem(t) for t in _tokens(text)]


@lru_cache
def _index():
    passages: list[Passage] = []
    for f in sorted(CORPUS_DIR.glob("*.md")):
        title, section, buf = f.stem.replace("_", " ").title(), "Overview", []
        for line in f.read_text().splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
            elif line.startswith("## "):
                if buf:
                    passages.append(Passage(f"{f.stem}#{len(passages)}", title, section, " ".join(buf).strip()))
                section, buf = line[3:].strip(), []
            elif line.strip():
                buf.append(line.strip())
        if buf:
            passages.append(Passage(f"{f.stem}#{len(passages)}", title, section, " ".join(buf).strip()))
    docs = [Counter(_terms(p.section + " " + p.section + " " + p.text)) for p in passages]  # section words weigh double
    df = Counter(t for d in docs for t in d)
    avg = sum(sum(d.values()) for d in docs) / max(len(docs), 1)
    return passages, docs, df, avg


def search(query: str, k: int = 3, min_score: float = 1.2, min_coverage: float = 0.5) -> list[tuple[Passage, float]]:
    """Returns passages that clear BOTH a relevance score and a query-coverage bar; otherwise nothing.
    Returning nothing is what lets the Guide refuse instead of improvising (citation-or-refuse)."""
    passages, docs, df, avg = _index()
    q = list(dict.fromkeys(_terms(query)))
    if not q:
        return []
    n, scored = len(passages), []
    for p, d in zip(passages, docs):
        length = sum(d.values())
        score = 0.0
        for t in q:
            if t in d:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * d[t] * 2.5 / (d[t] + 1.5 * (0.25 + 0.75 * length / avg))
        coverage = sum(1 for t in q if t in d) / len(q)
        if score >= min_score and coverage >= min_coverage:
            scored.append((p, score))
    return sorted(scored, key=lambda x: -x[1])[:k]
