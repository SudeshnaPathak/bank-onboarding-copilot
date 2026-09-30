from __future__ import annotations

from ..llm import guardrails
from ..llm.factory import get_llm
from ..rag.retriever import search

NO_ANSWER = ("I don't have that in my product notes, and I'd rather not guess. "
             "A bank advisor can help with that. Meanwhile, I'm happy to keep going with your application.")


async def guide_node(state: dict) -> dict:
    """Citation-or-refuse: answers only from retrieved passages; otherwise says so."""
    text = (state.get("text") or "").strip()
    if kind := guardrails.detect(text):
        return {"passive": True, "replies": [{"text": guardrails.REFUSALS[kind], "ui": None}],
                "trace": [{"node": "guide", "detail": f"refused ({kind})"}]}
    hits = search(text)
    if not hits:
        return {"passive": True, "replies": [{"text": NO_ANSWER, "ui": None}],
                "trace": [{"node": "guide", "detail": "no grounded passage, declined to answer"}]}
    passages = [p for p, _ in hits]
    answer = await get_llm().answer(text, passages)
    cited = [p for p in passages if p.id in answer.used_ids] or passages[:1]
    ui = {"type": "citations", "items": [{"title": p.doc, "section": p.section} for p in cited]}
    return {"passive": True, "replies": [{"text": answer.text, "ui": ui}],
            "trace": [{"node": "guide", "detail": f"answered from {len(cited)} passage(s) via {get_llm().name}"}]}
