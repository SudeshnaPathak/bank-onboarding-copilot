from app.services import flow
from app.services.form_schema import validate
from tests.unit.helpers import scenario


def test_mobile_validation():
    assert validate("mobile", "+91 98765 43210")[:2] == (True, "9876543210")
    assert validate("mobile", "12345")[0] is False
    assert validate("mobile", "5876543210")[0] is False  # must start with 6-9


def test_email_and_bool_validation():
    assert validate("email", "Priya@Example.com")[1] == "priya@example.com"
    assert validate("email", "priya@")[0] is False
    assert validate("us_tax_resident", "No")[1] is False
    assert validate("consent", "yes")[1] is True
    assert validate("consent", "maybe")[0] is False


def test_nominee_can_be_skipped():
    assert validate("nominee_name", "Skip")[:2] == (True, "")
    assert validate("nominee_name", "asha sharma")[1] == "Asha Sharma"


def test_clean_documents_need_no_confirmation():
    extracted, _ = scenario("clean")
    assert flow.pending_confirmations(extracted, {}) == []


def test_mismatched_documents_ask_customer_to_confirm():
    extracted, _ = scenario("mismatch")
    # the scenario has a DOB conflict, an address conflict and a low-confidence name on the Aadhaar card
    assert flow.pending_confirmations(extracted, {}) == ["name", "dob", "address"]
    done = {"confirmations": {"name": "PRIYA SHARMA", "dob": "14/03/1998", "address": "12 Park Street, Kolkata - 700016"}}
    assert flow.pending_confirmations(extracted, done) == []


def test_next_step_order_is_documents_then_confirmations_then_fields():
    extracted, _ = scenario("clean")
    assert flow.next_step("basic_savings", set(), {}, {})["kind"] == "upload"
    docs = {"pan", "aadhaar", "driving_licence"}
    assert flow.next_step("basic_savings", docs, extracted, {})["field"] == "mobile"
    full = {"mobile": "9876543210", "email": "a@b.co", "occupation": "Salaried", "nominee_name": "",
            "us_tax_resident": False, "consent": True}
    assert flow.next_step("basic_savings", docs, extracted, full)["kind"] == "ready"


def test_declined_consent_blocks_submission():
    extracted, _ = scenario("clean")
    full = {"mobile": "9876543210", "email": "a@b.co", "occupation": "Salaried", "nominee_name": "",
            "us_tax_resident": False, "consent": False}
    assert flow.next_step("basic_savings", {"pan", "aadhaar", "driving_licence"}, extracted, full)["kind"] == "blocked"
