# frontend/

React/TypeScript PWA: pattern library, import wizard, tracking screen
(`<canvas>` rendering), statistics, settings. See `docs/specification.md`
§5.3 and §7.

## Running in development

```bash
npm install
npm run dev     # http://127.0.0.1:5173, /api proxied to the backend
```

The backend must be running alongside on port 8000 (see `backend/README.md`),
otherwise the application shows up but reports "server unreachable".

```bash
npm run typecheck
npm run build   # produces dist/, served as is by the backend in production
```

## Layout

| Path | Role |
| --- | --- |
| `src/index.css` | Design system: tokens, light/dark theme, component classes. |
| `src/i18n/` | FR/EN translations. `fr.ts` defines the keys, `en.ts` is typed from it. |
| `src/pattern/` | Pattern core: types, counts, canvas rendering. No dependency on React. |
| `src/state/useTracker.ts` | Local tracking state: progress, view, tool, undo. |
| `src/state/useSyncedTracker.ts` | Adds server synchronisation by versioned deltas on top of `useTracker` (IndexedDB queue, offline fallback). |
| `src/state/usePatternLibrary.ts` | Loads the library: server → IndexedDB cache → demo pattern, depending on what responds. |
| `src/screens/` | The five screens. |
| `src/components/` | Navigation shell, colour list, thumbnails, icons. |
| `src/demo/` | Purely client-side demo pattern. Still useful even after real import arrived: it is the first-launch fallback when neither the server nor the local cache has a pattern yet. |
| `src/lib/` | Theme, routing, API client, grid/bitmap codec, IndexedDB cache (Dexie), formatting, screen wake lock. |

## Rules to follow

- **Never one DOM element per cell.** The reference pattern has 45,900 cells:
  the whole grid goes through `<canvas>`, and only visible cells are drawn
  (`src/pattern/render.ts`).
- **No hard-coded string in a component.** Everything goes through `useT()` and
  the keys in `src/i18n/`. Adding a key to `fr.ts` breaks compilation until
  `en.ts` is completed — this is intentional.
- **No hard-coded theme colour in JavaScript.** Canvas rendering reads the CSS
  variables back (`readGridTheme`), so `index.css` remains the only source.
- **No network call to a third party.** All requests are relative to the
  origin serving the application.
- **Touch targets of at least 44 px**, and a font size of at least 16 px in
  input fields — below that, iOS zooms in on focus.

## Typography

The mockups used Caprasimo and Figtree, loaded from Google Fonts. A
self-hosted instance must not depend on any third-party service or stop
working offline: system font stacks are therefore used by default. To get the
mockups' exact typography back, drop the `.woff2` files into
`src/assets/fonts/`, declare them with `@font-face` in `src/index.css`, and
change `--font-heading` / `--font-body`. The fonts will then be included in
the service worker's precache (see `vite.config.ts`).
