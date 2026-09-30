import asyncio

from app.agents.intake_logic import intake_core
from app.llm.rule_based import RuleBasedLLM
from tests.unit.helpers import base_state, scenario

LLM = RuleBasedLLM()


def run(state):
    return asyncio.run(intake_core(state, LLM))


def last_ui(out):
    return out["replies"][-1]["ui"]


def test_start_greets_and_asks_for_first_document():
    out = run(base_state({}, uploaded=[], action={"type": "start"}, passive=True))
    assert "Priya" in out["replies"][0]["text"]
    assert last_ui(out)["type"] == "upload_request" and last_ui(out)["doc_type"] == "pan"


def test_valid_answer_is_saved_and_next_field_asked():
    extracted, _ = scenario("clean")
    out = run(base_state(extracted, text="9876543210"))
    assert out["form"]["mobile"] == "9876543210"
    assert out["user_display"].startswith("+91 98XXXXXX")  # the raw number is never echoed into the transcript
    assert last_ui(out)["field"] == "email"


def test_invalid_answer_explains_and_reasks_the_same_field():
    extracted, _ = scenario("clean")
    out = run(base_state(extracted, text="12345"))
    assert "mobile" not in out["form"]
    assert "10-digit" in out["replies"][0]["text"]
    assert last_ui(out)["field"] == "mobile"


def test_free_text_choice_is_parsed_for_occupation():
    extracted, _ = scenario("clean")
    form = {"mobile": "9876543210", "email": "a@b.co"}
    out = run(base_state(extracted, form=form, text="I'm a software engineer"))
    assert out["form"]["occupation"] == "Salaried"


def test_conflicts_must_be_confirmed_before_details():
    extracted, _ = scenario("mismatch")
    out = run(base_state(extracted, text="hello", passive=True))
    ui = last_ui(out)
    assert ui["type"] == "confirm" and ui["field"] == "name"
    values = {o["value"] for o in last_ui(run(base_state(extracted, form={"confirmations": {"name": "PRIYA SHARMA"}}, passive=True)))["options"]}
    assert values == {"14/03/1998", "15/03/1998"}


def test_confirm_action_stores_choice_and_advances():
    extracted, _ = scenario("mismatch")
    form = {"confirmations": {"name": "PRIYA SHARMA"}}
    out = run(base_state(extracted, form=form, action={"type": "confirm", "field": "dob", "value": "14/03/1998"}))
    assert out["form"]["confirmations"]["dob"] == "14/03/1998"
    assert last_ui(out)["field"] == "address"


def test_confirm_rejects_values_that_were_never_extracted():
    extracted, _ = scenario("mismatch")
    out = run(base_state(extracted, action={"type": "confirm", "field": "dob", "value": "01/01/1990"}))
    assert "dob" not in out["form"]["confirmations"]


def test_new_upload_clears_earlier_confirmations():
    extracted, _ = scenario("clean")
    last = {"doc_type": "pan", "label": "PAN card", "fields": [], "missing": []}
    out = run(base_state(extracted, form={"confirmations": {"name": "X"}}, last_upload=last, passive=True))
    assert out["form"]["confirmations"] == {}
    assert out["replies"][0]["ui"]["type"] == "extraction"


def test_complete_application_shows_ready_summary():
    extracted, _ = scenario("clean")
    form = {"mobile": "9876543210", "email": "a@b.co", "occupation": "Salaried", "nominee_name": "",
            "us_tax_resident": False, "consent": True}
    out = run(base_state(extracted, form=form, passive=True))
    assert last_ui(out)["type"] == "ready"
    assert {"label": "Name", "value": "PRIYA SHARMA"} in last_ui(out)["items"]


def test_submitted_case_is_read_only():
    extracted, _ = scenario("clean")
    out = run(base_state(extracted, status="under_review", text="9876543210"))
    assert out["form"].get("mobile") is None
    assert "reviewer" in out["replies"][0]["text"]
