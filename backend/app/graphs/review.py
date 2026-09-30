"""Review graph. Runs once per submission.

validation -> risk_scoring -> readiness -> await_decision (interrupt) -> apply_decision

Validation and scoring are deterministic code. The only LLM step is the readiness summary, which
describes flags the rules already raised. The graph pauses at `interrupt()` until a human analyst decides;
`apply_decision` then calls `decide_case()`, the only function allowed to write a final status.
"""
from __future__ import annotations

import logging
from datetime import date

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select

from ..db import session_scope
from ..llm.factory import get_llm
from ..models import Case, Document, ReviewRun
from ..rules.engine import rules_version, score_flags
from ..rules.validation import run_validation
from ..security.crypto import decrypt_json
from ..security.masking import redact_text
from ..services import audit
from ..services.decision import DecisionError, decide_case
from ..services.flow import required_docs
from .state import ReviewState

log = logging.getLogger("review")


async def validation_node(state: ReviewState) -> dict:
    async with session_scope() as s:
        case = await s.get(Case, state["case_id"])
        docs = (await s.execute(select(Document).where(Document.case_id == case.id))).scalars().all()
        product, confirmations = case.product, dict(case.form.get("confirmations", {}))
        data = {d.doc_type: decrypt_json(d.fields_enc) for d in docs}  # decrypted inside the node, never put in graph state
    flags = run_validation(required_docs(product), confirmations, data, date.today())
    await audit.record("agent:validation", "review.validated", state["case_id"],
                       {"submission_no": state["submission_no"], "flags": [f["code"] for f in flags]})
    return {"flags": flags}


async def risk_scoring_node(state: ReviewState) -> dict:
    score, breakdown, band = score_flags(state["flags"])
    return {"score": score, "breakdown": breakdown, "band": band}


async def readiness_node(state: ReviewState) -> dict:
    payload = {"score": state["score"], "band": state["band"],
               "flags": [{**f, "message": redact_text(f["message"]), "evidence": {}} for f in state["flags"]]}
    summary = await get_llm().summarize_review(payload)
    try:
        from ..llm.gemini import prompt_versions
        prompts = prompt_versions()
    except Exception:  # noqa: BLE001  (gemini deps are optional)
        prompts = {}
    provenance = {"rules": rules_version(), "summariser": get_llm().name, "prompts": prompts}
    async with session_scope() as s:
        s.add(ReviewRun(case_id=state["case_id"], submission_no=state["submission_no"], flags=state["flags"],
                        score=state["score"], band=state["band"], breakdown=state["breakdown"],
                        summary=summary, provenance=provenance))
    await audit.record("agent:readiness", "review.completed", state["case_id"],
                       {"submission_no": state["submission_no"], "score": state["score"], "band": state["band"]})
    return {"summary": summary, "provenance": provenance}


async def await_decision_node(state: ReviewState) -> dict:
    """Pauses the graph. Nothing above this line can approve or reject; only a human resume can continue."""
    decision = interrupt({"case_id": state["case_id"], "score": state["score"], "band": state["band"]})
    return {"decision": decision}


async def apply_decision_node(state: ReviewState) -> dict:
    d = state["decision"]
    result = await decide_case(state["case_id"], d["reviewer_id"], d["action"], d.get("note", ""))
    return {"result": result}


def build_review_graph(checkpointer):
    g = StateGraph(ReviewState)
    g.add_node("validation", validation_node)
    g.add_node("risk_scoring", risk_scoring_node)
    g.add_node("readiness", readiness_node)
    g.add_node("await_decision", await_decision_node)
    g.add_node("apply_decision", apply_decision_node)
    g.add_edge(START, "validation")
    g.add_edge("validation", "risk_scoring")
    g.add_edge("risk_scoring", "readiness")
    g.add_edge("readiness", "await_decision")
    g.add_edge("await_decision", "apply_decision")
    g.add_edge("apply_decision", END)
    return g.compile(checkpointer=checkpointer)


_graph = None


def set_review_graph(graph) -> None:
    global _graph
    _graph = graph


def _config(case_id: str, submission_no: int) -> dict:
    return {"configurable": {"thread_id": f"{case_id}:{submission_no}"}, "recursion_limit": 25}


async def start_review(case_id: str, submission_no: int) -> None:
    """Runs until the interrupt. On any failure the case still reaches the analyst queue (analysis pending)."""
    try:
        await _graph.ainvoke({"case_id": case_id, "submission_no": submission_no}, _config(case_id, submission_no))
    except Exception as exc:  # noqa: BLE001
        log.exception("review pipeline failed for %s", case_id)
        await audit.record("system", "review.failed", case_id, {"error": type(exc).__name__})


async def resume_review(case_id: str, submission_no: int, decision: dict) -> dict:
    cfg = _config(case_id, submission_no)
    snapshot = await _graph.aget_state(cfg)
    if snapshot and tuple(snapshot.next) == ("await_decision",):  # paused for a human: resume, the graph applies it
        out = await _graph.ainvoke(Command(resume=decision), cfg)
        return out["result"]
    # analysis never completed (failed run): the analyst can still decide, through the same function
    return await decide_case(case_id, decision["reviewer_id"], decision["action"], decision.get("note", ""))


__all__ = ["DecisionError", "build_review_graph", "resume_review", "set_review_graph", "start_review"]
