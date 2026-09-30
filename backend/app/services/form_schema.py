"""Schema-driven application form. The conversation collects these fields; nothing is hard-coded in prompts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PRODUCTS = {
    "basic_savings": {"name": "Basic Savings Account", "documents": ["pan", "aadhaar", "driving_licence"]},
}

DOC_LABELS = {"pan": "PAN card", "aadhaar": "Aadhaar card", "driving_licence": "Driving licence"}
DOC_WHY = {
    "pan": "Your PAN is your tax identity. Banks must record it to open an account.",
    "aadhaar": "Your Aadhaar confirms your identity and address.",
    "driving_licence": "A driving licence is an extra proof of your address and date of birth, and shows it is still valid.",
}
DOC_TIPS = ["Place the card on a flat surface in good light", "Keep all four corners in the photo", "Avoid glare and shadows"]

FIELD_LABELS = {"name": "Name", "dob": "Date of birth", "address": "Address", "pan_number": "PAN number",
                "aadhaar_number": "Aadhaar number", "dl_number": "Licence number", "valid_till": "Valid till",
                "father_name": "Father's name", "gender": "Gender", "issue_date": "Issue date"}

OCCUPATIONS = ["Salaried", "Self-employed", "Student", "Homemaker", "Retired", "Other"]
RELATIONS = ["Spouse", "Parent", "Child", "Sibling", "Other"]


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    ask: str
    why: str
    kind: str  # text | choice | bool
    choices: list[str] = field(default_factory=list)
    optional: bool = False


FIELDS: list[FieldSpec] = [
    FieldSpec("mobile", "Mobile number", "What's your 10-digit mobile number?",
              "We send one-time passwords and account alerts to it.", "text"),
    FieldSpec("email", "Email", "And your email address?", "We use it for statements and important notices.", "text"),
    FieldSpec("occupation", "Occupation", "Which best describes what you do?",
              "Banks record occupation to understand how the account will be used.", "choice", OCCUPATIONS),
    FieldSpec("nominee_name", "Nominee", "Would you like to add a nominee? Type their name, or choose Skip.",
              "A nominee receives the balance if something happens to you. It's optional.", "text", optional=True),
    FieldSpec("nominee_relation", "Nominee relationship", "How is your nominee related to you?",
              "We record the relationship with the nominee's name.", "choice", RELATIONS),
    FieldSpec("us_tax_resident", "US tax resident", "Are you a tax resident of the United States?",
              "This is the FATCA declaration: banks must ask every customer. Most customers answer No.", "bool"),
    FieldSpec("consent", "Declaration", "Do you confirm the details are correct and agree to the account terms?",
              "We need your confirmation before sending the application to a reviewer.", "bool"),
]
FIELD_BY_KEY = {f.key: f for f in FIELDS}

_YES = re.compile(r"^(y|yes|yeah|yep|sure|correct|right|i do|i agree|agree|confirm|ok|okay|true)\b", re.I)
_NO = re.compile(r"^(n|no|nope|nah|not|false|i don'?t|disagree)\b", re.I)
_SKIP = re.compile(r"^(skip|none|no|not now|later|na|n/a|no nominee)\W*$", re.I)


def is_yes(text: str) -> bool:
    return bool(_YES.match(text.strip()))


def is_no(text: str) -> bool:
    return bool(_NO.match(text.strip()))


def validate(key: str, text: str) -> tuple[bool, object, str]:
    """(ok, normalised_value, friendly_error). Deterministic validators; the LLM only helps with free-text choices."""
    t = (text or "").strip()
    if key == "mobile":
        digits = re.sub(r"\D", "", t)
        digits = digits[-10:] if len(digits) > 10 and digits.startswith(("91", "0")) else digits
        if re.fullmatch(r"[6-9]\d{9}", digits):
            return True, digits, ""
        return False, None, "That doesn't look like a 10-digit Indian mobile number. It should start with 6, 7, 8 or 9."
    if key == "email":
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", t):
            return True, t.lower(), ""
        return False, None, "That email doesn't look right. It should look like name@example.com."
    if key in ("occupation", "nominee_relation"):
        for c in FIELD_BY_KEY[key].choices:
            if t.lower() == c.lower():
                return True, c, ""
        return False, None, ""  # caller may retry with the LLM parser, then re-ask
    if key == "nominee_name":
        if _SKIP.match(t):
            return True, "", ""
        if re.fullmatch(r"[A-Za-z .'-]{2,60}", t) and len(t.split()) >= 1:
            return True, t.title(), ""
        return False, None, "Please type the nominee's name using letters only, or choose Skip."
    if key in ("us_tax_resident", "consent"):
        if is_yes(t):
            return True, True, ""
        if is_no(t):
            return True, False, ""
        return False, None, "Please answer Yes or No."
    return False, None, "I didn't understand that."


def display(key: str, value) -> str:
    if key == "mobile" and value:
        return f"+91 {value[:2]}XXXXXX{value[-2:]}"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return "Skipped" if value == "" else str(value)
