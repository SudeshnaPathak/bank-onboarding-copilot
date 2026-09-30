"""Intake logic: applies the customer's input to the application, then asks for the next thing.

Deterministic apart from one optional LLM call (parsing a free-text choice) and free of database access,
so it is unit-tested directly. agents/intake.py wraps it with persistence and audit.
"""
from __future__ import annotations

from ..rules.matchers import name_tokens, parse_date
from ..services.flow import (CONFIRM_FIELDS, missing_docs, needs_confirmation, next_step, resolved)
from ..services.form_schema import (DOC_LABELS, DOC_TIPS, DOC_WHY, FIELD_BY_KEY, FIELD_LABELS, FIELDS, PRODUCTS,
                                    display, validate)

EDITABLE = {"draft", "info_requested"}
STATUS_TEXT = {
    "under_review": "Your application is with a bank reviewer. I'll post the decision here as soon as it's made.",
    "approved": "Your application has been approved by a bank reviewer.",
    "rejected": "A bank reviewer has decided on your application. Please contact the bank for details.",
}


def _greeting(state: dict) -> str:
    first = (state.get("user_name") or "there").split()[0]
    product = PRODUCTS[state["product"]]["name"]
    return (f"Hi {first}! I'm your onboarding assistant for the {product}. I'll read your documents so you "
            "don't have to type everything, explain anything that's unclear, and check the details with you. "
            "A human bank reviewer makes the final decision on every application.")


def _validate_custom(field: str, text: str) -> tuple[bool, str, str]:
    t = " ".join(text.split())
    if field == "name":
        ok = len(name_tokens(t)) >= 1 and all(ch.isalpha() or ch in " .'-" for ch in t) and len(t) <= 80
        return ok, t.upper(), "" if ok else "Please type your name using letters only."
    if field == "dob":
        d = parse_date(t)
        return (True, f"{d.day:02d}/{d.month:02d}/{d.year}", "") if d else (False, "", "Please type it as DD/MM/YYYY.")
    ok = len(t) >= 10
    return ok, t, "" if ok else "That address looks too short. Please include house, area, city and PIN code."


def _extraction_card(last: dict) -> dict:
    fields = last["fields"]
    text = f"I read your {last['label']}. Here's what I found:"
    if last["missing"]:
        text += f" I couldn't read: {', '.join(last['missing'])}."
    return {"text": text, "ui": {"type": "extraction", "doc_type": last["doc_type"], "label": last["label"],
                                 "fields": fields, "missing": last["missing"]}}


def _summary_items(state: dict, form: dict) -> list[dict]:
    ex = state["extracted"]
    items = [{"label": FIELD_LABELS[k], "value": resolved(ex, form, k) or "-"} for k in CONFIRM_FIELDS]
    for f in FIELDS:
        if f.key in form and f.key != "consent":
            items.append({"label": f.label, "value": display(f.key, form[f.key])})
    items.append({"label": "Documents", "value": ", ".join(DOC_LABELS[d] for d in sorted(state["uploaded"]))})
    return items


def _prompt(state: dict, form: dict, step: dict) -> dict:
    ex, kind = state["extracted"], step["kind"]
    if kind == "upload":
        dt = step["doc_type"]
        remaining = [DOC_LABELS[d] for d in missing_docs(state["product"], set(state["uploaded"]))]
        return {"text": f"Next, please upload your {DOC_LABELS[dt]}. {DOC_WHY[dt]}",
                "ui": {"type": "upload_request", "doc_type": dt, "label": DOC_LABELS[dt], "why": DOC_WHY[dt],
                       "tips": DOC_TIPS, "remaining": remaining}}
    if kind == "confirm":
        f = step["field"]
        cands = ex[f]
        reason = needs_confirmation(f, cands)
        seen, options = set(), []
        for c in cands:
            if c["value"] not in seen:
                seen.add(c["value"])
                options.append({"value": c["value"], "source": DOC_LABELS.get(c["source_doc"], c["source_doc"]),
                                "confidence": c["confidence"]})
        label = FIELD_LABELS[f].lower()
        text = (f"Your documents show different values for your {label}. Which one is correct?"
                if reason == "conflict" else f"I'm not fully sure I read your {label} correctly. Is this right?")
        return {"text": text, "ui": {"type": "confirm", "field": f, "label": FIELD_LABELS[f], "reason": reason,
                                     "options": options}}
    if kind == "field":
        spec = FIELD_BY_KEY[step["field"]]
        return {"text": f"{spec.ask}\n\nWhy we ask: {spec.why}",
                "ui": {"type": "field", "field": spec.key, "label": spec.label, "kind": spec.kind,
                       "choices": spec.choices, "optional": spec.optional}}
    if kind == "blocked":
        spec = FIELD_BY_KEY["consent"]
        return {"text": "Without your confirmation I can't send the application to a reviewer. "
                        "If that was a mistake, you can change your answer now.",
                "ui": {"type": "field", "field": "consent", "label": spec.label, "kind": "bool",
                       "choices": [], "optional": False}}
    return {"text": "That's everything I need. Please check the summary, then submit it for review.",
            "ui": {"type": "ready", "items": _summary_items(state, form)}}


