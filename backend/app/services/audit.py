"""Append-only, hash-chained audit log. Each row commits to the previous row's hash, so any edit or
deletion breaks verification. On Postgres also apply db/immutability.sql to block UPDATE/DELETE."""
from __future__ import annotations

import asyncio
import hashlib
import json

from sqlalchemy import select

from ..db import session_scope
from ..models import AuditLog, utcnow

_lock = asyncio.Lock()
GENESIS = "0" * 64


def _digest(prev: str, ts, actor: str, action: str, case_id, details: dict) -> str:
    body = json.dumps({"prev": prev, "ts": ts.isoformat(), "actor": actor, "action": action,
                       "case_id": case_id, "details": details}, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


async def record(actor: str, action: str, case_id: str | None = None, details: dict | None = None) -> None:
    """Independent short transaction, so a failure elsewhere can never erase the record of what happened."""
    details = json.loads(json.dumps(details or {}, default=str))
    async with _lock:
        async with session_scope() as s:
            last = (await s.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))).scalar_one_or_none()
            prev = last.hash if last else GENESIS
            ts = utcnow().replace(microsecond=0)
            s.add(AuditLog(ts=ts, actor=actor, action=action, case_id=case_id, details=details,
                           prev_hash=prev, hash=_digest(prev, ts, actor, action, case_id, details)))


async def verify_chain() -> dict:
    async with session_scope() as s:
        rows = (await s.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    prev = GENESIS
    for r in rows:
        if r.prev_hash != prev or r.hash != _digest(prev, r.ts, r.actor, r.action, r.case_id, r.details):
            return {"valid": False, "entries": len(rows), "broken_at": r.id}
        prev = r.hash
    return {"valid": True, "entries": len(rows), "broken_at": None}


async def entries_for_case(case_id: str) -> list[dict]:
    async with session_scope() as s:
        rows = (await s.execute(select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.id))).scalars().all()
    return [{"id": r.id, "ts": r.ts.isoformat() + "Z", "actor": r.actor, "action": r.action, "details": r.details} for r in rows]
