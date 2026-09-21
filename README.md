# Palworld Checklist

Vue 3, TypeScript, Pinia, PrimeVue, and a local Python helper for OCR and in-game map automation.

## Project structure

- `src/`: Vue application source.
- `public/`: static files copied into the production build, including game data.
- `server/`: local HTTP server, OCR, HUD, and native Palworld automation.
- `scripts/`: Windows protocol registration and helper lifecycle scripts.
- `tests/`: TypeScript, browser, and Python tests.
- `tools/`: data generation, validation utilities, source data, and research artifacts.
- `.cache/`: generated map tiles, downloaded icons, and OCR captures.
- `.local/`: local progress persisted by the helper.

## Run

```bash
py -3 run.py
```

Builds the Vue app when needed, starts the local helper, and opens `http://127.0.0.1:8765/`. Stop with **Ctrl+C**.

On Windows you can also double-click `start.bat` (same entrypoint).

For frontend-only development, use `npm run dev -- --host 0.0.0.0` and open
`http://localhost:5173/`. The local helper features require `py -3 run.py` so
the backend is available on port `8765`.

## Validate

```bash
npm run validate
npm run test:e2e
```
