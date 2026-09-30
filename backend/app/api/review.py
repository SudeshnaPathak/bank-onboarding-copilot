"""Analyst-facing API. Every route requires the analyst role; the decision route is the only way to a final status."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from ..db import session_scope
from ..deps import require_role
from ..graphs.review import resume_review
from ..ocr import pdf
from ..models import Case, Decision, Document, Message, ReviewRun, User
from ..rules.engine import load_rules
from ..security.crypto import decrypt_json
from ..services import audit, storage
from ..services.decision import ACTIONS, DecisionError
from ..services.flow import resolved
from ..services.form_schema import DOC_LABELS, FIELD_LABELS, display

router = APIRouter(prefix="/review", tags=["analyst"], dependencies=[Depends(require_role("analyst"))])
SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class DecisionIn(BaseModel):
    action: str
    note: str = ""


async def _latest_run(s, case_id: str) -> ReviewRun | None:
    return (await s.execute(select(ReviewRun).where(ReviewRun.case_id == case_id)
                            .order_by(ReviewRun.created_at.desc()).limit(1))).scalar_one_or_none()


@router.get("/queue")
async def queue() -> list[dict]:
    async with session_scope() as s:
        cases = (await s.execute(select(Case).where(Case.status == "under_review").order_by(Case.submitted_at))).scalars().all()
        out = []
        for c in cases:
            run = await _latest_run(s, c.id)
            worst = min((SEV_RANK[f["severity"]] for f in (run.flags if run else [])), default=9)
            out.append({"id": c.id, "customer": c.user.name, "product": c.product, "submitted_at": c.submitted_at.isoformat() + "Z",
                        "submission_no": c.submission_no, "analysis_ready": run is not None,
                        "score": run.score if run else None, "band": run.band if run else None,
                        "flag_count": len(run.flags) if run else 0,
                        "top_severity": None if worst == 9 else [k for k, v in SEV_RANK.items() if v == worst][0]})
    # most attention-worthy first: lowest score, then oldest
    return sorted(out, key=lambda r: (r["score"] if r["score"] is not None else -1, r["submitted_at"]))


@router.get("/{case_id}")
async def detail(case_id: str, analyst: User = Depends(require_role("analyst"))) -> dict:
    async with session_scope() as s:
        case = await s.get(Case, case_id)
        if case is None:
            raise HTTPException(404, "Case not found")
        run = await _latest_run(s, case_id)
        docs = (await s.execute(select(Document).where(Document.case_id == case_id))).scalars().all()
        decisions = (await s.execute(select(Decision).where(Decision.case_id == case_id).order_by(Decision.created_at))).scalars().all()
        msgs = (await s.execute(select(Message).where(Message.case_id == case_id).order_by(Message.created_at, Message.id))).scalars().all()
    await audit.record(f"user:{analyst.id}", "case.opened_by_analyst", case_id, {})
    form = case.form or {}
    details = [{"label": FIELD_LABELS[k], "value": resolved(case.extracted, form, k) or "-",
                "confirmed_by_customer": k in form.get("confirmations", {})} for k in ("name", "dob", "address")]
    details += [{"label": lbl, "value": display(k, form[k])} for k, lbl in
                (("mobile", "Mobile"), ("email", "Email"), ("occupation", "Occupation"), ("nominee_name", "Nominee"),
                 ("us_tax_resident", "US tax resident")) if k in form]
    return {
        "id": case.id, "status": case.status, "customer": {"name": case.user.name, "email": case.user.email},
        "submission_no": case.submission_no, "submitted_at": case.submitted_at.isoformat() + "Z" if case.submitted_at else None,
        "details": details,
        "documents": [{"id": d.id, "doc_type": d.doc_type, "label": DOC_LABELS[d.doc_type], "fields": d.summary.get("fields", []),
                       "quality": d.quality, "sha256": d.sha256[:16],
                       "pages": (d.quality or {}).get("pdf_pages", 1)} for d in docs],
        "analysis": None if run is None else {"score": run.score, "band": run.band, "flags": run.flags, "breakdown": run.breakdown,
                                              "summary": run.summary, "provenance": run.provenance},
        "score_bands": load_rules()["bands"],
        "decisions": [{"action": d.action, "note": d.note, "at": d.created_at.isoformat() + "Z"} for d in decisions],
        "conversation": [{"role": m.role, "text": m.text} for m in msgs],
        "audit": await audit.entries_for_case(case_id),
        "can_decide": case.status == "under_review",
    }


@router.get("/{case_id}/documents/{doc_id}/image")
async def document_image(case_id: str, doc_id: str, page: int = Query(0, ge=0, le=20),
                         analyst: User = Depends(require_role("analyst"))):
    async with session_scope() as s:
        doc = (await s.execute(select(Document).where(Document.id == doc_id, Document.case_id == case_id))).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Document not found")
    data, media_type = storage.load_decrypted(doc.storage_key), doc.content_type
    if media_type == "application/pdf":
        # Analysts are shown a server-side render of the page, never the uploaded PDF itself.
        if page >= (doc.quality or {}).get("pdf_pages", 1):
            raise HTTPException(404, "Page not found")
        with storage.temp_plain_file(data, "pdf") as path:
            try:
                data, media_type = await asyncio.to_thread(pdf.render_page_png, path, page), "image/png"
            except (pdf.PdfProblem, IndexError):
                raise HTTPException(422, "This PDF could not be displayed")
    elif page:
        raise HTTPException(404, "Page not found")
    await audit.record(f"user:{analyst.id}", "document.viewed", case_id, {"doc_type": doc.doc_type, "page": page})
    return Response(data, media_type=media_type,
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/{case_id}/decide")
async def decide(case_id: str, body: DecisionIn, analyst: User = Depends(require_role("analyst"))) -> dict:
    if body.action not in ACTIONS:
        raise HTTPException(422, "Unknown action")
    if body.action != "approve" and len((body.note or "").strip()) < 5:
        raise HTTPException(422, "A note of at least 5 characters is required to reject or request information.")
    async with session_scope() as s:
        case = await s.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    if case.status != "under_review":
        raise HTTPException(409, "This case is not awaiting a decision.")
    try:
        return await resume_review(case_id, case.submission_no,
                                   {"reviewer_id": analyst.id, "action": body.action, "note": body.note})
    except DecisionError as exc:
        raise HTTPException(400, str(exc))
