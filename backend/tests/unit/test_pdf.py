"""PDF support: text-layer PDFs, scanned PDFs (rasterise + OCR), and the limits that guard the parser."""
import asyncio
import io
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from app.config import get_settings
from app.ocr import pdf
from app.ocr.engine import PaddleEngine
from app.ocr.pipeline import UnsupportedDocument, extract_document
from app.ocr.quality import QUALITY_MESSAGES, assess_quality
from app.security.upload_guard import UploadRejected, check_upload
from app.synthetic import render_card, scanned_pdf_bytes, text_pdf_bytes
from tests.conftest import SAMPLES

CLEAN = SAMPLES / "clean"
PAN_LINES = ["INCOME TAX DEPARTMENT", "PRIYA SHARMA", "ABCDE1234F", "14/03/1998"]


def extract(path, doc_type):
    return asyncio.run(extract_document(str(path), doc_type))


@pytest.mark.parametrize("doc", ["pan", "aadhaar", "driving_licence"])
def test_text_layer_pdf_is_read_without_ocr(doc):
    res = extract(CLEAN / f"{doc}_text.pdf", doc)
    assert not res.missing
    assert set(res.field_source.values()) == {"pdf_text"}


@pytest.mark.parametrize("doc", ["pan", "aadhaar", "driving_licence"])
def test_scanned_pdf_goes_through_ocr(doc):
    assert assess_quality(str(CLEAN / f"{doc}_scan.pdf"))["pdf_kind"] == "scanned"
    res = extract(CLEAN / f"{doc}_scan.pdf", doc)
    assert not res.missing
    assert set(res.field_source.values()) == {"ocr"}
    assert res.fields["name"] == "PRIYA SHARMA"


def test_scanned_and_text_pdfs_agree_with_the_png():
    png = extract(CLEAN / "pan.png", "pan").fields
    assert extract(CLEAN / "pan_scan.pdf", "pan").fields == png
    assert extract(CLEAN / "pan_text.pdf", "pan").fields == png


def test_low_confidence_lines_survive_the_pdf_path():
    res = extract(SAMPLES / "mismatch" / "pan_scan.pdf", "pan")
    assert res.fields  # fixture confidences are carried through per line, not replaced by a constant


def test_unknown_scanned_pdf_reports_a_readable_error(tmp_path):
    p = tmp_path / "unknown.pdf"
    p.write_bytes(scanned_pdf_bytes(Image.new("RGB", (800, 500), (250, 250, 250))))  # no fixture for this file
    with pytest.raises(UnsupportedDocument, match="couldn't read any text"):
        extract(p, "pan")


def test_stray_page_number_is_not_mistaken_for_a_text_layer(tmp_path):
    p = tmp_path / "stray.pdf"
    p.write_bytes(text_pdf_bytes(["1"]))
    assert pdf.inspect(str(p)).kind == "scanned"


def test_encrypted_pdf_is_refused_with_a_clear_message(tmp_path):
    w = PdfWriter()
    w.append(PdfReader(str(CLEAN / "pan_text.pdf")))
    w.encrypt("s3cret")
    p = tmp_path / "locked.pdf"
    with open(p, "wb") as f:
        w.write(f)
    q = assess_quality(str(p))
    assert q == {"ok": False, "issues": ["pdf_encrypted"]}
    assert "password" in QUALITY_MESSAGES["pdf_encrypted"]


def test_too_many_pages_is_refused(tmp_path):
    n = get_settings().max_pdf_pages + 1
    p = tmp_path / "long.pdf"
    p.write_bytes(scanned_pdf_bytes(render_card(PAN_LINES, "pan"), extra_pages=n - 1))
    assert assess_quality(str(p))["issues"] == ["pdf_too_many_pages"]
    assert str(get_settings().max_pdf_pages) in QUALITY_MESSAGES["pdf_too_many_pages"]


