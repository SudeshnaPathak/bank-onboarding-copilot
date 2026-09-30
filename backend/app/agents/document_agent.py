"""Document agent: quality gate -> OCR -> parse -> verified fallback -> encrypted persistence -> candidate merge."""
from __future__ import annotations

from sqlalchemy import select

from ..db import session_scope
from ..llm.factory import get_llm
from ..models import Document
from ..ocr.pipeline import UnsupportedDocument, extract_document
from ..ocr.quality import QUALITY_MESSAGES, assess_quality
from ..security.crypto import encrypt_json
from ..ocr.candidates import merge_candidates
from ..security.masking import mask_field
from ..services import audit, storage
from ..services.form_schema import DOC_LABELS, FIELD_LABELS

async def document_node(state: dict) -> dict:
    up, label = state["pending_upload"], DOC_LABELS[state["pending_upload"]["doc_type"]]
    doc_type = up["doc_type"]
    trace = lambda d: [{"node": "document", "detail": d}]

    quality = assess_quality(up["temp_path"])
    if not quality["ok"]:
        msgs = [f"{label}: {QUALITY_MESSAGES[i]}" for i in quality["issues"]]
        await audit.record(f"user:{state['user_id']}", "document.rejected_quality", state["case_id"],
                           {"doc_type": doc_type, "issues": quality["issues"], "sharpness": quality.get("sharpness")})
        return {"passive": True, "upload_feedback": msgs, "pending_upload": None,
                "trace": trace(f"{doc_type}: rejected by quality gate {quality['issues']}")}
    try:
        res = await extract_document(up["temp_path"], doc_type, get_llm())
    except UnsupportedDocument as exc:
        return {"passive": True, "upload_feedback": [f"{label}: {exc}"], "pending_upload": None,
                "trace": trace(f"{doc_type}: unsupported document")}
    if not res.fields:
        return {"passive": True, "pending_upload": None,
                "upload_feedback": [f"{label}: I couldn't read any text from that image. Please retake it in better light."],
                "trace": trace(f"{doc_type}: OCR returned nothing")}

    summary_fields = [{"key": k, "label": FIELD_LABELS.get(k, k), "value": mask_field(k, v),
                       "confidence": res.field_confidence.get(k), "source": res.field_source.get(k)}
                      for k, v in res.fields.items()]
    async with session_scope() as s:
        for old in (await s.execute(select(Document).where(Document.case_id == state["case_id"], Document.doc_type == doc_type))).scalars():
            storage.delete(old.storage_key)
            await s.delete(old)
        s.add(Document(
            case_id=state["case_id"], doc_type=doc_type, storage_key=storage.save_encrypted(up["data"]),
            sha256=up["sha256"], content_type=up["content_type"], quality=quality,
            fields_enc=encrypt_json({"fields": res.fields, "field_confidence": res.field_confidence,
                                     "field_source": res.field_source, "raw_text": res.raw_text}),
            summary={"fields": summary_fields, "missing": res.missing, "mean_confidence": res.mean_confidence}))
    await audit.record("agent:document", "document.extracted", state["case_id"],
                       {"doc_type": doc_type, "fields": sorted(res.fields), "missing": res.missing,
                        "sources": sorted(set(res.field_source.values()))})

    uploaded = sorted(set(state["uploaded"]) | {doc_type})
    return {
        "passive": True, "pending_upload": None, "uploaded": uploaded,
        "extracted": merge_candidates(state["extracted"], doc_type, res),
        "last_upload": {"doc_type": doc_type, "label": label, "fields": summary_fields,
                        "missing": [FIELD_LABELS.get(m, m) for m in res.missing]},
        "trace": trace(f"{doc_type}: {len(res.fields)} fields read, {len(res.missing)} missing"),
    }
