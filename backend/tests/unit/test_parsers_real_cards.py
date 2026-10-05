"""Regression tests built from the bilingual sample cards (PAN, Aadhaar front+back, driving licence front+back).

REAL_* are verbatim Tesseract output (text, confidence) captured from the sample files, including the Hindi
garbage and QR-code noise. The clean_* variants are what a good OCR engine returns, in different reading orders.
"""
import pytest

from app.ocr.parsers import PARSERS
from app.ocr.parsers.common import english_part
from app.rules.matchers import names_compatible, same_value

REAL_PAN = [("arene fart WRd Arar", .17), ("INCOME TAX DEPARTMENT", .96), ("GOVT. OF INDIA", .95), ("eure crear Gear Hrs", .38), ("Mere", 0), ("ay", .2), ("ahi", .16), ("ey", .52), ("d", .12), ("Permanent Account Number Car", .96), ("ai", .14), ("Re,", .3), ("8", .27), ("sto", .35), ("Bes", .46), ("PRIYA1234S", .89), ("ane)", .2), ("eh", .68), ("=3", .05), ("a4 / Name", .75), ("«4", .06), ("7;", .48), ("ftrat staf / Priya Sharma", .64), ("Thar", .35), ("fiat a1 ATF / Father's Name", .64), ("BAe Par / SUNIL KUMAR", .81), ("ora ft arta /", .49), ("“Bignabiine", .25), ("Date of Birth", .96), ("04/08/1990", .6), ("Feerert / Signature", .56)]
REAL_AADHAAR = [("g", .5), ("RGR", .37), ("- Governmentofindia", .27), ("a", .13), ("far raf", .51), ("Priya Sharma", .96), ("fOar at 41a / Father's Name: RAJESH SHARMA", .73), ("wa fafa / DOB: 05/08/1995", .83), ("Cie?", .31), ("feet / Female", .61), ("4.", .34), ("gat", .36), ("re “Ant", .27), ("123 Main St", .95), ("vet", .14), ("Lt", .53), ("New Delhi - 110001", .93), ("ee)", .1), ("x", .77), ("44", .57), ("Oy eh", .23), ("1234 5678 9101", .95), ("see — sa snes ar after", .45),
                ("«rede fate gare matte", .06), ("“A", .54), ("~ Identification Unique Authority of India", .7), ("AADHAAR", .46), ("Address:", .96), ("123 Main St, New Delhi - 110001", .91), ("1234 5678 9101", .96), ("1947", .96), ("support@", .46), ("www.uidai.gov.in", .76)]
REAL_DL = [("UNION OF INDIA Driving Licence (Rr) (7)", .67), ("AR02 2021 0000075", .85), ("wou", .5), ("arate act", .2), ("Date of Issue", .95), ("Validity", .96), ("15-09-2023", .96), ("@® 11-01-2048", .74), ("cre", .31), ("ae", .14), ("Date of Birth", .97), ("Blood Group", .96), ("05/08/1995", .96), ("B+", .96), ("Name", .96), ("—", .6), ("PRIYA SHARMA", .94), ("Father's Name", .68), ("RAJESH SHARMA", .96), ("PRIYA SHARMA", .96),
           ("Mobile No.", .95), ("AR02 2021 0000075", .77), ("siiiaad {", .01), ("Endorsement Date", .96), ("15-09-2023", .8), ("LMV", .9), ("M", .92), ("15-09-2023", .96), ("15-09-2023", .96), ("15-09-2023", .96), ("Endorsement No.", .96), ("Present Address", .96), ("AR02/DLE/0000053/2023", .44), ("HNO 123, Street No 4,", .96), ("Pitam Pura,", .94), ("New Delhi - 110034,", .94), ("Delhi, India.", .96), ("Valid only if produced with front side.", .96), ("a", .08), ("-", .37), ("This is a copy. Issued for reference only.", .95), ("Dp ‘", .31), ("Sharma", .8), ("Issuing Authority", .94), ("Holder's Signature", .66), ("DTO, NEW DELHI", .93)]


