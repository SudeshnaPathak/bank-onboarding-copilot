# diagnose_gateway.py
import os

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

MODEL = os.environ.get("AIPG_MODEL", "gemini-3.8-flash")
REGIONS = {
    "US": "https://openai.generative.engine.capgemini.com/v1",
    "EU": "https://openai.generative-eu.engine.capgemini.com/v1",
}


def check(region: str, base_url: str, api_key: str) -> None:
    with OpenAI(base_url=base_url, api_key=api_key, timeout=30.0) as client:
        try:
            ids = [m.id for m in client.models.list().data]
            print(f"{region} models.list OK: {len(ids)} models; {MODEL} present: {MODEL in ids}")
        except APIStatusError as exc:
            print(f"{region} models.list HTTP {exc.status_code}: {exc.response.text[:300]}")
        except (APIConnectionError, APITimeoutError) as exc:
            print(f"{region} models.list connection problem: {exc}")

        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": "Reply with one word."}],
                max_completion_tokens=16,
            )
            print(f"{region} chat OK: {resp.choices[0].message.content!r}")
        except APIStatusError as exc:
            print(f"{region} chat HTTP {exc.status_code}: {exc.response.text[:300]}")
        except (APIConnectionError, APITimeoutError) as exc:
            print(f"{region} chat connection problem: {exc}")


if __name__ == "__main__":
    from app.config import get_settings  # adjust to your package path

    key = get_settings().aipg_api_key
    if not key:
        raise SystemExit("No aipg_api_key found in the environment or backend/.env.")
    for name, url in REGIONS.items():
        check(name, url, key)