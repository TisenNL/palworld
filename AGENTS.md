# AGENTS.md

Vue 3 + TS frontend (Leaflet map, Pinia) plus a **separate Python helper process** for OCR / HUD /
mouse automation. Windows-first (Win32 `ctypes`, Tk overlay, `palchecklist://` protocol).

## Commands

```bash
npm run dev          # 127.0.0.1:5173, strictPort
npm run test:watch   # vitest
npm run test:e2e     # Playwright (auto-starts dev server)
py -3 run.py         # or start.bat — full app: builds frontend + launches helper on 8765
npm run validate     # typecheck -> lint -> test -> test:server -> build:only
```

`npm run validate` is the gate to run before claiming done. `npm run build` = `typecheck` + `build:only`.

**`vue-tsc --noEmit` on its own is a no-op**: `tsconfig.json` is solution-style with `files: []`,
so it sees no files and always exits 0. The `typecheck` script passes `-p tsconfig.app.json` and
`-p tsconfig.node.json` on purpose — do not strip the `-p` flags.

- Unit tests: `npx vitest run tests/breeding.spec.ts` (happy-dom, globals on). Naming is mixed —
  `.spec.ts` *and* `.test.ts` are both collected. `tests/e2e/**` is excluded from vitest but **is**
  type-checked by `npm run typecheck` (`tsconfig.app.json` includes `tests/**/*.ts`).
- Python tests: `py -3 -m unittest tests.test_game_marker_automation` (30 tests, single class);
  player-position reader tests: `py -3 -m unittest tests.test_player_position`.
  Must run from repo root. No `pytest`, no `requirements.txt`.
- Python deps are implicit: `Pillow` must be preinstalled (hard import); `rapidocr-onnxruntime` and
  `mss` are lazily imported and auto-piped by `run.py`. No `pyautogui` — input is raw `user32`.
- ESLint is type-aware (`recommendedTypeChecked` + `projectService`). `no-floating-promises` /
  `no-misused-promises` / `consistent-type-imports` are errors, so type-only imports must use
  `import type` and promises need explicit `.catch()` / `void`. `scripts/**` is in `ignores` — pure
  JS with no TS project, so the project service can't parse it under type-aware linting.
- Prettier only runs over `src tests *.config.ts package.json tsconfig*.json`. **Do not** run
  `npm run format` expecting it to touch `server/`, `scripts/`, or `tools/`.

## Architecture notes

- Two processes, one origin in prod: the Python helper serves `dist/` on **:8765**, so the frontend
  uses same-origin relative paths (`apiBase` is `''`). In dev, Vite proxies only the 11 helper routes
  listed in `vite.config.ts:6-19` to 8765, with `proxy.on('error')` swallowing failures so the map
  works with the helper offline. **Adding a helper route means adding it to that list.**
- Only env var: `VITE_HELPER_URL`. No `.env*` file exists; don't assume one.
- The Python helper **validates `Host` and `Origin`** against `ALLOWED_LOCAL_HOSTS`
  (`server/coord_tooltip.py`) and never sends `Access-Control-Allow-Origin: *`. Without that any
  web page could drive the mouse/keyboard automation or read/write `/progress`. A new dev origin
  means editing that set.
- Live player tracking (`server/player_position.py`) is read-only, requires the validated Palworld
  executable SHA-256, and gets its initial actor address from the local Overwolf Palworld app log.
  It follows only the validated actor-relative pointer chain; do not replace this with an
  unrestricted process-memory scan. A game update must be revalidated before changing the build
  fingerprint or offsets.
- `src/domain/` is pure logic (no Vue/Pinia imports) — keep it that way; it's the only thing
  coverage measures (`src/domain/**` + `src/stores/**`).
- Zod schemas live beside their types in `src/types/*.ts` and are the validation layer for all
  server + data files. Deliberate exceptions: the 3.4 MB marker JSON is validated only under
  `import.meta.env.DEV` (`src/stores/opggMap.ts:172`), and progress POSTs are hardcoded relative
  paths that bypass `src/services/api.ts` via `sendBeacon`/`keepalive` (`src/stores/checklist.ts:232`).
