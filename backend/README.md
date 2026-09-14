# backend/

API FastAPI, base SQLite, et — à partir du Lot 4 — le moteur d'extraction PDF.
Voir `docs/cahier-des-charges.md` §5.2, §6, §8 et §9 pour l'architecture, le
modèle de données et le contrat d'API.

## Lancer en développement

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

L'API écoute sur `http://127.0.0.1:8000`. En développement, `CSH_FRONTEND_DIST`
n'est pas défini : ce processus ne sert que `/api`, et le serveur Vite du
frontend lui transmet les requêtes.

- Documentation interactive : `http://127.0.0.1:8000/api/docs`
- État de l'instance : `http://127.0.0.1:8000/api/health`

## Vérifications

```bash
ruff check .   # style et erreurs courantes
mypy           # typage strict
pytest         # tests
```

## Organisation

| Chemin | Rôle |
| --- | --- |
| `app/config.py` | Réglages, tous surchargeables par variables `CSH_*`. |
| `app/db.py` | Moteur SQLAlchemy et réglages SQLite (WAL, clés étrangères). |
| `app/models.py` | Modèles : `patterns`, `palette_entries`, `grids`, `progress`, `progress_events` (Lot 1). |
| `app/codec.py` | Encodage compact de la grille (`Uint16Array`) et du bitmap de progression (1 bit/case). |
| `app/schemas.py` | Schémas Pydantic de l'API. |
| `app/seed.py` | Motif de démonstration 255×180, purement synthétique, pour les tests de perf du rendu. |
| `app/migrations.py` | Application des migrations au démarrage du conteneur. |
| `app/main.py` | Application FastAPI, service du frontend construit, repli SPA. |
| `app/api/` | Routes HTTP. |
| `alembic/` | Migrations de schéma. |
| `scripts/seed_demo_pattern.py` | Injecte le motif de démonstration en base (`python scripts/seed_demo_pattern.py`). |

## Ajouter une migration

```bash
alembic revision --autogenerate -m "description courte"
alembic upgrade head
```

`alembic/env.py` lit l'URL de base depuis `app.config`, jamais depuis
`alembic.ini` : une migration lancée à la main et le démarrage du conteneur
visent donc forcément le même fichier.
