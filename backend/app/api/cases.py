"""Customer-facing API: the case, the conversation (SSE) and document upload."""
from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..deps import customer_case, require_role
from ..models import Case, User
from ..security.ratelimit import rate_limit
from ..security.upload_guard import UploadRejected, check_upload
from ..services import storage
from ..services.form_schema import DOC_LABELS
from ..services.turns import case_view, create_or_get_case, run_turn

router = APIRouter(prefix="/cases", tags=["customer"])


class ChatIn(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    action: dict | None = None


def _sse(events: AsyncIterator[dict]) -> StreamingResponse:
    async def gen():
        async for e in events:
            yield f"event: {e['event']}\ndata: {json.dumps(e['data'], default=str)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("")
async def open_case(user: User = Depends(require_role("customer"))) -> dict:
    case = await create_or_get_case(user)
    return await case_view(case.id)


@router.get("/{case_id}")
async def get_case(case: Case = Depends(customer_case)) -> dict:
    return await case_view(case.id)


@router.post("/{case_id}/chat", dependencies=[Depends(rate_limit)])
async def chat(body: ChatIn, case: Case = Depends(customer_case), user: User = Depends(require_role("customer"))):
    if not (body.text or body.action):
        raise HTTPException(422, "Send text or an action")
    if body.action and body.action.get("type") not in {"start", "confirm", "answer", "submit"}:
        raise HTTPException(422, "Unknown action")
    return _sse(run_turn(user, case.id, text=body.text, action=body.action))


@router.post("/{case_id}/documents", dependencies=[Depends(rate_limit)])
async def upload_document(doc_type: str = Form(...), file: UploadFile = File(...),
                          case: Case = Depends(customer_case), user: User = Depends(require_role("customer"))):
    if doc_type not in DOC_LABELS:
        raise HTTPException(422, "Unknown document type")
    if case.status not in ("draft", "info_requested"):
        raise HTTPException(409, "This application can no longer be changed")
    data = await file.read(9 * 1024 * 1024)
    try:
        checked = check_upload(data)
    except UploadRejected as exc:
        raise HTTPException(422, str(exc))

    async def events():
        with storage.temp_plain_file(data, checked.ext) as path:
            upload = {"doc_type": doc_type, "temp_path": path, "data": data,
                      "sha256": hashlib.sha256(data).hexdigest(), "content_type": checked.content_type}
            async for e in run_turn(user, case.id, upload=upload):
                yield e
    return _sse(events())