async def _apply_input(state: dict, form: dict, step: dict, llm) -> tuple[str, str, str | None, list[dict]]:
    """Returns (user_display, lead_text, error_text, audit_events)."""
    action, text = state.get("action") or {}, (state.get("text") or "").strip()
    kind, events = step["kind"], []

    if action.get("type") == "confirm":
        f, value = action.get("field"), str(action.get("value", "")).strip()
        valid_values = {c["value"] for c in state["extracted"].get(f, [])}
        if f in CONFIRM_FIELDS and value in valid_values:
            form["confirmations"][f] = value
            events.append(("field.confirmed", {"field": f}))
            return value, "", None, events
        return "", "", "That option isn't available any more. Please choose from the options shown.", events

    if action.get("type") == "answer":
        f, text = action.get("field"), str(action.get("value", "")).strip()
        kind = "blocked" if (f == "consent" and step["kind"] == "blocked") else ("field" if f in FIELD_BY_KEY else kind)
        step = {"kind": kind, "field": f} if kind == "field" else step

    if kind == "upload":
        return text, "", (f"I need your {DOC_LABELS[step['doc_type']]} before we can continue. "
                          "Use the upload button, or type a question if you'd like help."), events
    if kind == "confirm":
        f = step["field"]
        ok, value, err = _validate_custom(f, text)
        if not ok:
            return text, "", err, events
        form["confirmations"][f] = value
        events.append(("field.confirmed", {"field": f, "custom": True}))
        return value, "", None, events
    if kind in ("field", "blocked"):
        key = "consent" if kind == "blocked" else step["field"]
        spec = FIELD_BY_KEY[key]
        ok, value, err = validate(key, text)
        if not ok and spec.kind == "choice":
            parsed = await llm.parse_field(key, spec.choices, text)
            if parsed in spec.choices:
                ok, value = True, parsed
        if not ok:
            return text, "", err or f"Please pick one of: {', '.join(spec.choices)}.", events
        form[key] = value
        events.append(("field.answered", {"field": key}))
        return display(key, value), "", None, events
    return text, "Everything's in place. Press Submit for review when you're ready.", None, events


async def intake_core(state: dict, llm) -> dict:
    form = {**state["form"], "confirmations": dict(state["form"].get("confirmations", {}))}
    replies, trace, events = [], [], []
    out: dict = {"form": form}

    if state.get("status") not in EDITABLE:
        if not state.get("passive"):
            replies.append({"text": STATUS_TEXT.get(state.get("status"), STATUS_TEXT["under_review"]), "ui": None})
        return {**out, "replies": replies, "events": events,
                "trace": [{"node": "intake", "detail": f"case is {state.get('status')}, no changes"}]}

    lead: list[str] = []
    if (state.get("action") or {}).get("type") == "start":
        lead.append(_greeting(state))
    if state.get("last_upload"):
        form["confirmations"] = {}  # documents changed, so earlier confirmations no longer apply
        replies.append(_extraction_card(state["last_upload"]))
    lead += state.get("upload_feedback", []) + state.get("gate_errors", [])

    error = None
    if not state.get("passive") and (state.get("action") or {}).get("type") != "start":
        step = next_step(state["product"], set(state["uploaded"]), state["extracted"], form)
        display_text, extra, error, events = await _apply_input(state, form, step, llm)
        out["user_display"] = display_text
        if extra:
            lead.append(extra)
        if error:
            lead.append(error)

    step = next_step(state["product"], set(state["uploaded"]), state["extracted"], form)
    prompt = _prompt(state, form, step)
    if lead:
        replies.insert(0, {"text": "\n\n".join(lead), "ui": None})
    replies.append(prompt)
    trace.append({"node": "intake", "detail": f"next step: {step['kind']}" + (f" ({step.get('field') or step.get('doc_type')})" if step.get("field") or step.get("doc_type") else "")})
    return {**out, "replies": replies, "trace": trace, "events": events}
