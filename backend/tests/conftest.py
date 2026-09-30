"""Test environment: temp database/storage, rule-based LLM, fixture OCR. Runs offline and deterministically."""
import json
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="onboarding-tests-"))
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP / 'app.db'}", "CHECKPOINT_URL": str(_TMP / "checkpoints.db"),
    "STORAGE_DIR": str(_TMP / "files"), "FIXTURE_DIR": str(_TMP / "fixtures"), "SAMPLES_DIR": str(_TMP / "samples"),
    "LLM_PROVIDER": "rules", "OCR_ENGINE": "fixture", "DEMO_MODE": "true", "RATE_LIMIT_PER_MIN": "10000",
    "ENV": "dev", "FERNET_KEY": "",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.synthetic import generate_all  # noqa: E402

generate_all(get_settings().samples_dir, get_settings().fixture_dir)
SAMPLES = Path(get_settings().samples_dir)


class Api:
    def __init__(self, client: TestClient):
        self.c = client

    def login(self, email: str) -> dict:
        r = self.c.post("/api/auth/login", json={"email": email, "password": "demo1234"})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}

    @staticmethod
    def events(resp) -> list[dict]:
        assert resp.status_code == 200, resp.text
        out = []
        for block in resp.text.strip().split("\n\n"):
            ev, data = block.split("\n", 1)
            out.append({"event": ev.removeprefix("event: "), "data": json.loads(data.removeprefix("data: "))})
        return out

    def chat(self, h, case_id, **body):
        return self.events(self.c.post(f"/api/cases/{case_id}/chat", json=body, headers=h))

    def state(self, evs):
        return next(e["data"] for e in evs if e["event"] == "state")

    def upload_bytes(self, h, case_id, doc_type, data: bytes, filename="upload.bin", ctype="application/octet-stream", raw=False):
        r = self.c.post(f"/api/cases/{case_id}/documents", data={"doc_type": doc_type}, headers=h,
                        files={"file": (filename, data, ctype)})
        return r if raw else self.events(r)

    def upload(self, h, case_id, doc_type, scenario="clean", name=None, ext="png"):
        path = SAMPLES / scenario / f"{name or doc_type}.{ext}"
        ctype = "application/pdf" if ext == "pdf" else "image/png"
        return self.upload_bytes(h, case_id, doc_type, path.read_bytes(), path.name, ctype)

    def fresh_case(self, h) -> str:
        self.c.post("/api/demo/reset", headers=h)
        case = self.c.post("/api/cases", headers=h).json()
        self.chat(h, case["id"], action={"type": "start"})
        return case["id"]


@pytest.fixture(scope="session")
def api():
    from app.main import create_app
    with TestClient(create_app()) as client:
        yield Api(client)
