# Bank Onboarding Copilot

Agentic customer onboarding for a basic savings account: a customer chats and uploads
Aadhaar, PAN and a driving licence; the system extracts and cross-checks the fields, then hands
a prepared case to a human analyst. **Rules detect, AI explains, only `decide_case()` writes a
final status.** The system never approves or rejects anyone on its own.

## Architecture

| Layer | What it does |
|---|---|
| Chat graph (LangGraph) | Runs on every customer message: router -> guide (RAG answers) / document agent / intake (form) -> submit gate -> persist |
| Review graph (LangGraph) | Runs once on submit, then pauses for the analyst |
| Rules engine (`rules.yaml`) | Versioned checks and penalties: name/DOB/address matching, expiry, watchlist, quality, injection flags |
| OCR package | Three parsers (Aadhaar, PAN, driving licence), per-field confidence, JPG/PNG/PDF input, fixture engine for offline demo, PaddleOCR when installed |
| Security | Fernet-encrypted uploads, masked identifiers, hash-chained audit log, JWT roles, rate limiting, upload guard |
| LLM layer | Rule-based service by default; Gemini when `GOOGLE_API_KEY` is set. Output is passed through guardrails |
| Frontend | React + Vite: customer chat/upload (SSE), analyst queue and case review |

## Run it

```bash
make setup      # venv + pip install, npm install
make samples    # synthetic documents + OCR fixtures (6 scenarios)
make backend    # http://localhost:8000  (docs at /docs)
make frontend   # http://localhost:5173
```

Demo logins (password `demo1234`): `priya@example.com`, `amit@example.com` (customers),
`ravi@bank.example.com` (analyst).

Copy `backend/.env.example` to `backend/.env` to configure. With `ENV` other than `dev`, set
`JWT_SECRET` and `FERNET_KEY`. Docker: `docker compose up`.

## PDF support

Customers can upload a JPG, PNG or PDF for any document.

| PDF type | How it is read |
|---|---|
| Text PDF (e-PAN, print-to-PDF, most downloads) | Text layer read directly, no OCR. Field source is shown as `pdf_text` |
| Scanned PDF (phone scanner apps, flatbed scans) | Each page is rendered with `pypdfium2` and OCR'd in order. A front+back scan works because all pages feed one parser |

Guardrails: up to `MAX_PDF_PAGES` pages (default 5); password-protected, damaged and empty PDFs are refused
with a message telling the customer what to do; PDFs containing JavaScript, launch actions or attachments are
rejected; oversized pages are rendered within a pixel budget; file type is decided by content, not name.
Analysts are shown a server-side render of each page, never the uploaded PDF itself.

Text is normalised before parsing (curly quotes, dashes, non-breaking spaces, ligatures), because PDF text
layers use characters such as `Father’s Name` (curly apostrophe) that a plain-ASCII pattern would miss.

## Demo scenarios

`clean`, `mismatch`, `expired_dl`, `blurry`, `injection`, `watchlist`. The upload dialog offers
these samples in demo mode so the flow works without real documents. `make samples` also writes PDF versions
to `samples/<scenario>/`: `<doc>_scan.pdf` (image-only) and `<doc>_text.pdf` (text layer). Upload them with
"Choose a photo or PDF".

## Tests

```bash
make test       # pytest (unit, integration golden path, security) + frontend typecheck
make e2e        # Playwright; needs `make backend` and `make frontend` running
```

## Known limits

- The bundled OCR runs in fixture mode, which only recognises the synthetic sample images. Install
  `paddlepaddle paddleocr` and set `OCR_ENGINE=paddle` for real documents, and re-tune the rule
  thresholds against real scans first.
- Password-protected PDFs are refused. Note that e-Aadhaar PDFs downloaded from UIDAI are password-protected;
  customers must remove the password or upload a screenshot. Prompting for the password is a possible next step.
- A text-layer PDF is trusted as written. A PDF can carry hidden text that differs from what is visible; analysts
  see the rendered page next to the extracted fields, which is the check for this. The OCR'd image path has no such gap.
- The photo blur/size gate is skipped for PDFs (it is tuned for card-sized images and would misfire on an A4 page);
  a poor scan shows up as low per-field OCR confidence and is handled by the rules engine instead.
- Text-layer parsing was tested on generated PDFs only. Real e-PAN / e-Aadhaar layouts may order lines differently,
  so run a few real ones through before relying on them. Scanned-PDF OCR with PaddleOCR is also unverified here;
  the rasterise-then-OCR path is tested with a stand-in engine.
- `GEMINI_MODEL` should be checked against the models your account can use.
- Phases 5 and 6 of the plan (evals, deployment hardening) are not built.
- Demo passwords and dev keys are for local use only.
