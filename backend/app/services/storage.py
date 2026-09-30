from __future__ import annotations

import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from ..config import get_settings
from ..security.crypto import decrypt_bytes, encrypt_bytes


def _dir() -> Path:
    p = Path(get_settings().storage_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_encrypted(data: bytes) -> str:
    key = f"{uuid.uuid4()}.bin"  # server-generated: client filenames never touch the filesystem
    (_dir() / key).write_bytes(encrypt_bytes(data))
    return key


def load_decrypted(key: str) -> bytes:
    return decrypt_bytes((_dir() / Path(key).name).read_bytes())


def delete(key: str) -> None:
    (_dir() / Path(key).name).unlink(missing_ok=True)


@contextmanager
def temp_plain_file(data: bytes, ext: str):
    """Plaintext copy exists only for the duration of OCR, then is removed."""
    fd, path = tempfile.mkstemp(suffix=f".{ext}")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        yield path
    finally:
        Path(path).unlink(missing_ok=True)
