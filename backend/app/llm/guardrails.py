"""Deterministic guardrails that run before any model: advice, approval prediction, prompt injection."""
from __future__ import annotations

import re

_ADVICE = re.compile(
    r"\b(invest(ment|ing)?|mutual funds?|stocks?|shares?|crypto|bitcoin|which (bank|fund|scheme|policy)|"
    r"should i (buy|sell|invest|take a loan)|best (scheme|fund|investment)|tax[- ]saving|insurance policy)\b", re.I)
_APPROVAL = re.compile(
    r"(will|would|can|could|am)\s+(i|my application|my account)\s+(be\s+|going to be\s+)?(get\s+)?(approved|accepted|rejected|declined)|"
    r"\bchances?\s+of\s+(approval|being approved|getting approved)|\b(likely|odds).{0,20}approv", re.I)
_INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions?|rules|prompts?)|"
    r"\b(system|developer)\s+prompt\b|\bjailbreak\b|\bact as\b.{0,30}\b(admin|analyst|reviewer)\b|"
    r"\b(approve|verify|mark)\b.{0,40}\b(my|this)\s+(application|account|case)\b", re.I)

REFUSALS = {
    "advice": ("I can't give investment or financial advice. A bank advisor can help with that. "
               "I'm happy to keep helping with your account application."),
    "approval_prediction": ("I can't predict whether an application will be approved. A human reviewer makes that decision "
                            "after checking your documents. I can help make sure your application is complete and clear."),
    "injection": ("I can't do that. I only help with opening your account, and approvals are always decided by a human reviewer."),
}


def detect(text: str) -> str | None:
    if not text:
        return None
    if _INJECTION.search(text):
        return "injection"
    if _APPROVAL.search(text):
        return "approval_prediction"
    if _ADVICE.search(text):
        return "advice"
    return None
