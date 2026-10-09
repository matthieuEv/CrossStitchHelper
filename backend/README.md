# backend/

FastAPI API, SQLite database, and — from Lot 4 onwards — the PDF extraction
engine. See `docs/specification.md` §5.2, §6, §8 and §9 for the architecture,
the data model and the API contract.

## Running in development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The API listens on `http://127.0.0.1:8000`. In development, `CSH_FRONTEND_DIST`
is not set: this process only serves `/api`, and the frontend's Vite server
proxies requests to it.

- Interactive documentation: `http://127.0.0.1:8000/api/docs`
- Instance status: `http://127.0.0.1:8000/api/health`

## Checks

```bash
ruff check .   # style and common errors
mypy           # strict typing
pytest         # tests
```

## Layout

| Path | Role |
| --- | --- |
| `app/config.py` | Settings, all overridable via `CSH_*` variables. |
| `app/db.py` | SQLAlchemy engine and SQLite settings (WAL, foreign keys). |
| `app/models.py` | Models: `patterns`, `palette_entries`, `grids`, `progress`, `progress_events` (Lot 1). |
| `app/codec.py` | Compact encoding of the grid (`Uint16Array`) and of the progress bitmap (1 bit/cell). |
| `app/schemas.py` | Pydantic API schemas. |
| `app/seed.py` | 255×180 demo pattern, purely synthetic, for rendering performance tests. |
| `app/migrations.py` | Applies migrations when the container starts. |
| `app/main.py` | FastAPI application, serving of the built frontend, SPA fallback. |
| `app/api/` | HTTP routes. |
| `alembic/` | Schema migrations. |
| `scripts/seed_demo_pattern.py` | Injects the demo pattern into the database (`python scripts/seed_demo_pattern.py`). |

## Adding a migration

```bash
alembic revision --autogenerate -m "short description"
alembic upgrade head
```

`alembic/env.py` reads the database URL from `app.config`, never from
`alembic.ini`: a migration run by hand and the container startup therefore
necessarily target the same file.
