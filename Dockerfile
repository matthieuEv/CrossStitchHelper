# syntax=docker/dockerfile:1

# Single image: one container serves the API and the built frontend, on a
# single port. That is what lets an installation fit in one command and
# require neither a reverse proxy nor a database to administer.

# ---------------------------------------------------------------------------
# 1. Frontend build
# ---------------------------------------------------------------------------
FROM --platform=$BUILDPLATFORM node:26-alpine AS frontend

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

# The application runs unprivileged. The container still starts as root: the
# entrypoint first makes the data directory writable (whoever owns it on the
# host), then drops to an unprivileged uid — see docker-entrypoint.sh.
# The code stays root's and only readable: the uid chosen at startup is not
# necessarily `csh`, and the application never writes to it anyway.
RUN groupadd --system --gid 10001 csh \
    && useradd --system --uid 10001 --gid csh --home /app csh \
    && chmod -R a+rX /app \
    && mkdir -p /data \
    && chown csh:csh /data
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

VOLUME ["/data"]
EXPOSE 8000

# `curl` is not installed in the slim image: the probe uses Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