- Pinia stores are all setup-style. Stores instantiate other stores inside actions — that's the
  existing pattern, not a bug to "fix".
- Routing: all views lazy-loaded in `src/router.ts`; nav links are hand-duplicated in
  `src/components/layout/AppShell.vue:11-17`. Adding a route = edit both. Dark mode is forced on
  (`app-dark` class + PrimeVue `darkModeSelector`), no light theme.
- Heavy `tsconfig` flags (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`) are why the
  codebase is full of `!` and `?? fallback`. Match that rather than loosening the config.
- Marker coordinate math is reverse-engineered op.gg `CRS.Simple` in `src/domain/opggCoordinates.ts`
  and duplicated in `scripts/convert_opgg_points.mjs`. If you change one, change both.
- `MapZone` is declared in three places (`types/opggMarker.ts`, `domain/opggCoordinates.ts`,
  `stores/opggMap.ts`) — re-export from `domain` rather than adding a fourth.
- Comments/commits are mixed Portuguese and English. Both exist; match surrounding file.

## Generated & committed data (do not hand-edit)

`public/` holds ~1550 tracked files, many multi-MB generated artifacts:
`opgg-markers-palpagos.json` (3.4 MB), `opgg-data/points.json` (raw op.gg, UE5 cm),
`opgg-map-tiles/`, `data.json`, `breed.json`, `wt-data.json`, `map_icons.json`.Regeneration chain: `py -3 download_opgg_data.py` → `node scripts/rename_opgg_tiles.mjs` /
`node scripts/convert_opgg_points.mjs`. Regenerate Pal and human habitat catalog/points with
`py -3 scripts/download_opgg_spawn_locations.py`.

`convert_opgg_points.mjs` guarantees **unique** marker ids (`{type}:{lat}:{lng}` plus `#n` on
collision). The renderer dedupes by `id`, so a collision silently drops markers (sidebar counts stop
matching the map) and makes the "checked" state shared between unrelated things — that was the case
for 84 coal nodes and two World Tree quests. `id` is only parsed via `id.split(':')[0]` (the type),
so the suffix is safe. Rebuild `data.json`/`wt-data.json` from
`tools/build_data_from_map.py`, `breed.json` from `tools/build_breed_data.py`.

Root-level `index.json`, `points.json`, `resources.json`, `map_data_en_full.js`,
`palpagos.html`, `worldtree.html`, `test_*.txt` are **stray leftovers not read by any code**
(`points.json` at root is even a corrupt S3 error page). Don't wire anything to them; don't treat
them as input.

Tests import `public/*.json` directly, so data regeneration can break unit tests
(`tests/breeding.spec.ts:50-51` hard-asserts 297 pals / 160 unique combinations).

## Progress persistence

Two independent layers — don't conflate them:

- Server file `.local/progress.json` (gitignored, legacy `progress.json` fallback). Browser copy
  `palworld-progress-v2`; the merge logic in `src/stores/checklist.ts:162-224` is the subtlest code in
  the repo — higher `revision` wins, v1 payloads merge per-category, `breedOwned` is always
  union-merged so a local-only selection survives.
- Map marker progress (`palworld:map:checked-collectibles`) is localStorage-only and never syncs to
  `/progress`. Key list is `storageKeys` in `src/stores/checklist.ts:25-38`, `preferences.ts:6`,
  `cake.ts:14`, `opggMap.ts:36-37`, `serverHud.ts:18`. `palworld:map:checked-collectibles` uses
  op.gg's on-disk format deliberately — keep it byte-compatible.

## Local caches

`.cache/` (gitignored) is runtime state owned by `server/`, not build junk: game-marker calibration,
icon disk cache, OCR debug crops, optional timing JSONL. Delete freely; regenerated.

`.kilo/` (has a **registered git worktree** at `.kilo/worktrees/vast-character`) and `.freebuff/` are
other agents' tooling artifacts, excluded from vitest and eslint. Don't edit them, don't let them
confuse `git status`/`git branch`.