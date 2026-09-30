"""Runs one customer turn through the chat graph and persists the conversation.

The graph is rebuilt from the database each turn (source of truth), so a customer can close the tab and
resume exactly where they were.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import timedelta

from sqlalchemy import delete, select

from ..db import session_scope
from ..graphs.chat import get_chat_graph
from ..models import Case, Decision, Document, Message, ReviewRun, User, utcnow
from ..security.masking import redact_text
from . import audit
from .flow import next_step, progress
from .form_schema import DOC_LABELS, PRODUCTS

log = logging.getLogger("turns")
FRIENDLY_ERROR = "Sorry, something went wrong on my side. Your progress is saved. Please try again."


async def create_or_get_case(user: User) -> Case:
    async with session_scope() as s:
        cases = (await s.execute(select(Case).where(Case.user_id == user.id).order_by(Case.created_at.desc()))).scalars().all()
        for c in cases:
            if c.status not in ("approved", "rejected"):
                return c
        case = Case(user_id=user.id, product="basic_savings", status="draft", form={}, extracted={})
        s.add(case)
    await audit.record(f"user:{user.id}", "case.created", case.id, {"product": case.product})
    return case


async def reset_customer_data(user: User) -> None:
    """Demo helper: wipes the customer's cases so the demo can be rehearsed. The audit chain is kept."""
    async with session_scope() as s:
        ids = [c.id for c in (await s.execute(select(Case).where(Case.user_id == user.id))).scalars()]
        if ids:
            docs = (await s.execute(select(Document).where(Document.case_id.in_(ids)))).scalars().all()
            from . import storage
            for d in docs:
                storage.delete(d.storage_key)
            for model in (Message, Document, ReviewRun, Decision):
                await s.execute(delete(model).where(model.case_id.in_(ids)))
            await s.execute(delete(Case).where(Case.id.in_(ids)))
    await audit.record(f"user:{user.id}", "demo.reset", None, {})


async def case_view(case_id: str) -> dict:
    async with session_scope() as s:
        case = await s.get(Case, case_id)
        msgs = (await s.execute(select(Message).where(Message.case_id == case_id).order_by(Message.created_at, Message.id))).scalars().all()
        docs = (await s.execute(select(Document).where(Document.case_id == case_id))).scalars().all()
    uploaded = {d.doc_type for d in docs}
    step = next_step(case.product, uploaded, case.extracted, case.form)
    return {
        "id": case.id, "status": case.status, "product": case.product,
        "product_name": PRODUCTS[case.product]["name"], "submission_no": case.submission_no,
        "progress": progress(case.product, uploaded, case.extracted, case.form, case.status),
        "next_step": step,
        "documents": [{"id": d.id, "doc_type": d.doc_type, "label": DOC_LABELS[d.doc_type],
                       "fields": d.summary.get("fields", []), "missing": d.summary.get("missing", [])} for d in docs],
        "messages": [{"id": m.id, "role": m.role, "text": m.text, "ui": m.ui,
                      "trace": (m.meta or {}).get("trace"), "created_at": m.created_at.isoformat() + "Z"} for m in msgs],
    }


async def _load_state(case_id: str, user: User) -> tuple[dict, int]:
    async with session_scope() as s:
        case = await s.get(Case, case_id)
        docs = (await s.execute(select(Document.doc_type).where(Document.case_id == case_id))).scalars().all()
        count = len((await s.execute(select(Message.id).where(Message.case_id == case_id))).scalars().all())
    return {"case_id": case.id, "user_id": user.id, "user_name": user.name, "product": case.product,
            "status": case.status, "form": dict(case.form or {}), "extracted": dict(case.extracted or {}),
            "uploaded": sorted(set(docs))}, count


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": data}


async def run_turn(user: User, case_id: str, *, text: str | None = None, action: dict | None = None,
                   upload: dict | None = None) -> AsyncIterator[dict]:
    state, message_count = await _load_state(case_id, user)
    if (action or {}).get("type") == "start" and message_count:
        yield _sse("state", await case_view(case_id))
        return  # the conversation already started: never greet twice

    label = DOC_LABELS[upload["doc_type"]] if upload else None
    init = {**state, "text": text, "action": action, "pending_upload": upload,
            "user_display": f"Uploaded {label}" if upload else (redact_text(text or "")),
            "user_ui": {"type": "upload_ack", "doc_type": upload["doc_type"]} if upload else None,
            "replies": [], "trace": [], "upload_feedback": [], "gate_errors": []}
    t0 = utcnow()
    replies, trace, user_display = [], [], init["user_display"]
    try:
        async for chunk in get_chat_graph().astream(init, stream_mode="updates"):
            for node, update in (chunk or {}).items():
                update = update or {}
                for t in update.get("trace", []):
                    trace.append(t)
                    yield _sse("node", t)
                replies += update.get("replies", [])
                user_display = update.get("user_display", user_display) or user_display
    except Exception:  # noqa: BLE001
        log.exception("turn failed for case %s", case_id)
        await audit.record("system", "turn.failed", case_id, {})
        yield _sse("error", {"message": FRIENDLY_ERROR})
        return

    async with session_scope() as s:
        if (action or {}).get("type") != "start" and (text or action or upload):
            s.add(Message(case_id=case_id, role="user", text=user_display or "(no text)", ui=init["user_ui"], created_at=t0))
        for i, r in enumerate(replies):
            s.add(Message(case_id=case_id, role="assistant", text=r["text"], ui=r.get("ui"),
                          meta={"trace": trace} if i == len(replies) - 1 else None,
                          created_at=t0 + timedelta(milliseconds=i + 1)))
    yield _sse("state", await case_view(case_id))
