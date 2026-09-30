from __future__ import annotations

from ..llm import guardrails
from ..llm.factory import get_llm
from ..services.flow import next_step


async def classify_intent_node(state: dict) -> dict:
    """Decides what kind of turn this is. Structured actions and guardrails are handled in code before any model."""
    action, text = state.get("action"), (state.get("text") or "").strip()
    if action:
        intent = "submit" if action["type"] == "submit" else "intake"
        source = "action"
    elif (kind := guardrails.detect(text)):
        intent, source = "out_of_scope", f"guardrail:{kind}"
    else:
        step = next_step(state["product"], set(state["uploaded"]), state["extracted"], state["form"])
        intent = await get_llm().classify_intent(text, {"step": step["kind"]})
        source = get_llm().name
    return {"intent": intent, "trace": [{"node": "router", "detail": f"intent={intent} via {source}"}]}


def route_after_classify(state: dict) -> str:
    return {"product_qa": "guide", "out_of_scope": "guide", "submit": "submit_gate"}.get(state["intent"], "intake")


def route_entry(state: dict) -> str:
    return "document" if state.get("pending_upload") else "classify_intent"
