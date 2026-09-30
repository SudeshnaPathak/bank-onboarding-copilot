"""Chat graph. Runs once per customer turn (message, button action or document upload).

START -> document (if an upload is attached) | classify_intent
classify_intent -> guide | intake | submit_gate
guide -> intake (re-prompts the current step)    document -> intake
submit_gate -> persist (complete) | intake (explains what is missing)
The database is the source of truth; graph state is rebuilt at the start of every turn.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

try:  # retry support differs slightly between LangGraph versions
    from langgraph.types import RetryPolicy
except ImportError:  # pragma: no cover
    RetryPolicy = None

from ..agents.document_agent import document_node
from ..agents.guide import guide_node
from ..agents.intake import intake_node
from ..agents.persist import persist_node
from ..agents.router import classify_intent_node, route_after_classify, route_entry
from ..agents.submit_gate import route_after_gate, submit_gate_node
from .state import ChatState


def _add(g: StateGraph, name: str, fn, retries: int = 0) -> None:
    if retries and RetryPolicy is not None:
        try:
            g.add_node(name, fn, retry_policy=RetryPolicy(max_attempts=retries + 1))
            return
        except TypeError:
            pass
    g.add_node(name, fn)


def build_chat_graph():
    g = StateGraph(ChatState)
    _add(g, "classify_intent", classify_intent_node, retries=1)
    _add(g, "guide", guide_node, retries=1)
    _add(g, "document", document_node)
    _add(g, "intake", intake_node)
    _add(g, "submit_gate", submit_gate_node)
    _add(g, "persist", persist_node)
    g.add_conditional_edges(START, route_entry, {"document": "document", "classify_intent": "classify_intent"})
    g.add_conditional_edges("classify_intent", route_after_classify,
                            {"guide": "guide", "intake": "intake", "submit_gate": "submit_gate"})
    g.add_edge("guide", "intake")
    g.add_edge("document", "intake")
    g.add_conditional_edges("submit_gate", route_after_gate, {"persist": "persist", "intake": "intake"})
    g.add_edge("intake", END)
    g.add_edge("persist", END)
    return g.compile()


_graph = None


def get_chat_graph():
    global _graph
    if _graph is None:
        _graph = build_chat_graph()
    return _graph
