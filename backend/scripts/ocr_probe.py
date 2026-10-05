"""Debug any document: raw OCR lines (with scores) -> English-only lines -> parsed fields -> missing fields.

    cd backend
    python -m scripts.ocr_probe "dummyIds/Driving Licence.pdf" --type driving_licence
    python scripts/ocr_probe.py dummyIds/Driving Licence.pdf --type driving_licence   # also works, even unquoted
    python -m scripts.ocr_probe PAN.jpeg --type pan --engine paddle     # default: paddle if installed
    python -m scripts.ocr_probe Aadhar.pdf --type aadhaar --engine tesseract   # needs tesseract + pytesseract

PDFs are rasterised with pypdfium2 and white margins are cropped before OCR (an A4 page with a card in the
middle wastes pixels and hurts both OCR and any sharpness check).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/, so `app` imports work however this is run

from PIL import Image, ImageChops, ImageOps

from app.ocr.parsers import PARSERS
from app.ocr.parsers.common import prepare

try:
    from app.ocr.pipeline import REQUIRED_FIELDS
except ImportError:  # different pipeline layout: skip the 'missing fields' summary
    REQUIRED_FIELDS = {}

ALIASES = {"driving_license": "driving_licence", "licence": "driving_licence", "license": "driving_licence",
           "dl": "driving_licence", "aadhar": "aadhaar"}


def autocrop(img: Image.Image, margin: int = 12) -> Image.Image:
    diff = ImageChops.difference(img, Image.new(img.mode, img.size, (255, 255, 255))).convert("L").point(lambda p: 255 if p > 18 else 0)
    box = diff.getbbox()
    if not box:
        return img
    l, t, r, b = box
    return img.crop((max(l - margin, 0), max(t - margin, 0), min(r + margin, img.width), min(b + margin, img.height)))


def pages(path: str) -> list[Image.Image]:
    if path.lower().endswith(".pdf"):
        import pypdfium2 as pdfium
        return [autocrop(p.render(scale=2.5).to_pil().convert("RGB")) for p in pdfium.PdfDocument(path)]
    return [ImageOps.exif_transpose(Image.open(path)).convert("RGB")]


def read_paddle(img: Image.Image, tmp: str) -> list[tuple[str, float]]:
    from app.ocr.engine import PaddleEngine
    img.save(tmp)
    return PaddleEngine().read(tmp)


def read_tesseract(img: Image.Image, tmp: str) -> list[tuple[str, float]]:
    import pytesseract
    d = pytesseract.image_to_data(img, lang="eng", config="--psm 11", output_type=pytesseract.Output.DICT)
    rows: dict[tuple, list[int]] = {}
    for i, t in enumerate(d["text"]):
        if t.strip() and float(d["conf"][i]) >= 0:
            rows.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(i)
    items = []
    for idx in rows.values():
        idx.sort(key=lambda i: d["left"][i])
        items.append((min(d["top"][i] for i in idx), min(d["left"][i] for i in idx), " ".join(d["text"][i] for i in idx),
                      sum(float(d["conf"][i]) for i in idx) / len(idx) / 100))
    return [(t, round(c, 2)) for _, _, t, c in sorted(items)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="+", help="path to the document (spaces are fine, quoted or not)")
    ap.add_argument("--type", required=True, type=lambda v: ALIASES.get(v.lower(), v.lower()), choices=sorted(PARSERS))
    ap.add_argument("--engine", default="auto", choices=["auto", "paddle", "tesseract"])
    args = ap.parse_args()
    args.file = " ".join(args.file)
    if not Path(args.file).is_file():
        ap.error(f"file not found: {args.file!r} (run from the backend folder, or give the full path)")

    engine = args.engine
    if engine == "auto":
        from app.ocr.engine import paddle_available
        engine = "paddle" if paddle_available() else "tesseract"
    read = read_paddle if engine == "paddle" else read_tesseract

    all_lines: list[tuple[str, float]] = []
    for n, img in enumerate(pages(args.file)):
        lines = read(img, f"/tmp/_probe_p{n}.png")
        print(f"\n--- page {n} ({img.size[0]}x{img.size[1]}) raw OCR [{engine}]")
        for t, s in lines:
            print(f"  {s:4.2f}  {t}")
        all_lines += lines

    texts, scores = prepare([t for t, _ in all_lines], [s for _, s in all_lines])
    print("\n--- English-only lines used by the parser")
    for t, s in zip(texts, scores):
        print(f"  {s:4.2f}  {t}")
    fields = PARSERS[args.type]([t for t, _ in all_lines], [s for _, s in all_lines])
    print("\n--- parsed fields")
    for k, v in fields.items():
        print(f"  {k:15} {v}")
    if REQUIRED_FIELDS:
        missing = [f for f in REQUIRED_FIELDS[args.type] if not fields.get(f)]
        print(f"\n--- missing required fields: {missing or 'none'}")


if __name__ == "__main__":
    main()