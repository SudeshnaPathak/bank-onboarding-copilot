"""Central settings. Everything is overridable via environment variables or backend/.env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    env: str = "dev"
    # Database: sqlite for zero-setup dev, postgresql+asyncpg://... in docker-compose
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'app.db'}"
    # LangGraph checkpoint store (review graph interrupt/resume). sqlite path or postgres URL.
    checkpoint_url: str = str(BASE_DIR / "data" / "checkpoints.db")

    jwt_secret: str = "dev-only-change-me"
    jwt_ttl_minutes: int = 480
    fernet_key: str = ""  # required outside dev; auto-generated in dev

    storage_dir: str = str(BASE_DIR / "data" / "files")
    max_upload_mb: int = 8
    # Paddle 3.x enables oneDNN/MKLDNN on CPU by default, which crashes on some builds with
    # 'ConvertPirAttribute2RuntimeAttribute not support ...'. Off is the safe default; turn on only if it works for you.
    paddle_enable_mkldnn: bool = False
    max_pdf_pages: int = 5           # an ID document is 1-2 pages; more is almost certainly the wrong file
    pdf_render_dpi: int = 200        # used when a scanned PDF has to be rasterised for OCR

    # LLM: "auto" uses the gateway-backed Gemini service when AIPG_API_KEY is set, otherwise the rule-based service.
    llm_provider: str = "auto"  # auto | gemini | rules
    aipg_api_key: str = ""
    # US production. The base URL already includes /v1, so do not append another one.
    # EU hosting / data residency: https://openai.generative-eu.engine.capgemini.com/v1
    aipg_base_url: str = "https://openai.generative.engine.capgemini.com/v1"
    gemini_model: str = "gemini-3.8-flash"  # verify with models.list() for your Studio
    gemini_router_model: str = ""  # optional cheaper model for routing

    # OCR: "auto" = PaddleOCR when installed, else fixture engine (deterministic demo/tests)
    ocr_engine: str = "auto"  # auto | paddle | fixture
    fixture_dir: str = str(BASE_DIR / "fixtures" / "ocr")

    demo_mode: bool = True  # seeds demo users, exposes /demo sample documents
    samples_dir: str = str(BASE_DIR.parent / "samples")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    rate_limit_per_min: int = 60


def _ensure_dirs(s: Settings) -> None:
    """SQLite, the checkpoint store, encrypted uploads and the dev key all live under data/, which is not shipped in the zip."""
    dirs = [BASE_DIR / "data", Path(s.storage_dir)]
    if s.database_url.startswith("sqlite"):
        dirs.append(Path(s.database_url.split(":///", 1)[1]).parent)
    if "://" not in s.checkpoint_url:
        dirs.append(Path(s.checkpoint_url).parent)
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    _ensure_dirs(s)
    return s
