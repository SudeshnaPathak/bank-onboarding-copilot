"""OCR engines behind one interface.

PaddleEngine  - real OCR (install paddleocr + paddlepaddle). Untested in the sandbox this repo was built in.
FixtureEngine - deterministic, keyed by the file's sha256. Used for tests and offline demos with the
                bundled synthetic documents (see scripts/generate_samples.py).

Both expose read(image_path) and read_pdf(pdf_path). PDFs that already contain text never reach an engine;
see ocr/pipeline.py.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Protocol

from ..config import get_settings

Lines = list[tuple[str, float]]


class OcrEngine(Protocol):
    name: str

    def read(self, path: str) -> Lines: ...

    def read_pdf(self, path: str) -> Lines:
        """OCR a scanned PDF (all pages, in order)."""
        ...


def file_sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FixtureEngine:
    name = "fixture"

    def read(self, path: str) -> Lines:
        fx = Path(get_settings().fixture_dir) / f"{file_sha256(path)}.json"
        if not fx.exists():
            return []
        return [(str(t), float(s)) for t, s in json.loads(fx.read_text())["lines"]]

    def read_pdf(self, path: str) -> Lines:
        # Fixtures for PDFs are keyed by the PDF file itself. Rasterised pixels differ between pdfium versions,
        # so hashing the render would make the offline demo fragile.
        return self.read(path)


class PaddleEngine:
    name = "paddle"
    _lock = threading.Lock()  # the engine is a shared singleton; serialise predict calls
    _ocr = None

    @classmethod
    def _engine(cls):
        if cls._ocr is None:
            from paddleocr import PaddleOCR  # heavy import, only when actually used
            cls._ocr = PaddleOCR(lang="en", use_angle_cls=True, enable_mkldnn=get_settings().paddle_enable_mkldnn)
        return cls._ocr

    def read_pdf(self, path: str) -> Lines:
        from .pdf import rendered_pages  # rasterise pages to temp PNGs, deleted on exit
        lines: Lines = []
        with rendered_pages(path) as pages:
            for page_path in pages:
                lines += self.read(page_path)
        return lines

    def read(self, path: str) -> Lines:
        with self._lock:
            eng = self._engine()
            lines: Lines = []
            if hasattr(eng, "predict"):  # PaddleOCR 3.x
                for res in eng.predict(path):
                    texts, scores = res.get("rec_texts", []), res.get("rec_scores", [])
                    lines += [(str(t), float(s)) for t, s in zip(texts, scores)]
            else:  # PaddleOCR 2.x
                for page in eng.ocr(path, cls=True) or []:
                    for item in page or []:
                        text, conf = item[1]
                        lines.append((str(text), float(conf)))
            return lines


def paddle_available() -> bool:
    try:
        import paddleocr  # noqa: F401
        return True
    except Exception:
        return False


_engine: OcrEngine | None = None


def get_engine() -> OcrEngine:
    global _engine
    if _engine is None:
        choice = get_settings().ocr_engine
        use_paddle = choice == "paddle" or (choice == "auto" and paddle_available())
        _engine = PaddleEngine() if use_paddle else FixtureEngine()
    return _engine


def reset_engine() -> None:
    global _engine
    _engine = None
