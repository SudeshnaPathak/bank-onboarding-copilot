from datetime import date

from app.rules.engine import score_flags
from app.rules.validation import run_validation
from app.services.flow import required_docs
from tests.unit.helpers import scenario

TODAY = date(2026, 9, 30)
REQ = required_docs("basic_savings")


def codes(key, confirmations=None):
    _, data = scenario(key)
    return [f["code"] for f in run_validation(REQ, confirmations or {}, data, TODAY)]


def test_clean_application_has_no_flags_and_full_score():
    _, data = scenario("clean")
    flags = run_validation(REQ, {}, data, TODAY)
    assert flags == []
    assert score_flags(flags) == (100, [], "clean")


def test_dob_mismatch_is_flagged_and_confirmation_reduces_penalty():
    _, data = scenario("mismatch")
    flags = run_validation(REQ, {}, data, TODAY)
    assert {f["code"] for f in flags} == {"DOB_MISMATCH", "ADDRESS_MISMATCH", "LOW_CONFIDENCE_FIELD"}
    unconfirmed = score_flags(flags)[0]
    confirmed = run_validation(REQ, {"dob": "14/03/1998"}, data, TODAY)
    dob_flag = next(f for f in confirmed if f["code"] == "DOB_MISMATCH")
    assert dob_flag["confirmed_by_customer"] is True
    assert score_flags(confirmed)[0] > unconfirmed  # still flagged, but penalised less


def test_expired_licence_is_flagged():
    assert "DOC_EXPIRED" in codes("expired_dl")


def test_watchlist_is_a_lead_not_a_verdict():
    _, data = scenario("watchlist")
    hit = [f for f in run_validation(REQ, {}, data, TODAY) if f["code"] == "WATCHLIST_HIT"]
    assert hit and hit[0]["severity"] == "critical"
    assert "not a determination" in hit[0]["message"]


def test_missing_document_is_flagged():
    _, data = scenario("clean")
    data.pop("aadhaar")
    assert "MISSING_DOCUMENT" in [f["code"] for f in run_validation(REQ, {}, data, TODAY)]


def test_evidence_never_contains_full_id_numbers():
    import json
    _, data = scenario("mismatch")
    blob = json.dumps(run_validation(REQ, {}, data, TODAY))
    for doc in data.values():
        for key in ("aadhaar_number", "pan_number", "dl_number"):
            if doc["fields"].get(key):
                assert doc["fields"][key] not in blob


def test_scoring_is_a_pure_function_of_flags():
    _, data = scenario("mismatch")
    flags = run_validation(REQ, {}, data, TODAY)
    assert score_flags(flags) == score_flags(list(flags))
