"""Deterministic LLMService. Powers offline demos, tests, and is the graceful-degradation path when Gemini fails."""
from __future__ import annotations

import re

from ..rag.retriever import Passage
from . import guardrails
from .base import GuideAnswer

_QUESTION_START = re.compile(r"^(what|why|how|who|when|where|which|can|could|do|does|is|are|will|should|tell me|explain)\b", re.I)
_SUBMIT = re.compile(r"^(submit|submit (my )?application|i'?m done|done|finish|send it|go ahead and submit)\W*$", re.I)
_OCCUPATION = {
    "Salaried": ("salaried", "employee", "job", "work for", "works at", "software", "engineer", "teacher", "doctor", "company", "it "),
    "Self-employed": ("self", "business", "freelanc", "own a", "shop", "consultant", "entrepreneur"),
    "Student": ("student", "college", "school", "studying", "university"),
    "Homemaker": ("homemaker", "housewife", "house wife", "home maker"),
    "Retired": ("retired", "pension"),
}
BAND_LABEL = {"clean": "no inconsistencies found", "review": "needs a closer look", "attention": "needs careful review"}


class RuleBasedLLM:
    name = "rules"

    async def classify_intent(self, text: str, context: dict) -> str:
        if guardrails.detect(text):
            return "out_of_scope"
        t = (text or "").strip()
        if _SUBMIT.match(t):
            return "submit"
        if "?" in t or _QUESTION_START.match(t):
            # a question about the current field ("why do you need my mobile?") is still a product question
            return "product_qa"
        return "intake"

    async def answer(self, question: str, passages: list[Passage]) -> GuideAnswer:
        top = passages[0]
        sentences = re.split(r"(?<=[.!?])\s+", top.text)
        return GuideAnswer(" ".join(sentences[:3]), [top.id])

    async def parse_field(self, field_key: str, choices: list[str], text: str) -> str | None:
        low = (text or "").lower()
        for choice in choices:
            if choice.lower() in low:
                return choice
        if field_key == "occupation":
            for choice, keys in _OCCUPATION.items():
                if any(k in low for k in keys):
                    return choice
        return None

    async def fallback_extract(self, doc_type: str, raw_text: str, missing: list[str]) -> dict[str, str]:
        return {}

    async def summarize_review(self, payload: dict) -> str:
        flags, score, band = payload["flags"], payload["score"], payload["band"]
        head = f"Consistency score {score}/100 ({BAND_LABEL[band]})."
        if not flags:
            return f"{head} No inconsistencies were found across the submitted documents. A human reviewer makes the final decision."
        lines = []
        for i, f in enumerate(flags, 1):
            note = " The customer confirmed this during the chat." if f.get("confirmed_by_customer") else ""
            lines.append(f"{i}. {f['title']} ({f['severity']}): {f['message']}{note}")
        return f"{head} {len(flags)} item(s) raised by the rules:\n" + "\n".join(lines) + "\nA human reviewer makes the final decision."
