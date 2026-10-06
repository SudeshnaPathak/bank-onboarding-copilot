from __future__ import annotations

import asyncio
import logging

from ..config import get_settings
from . import stats
from .base import LLMService
from .rule_based import RuleBasedLLM

log = logging.getLogger("llm")


class ResilientLLM:
    """Primary model with timeout, falling back to the deterministic service on ANY failure.
    The application keeps working (degraded but correct) when the model is down or rate-limited."""

    def __init__(self, primary: LLMService, fallback: LLMService):
        self.primary, self.fallback = primary, fallback
        self.name = f"{primary.name}+fallback"

    async def _call(self, method: str, *args):
        try:
            return await asyncio.wait_for(getattr(self.primary, method)(*args), timeout=45)
        except Exception as exc:  # noqa: BLE001
            stats.record_failure(method)
            log.warning("LLM %s failed (%s); using rule-based fallback", method, type(exc).__name__)
            return await getattr(self.fallback, method)(*args)

    async def classify_intent(self, text, context): return await self._call("classify_intent", text, context)
    async def answer(self, question, passages): return await self._call("answer", question, passages)
    async def parse_field(self, field_key, choices, text): return await self._call("parse_field", field_key, choices, text)
    async def fallback_extract(self, doc_type, raw_text, missing): return await self._call("fallback_extract", doc_type, raw_text, missing)
    async def summarize_review(self, payload): return await self._call("summarize_review", payload)


_llm: LLMService | None = None


def get_llm() -> LLMService:
    global _llm
    if _llm is None:
        s = get_settings()
        use_gemini = s.llm_provider == "gemini" or (s.llm_provider == "auto" and s.aipg_api_key)
        if use_gemini and s.aipg_api_key:
            from .gemini import GeminiLLM
            _llm = ResilientLLM(
                GeminiLLM(s.aipg_api_key, s.gemini_model, s.gemini_router_model, s.aipg_base_url),
                RuleBasedLLM(),
            )
        else:
            _llm = RuleBasedLLM()
        log.info("LLM service active: %s", _llm.name)
    return _llm


def set_llm(llm: LLMService | None) -> None:
    global _llm
    _llm = llm

async def close_llm() -> None:
    """Call from your app's shutdown hook so the HTTP client closes cleanly."""
    primary = getattr(_llm, "primary", None)
    close = getattr(primary, "close", None)
    if close is not None:
        await close()
