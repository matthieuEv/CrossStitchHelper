# e2e/

Tests bout-en-bout Playwright, contre une instance réelle (backend + frontend
construit), pas des mocks. Chaque test vise un critère "terminé quand" concret
de `docs/roadmap.md` — le nom du fichier indique le lot qu'il valide.

## Lancer en local

Trois choses doivent tourner : un backend avec au moins un motif en base, et
le frontend construit servi par ce même backend (le plus proche de la
production, et ce que fait la CI) — ou, plus rapide en développement, le
serveur Vite en parallèle du backend.

```bash
# 1. Backend, avec le motif de démonstration
cd backend
CSH_DATA_DIR=/tmp/csh-e2e-data .venv/bin/python scripts/seed_demo_pattern.py
CSH_DATA_DIR=/tmp/csh-e2e-data .venv/bin/uvicorn app.main:app --port 8000 &

# 2. Frontend (serveur de dev, proxy /api vers le port 8000)
cd frontend
npm run dev &

# 3. Tests, contre le serveur de dev
cd frontend
PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173 npm run test:e2e
```

Sans `PLAYWRIGHT_BASE_URL`, la cible par défaut est `http://127.0.0.1:8000`
(l'image Docker, qui sert l'API et le frontend construit sur le même port —
voir `.github/workflows/ci.yml`).

## Écrire un nouveau test

- Un fichier par lot (`lotN-*.spec.ts`), nommé d'après ce qu'il valide.
- Toujours contre l'API réelle (`request.get("/api/...")`) pour établir l'état
  attendu, jamais de données codées en dur qui supposent un contenu précis du
  motif de démonstration — ce motif est généré de façon déterministe mais son
  dessin n'a pas de sens fonctionnel garanti.
- Un test qui coche des cases doit rester correct qu'il soit lancé une fois ou
  cent fois de suite sur la même base (voir `lot1-persistence.spec.ts` pour le
  motif : vider une zone avant de la remplir, pour ne jamais dépendre de l'état
  laissé par une exécution précédente).