def run(doc, rows):
    return PARSERS[doc]([t for t, _ in rows], [s for _, s in rows])


# ------------------------------------------------------------------ PAN
def test_pan_name_from_real_ocr_without_llm_fallback():
    out = run("pan", REAL_PAN)
    assert out["name"] == "Priya Sharma"            # was: missed, filled by the AI fallback
    assert out["father_name"] == "Sunil Kumar"
    assert out["pan_number"] == "PRIYA1234S"
    assert out["dob"] == "04/08/1990"


def test_pan_clean_bilingual_with_curly_apostrophe():
    lines = ["आयकर विभाग", "INCOME TAX DEPARTMENT", "भारत सरकार", "GOVT. OF INDIA", "स्थायी लेखा संख्या कार्ड",
             "Permanent Account Number Card", "PRIYA1234S", "नाम / Name", "प्रिया शर्मा / Priya Sharma",
             "पिता का नाम / Father\u2019s Name", "सुनील कुमार / SUNIL KUMAR", "जन्म की तारीख /", "Date of Birth",
             "04/08/1990", "Signature", "हस्ताक्षर / Signature"]
    out = PARSERS["pan"](lines)
    assert (out["name"], out["father_name"], out["dob"]) == ("Priya Sharma", "Sunil Kumar", "04/08/1990")


def test_pan_hindi_dropped_entirely_by_ocr():
    out = PARSERS["pan"](["INCOME TAX DEPARTMENT", "PRIYA1234S", "Name", "Priya Sharma", "Father's Name", "SUNIL KUMAR", "Date of Birth", "04/08/1990"])
    assert out["name"] == "Priya Sharma" and out["father_name"] == "Sunil Kumar"


def test_pan_positional_fallback_when_no_label_is_readable():
    out = PARSERS["pan"](["INCOME TAX DEPARTMENT", "GOVT. OF INDIA", "PRIYA1234S", "Priya Sharma", "SUNIL KUMAR", "04/08/1990"])
    assert out["name"] == "Priya Sharma" and out["father_name"] == "Sunil Kumar" and out["dob"] == "04/08/1990"


# ------------------------------------------------------------------ Aadhaar
def test_aadhaar_name_and_address_from_real_ocr():
    out = run("aadhaar", REAL_AADHAAR)
    assert out["name"] == "Priya Sharma"            # not the Hindi-garbage line "far raf"
    assert out["address"] == "123 Main St, New Delhi - 110001"
    assert out["dob"] == "05/08/1995" and out["gender"] == "Female"
    assert out["aadhaar_number"] == "123456789101"


def test_aadhaar_front_only_reads_unlabelled_address_and_ignores_qr_noise():
    out = run("aadhaar", REAL_AADHAAR[:23])
    assert out["address"] == "123 Main St, New Delhi - 110001"
    assert out["name"] == "Priya Sharma"


def test_aadhaar_back_only_reads_labelled_address():
    out = run("aadhaar", REAL_AADHAAR[23:])
    assert out["address"] == "123 Main St, New Delhi - 110001"
    assert "name" not in out


def test_aadhaar_clean_bilingual():
    lines = ["भारत सरकार", "Government of India", "प्रिया शर्मा", "Priya Sharma", "पिता का नाम / Father\u2019s Name: RAJESH SHARMA",
             "जन्म तिथि / DOB: 05/08/1995", "महिला / Female", "123 Main St,", "New Delhi - 110001", "1234 5678 9101"]
    out = PARSERS["aadhaar"](lines)
    assert out["name"] == "Priya Sharma" and out["address"] == "123 Main St, New Delhi - 110001"


def test_aadhaar_year_of_birth_only():
    out = PARSERS["aadhaar"](["Government of India", "Priya Sharma", "Year of Birth: 1995", "Female", "2345 6789 0124"])
    assert out["dob"] == "1995" and out["name"] == "Priya Sharma"


