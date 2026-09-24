# e2e/

Playwright end-to-end tests, against a real instance (backend + built
frontend), not mocks. Each test targets a concrete "done when" criterion from
`docs/roadmap.md` — the file name indicates the lot it validates.

## Running locally

Three things must be running: a backend with at least one pattern in the
database, and the built frontend served by that same backend (closest to
production, and what CI does) — or, faster in development, the Vite server
alongside the backend.

```bash
# 1. Backend, with the demo pattern
cd backend
CSH_DATA_DIR=/tmp/csh-e2e-data .venv/bin/python scripts/seed_demo_pattern.py
CSH_DATA_DIR=/tmp/csh-e2e-data .venv/bin/uvicorn app.main:app --port 8000 &

# 2. Frontend (dev server, /api proxied to port 8000)
cd frontend
npm run dev &

# 3. Tests, against the dev server
cd frontend
PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173 npm run test:e2e
```

Without `PLAYWRIGHT_BASE_URL`, the default target is `http://127.0.0.1:8000`
(the Docker image, which serves the API and the built frontend on the same
port — see `.github/workflows/ci.yml`).

## Writing a new test

- One file per lot (`lotN-*.spec.ts`), named after what it validates.
- Always use the real API (`request.get("/api/...")`) to establish the
  expected state, never hard-coded data that assumes specific content in the
  demo pattern — that pattern is generated deterministically but its drawing
  has no guaranteed functional meaning.
- A test that checks cells must stay correct whether it runs once or a
  hundred times in a row on the same database (see `lot1-persistence.spec.ts`
  for the pattern: clear an area before filling it, so as never to depend on
  the state left by a previous run).
