"""Demo helpers (only mounted when DEMO_MODE=true): sample documents for the upload dialog and a reset button."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..config import get_settings
from ..deps import require_role
from ..models import User
from ..services.turns import reset_customer_data

router = APIRouter(prefix="/demo", tags=["demo"])


def _samples() -> Path:
    return Path(get_settings().samples_dir)


@router.get("/samples")
async def samples() -> list[dict]:
    manifest = _samples() / "manifest.json"
    if not manifest.exists():
        return []
    data = json.loads(manifest.read_text())
    return [{"key": k, **v} for k, v in data.items()]


@router.get("/samples/{scenario}/{doc_type}")
async def sample_file(scenario: str, doc_type: str):
    path = (_samples() / scenario / f"{doc_type}.png").resolve()
    if not path.is_file() or _samples().resolve() not in path.parents:  # no path traversal
        raise HTTPException(404, "Sample not found")
    return FileResponse(path, media_type="image/png")


@router.post("/reset")
async def reset(user: User = Depends(require_role("customer"))) -> dict:
    await reset_customer_data(user)
    return {"ok": True}
