# syntax=docker/dockerfile:1

# Single image: one container serves the API and the built frontend, on a
# single port. That is what lets an installation fit in one command and
# require neither a reverse proxy nor a database to administer.

# ---------------------------------------------------------------------------
# 1. Frontend build
# ---------------------------------------------------------------------------
FROM node:25-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
# `npm ci` requires a lockfile; on a first clone it does not exist yet.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# 2. Runtime
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

# Injected by `.github/workflows/release.yml` (`--build-arg VERSION=<tag>`) when
# a git tag is pushed: the version shown in the app is thus always that of the
# tag that produced the image, never maintained by hand in the code.
ARG VERSION=v0.0.0-dev

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    CSH_DATA_DIR=/data \
    CSH_FRONTEND_DIST=/app/frontend-dist \
    CSH_APP_VERSION=$VERSION

WORKDIR /app

# Dependencies are read from pyproject.toml: a single source of truth for
# development and for the image. This layer is only rebuilt when
# pyproject.toml changes.
COPY backend/pyproject.toml /tmp/pyproject.toml
RUN python -c "\
import subprocess, sys, tomllib;\
data = tomllib.load(open('/tmp/pyproject.toml', 'rb'));\
subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *data['project']['dependencies']])\
" && rm /tmp/pyproject.toml

COPY backend/ /app/
COPY --from=frontend /build/dist /app/frontend-dist

# The application runs unprivileged; the data volume belongs to it.
RUN useradd --system --uid 10001 --home /app csh \
    && mkdir -p /data \
    && chown -R csh:csh /app /data
USER csh

VOLUME ["/data"]
EXPOSE 8000

# `curl` is not installed in the slim image: the probe uses Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
