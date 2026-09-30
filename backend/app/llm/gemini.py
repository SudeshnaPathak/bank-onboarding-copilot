"""Gemini-backed LLMService via LangChain structured output.

NOTE: written against langchain-google-genai's public API but not executed in the sandbox this repo was
built in (no API key). ResilientLLM wraps every call, so any failure degrades to the rule-based service.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..rag.retriever import Passage
from . import stats
from .base import INTENTS, GuideAnswer

_PROMPT_DIR = Path(__file__).with_name("prompts")


def load_prompt(name: str) -> tuple[str, str]:
    raw = (_PROMPT_DIR / f"{name}.md").read_text()
    version = raw.split("version:")[1].split("-->")[0].strip() if "version:" in raw else "0"
    return raw.split("-->", 1)[-1].strip(), version


def prompt_versions() -> dict[str, str]:
    return {p.stem: load_prompt(p.stem)[1] for p in _PROMPT_DIR.glob("*.md")}


class IntentOut(BaseModel):
    intent: str = Field(description=f"one of {INTENTS}")


class GuideOut(BaseModel):
    answer: str
    used_ids: list[str]


class FieldOut(BaseModel):
    value: str | None = None


class ExtractOut(BaseModel):
    fields: dict[str, str | None]


class GeminiLLM:
    name = "gemini"

    def __init__(self, api_key: str, model: str, router_model: str = ""):
        from langchain_google_genai import ChatGoogleGenerativeAI

        kw = dict(google_api_key=api_key, temperature=0, max_retries=2, timeout=30)
        self._chat = ChatGoogleGenerativeAI(model=model, **kw)
        self._router = ChatGoogleGenerativeAI(model=router_model or model, **kw)
        self.model = model

    async def _run(self, chat, schema, prompt_name: str, human: str):
        from langchain_core.messages import HumanMessage, SystemMessage

        system, _ = load_prompt(prompt_name)
        out = await chat.with_structured_output(schema, include_raw=True).ainvoke(
            [SystemMessage(content=system), HumanMessage(content=human)])
        raw = out.get("raw")
        stats.record_call(prompt_name, getattr(raw, "usage_metadata", None))
        if out.get("parsed") is None:
            raise ValueError(f"unparseable model output for {prompt_name}")
        return out["parsed"]

    async def classify_intent(self, text: str, context: dict) -> str:
        res = await self._run(self._router, IntentOut, "router",
                              f"Current step: {context.get('step')}\n<customer_message>{text}</customer_message>")
        if res.intent not in INTENTS:
            raise ValueError("bad intent")
        return res.intent

    async def answer(self, question: str, passages: list[Passage]) -> GuideAnswer:
        ctx = "\n".join(f"[{p.id}] ({p.doc} / {p.section}) {p.text}" for p in passages)
        res = await self._run(self._chat, GuideOut, "guide", f"Passages:\n{ctx}\n\n<question>{question}</question>")
        valid = {p.id for p in passages}
        used = [i for i in res.used_ids if i in valid]
        if not used:
            raise ValueError("answer cites no retrieved passage")  # ungrounded -> fall back to extractive
        return GuideAnswer(res.answer, used)

    async def parse_field(self, field_key: str, choices: list[str], text: str) -> str | None:
        res = await self._run(self._router, FieldOut, "parse_field",
                              f"Field: {field_key}\nAllowed: {choices}\n<message>{text}</message>")
        return res.value if res.value in choices else None

    async def fallback_extract(self, doc_type: str, raw_text: str, missing: list[str]) -> dict[str, str]:
        res = await self._run(self._chat, ExtractOut, "extract",
                              f"Document type: {doc_type}\nFields to extract: {missing}\n<ocr_text>\n{raw_text}\n</ocr_text>")
        return {k: v for k, v in res.fields.items() if v and k in missing}

    async def summarize_review(self, payload: dict) -> str:
        import json
        res = await self._chat.ainvoke([("system", load_prompt("review_summary")[0]), ("human", json.dumps(payload))])
        stats.record_call("review_summary", getattr(res, "usage_metadata", None))
        return str(res.content).strip()
