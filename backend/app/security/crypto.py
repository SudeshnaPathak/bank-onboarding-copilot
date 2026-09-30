"""Encryption at rest for uploaded files and extracted PII (Fernet)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet

from ..config import BASE_DIR, get_settings


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        if get_settings().env != "dev":
            raise RuntimeError("FERNET_KEY must be set outside dev")
        keyfile = Path(BASE_DIR / "data" / "dev.key")
        keyfile.parent.mkdir(parents=True, exist_ok=True)
        if not keyfile.exists():
            keyfile.write_bytes(Fernet.generate_key())
        key = keyfile.read_text()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return _fernet().decrypt(token)


def encrypt_json(obj: dict) -> str:
    return _fernet().encrypt(json.dumps(obj).encode()).decode()


def decrypt_json(token: str) -> dict:
    return json.loads(_fernet().decrypt(token.encode()).decode()) if token else {}