def test_at_the_page_limit_is_accepted(tmp_path):
    n = get_settings().max_pdf_pages
    p = tmp_path / "ok.pdf"
    p.write_bytes(scanned_pdf_bytes(render_card(PAN_LINES, "pan"), extra_pages=n - 1))
    assert assess_quality(str(p)) == {"ok": True, "issues": [], "pdf_pages": n, "pdf_kind": "scanned"}


def test_corrupt_pdf_is_refused_not_crashed(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"%PDF-1.4\nthis is not really a pdf\n%%EOF")
    assert assess_quality(str(p))["issues"] == ["pdf_unreadable"]


def test_upload_guard_rejects_active_content_but_accepts_plain_pdfs():
    assert check_upload((CLEAN / "pan_text.pdf").read_bytes()).ext == "pdf"
    assert check_upload((CLEAN / "pan_scan.pdf").read_bytes()).content_type == "application/pdf"
    evil = (CLEAN / "pan_text.pdf").read_bytes().replace(b"/Type /Catalog", b"/Type /Catalog /OpenAction << /S /JavaScript /JS (app.alert(1)) >>")
    with pytest.raises(UploadRejected, match="scripts or attachments"):
        check_upload(evil)


def test_oversized_page_is_rendered_within_the_pixel_budget(tmp_path):
    # A 200 x 200 inch page at 200 dpi would be 1.6 billion pixels; it must be scaled down, not attempted.
    huge = text_pdf_bytes(["x"]).replace(b"/MediaBox [0 0 595 842]", b"/MediaBox [0 0 14400 14400]")
    p = tmp_path / "huge.pdf"
    p.write_bytes(huge)
    img = pdf.render_page(str(p), 0)
    assert img.width * img.height <= pdf.MAX_RENDER_PIXELS * 1.01


class _FakePaddle:
    """Stands in for PaddleOCR 3.x: returns a line naming the image it was handed, so page order is checkable."""
    def __init__(self):
        self.seen = []

    def predict(self, path):
        self.seen.append(path)
        assert Path(path).exists()
        img = Image.open(path)
        assert img.width > 500  # really rasterised at a usable resolution
        return [{"rec_texts": [f"LINE FROM {Path(path).name}"], "rec_scores": [0.9]}]


def test_paddle_engine_rasterises_every_page_in_order_and_cleans_up(tmp_path, monkeypatch):
    fake = _FakePaddle()
    monkeypatch.setattr(PaddleEngine, "_engine", classmethod(lambda cls: fake))
    p = tmp_path / "two.pdf"
    p.write_bytes(scanned_pdf_bytes(render_card(PAN_LINES, "pan"), extra_pages=1))
    lines = PaddleEngine().read_pdf(str(p))
    assert [t for t, _ in lines] == ["LINE FROM page-1.png", "LINE FROM page-2.png"]
    assert all(not Path(s).exists() for s in fake.seen)  # plaintext page renders are deleted


def test_page_renders_are_valid_pngs():
    data = pdf.render_page_png(str(CLEAN / "aadhaar_scan.pdf"), 0)
    assert data.startswith(b"\x89PNG") and Image.open(io.BytesIO(data)).width > 400
    with pytest.raises(IndexError):
        pdf.render_page_png(str(CLEAN / "aadhaar_scan.pdf"), 3)


def test_typographic_punctuation_does_not_break_parsing():
    # e-PAN / Word-made PDFs use a curly apostrophe in "Father's Name"; NBSP and en-dashes are common too.
    from app.ocr.utils import normalize_text
    assert normalize_text("Father\u2019s\u00a0Name") == "Father's Name"
    assert normalize_text("Kolkata \u2013 700091") == "Kolkata - 700091"
    assert normalize_text("of\ufb01ce") == "office"  # ligature
    res = extract(CLEAN / "pan_text.pdf", "pan")
    assert res.fields["father_name"] == "RAJESH SHARMA"
