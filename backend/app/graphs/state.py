from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict


class ChatState(TypedDict, total=False):
    # loaded from the database at the start of every turn (the database is the source of truth)
    case_id: str
    user_id: str
    user_name: str
    product: str
    status: str
    form: dict[str, Any]
    extracted: dict[str, list[dict]]
    uploaded: list[str]
    # this turn's input
    text: str | None
    action: dict | None
    pending_upload: dict | None
    user_display: str
    user_ui: dict | None
    # working state
    intent: str
    passive: bool
    last_upload: dict | None
    upload_feedback: list[str]
    gate_errors: list[str]
    # outputs (reducers append across nodes)
    replies: Annotated[list[dict], add]
    trace: Annotated[list[dict], add]
    submit_ready: bool
    saved: list[dict]


class ReviewState(TypedDict, total=False):
    case_id: str
    submission_no: int
    flags: list[dict]
    score: int
    band: str
    breakdown: list[dict]
    summary: str
    provenance: dict
    decision: dict
    result: dict
