"""Regenerate synthetic demo documents and OCR fixtures:  python -m scripts.generate_samples"""
from app.config import get_settings
from app.synthetic import generate_all

if __name__ == "__main__":
    s = get_settings()
    m = generate_all(s.samples_dir, s.fixture_dir)
    print(f"Generated {len(m)} scenarios into {s.samples_dir}")
