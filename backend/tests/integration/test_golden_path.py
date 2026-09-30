"""End to end through the real API, chat graph, review graph (interrupt/resume), database and audit chain."""
from tests.conftest import SAMPLES  # noqa: F401


def answer(api, h, cid, field, value):
    return api.state(api.chat(h, cid, action={"type": "answer", "field": field, "value": value}))


def complete_details(api, h, cid):
    for field, value in [("mobile", "9876543210"), ("email", "priya@example.com"), ("occupation", "Salaried"),
                         ("nominee_name", "Skip"), ("us_tax_resident", "No"), ("consent", "Yes")]:
        state = answer(api, h, cid, field, value)
    return state


def test_clean_application_end_to_end(api):
    cust, analyst = api.login("priya@example.com"), api.login("ravi@bank.example.com")
    cid = api.fresh_case(cust)

    for doc in ("pan", "aadhaar", "driving_licence"):
        evs = api.upload(cust, cid, doc)
        assert {"router", "document", "intake"} & {e["data"]["node"] for e in evs if e["event"] == "node"} >= {"document", "intake"}
    state = complete_details(api, cust, cid)
    assert state["next_step"]["kind"] == "ready"

    submitted = api.state(api.chat(cust, cid, action={"type": "submit"}))
    assert submitted["status"] == "under_review"

    queue = api.c.get("/api/review/queue", headers=analyst).json()
    row = next(r for r in queue if r["id"] == cid)
    assert row["analysis_ready"] and row["score"] == 100 and row["flag_count"] == 0

    detail = api.c.get(f"/api/review/{cid}", headers=analyst).json()
    assert detail["analysis"]["band"] == "clean" and detail["can_decide"]
    aadhaar = [f for d in detail["documents"] for f in d["fields"] if f["key"] == "aadhaar_number"]
    assert aadhaar and all(f["value"].startswith("XXXX XXXX") for f in aadhaar)  # analysts see masked identifiers

    r = api.c.post(f"/api/review/{cid}/decide", json={"action": "approve"}, headers=analyst)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    final = api.c.get(f"/api/cases/{cid}", headers=cust).json()
    assert final["status"] == "approved"
    assert "approved" in final["messages"][-1]["text"].lower()
    assert api.c.get("/api/audit/verify", headers=analyst).json()["valid"] is True


def test_mismatch_is_flagged_and_customer_confirmation_is_recorded(api):
    cust, analyst = api.login("priya@example.com"), api.login("ravi@bank.example.com")
    cid = api.fresh_case(cust)
    for doc in ("pan", "aadhaar", "driving_licence"):
        state = api.state(api.upload(cust, cid, doc, scenario="mismatch"))
    assert state["next_step"] == {"kind": "confirm", "field": "name"}
    for field, value in [("name", "PRIYA SHARMA"), ("dob", "14/03/1998"), ("address", "12 Park Street, Kolkata, West Bengal - 700016")]:
        api.chat(cust, cid, action={"type": "confirm", "field": field, "value": value})
    complete_details(api, cust, cid)
    api.chat(cust, cid, action={"type": "submit"})
    detail = api.c.get(f"/api/review/{cid}", headers=analyst).json()
    codes = {f["code"] for f in detail["analysis"]["flags"]}
    assert {"DOB_MISMATCH", "ADDRESS_MISMATCH"} <= codes
    assert detail["analysis"]["band"] != "clean"
    assert any(a["action"] == "field.confirmed" for a in detail["audit"])


def test_blurry_document_is_rejected_with_actionable_advice(api):
    cust = api.login("priya@example.com")
    cid = api.fresh_case(cust)
    evs = api.upload(cust, cid, "pan", scenario="blurry")
    state = api.state(evs)
    assert "pan" not in [d["doc_type"] for d in state["documents"]]
    assert "PAN card" in state["messages"][-2]["text"]  # feedback names the document and what to fix
    retake = api.state(api.upload(cust, cid, "pan", scenario="blurry", name="pan_retake"))
    assert "pan" in [d["doc_type"] for d in retake["documents"]]


def test_request_info_reopens_the_application(api):
    cust, analyst = api.login("priya@example.com"), api.login("ravi@bank.example.com")
    cid = api.fresh_case(cust)
    for doc in ("pan", "aadhaar", "driving_licence"):
        api.upload(cust, cid, doc)
    complete_details(api, cust, cid)
    api.chat(cust, cid, action={"type": "submit"})
    assert api.c.post(f"/api/review/{cid}/decide", json={"action": "request_info"}, headers=analyst).status_code == 422
    r = api.c.post(f"/api/review/{cid}/decide", json={"action": "request_info", "note": "Please re-upload a clearer Aadhaar"}, headers=analyst)
    assert r.json()["status"] == "info_requested"
    resubmitted = api.state(api.chat(cust, cid, action={"type": "submit"}))
    assert resubmitted["status"] == "under_review" and resubmitted["submission_no"] == 2
