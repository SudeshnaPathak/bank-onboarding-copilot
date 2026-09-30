"""Lightweight LLM usage counters for the cost story (/health/llm). Tokens come from provider metadata."""
from __future__ import annotations

from collections import defaultdict

_calls: dict[str, int] = defaultdict(int)
_tokens = {"input": 0, "output": 0}
_failures: dict[str, int] = defaultdict(int)
_fallbacks = 0


def record_call(tag: str, usage: dict | None) -> None:
    _calls[tag] += 1
    if usage:
        _tokens["input"] += int(usage.get("input_tokens", 0) or 0)
        _tokens["output"] += int(usage.get("output_tokens", 0) or 0)


def record_failure(tag: str) -> None:
    global _fallbacks
    _failures[tag] += 1
    _fallbacks += 1


def snapshot() -> dict:
    return {"calls": dict(_calls), "tokens": dict(_tokens), "failures": dict(_failures), "fallbacks_to_rules": _fallbacks}


def reset() -> None:
    global _fallbacks
    _calls.clear(); _failures.clear(); _tokens.update(input=0, output=0); _fallbacks = 0
