# Batch Mark in Game — Implementation Plan

## Goal
Allow users to select multiple markers on the map (Ctrl/Cmd + Click), queue them, and sequentially mark them in-game via the existing automation. Queue persists after completion. Errors stop the batch. All markers must be from the same map zone.

---

## Architecture Overview

### Frontend (Vue 3 + Pinia)
1. **`src/stores/opggMap.ts`** — Extend selection state from single marker to array
2. **`src/components/map/LeafletMapView.vue`** — Handle Ctrl/Cmd + Click for multi-select
3. **`src/views/MapView.vue`** — Add queue panel UI in sidebar
4. **`src/stores/serverHud.ts`** — Add batch marking logic with sequential processing
5. **`src/services/api.ts`** — Add batch endpoint (or reuse single endpoint in loop)

### Backend (Python HTTP Server)
6. **`server/coord_tooltip.py`** — Add `/game-marker/start-batch` endpoint that queues targets
7. **`server/game_marker_automation.py`** — Reuse existing `GameMarkerController` sequentially

---

## Detailed Tasks

### 1. Update `opggMap` Store (`src/stores/opggMap.ts`)

**State changes:**
- Replace `selectedMarker: Marker | null` with `selectedMarkers: Marker[]`
- Add `selectionAnchor: Marker | null` (for Shift+Click range, optional future)
- Keep `selectMarker(marker)` but make it toggle when Ctrl/Cmd held
- Add `addToSelection(marker)`, `removeFromSelection(marker)`, `clearSelection()`, `selectAllVisible(group?)`
- Add computed `hasSelection: boolean`, `selectionCount: number`
- Add validation: all selected markers must share same `mapZone` (derive from store's activeZone or marker data)

**Migration notes:**
- Existing `selectedMarker` getter can return `selectedMarkers[0]` for backward compat
- Update any components using `selectedMarker` to use `selectedMarkers`

---

### 2. Update `LeafletMapView.vue` (`src/components/map/LeafletMapView.vue`)

**Marker click handler:**
- On marker click, emit `marker-click` with `{ marker, metaKey, shiftKey }`
- Parent (`MapView.vue`) decides selection logic based on modifier keys

**Visual feedback:**
- Selected markers: distinct style (outline, pulse, or different icon)
- Use `L.DivIcon` or `className` on marker element to show selection state

---

### 3. Update `MapView.vue` (`src/views/MapView.vue`)

**Sidebar Queue Panel:**
- Add collapsible "Mark Queue" section in Tools panel (below existing "Mark in game")
- Show list of queued markers with:
  - Icon + display name
  - In-game coordinates (X, Y)
  - Drag handle for reordering (optional, use `vuedraggable` or native HTML5 DnD)
  - Remove button (×) per item
  - "Clear queue" button
- Show status badges: `pending` | `processing` | `completed` | `failed`

**Batch action button:**
- "Mark all in game" primary button (disabled when queue empty or batch running)
- Shows progress: "Processing 3 of 7…"
- Cancel button during batch execution

**Selection handlers:**
- `onMarkerClick({ marker, metaKey, shiftKey })`:
  - `metaKey` (Ctrl/Cmd) → toggle marker in `selectedMarkers`
  - No modifier → replace selection with single marker (current behavior)
  - `shiftKey` → range select (optional, skip for v1)
- After multi-select, user clicks "Mark all in game" to start batch

---

### 4. Update `serverHud` Store (`src/stores/serverHud.ts`)

**New state:**
- `batchQueue: BatchItem[]` — mirrors frontend queue (or frontend drives, store just tracks current)
- `batchRunning: boolean`
- `batchCurrentIndex: number`

**New actions:**
- `startBatchMark(queue: CoordinateItem[])` → calls API for each sequentially
- `cancelBatchMark()` → cancels current + clears queue
- Internal: `processQueue()` loop:
  - For each item: `await startGameMarker(item)`, `await waitForGameMarkerDone()`
  - On error: stop, show toast, keep remaining in queue (per "stop on first error")
  - Update `batchCurrentIndex` for progress UI

**Types:**
```ts
interface BatchItem {
  id: string
  x: number
  y: number
  label: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
}
```

---

### 5. Update `api.ts` (`src/services/api.ts`)

**Option A (simpler): Reuse existing endpoint in loop**
- Frontend/store calls `api.startGameMarker(x, y)` in sequence
- No backend changes needed

**Option B (cleaner): New batch endpoint**
- Add `startGameMarkerBatch(items: CoordinateItem[])` → POST `/game-marker/start-batch`
- Backend manages queue, returns batch ID
- Frontend polls `/game-marker/state` for progress

**Decision: Option A** — Reuse existing robust single-marker automation. Simpler, less backend change, same reliability. The Python side already handles calibration caching across runs.

---

### 6. Backend: Add Batch Endpoint (`server/coord_tooltip.py`)

**New endpoint:** `POST /game-marker/start-batch`
```python
body: { targets: [{x, y, label}, ...], confirm: true, dryRun: false }
```

**Implementation:**
- Validate all targets same zone (compare against current map zone config)
- Store queue in `game_marker_batch_queue` (list)
- Set `game_marker_batch_active = True`
- Process sequentially in background thread:
  - For each target: call existing `begin_game_marker_after_selection()`
  - Wait for completion (poll `game_marker_state`)
  - On error: stop, set batch status `error`, keep remaining
  - On cancel: stop, set status `cancelled`
- Expose batch state via extended `/game-marker/state`:
  ```json
  { "batchActive": true, "batchQueue": [...], "batchIndex": 2, "batchTotal": 5 }
  ```

**Alternative (simpler):** Don't add batch endpoint. Let frontend loop call `/game-marker/start` sequentially. Backend stays unchanged. Frontend tracks queue state.

**Decision: Frontend-driven loop** — Less backend complexity. The Python automation already caches calibration between runs, so sequential calls are fast after first.

---

### 7. Visual Selection State in Leaflet

**Marker rendering:**
- In `LeafletMapView.vue`, markers are created via `L.marker` or `L.circleMarker`
- Add `className: 'marker-selected'` when marker.id in `selectedMarkers`
- CSS: `.marker-selected { filter: drop-shadow(0 0 4px #6c5ce7); }` or custom icon

---

## Data Flow

```
User Ctrl+Click marker
    → MapView.onMarkerClick(metaKey=true)
    → opggMap.addToSelection(marker)
    → LeafletMapView re-renders with selection class
    → User clicks "Mark all in game"
    → MapView.startBatchMark()
    → serverHud.startBatchMark(queue)
    → Loop: api.startGameMarker() + pollGameMarker() per item
    → Python automation runs sequentially (reuses calibration)
    → UI updates batchCurrentIndex, item statuses
    → On completion: toast "Batch completed", queue persists
```

---

## Error Handling

- If any marker fails (timeout, OCR error, focus lost):
  - Stop batch
  - Mark failed item as `failed`
  - Show toast with error
  - Remaining items stay `pending` in queue
  - User can retry by clicking "Mark all in game" again

---

## Zone Validation

- Before starting batch, verify all selected markers have same `activeZone` as current map
- If mismatch: show toast "All markers must be from the same map zone", abort

---

## Testing Checklist

1. Ctrl+Click selects multiple markers, visual feedback works
2. Click without modifier clears selection (single select)
3. Queue panel shows selected markers with correct info
4. Drag to reorder works (if implemented)
5. "Mark all in game" processes sequentially
6. Progress updates in real-time
7. Cancel stops current + leaves rest pending
8. Error on one marker stops batch, shows error
9. Calibration reused on 2nd+ markers (fast)
10. Mixed-zone selection rejected
11. Queue persists after completion
12. Works on both Palpagos and World Tree maps

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/stores/opggMap.ts` | Multi-select state, actions |
| `src/components/map/LeafletMapView.vue` | Click handler with modifiers, selection styling |
| `src/views/MapView.vue` | Queue panel UI, batch logic, selection handlers |
| `src/stores/serverHud.ts` | Batch processing loop, state |
| `src/services/api.ts` | (No change needed if frontend-driven) |
| `server/coord_tooltip.py` | (No change needed if frontend-driven) |

---

## Effort Estimate

| Component | Complexity |
|-----------|------------|
| Store multi-select | Low |
| Leaflet click + styling | Medium |
| Sidebar queue UI | Medium |
| Batch loop in store | Medium |
| Integration/testing | Medium |
| **Total** | **~Medium** |

---

## Open Questions (Resolved)

1. Selection method → **Ctrl/Cmd + Click**
2. Processing → **Sequential**
3. Queue UI → **Sidebar panel**
4. Post-completion → **Persist queue**
5. Error handling → **Stop on first error**
6. Zone mixing → **Same zone only**

---

## Next Steps

1. Implement store changes (`opggMap.ts`)
2. Update LeafletMapView for multi-select click handling
3. Build queue panel in MapView.vue sidebar
4. Add batch loop in serverHud store
5. Test end-to-end with 3-5 markers