# ------------------------------------------------------------------ Driving licence
def test_dl_dates_from_real_ocr():
    out = run("driving_licence", REAL_DL)
    assert out["issue_date"] == "15/09/2023"
    assert out["valid_till"] == "11/01/2048"        # was: 15/09/2023 (the first date, i.e. the issue date)
    assert out["dob"] == "05/08/1995"               # was: missed, because the line after 'Date of Birth' is 'Blood Group'
    assert out["dl_number"] == "AR0220210000075"


def test_dl_address_and_name_from_real_ocr():
    out = run("driving_licence", REAL_DL)
    assert out["address"] == "HNO 123, Street No 4, Pitam Pura, New Delhi - 110034, Delhi, India"  # skips AR02/DLE/... line
    assert out["name"] == "Priya Sharma" and out["father_name"] == "Rajesh Sharma"


def test_dl_column_major_reading_order():
    lines = ["AR02 2021 0000075", "Date of Issue", "15-09-2023", "Validity", "(NT) 11-01-2048", "Date of Birth", "05/08/1995",
             "Blood Group", "B+", "Name", "PRIYA SHARMA", "Father's Name", "RAJESH SHARMA"]
    out = PARSERS["driving_licence"](lines)
    assert (out["issue_date"], out["valid_till"], out["dob"]) == ("15/09/2023", "11/01/2048", "05/08/1995")


def test_dl_labels_with_inline_values():
    out = PARSERS["driving_licence"](["DL No: WB0620190012345", "Name: PRIYA SHARMA", "DOB: 14/03/1998", "Issue Date: 20/07/2019",
                                      "Valid Till: 13/03/2038", "Address: Flat 4B, Lake View Apartments,", "Kolkata, West Bengal - 700091"])
    assert (out["dob"], out["issue_date"], out["valid_till"]) == ("14/03/1998", "20/07/2019", "13/03/2038")
    assert out["address"].endswith("Kolkata, West Bengal - 700091")


def test_dl_never_returns_issue_date_as_expiry_when_validity_value_is_missing():
    out = PARSERS["driving_licence"](["AR02 2021 0000075", "Date of Issue", "Validity", "15-09-2023", "Date of Birth", "05/08/1995"])
    assert out.get("valid_till") != out["issue_date"]


def test_dl_sanity_repair_when_labels_pair_wrongly():
    # validity label got paired with the earlier date: the sanity layer must fix it from the dates themselves
    out = PARSERS["driving_licence"](["Validity", "15-09-2023", "Date of Issue", "15-09-2023", "Date of Birth", "05/08/1995", "(NT) 11-01-2048"])
    assert out["valid_till"] == "11/01/2048"


# ------------------------------------------------------------------ helpers & case-insensitive comparison
@pytest.mark.parametrize("raw,expected", [
    ("ftrat staf / Priya Sharma", "Priya Sharma"), ("a4 / Name", "Name"), ("ora ft arta /", ""),
    ("wa fafa / DOB: 05/08/1995", "DOB: 05/08/1995"), ("04/08/1990", "04/08/1990"),
    ("12/A Park Street, Kolkata - 700016", "12/A Park Street, Kolkata - 700016"), ("Father\u2019s Name", "Father's Name"),
])
def test_english_part(raw, expected):
    assert english_part(raw) == expected


@pytest.mark.parametrize("a,b", [("PRIYA SHARMA", "Priya Sharma"), ("priya sharma", "PRIYA SHARMA"), ("Priya  Sharma", "PRIYA SHARMA"),
                                 ("SHARMA PRIYA", "Priya Sharma"), ("P. Sharma", "PRIYA SHARMA")])
def test_names_match_ignoring_case_spacing_order_and_initials(a, b):
    assert names_compatible(a, b) and same_value("name", a, b)


def test_different_names_still_differ():
    assert not names_compatible("Priya Sharma", "Pooja Verma")


def test_cross_document_names_from_real_ocr_agree():
    names = {run("pan", REAL_PAN)["name"], run("aadhaar", REAL_AADHAAR)["name"], run("driving_licence", REAL_DL)["name"]}
    assert len(names) == 1  # one canonical value, so the customer is never asked to choose between 'PRIYA' and 'Priya'
