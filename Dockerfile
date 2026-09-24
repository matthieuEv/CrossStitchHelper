# syntax=docker/dockerfile:1

# Image unique : un seul conteneur sert l'API et le frontend construit, sur un
# seul port. C'est la condition pour qu'une installation tienne en une commande
# et n'impose ni reverse proxy ni base de données à administrer.

# ---------------------------------------------------------------------------
# 1. Construction du frontend
# ---------------------------------------------------------------------------
FROM node:25-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
# `npm ci` exige un verrou ; au premier clone il n'existe pas encore.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# 2. Exécution
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Injecté par `.github/workflows/release.yml` (`--build-arg VERSION=<tag>`) au
# push d'un tag git : la version affichée dans l'app est ainsi toujours celle
# du tag qui a produit l'image, jamais maintenue à la main dans le code.
ARG VERSION=v0.0.0-dev

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    CSH_DATA_DIR=/data \
    CSH_FRONTEND_DIST=/app/frontend-dist \
    CSH_APP_VERSION=$VERSION

WORKDIR /app

# Les dépendances sont lues depuis pyproject.toml : une seule source de vérité
# pour le développement et pour l'image. Cette couche n'est reconstruite que
# lorsque pyproject.toml change.
COPY backend/pyproject.toml /tmp/pyproject.toml
RUN python -c "\
import subprocess, sys, tomllib;\
data = tomllib.load(open('/tmp/pyproject.toml', 'rb'));\
subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *data['project']['dependencies']])\
" && rm /tmp/pyproject.toml

COPY backend/ /app/
COPY --from=frontend /build/dist /app/frontend-dist

# L'application tourne sans privilèges ; le volume de données lui appartient.
RUN useradd --system --uid 10001 --home /app csh \
    && mkdir -p /data \
    && chown -R csh:csh /app /data
USER csh

VOLUME ["/data"]
EXPOSE 8000

# `curl` n'est pas installé dans l'image slim : la sonde utilise Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
