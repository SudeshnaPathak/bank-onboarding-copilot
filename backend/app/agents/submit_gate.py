from __future__ import annotations

from ..services.flow import next_step


async def submit_gate_node(state: dict) -> dict:
    """Deterministic pre-submit check. Nothing reaches a reviewer with missing documents, unresolved
    confirmations or missing declarations."""
    step = next_step(state["product"], set(state["uploaded"]), state["extracted"], state["form"])
    if step["kind"] == "ready":
        return {"submit_ready": True, "trace": [{"node": "submit_gate", "detail": "all checks passed"}]}
    return {"submit_ready": False, "passive": True,
            "gate_errors": ["Almost there. Before I can send this to a reviewer, I still need a few things:"],
            "trace": [{"node": "submit_gate", "detail": f"blocked at step {step['kind']}"}]}


def route_after_gate(state: dict) -> str:
    return "persist" if state.get("submit_ready") else "intake"
