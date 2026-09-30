from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..rag.retriever import Passage

INTENTS = ("product_qa", "intake", "submit", "out_of_scope")


@dataclass
class GuideAnswer:
    text: str
    used_ids: list[str] = field(default_factory=list)


class LLMService(Protocol):
    name: str

    async def classify_intent(self, text: str, context: dict) -> str: ...
    async def answer(self, question: str, passages: list[Passage]) -> GuideAnswer: ...
    async def parse_field(self, field_key: str, choices: list[str], text: str) -> str | None: ...
    async def fallback_extract(self, doc_type: str, raw_text: str, missing: list[str]) -> dict[str, str]: ...
    async def summarize_review(self, payload: dict) -> str: ...
