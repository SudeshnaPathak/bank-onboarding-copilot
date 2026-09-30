.PHONY: setup backend frontend test samples e2e
setup:
	cd backend && py -3.12 -m venv .venv && .\.venv\Scripts\activate && pip install -r requirements-dev.txt
	cd frontend && npm install
samples:            ## regenerate synthetic documents + OCR fixtures
	cd backend && .\.venv\Scripts\activate && python -m scripts.generate_samples
backend:
	cd backend && .\.venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
frontend:
	cd frontend && npm run dev
test:
	cd backend && .\.venv\Scripts\activate && pytest -q
	cd frontend && npm run typecheck
e2e:                ## needs `make backend` and `make frontend` running
	cd frontend && npx playwright test
