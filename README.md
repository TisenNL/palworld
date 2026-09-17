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

Use `start.bat` on Windows. It installs dependencies when needed, builds the Vue application, starts the local helper, and opens `http://127.0.0.1:8765/`.

## Validate

```bash
npm run validate
npm run test:e2e
```
