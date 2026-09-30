"""PDFs through the real API: customer upload, chat feedback, submit, and the analyst viewer."""
import io

from PIL import Image
from pypdf import PdfReader, PdfWriter

from tests.conftest import SAMPLES
from tests.integration.test_golden_path import complete_details


def test_application_with_pdf_documents_end_to_end(api):
    cust, analyst = api.login("priya@example.com"), api.login("ravi@bank.example.com")
    cid = api.fresh_case(cust)

    # one of each kind: a scanned PDF, a text-layer PDF, and a plain photo
    api.upload(cust, cid, "pan", name="pan_scan", ext="pdf")
    api.upload(cust, cid, "aadhaar", name="aadhaar_text", ext="pdf")
    state = api.state(api.upload(cust, cid, "driving_licence"))
    assert {d["doc_type"] for d in state["documents"]} == {"pan", "aadhaar", "driving_licence"}

    state = complete_details(api, cust, cid)
    assert state["next_step"]["kind"] == "ready"
    assert api.state(api.chat(cust, cid, action={"type": "submit"}))["status"] == "under_review"

    detail = api.c.get(f"/api/review/{cid}", headers=analyst).json()
    assert detail["analysis"]["band"] == "clean"  # PDFs and photos of the same person reconcile cleanly
    by_type = {d["doc_type"]: d for d in detail["documents"]}
    assert by_type["pan"]["quality"]["pdf_kind"] == "scanned" and by_type["pan"]["pages"] == 1
    assert by_type["aadhaar"]["quality"]["pdf_kind"] == "text"
    assert "pdf_pages" not in by_type["driving_licence"]["quality"] and by_type["driving_licence"]["pages"] == 1
    sources = {f["source"] for d in detail["documents"] for f in d["fields"]}
    assert {"ocr", "pdf_text"} <= sources

    # identifiers stay masked for the analyst regardless of source format
    aad = [f for f in by_type["aadhaar"]["fields"] if f["key"] == "aadhaar_number"]
    assert aad and all(f["value"].startswith("XXXX XXXX") for f in aad)


def test_analyst_sees_a_rendered_image_never_the_pdf(api):
    cust, analyst = api.login("priya@example.com"), api.login("ravi@bank.example.com")
    cid = api.fresh_case(cust)
    api.upload(cust, cid, "pan", name="pan_scan", ext="pdf")
    api.upload(cust, cid, "aadhaar")
    detail = api.c.get(f"/api/review/{cid}", headers=analyst).json()
    pan = next(d for d in detail["documents"] if d["doc_type"] == "pan")
    aadhaar = next(d for d in detail["documents"] if d["doc_type"] == "aadhaar")

    r = api.c.get(f"/api/review/{cid}/documents/{pan['id']}/image", headers=analyst)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    assert r.content.startswith(b"\x89PNG") and Image.open(io.BytesIO(r.content)).width > 400

    assert api.c.get(f"/api/review/{cid}/documents/{pan['id']}/image?page=1", headers=analyst).status_code == 404  # 1-page PDF
    assert api.c.get(f"/api/review/{cid}/documents/{aadhaar['id']}/image?page=1", headers=analyst).status_code == 404  # image
    assert api.c.get(f"/api/review/{cid}/documents/{aadhaar['id']}/image", headers=analyst).status_code == 200
    assert api.c.get(f"/api/review/{cid}/documents/{pan['id']}/image", headers=cust).status_code == 403


def test_customer_gets_actionable_feedback_for_bad_pdfs(api):
    cust = api.login("priya@example.com")
    cid = api.fresh_case(cust)
    clean = SAMPLES / "clean"

    w = PdfWriter()
    w.append(PdfReader(str(clean / "pan_text.pdf")))
    w.encrypt("s3cret")
    buf = io.BytesIO()
    w.write(buf)
    state = api.state(api.upload_bytes(cust, cid, "pan", buf.getvalue(), "locked.pdf", "application/pdf"))
    assert "pan" not in [d["doc_type"] for d in state["documents"]]
    assert "password" in state["messages"][-2]["text"].lower()

    blank = io.BytesIO()
    Image.new("RGB", (900, 600), "white").save(blank, format="PDF")
    state = api.state(api.upload_bytes(cust, cid, "pan", blank.getvalue(), "blank.pdf", "application/pdf"))
    assert "pan" not in [d["doc_type"] for d in state["documents"]]
    assert "couldn't read any text" in state["messages"][-2]["text"]


def test_pdf_with_scripts_is_rejected_before_any_processing(api):
    cust = api.login("priya@example.com")
    cid = api.fresh_case(cust)
    evil = (SAMPLES / "clean" / "pan_text.pdf").read_bytes().replace(
        b"/Type /Catalog", b"/Type /Catalog /OpenAction << /S /JavaScript /JS (app.alert(1)) >>")
    r = api.upload_bytes(cust, cid, "pan", evil, "pan.pdf", "application/pdf", raw=True)
    assert r.status_code == 422 and "scripts" in r.json()["detail"]


def test_extension_and_mime_are_ignored_content_decides(api):
    cust = api.login("priya@example.com")
    cid = api.fresh_case(cust)
    pdf_bytes = (SAMPLES / "clean" / "pan_scan.pdf").read_bytes()
    # a PDF labelled as a PNG still goes down the PDF path...
    state = api.state(api.upload_bytes(cust, cid, "pan", pdf_bytes, "pan.png", "image/png"))
    assert "pan" in [d["doc_type"] for d in state["documents"]]
    # ...and a non-PDF labelled as one is refused
    r = api.upload_bytes(cust, cid, "aadhaar", b"MZ\x90\x00 not a pdf", "aadhaar.pdf", "application/pdf", raw=True)
    assert r.status_code == 422
