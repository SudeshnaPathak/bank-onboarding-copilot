"""Cheap pre-OCR image-quality gate so the chat can say 'please retake' immediately."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

from . import pdf

QUALITY_MESSAGES = {
    "low_resolution": "The photo is too small to read clearly. Please upload a larger image.",
    "blurry": "The photo looks blurry. Please retake it in good light and hold the phone steady.",
    "unreadable_image": "I couldn't open that file. Please upload a JPG, PNG or PDF.",
}
QUALITY_MESSAGES.update({code: pdf.message_for(code) for code in pdf.PDF_MESSAGES})


def assess_quality(path: str, min_side: int = 500, min_sharpness: float = 60.0) -> dict:
    """Thresholds are starting points: tune them on your own sample photos."""
    if path.lower().endswith(".pdf"):
        # The photo blur/size checks are tuned for card-sized images and would misfire on a mostly-white A4 page,
        # so for PDFs the gate checks that the file opens and is within limits. OCR confidence (per field) and the
        # rules engine catch a poor scan later.
        try:
            info = pdf.inspect(path)
        except pdf.PdfProblem as exc:
            return {"ok": False, "issues": [exc.code]}
        return {"ok": True, "issues": [], "pdf_pages": info.pages, "pdf_kind": info.kind}
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            w, h = img.size
            gray = img.convert("L")
            gray.thumbnail((1200, 1200))
            g = np.asarray(gray, dtype=np.float64)
    except Exception:
        return {"ok": False, "issues": ["unreadable_image"]}
    issues: list[str] = []
    if min(w, h) < min_side:
        issues.append("low_resolution")
    lap = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    sharpness = float(lap.var())
    if sharpness < min_sharpness:
        issues.append("blurry")
    return {"ok": not issues, "issues": issues, "width": w, "height": h, "sharpness": round(sharpness, 1)}
