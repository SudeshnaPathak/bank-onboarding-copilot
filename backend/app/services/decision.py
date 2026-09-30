"""decide_case() is the ONLY place a case may enter a final state (approved / rejected / info_requested).
tests/security/test_decision_boundary.py fails the build if any other module writes those statuses."""
from __future__ import annotations

from sqlalchemy import select

from ..db import session_scope
from ..models import Case, Decision, Message
from . import audit

ACTIONS = {"approve": "approved", "reject": "rejected", "request_info": "info_requested"}


class DecisionError(ValueError):
    pass


async def decide_case(case_id: str, reviewer_id: str, action: str, note: str) -> dict:
    if action not in ACTIONS:
        raise DecisionError("Unknown action")
    note = (note or "").strip()
    if action != "approve" and len(note) < 5:
        raise DecisionError("A note of at least 5 characters is required to reject or request information.")
    async with session_scope() as s:
        case = (await s.execute(select(Case).where(Case.id == case_id))).scalar_one()
        if case.status != "under_review":
            raise DecisionError("This case is not awaiting a decision.")
        case.status = ACTIONS[action]
        s.add(Decision(case_id=case_id, submission_no=case.submission_no, reviewer_id=reviewer_id, action=action, note=note))
        if action == "approve":
            text = "Good news: your application has been approved by a bank reviewer. We'll guide you through your first steps soon."
        elif action == "reject":
            text = "A bank reviewer has reviewed your application and is unable to open the account. Please contact the bank for details."
            text += f"\n\nReviewer note: {note}"
        else:
            text = f"A bank reviewer needs a bit more information:\n\n{note}\n\nYou can upload a new document or continue here, then submit again."
        s.add(Message(case_id=case_id, role="assistant", text=text, meta={"source": "reviewer_decision", "action": action}))
    await audit.record(f"user:{reviewer_id}", f"decision.{action}", case_id, {"note": note})
    return {"case_id": case_id, "status": ACTIONS[action]}
