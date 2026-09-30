"""Submit node: moves a gated, complete application to `under_review` and starts the review graph."""
from __future__ import annotations

from ..db import session_scope
from ..graphs import review
from ..models import Case, utcnow
from ..services import audit
from .intake import EDITABLE, STATUS_TEXT


async def persist_node(state: dict) -> dict:
    async with session_scope() as s:
        case = await s.get(Case, state["case_id"])
        if case.status not in EDITABLE:  # double-click or replay: never submit twice
            return {"replies": [{"text": STATUS_TEXT.get(case.status, STATUS_TEXT["under_review"]), "ui": None}],
                    "trace": [{"node": "persist", "detail": f"ignored, case already {case.status}"}]}
        case.status, case.form, case.extracted = "under_review", state["form"], state["extracted"]
        case.submission_no += 1
        case.submitted_at = utcnow()
        submission_no = case.submission_no
    await audit.record(f"user:{state['user_id']}", "case.submitted", state["case_id"], {"submission_no": submission_no})
    await review.start_review(state["case_id"], submission_no)
    return {
        "replies": [{"text": "Submitted. Thank you! A bank reviewer will now check your documents and decide. "
                             "I'll post the outcome here. You don't need to do anything else.",
                     "ui": {"type": "submitted", "submission_no": submission_no}}],
        "trace": [{"node": "persist", "detail": f"submission #{submission_no} sent to review graph"}],
    }
