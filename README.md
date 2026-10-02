# Palworld Checklist — Interactive Map

Interactive map and checklist for Palworld, replicating the functionality of [op.gg/palworld/map](https://op.gg/palworld/map) with local progress tracking and optional game automation via a local helper.

## Quick Start

```bash
npm install
npm run dev
```

Open **http://127.0.0.1:5173** in your browser.

---

## Map Features

| Feature | Status |
|---|---|
| Leaflet map with pan, zoom and bounds (Palpagos + World Tree) | ✅ |
| Smooth scroll-wheel zoom (replicates op.gg) | ✅ |
| ~16,000 markers across 57 categories | ✅ |
| Icons per marker category | ✅ |
| Sidebar with per-category filters (toggle on/off) | ✅ |
| Group-level All/Hide buttons and Collapse All | ✅ |
| Popup on click with coordinates and Discovered toggle | ✅ |
| Progress persisted in localStorage (op.gg format) | ✅ |
| Cursor coordinates in real-time | ✅ |
| Go-to coordinates input | ✅ |
| Marker size slider | ✅ |
| Fullscreen button | ✅ |
| Responsive layout (sidebar collapses on mobile) | ✅ |
| World Tree map tab | ✅ |
| Pal and human location filters | ✅ |
| Live player marker (validated Palworld build required) | ✅ |
| OCR coordinates (requires local helper) | ✅ |
| HUD marker in-game (requires local helper) | ✅ |
| Mark-in-game automation (requires local helper) | ✅ |
| Mouse loop automation (requires local helper) | ✅ |
| Breeding calculator | ✅ |
| Cake planner | ✅ |
| Base Boost calculator | ✅ |
| Checklist (Lists view) | ✅ |
| Pal habitat day/night spawns | ✅ |
| URL-share progress export | ❌ (out of scope) |

---

## Updating Map Data

### Tiles (run once or when op.gg updates the map)

```bash
# Download all tiles from op.gg CDN
py -3 download_opgg_data.py

# Rename tiles to Leaflet format {z}-{x}-{y}.webp
node scripts/rename_opgg_tiles.mjs
```

Tiles are saved to `public/opgg-map-tiles/palpagos/` and `public/opgg-map-tiles/world-tree/`.

### Marker Data

```bash
# Download marker JSON from op.gg CDN
py -3 download_opgg_data.py

# Convert points.json (UE5 coords) → Leaflet lat/lng markers
node scripts/convert_opgg_points.mjs
```

Generates:
- `public/opgg-markers-palpagos.json` — ~16,000 markers for Palpagos Islands
- `public/opgg-markers-worldtree.json` — ~370 markers for World Tree
- `public/opgg-marker-counts.json` — counts per type and zone

### Pal and Human Locations

```bash
py -3 scripts/download_opgg_spawn_locations.py
```

Downloads the Pal and human location catalog and compact day/night spawn points to
`public/opgg-spawn-locations/`. Spawn point files are loaded on demand when selecting a Pal or
human in the map sidebar.

---

## Project Structure

```
src/
  components/
    layout/          AppShell (header + nav)
    map/
      LeafletMapView.vue   ← Leaflet map, tiles, markers, popup
      MarkerPopup.vue      ← Click popup with discovered toggle
  domain/
    opggCoordinates.ts     ← op.gg coordinate system (CRS.Simple)
    opggMarkerIcons.ts     ← Icon URLs and HTML for divIcon
    layers.ts              ← Layer definitions for Lists/checklist views
    breeding.ts / cakes.ts ← Non-map calculators
  stores/
    opggMap.ts             ← Markers, filters, progress, camera
    checklist.ts           ← Lists/breeding/cakes progress (server sync)
    preferences.ts         ← Sidebar state
    serverHud.ts           ← Local helper integration
  styles/
    leaflet-overrides.css  ← Leaflet reset + dark theme
    map-markers.css        ← Marker icons, slider, controls
  types/
    opggMarker.ts          ← Marker Zod schema + label helpers
  views/
    MapView.vue            ← Main map view (sidebar + LeafletMapView)
    ListsView.vue          ← Checklist by category
    BreedingView.vue       ← Breeding calculator
    CakesView.vue          ← Cake planner
    BaseBoostView.vue      ← Base Boost calculator

public/
  opgg-map-tiles/
    palpagos/    {z}-{x}-{y}.webp  (341 tiles z0-z4)
    world-tree/  {z}-{x}-{y}.webp  (341 tiles z0-z4)
  opgg-icons/
    effigies/ eggs/ markers/ resources/  (43 icons)
  opgg-data/
    points.json          ← Raw marker data from op.gg (818KB)
    index.json           ← Groups and counts
  opgg-markers-palpagos.json    ← Converted Leaflet markers
  opgg-markers-worldtree.json   ← Converted World Tree markers

scripts/
  rename_opgg_tiles.mjs         ← Tile renaming utility
  convert_opgg_points.mjs       ← Data conversion script

server/
  (Python local helper — OCR, HUD, game automation)
```

---

## Coordinate System

The map uses **Leaflet CRS.Simple** with `WORLD_SIZE = 256`, matching op.gg exactly.

All marker coordinates in `points.json` are in **Unreal Engine 5 units (cm)**.  
The conversion to Leaflet LatLng is done by `src/domain/opggCoordinates.ts`.

To display in-game pause menu coordinates:
```
ingameX = round((gameY - 158000) / 459)
ingameY = round((gameX + 123888) / 459)
ingameZ = round(gameZ / 100)   // in meters
```

---

## Local Helper (Optional)

The local Python helper enables:
- **Live player position** — read-only game-memory reader; enabled only for the validated Palworld executable build. No Overwolf app is required.
- **OCR** — read coordinates directly from your Palworld game screen
- **HUD** — place a marker in the Palworld in-game map
- **Mark in game** — automated map marking using mouse automation
- **Mouse loop** — repeat right-click + middle-click for gathering automation

Start the helper via `start.bat` or `py -3 run.py`, then features appear automatically in the map sidebar Tools section.

---

## Development

```bash
npm run dev          # Dev server at http://127.0.0.1:5173
npm run build        # Type-check + production build
npm test             # Unit tests (Vitest)
npm run typecheck    # TypeScript check only
npm run lint         # ESLint
```

---

## Technology

- **Vue 3** + Composition API + TypeScript
- **Pinia** — state management
- **Leaflet 1.9.4** — map rendering (CRS.Simple)
- **PrimeVue** — UI components (other views)
- **Zod** — runtime data validation
- **Vite** — build tool
- Tiles and marker data sourced from [op.gg/palworld/map](https://op.gg/palworld/map)
