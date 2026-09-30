from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import get_settings

_MAGIC = {
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"%PDF": ("pdf", "application/pdf"),
}


# Active content has no place in an ID scan. This is a best-effort byte scan (names can be obfuscated or sit inside
# compressed object streams), so it is defence in depth: the PDF is never executed here, and analysts are shown
# server-rendered page images rather than the original file.
_PDF_ACTIVE = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia)(?![A-Za-z0-9])")


class UploadRejected(ValueError):
    pass


@dataclass
class CheckedUpload:
    ext: str
    content_type: str


def check_upload(data: bytes) -> CheckedUpload:
    """Validate by content (magic bytes) and size, never by the client's filename or MIME header."""
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise UploadRejected(f"File is too large (limit {get_settings().max_upload_mb} MB).")
    for magic, (ext, ctype) in _MAGIC.items():
        if data.startswith(magic):
            if ext == "pdf" and _PDF_ACTIVE.search(data):
                raise UploadRejected("This PDF contains scripts or attachments, which we can't accept. "
                                     "Please upload a plain scan or a photo.")
            return CheckedUpload(ext, ctype)
    raise UploadRejected("Please upload a JPG, PNG or PDF file.")
