"""Intake node: runs the intake logic, then persists the form and records audit events."""
from __future__ import annotations

from ..db import session_scope
from ..llm.factory import get_llm
from ..models import Case
from ..services import audit
from .intake_logic import EDITABLE, STATUS_TEXT, intake_core  # noqa: F401  (re-exported)


async def intake_node(state: dict) -> dict:
    out = await intake_core(state, get_llm())
    async with session_scope() as s:
        case = await s.get(Case, state["case_id"])
        case.form, case.extracted = out["form"], state["extracted"]
    for action, details in out.pop("events", []):
        await audit.record(f"user:{state['user_id']}", action, state["case_id"], details)
    return out
