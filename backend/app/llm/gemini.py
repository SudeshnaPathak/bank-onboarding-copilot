"""Gemini via AI Passport Gateway (OpenAI-compatible endpoint, US production by default)."""
from __future__ import annotations

import json
from pathlib import Path

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

from ..rag.retriever import Passage
from . import stats
from .base import INTENTS, GuideAnswer

DEFAULT_BASE_URL = "https://openai.generative.engine.capgemini.com/v1"
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


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return text.strip()


def _usage(resp) -> dict | None:
    # Mapped to the LangChain usage_metadata shape; adjust to whatever stats.record_call expects.
    u = getattr(resp, "usage", None)
    if u is None:
        return None
    return {
        "input_tokens": u.prompt_tokens,
        "output_tokens": u.completion_tokens,
        "total_tokens": u.total_tokens,
    }


class GeminiLLM:
    name = "gemini"

    def __init__(self, api_key: str, model: str, router_model: str = "",
                 base_url: str = DEFAULT_BASE_URL):
        # Same timeout and retry budget as your previous LangChain client.
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key,
                                   timeout=30.0, max_retries=2)
        self.model = model
        self.router_model = router_model or model

    async def close(self) -> None:
        await self._client.close()

    async def _complete(self, model: str, system: str, human: str, max_tokens: int = 1024):
        return await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": human},
            ],
            max_completion_tokens=max_tokens,
            temperature=0,  # not documented for this endpoint; remove if the gateway rejects it
        )

    async def _run(self, model: str, schema, prompt_name: str, human: str):
        system, _ = load_prompt(prompt_name)
        system += (
            "\n\nRespond with ONLY a JSON object that matches this JSON Schema. "
            "No prose, no code fences:\n" + json.dumps(schema.model_json_schema())
        )
        resp = await self._complete(model, system, human)
        stats.record_call(prompt_name, _usage(resp))
        text = _strip_fences(resp.choices[0].message.content or "")
        try:
            return schema.model_validate_json(text)
        except ValidationError as exc:
            raise ValueError(f"unparseable model output for {prompt_name}") from exc

    async def classify_intent(self, text: str, context: dict) -> str:
        res = await self._run(self.router_model, IntentOut, "router",
                              f"Current step: {context.get('step')}\n<customer_message>{text}</customer_message>")
        if res.intent not in INTENTS:
            raise ValueError("bad intent")
        return res.intent

    async def answer(self, question: str, passages: list[Passage]) -> GuideAnswer:
        ctx = "\n".join(f"[{p.id}] ({p.doc} / {p.section}) {p.text}" for p in passages)
        res = await self._run(self.model, GuideOut, "guide",
                              f"Passages:\n{ctx}\n\n<question>{question}</question>")
        valid = {p.id for p in passages}
        used = [i for i in res.used_ids if i in valid]
        if not used:
            raise ValueError("answer cites no retrieved passage")  # ungrounded -> fall back
        return GuideAnswer(res.answer, used)

    async def parse_field(self, field_key: str, choices: list[str], text: str) -> str | None:
        res = await self._run(self.router_model, FieldOut, "parse_field",
                              f"Field: {field_key}\nAllowed: {choices}\n<message>{text}</message>")
        return res.value if res.value in choices else None

    async def fallback_extract(self, doc_type: str, raw_text: str, missing: list[str]) -> dict[str, str]:
        res = await self._run(self.model, ExtractOut, "extract",
                              f"Document type: {doc_type}\nFields to extract: {missing}\n<ocr_text>\n{raw_text}\n</ocr_text>")
        return {k: v for k, v in res.fields.items() if v and k in missing}

    async def summarize_review(self, payload: dict) -> str:
        resp = await self._complete(self.model, load_prompt("review_summary")[0], json.dumps(payload))
        stats.record_call("review_summary", _usage(resp))
        return (resp.choices[0].message.content or "").strip()