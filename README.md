# CrossStitchHelper

Application libre et **auto-hébergée** de suivi de grilles de point de croix.
Elle transforme un PDF (ou une photo) de grille en motif suivable : on coche les
cases au fur et à mesure, on sait toujours quelle couleur va où, et on obtient
ses statistiques d'avancement.

Elle s'utilise depuis un navigateur, principalement sur iPhone et iPad, et
s'ajoute à l'écran d'accueil pour fonctionner comme une application — y compris
hors ligne.

**Aucune donnée ne quitte votre serveur.** Aucun compte, aucune télémétrie,
aucun appel vers un service tiers.

---

## Installation

Prérequis : Docker et Docker Compose.

```bash
git clone <url-du-dépôt> crossstitchhelper
cd crossstitchhelper
docker compose up -d
```

L'application répond sur `http://<adresse-du-serveur>:8765`. Le port se change
dans `docker-compose.yml`.

Vérifier que tout va bien :

```bash
curl http://localhost:8765/api/health
# {"status":"ok","version":"0.1.0","database":"ok","schema_revision":"0001_initial"}
```

`status` vaut `ok` uniquement si la base a été créée **et** migrée. Les
migrations s'appliquent automatiquement à chaque démarrage : il n'y a aucune
commande à lancer après une mise à jour.

## Ajouter l'application à l'écran d'accueil (iPhone / iPad)

1. Ouvrir l'adresse de l'instance dans **Safari** (Chrome sur iOS ne sait pas
   installer de PWA).
2. Bouton Partager → **Sur l'écran d'accueil**.
3. L'icône se comporte alors comme une application : plein écran, sans barre
   d'adresse, et utilisable hors ligne.

> **À savoir :** iOS supprime les données des sites web inutilisés depuis
> plusieurs semaines. Une application ajoutée à l'écran d'accueil et ouverte
> régulièrement n'est pas concernée, et de toute façon la progression est
> conservée sur le serveur — le stockage local n'est qu'un cache.

## Mise à jour

```bash
git pull
docker compose up -d --build
```

Vos données ne sont pas touchées : elles vivent dans le volume, pas dans
l'image.

## Sauvegarde et restauration

Tout tient dans un seul répertoire, `./data` — base SQLite et fichiers
utilisateur.

```bash
# Sauvegarde (conteneur arrêté : la copie est cohérente à coup sûr)
docker compose stop
tar czf crossstitchhelper-$(date +%F).tar.gz data/
docker compose start
```

```bash
# Restauration
docker compose down
rm -rf data/
tar xzf crossstitchhelper-2026-09-14.tar.gz
docker compose up -d
```

Si l'arrêt du service n'est pas souhaitable, `sqlite3 data/crossstitchhelper.db
".backup sauvegarde.db"` produit une copie cohérente à chaud.

## Accès depuis l'extérieur

Par défaut l'instance n'est joignable que depuis votre réseau local, ce qui est
le réglage le plus sûr. Pour y accéder depuis l'extérieur, deux approches
raisonnables :

- un **VPN** (WireGuard, Tailscale) : rien n'est exposé publiquement ;
- un **reverse proxy avec HTTPS** (Caddy, Traefik, nginx) devant le port 8000.

HTTPS n'est pas un détail : Safari n'installe une PWA et n'active le service
worker que sur une origine sécurisée (ou sur `localhost`).

## Réglages

Toutes les variables d'environnement sont préfixées `CSH_`.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `CSH_DATA_DIR` | `/data` dans l'image | Répertoire unique des données. Le seul à sauvegarder. |
| `CSH_FRONTEND_DIST` | défini dans l'image | Répertoire du frontend construit. Vide en développement. |
| `CSH_DATABASE_FILENAME` | `crossstitchhelper.db` | Nom du fichier SQLite. |
| `CSH_RUN_MIGRATIONS_ON_STARTUP` | `true` | Applique les migrations au démarrage. |

---

## Développement

Deux processus : l'API et le serveur de développement Vite, qui lui transmet
les requêtes `/api`.

```bash
# Terminal 1 — API sur http://127.0.0.1:8000
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Terminal 2 — interface sur http://127.0.0.1:5173
cd frontend
npm install
npm run dev
```

Vérifications, telles que la CI les exécute :

```bash
cd backend  && ruff check . && mypy && pytest
cd frontend && npm run typecheck && npm run build
```

### Documentation

- `CLAUDE.md` — guide d'entrée pour travailler sur le dépôt.
- `docs/cahier-des-charges.md` — la spécification technique de référence.
- `docs/fonctionnalites-et-limites.md` — ce que l'application fait et ne fera
  jamais, en langage clair.
- `docs/roadmap.md` — découpage en lots, avec critères de fin.
- `fixtures/README.md` — les six PDF de référence du moteur d'extraction.

## État d'avancement

**Lots 0 et 1 (socle technique, rendu et suivi persistant).** L'application se
construit, se lance, s'installe sur l'écran d'accueil et fonctionne hors
ligne ; les cinq écrans sont implémentés et le suivi est pleinement
interactif. La progression est désormais persistée en base et synchronisée
entre appareils par deltas versionnés, avec repli hors-ligne sur IndexedDB — il
reste à valider le pan/zoom (glissé et pincement) sur un iPhone physique avant
de considérer ce lot entièrement clos.

L'import de fichiers n'est pas encore branché : l'assistant se parcourt mais
n'extrait rien, et l'application affiche un motif de démonstration tant
qu'aucun motif réel n'existe. Voir `docs/roadmap.md` — import manuel au Lot 2,
extraction automatique à partir du Lot 4.

## Licence

À décider avant toute publication publique (voir `docs/roadmap.md`).
