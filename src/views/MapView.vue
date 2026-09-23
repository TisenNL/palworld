<script setup lang="ts">
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Slider from 'primevue/slider'
import { useToast } from 'primevue/usetoast'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import SafeImage from '@/components/common/SafeImage.vue'
import CompactPanel from '@/components/layout/CompactPanel.vue'
import MapCanvas from '@/components/map/MapCanvas.vue'
import { layerGroups } from '@/domain/layers'
import { parseCoordinates } from '@/domain/coordinates'
import { useChecklistStore } from '@/stores/checklist'
import { useMapStore } from '@/stores/map'
import { usePreferencesStore } from '@/stores/preferences'
import { useServerHudStore } from '@/stores/serverHud'
import type { MapMarker } from '@/types/data'

interface MapCanvasExposed {
  fitMarkers: () => void
  centerGame: (x: number, y: number) => void
  redraw: () => void
}

const checklist = useChecklistStore()
const map = useMapStore()
const preferences = usePreferencesStore()
const server = useServerHudStore()
const router = useRouter()
const toast = useToast()
const canvas = ref<MapCanvasExposed | null>(null)
const browseGroup = ref(preferences.values.mapBrowseGroup)
const popup = ref({ visible: false, x: 0, y: 0 })
const mouseLoopSeconds = ref(40)
let cameraTimer: number | undefined
const markInGameRunning = ref(false)

const visibleCount = computed(
  () => checklist.layers.filter((layer) => preferences.values.mapLayers[layer.id]).length,
)
const layerCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const entry of checklist.entries) {
    counts.set(entry.layerId, (counts.get(entry.layerId) ?? 0) + 1)
  }
  return counts
})
const nearestMarker = computed(() =>
  map.selectedMarker ? map.nearestSameType(map.selectedMarker) : null,
)
const searching = computed(() => map.search.trim().length > 0)
const selectionCount = computed(() => map.selectedIds.size)

function panelOpen(key: string, fallback = true): boolean {
  return preferences.values.sideBlockOpen[key] ?? fallback
}

function setPanelOpen(key: string, value: boolean): void {
  preferences.values.sideBlockOpen[key] = value
}

function setGroup(value: string): void {
  browseGroup.value = value
  preferences.values.mapBrowseGroup = value
}

function layersForGroup(groupId: string) {
  return checklist.layers.filter((layer) => layer.group === groupId)
}

function toggleGroup(groupId: string, event: Event): void {
  const open = (event.currentTarget as HTMLDetailsElement).open
  if (open) setGroup(groupId)
  else if (browseGroup.value === groupId) setGroup('')
}

function updateCamera(next: { x: number; y: number; scale: number }): void {
  Object.assign(map.camera, next)
  window.clearTimeout(cameraTimer)
  cameraTimer = window.setTimeout(map.saveCamera, 250)
}

function centerTyped(): void {
  const point = parseCoordinates(map.coordinates)
  if (!point) {
    toast.add({
      severity: 'warn',
      summary: 'Invalid coordinates',
      detail: 'Use the X, Y format. Example: -16, -339.',
      life: 3000,
    })
    return
  }
  canvas.value?.centerGame(point.x, point.y)
  map.hoverText = `Centered on (${point.x}, ${point.y})`
}

async function runOcr(): Promise<void> {
  if (!server.online) {
    window.location.href = 'palchecklist://start'
    toast.add({
      severity: 'info',
      summary: 'Starting local helper',
      detail: 'Wait a few seconds and try OCR again.',
      life: 4000,
    })
    return
  }
  try {
    const value = await server.readCoordinates()
    if (value) {
      map.coordinates = value
      centerTyped()
    }
  } catch {
    toast.add({
      severity: 'error',
      summary: 'OCR unavailable',
      detail: server.error || 'Could not read the coordinates.',
      life: 3500,
    })
  }
}

/** Left-click on map icon: toggle selection (no popup). */
function handleSelect(marker: MapMarker | null): void {
  if (!marker) return
  map.toggleSelected(marker.id)
}

/** Right-click on map icon: open popup + optionally toggle HUD. */
function openPopup(marker: MapMarker | null, position: { x: number; y: number }): void {
  map.showMarker(marker)
  popup.value = {
    visible: Boolean(marker),
    x: Math.min(position.x + 10, window.innerWidth - 260),
    y: Math.min(position.y + 10, window.innerHeight - 180),
  }
}

async function contextMarker(marker: MapMarker, position: { x: number; y: number }): Promise<void> {
  openPopup(marker, position)
  if (!server.online) return
  try {
    const enabled = await server.toggleHud(marker.item, marker.label)
    toast.add({
      severity: 'info',
      summary: enabled ? 'HUD enabled' : 'HUD disabled',
      detail: marker.label,
      life: 2200,
    })
  } catch {
    toast.add({
      severity: 'error',
      summary: 'HUD failed',
      detail: 'The local helper did not respond.',
      life: 3000,
    })
  }
}

function goToList(): void {
  const marker = map.selectedMarker
  if (!marker) return
  void router.push({ path: '/lists', query: { item: `${marker.storage}:${marker.item.id}` } })
}

function toggleSelected(): void {
  const marker = map.selectedMarker
  if (!marker) return
  marker.done = checklist.toggleDone(marker.storage, marker.item.id)
}

function goToNearest(): void {
  const nearest = nearestMarker.value
  if (!nearest) return
  canvas.value?.centerGame(nearest.marker.item.x, nearest.marker.item.y)
  map.showMarker(nearest.marker)
  map.hoverText = `${nearest.marker.label} · ${nearest.distanceMeters.toLocaleString('en-US')} m away`
}

const MARK_MAX_RETRIES = 3

/**
 * Mark in game: iterate through all selected markers one by one.
 * Each marker is retried up to MARK_MAX_RETRIES times on error before
 * stopping the queue. Cancelled (Esc) stops immediately without retry.
 */
async function markInGame(): Promise<void> {
  if (markInGameRunning.value) return
  const queue = [...map.selectedMarkers]
  if (!queue.length) return

  if (!server.online) {
    window.location.href = 'palchecklist://start'
    toast.add({
      severity: 'info',
      summary: 'Starting local helper',
      detail: 'Keep the Palworld map open, then try again.',
      life: 4000,
    })
    return
  }

  markInGameRunning.value = true
  try {
    for (const marker of queue) {
      let attempt = 0
      let finalStatus = ''

      while (attempt < MARK_MAX_RETRIES) {
        attempt++

        try {
          await server.startGameMarker(marker.item)
          if (attempt === 1) {
            toast.add({
              severity: 'info',
              summary: 'Automation started',
              detail: `${marker.label} — Palworld will receive focus automatically. Press Esc to cancel.`,
              life: 5000,
            })
          } else {
            toast.add({
              severity: 'warn',
              summary: `Retrying (${attempt}/${MARK_MAX_RETRIES})`,
              detail: marker.label,
              life: 3000,
            })
          }
        } catch {
          toast.add({
            severity: 'error',
            summary: 'Automation unavailable',
            detail: server.error || 'Could not start game marker automation.',
            life: 4000,
          })
          finalStatus = 'error'
          break
        }

        finalStatus = await waitForGameMarkerDone()

        // Cancelled means user pressed Esc — stop immediately, no retry.
        if (finalStatus === 'cancelled') break

        // Completed — move to next marker.
        if (finalStatus === 'completed') break

        // Error — will retry unless we've hit the limit.
        if (attempt < MARK_MAX_RETRIES) {
          toast.add({
            severity: 'warn',
            summary: 'Retrying after error',
            detail: server.gameMarker?.message || server.gameMarker?.error || marker.label,
            life: 3000,
          })
          // Brief pause before retry so the server resets cleanly.
          await delay(800)
        }
      }

      if (finalStatus !== 'completed') {
        const isCancelled = finalStatus === 'cancelled'
        toast.add({
          severity: isCancelled ? 'warn' : 'error',
          summary: isCancelled ? 'Automation cancelled' : 'Automation failed',
          detail: server.gameMarker?.message || server.gameMarker?.error || marker.label,
          life: 5000,
        })
        break
      }
    }
  } finally {
    markInGameRunning.value = false
  }
}

/**
 * Polls /game-marker/state until the automation reaches a terminal status
 * (completed, cancelled, or error) with active=false, then returns that status.
 *
 * Keyed off status string + active flag — not the volatile boolean gameMarkerBusy —
 * so it is immune to the race where active flips true→false before the first poll.
 */
async function waitForGameMarkerDone(): Promise<string> {
  const TERMINAL = new Set(['completed', 'cancelled', 'error'])

  for (;;) {
    // Read the reactive state that the store auto-polls every 150ms while active.
    const state = server.gameMarker
    if (state && !state.active && TERMINAL.has(state.status)) {
      return state.status
    }
    // When active=false the store stops auto-polling, so drive one explicit poll
    // to pick up the final state, then check again immediately.
    if (state && !state.active) {
      await server.pollGameMarker()
      const final = server.gameMarker
      if (final && TERMINAL.has(final.status)) return final.status
    }
    // Yield for one poll cycle before reading again.
    await delay(150)
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function toggleMouseLoop(): Promise<void> {
  if (!server.online) {
    window.location.href = 'palchecklist://start'
    toast.add({
      severity: 'info',
      summary: 'Starting local helper',
      detail: 'Wait a few seconds and try again.',
      life: 4000,
    })
    return
  }
  try {
    if (server.mouseLoopBusy) {
      await server.stopMouseLoop()
      toast.add({
        severity: 'info',
        summary: 'Mouse loop stopped',
        detail: 'Right/middle click loop was cancelled.',
        life: 2500,
      })
      return
    }
    const seconds = Math.max(1, Math.round(Number(mouseLoopSeconds.value) || 40))
    mouseLoopSeconds.value = seconds
    await server.startMouseLoop(seconds)
    toast.add({
      severity: 'success',
      summary: 'Mouse loop started',
      detail: `Every ${seconds}s: focus Palworld, hold RMB, click MMB. Esc stops.`,
      life: 4500,
    })
  } catch {
    toast.add({
      severity: 'error',
      summary: 'Mouse loop unavailable',
      detail: server.error || 'Could not start the mouse combo loop.',
      life: 4000,
    })
  }
}

function setAll(visible: boolean): void {
  map.setAllLayers(visible)
}

function toggleSidebar(): void {
  preferences.values.sidebarCollapsed = !preferences.values.sidebarCollapsed
}

function focusSearchResult(marker: MapMarker): void {
  preferences.values.mapLayers[marker.layerId] = true
  map.showMarker(marker)
  canvas.value?.centerGame(marker.item.x, marker.item.y)
  popup.value = { visible: true, x: 24, y: 24 }
}

function toggleSearchResultDone(marker: MapMarker, done: boolean): void {
  checklist.setDone(marker.storage, marker.item.id, done)
}

map.restoreCamera()
void server.pollGameMarker()
void server.pollMouseLoop()
</script>

<template>
  <div class="workspace map-view">
    <h1 class="sr-only">Interactive map</h1>
    <aside class="sidebar map-sidebar" :aria-hidden="preferences.values.sidebarCollapsed">
      <div class="sidebar-scroll">
        <CompactPanel
          title="Categories"
          :open="panelOpen('map-categories')"
          @update:open="setPanelOpen('map-categories', $event)"
        >
          <InputText v-model="map.search" fluid placeholder="Procurar no mapa" />
          <template v-if="searching">
            <p class="search-meta">
              {{ map.searchResults.length.toLocaleString('pt-BR') }} resultado(s)
            </p>
            <div class="search-results">
              <label
                v-for="marker in map.searchResults"
                :key="marker.id"
                class="search-result"
                :class="{ active: map.selectedMarker?.id === marker.id, done: marker.done }"
              >
                <Checkbox
                  :model-value="checklist.isDone(marker.storage, marker.item.id)"
                  binary
                  @update:model-value="toggleSearchResultDone(marker, Boolean($event))"
                  @click.stop
                />
                <button
                  type="button"
                  class="search-result-main"
                  @click="focusSearchResult(marker)"
                >
                  <span class="layer-swatch" :style="{ background: marker.color }" />
                  <span class="search-result-text">
                    <span class="search-result-label">{{ marker.label }}</span>
                    <small>{{ marker.item.x }}, {{ marker.item.y }}</small>
                  </span>
                </button>
              </label>
              <p v-if="!map.searchResults.length" class="search-empty">Nenhum resultado.</p>
            </div>
          </template>
          <template v-else>
            <div class="quick-actions">
              <Button label="All" size="small" text @click="setAll(true)" />
              <Button label="Hide" size="small" text severity="secondary" @click="setAll(false)" />
            </div>
            <div class="category-accordions">
              <details
                v-for="group in layerGroups"
                :key="group.id"
                class="category-section"
                :open="browseGroup === group.id"
                @toggle="toggleGroup(group.id, $event)"
              >
                <summary>{{ group.label }}</summary>
                <div class="layer-browser">
                  <label
                    v-for="layer in layersForGroup(group.id)"
                    :key="layer.id"
                    class="layer-check"
                  >
                    <Checkbox
                      :model-value="preferences.values.mapLayers[layer.id]"
                      binary
                      @update:model-value="preferences.values.mapLayers[layer.id] = Boolean($event)"
                    />
                    <span class="layer-swatch" :style="{ background: layer.color }" />
                    <SafeImage
                      v-if="layer.iconUrl"
                      class="layer-image"
                      :src="layer.iconUrl"
                      :fallback-label="layer.label"
                    />
                    <span class="layer-label">{{ layer.label }}</span>
                    <span v-if="layer.label.endsWith(' Cluster')" class="layer-count">
                      {{ layerCounts.get(layer.id) ?? 0 }}
                    </span>
                  </label>
                </div>
              </details>
            </div>
          </template>
        </CompactPanel>

        <CompactPanel
          title="Display"
          :open="panelOpen('map-display', false)"
          @update:open="setPanelOpen('map-display', $event)"
        >
          <div class="display-options">
            <div class="slider-field">
              <span>Menu width</span>
              <Slider v-model="preferences.values.sidebarWidth" :min="260" :max="620" />
            </div>
            <div class="slider-field">
              <span>Transparency</span>
              <Slider v-model="preferences.values.sidebarTransparency" :min="0" :max="70" />
            </div>
          </div>
        </CompactPanel>

        <CompactPanel
          title="Tools"
          :open="panelOpen('map-tools', true)"
          @update:open="setPanelOpen('map-tools', $event)"
        >
          <div class="tool-actions">
            <div class="coordinate-row">
              <InputText
                v-model="map.coordinates"
                placeholder="-16, -339"
                aria-label="Coordinates"
                @keydown.enter="centerTyped"
              />
              <Button
                icon="pi pi-camera"
                severity="secondary"
                aria-label="Read coordinates from screen"
                :loading="server.ocrBusy"
                @click="runOcr"
              />
            </div>
            <div class="mouse-loop-row">
              <InputNumber
                v-model="mouseLoopSeconds"
                :min="1"
                :max="3600"
                :disabled="server.mouseLoopBusy"
                suffix=" s"
                fluid
                input-class="mouse-loop-input"
                aria-label="Mouse loop interval seconds"
              />
              <Button
                :label="server.mouseLoopBusy ? 'Stop' : 'Loop'"
                :icon="server.mouseLoopBusy ? 'pi pi-stop' : 'pi pi-play'"
                :severity="server.mouseLoopBusy ? 'danger' : 'help'"
                :outlined="!server.mouseLoopBusy"
                size="small"
                :aria-label="server.mouseLoopBusy ? 'Stop mouse loop' : 'Start mouse loop'"
                :title="
                  server.mouseLoopBusy
                    ? server.mouseLoop?.message || 'Stop mouse loop'
                    : 'Hold RMB + middle click loop'
                "
                @click="toggleMouseLoop"
              />
            </div>
            <small v-if="server.mouseLoopBusy" class="mouse-loop-status">
              {{ server.mouseLoop?.message || 'Mouse loop running' }}
            </small>
            <Button
              label="Fit to content"
              icon="pi pi-expand"
              size="small"
              outlined
              @click="canvas?.fitMarkers()"
            />
            <Button
              v-if="server.health?.active"
              label="Stop HUD"
              icon="pi pi-stop-circle"
              size="small"
              severity="danger"
              outlined
              @click="server.clearHud"
            />

            <!-- Mark in game section -->
            <div v-if="selectionCount > 0 || server.gameMarkerBusy" class="mark-in-game-section">
              <p class="selection-count">
                {{ selectionCount }} marker{{ selectionCount !== 1 ? 's' : '' }} selected
                <button
                  v-if="selectionCount > 0"
                  type="button"
                  class="clear-selection"
                  aria-label="Clear selection"
                  @click="map.clearSelected()"
                >
                  ×
                </button>
              </p>
              <div v-if="server.gameMarkerBusy" class="game-marker-progress">
                <span>{{ server.gameMarker?.message }}</span>
                <small v-if="server.gameMarker?.current">
                  {{ server.gameMarker.current.join(', ') }}
                  <template v-if="server.gameMarker.distanceMeters !== null">
                    · {{ server.gameMarker.distanceMeters.toLocaleString('en-US') }} m
                  </template>
                </small>
                <Button
                  label="Cancel"
                  icon="pi pi-times"
                  size="small"
                  severity="danger"
                  text
                  @click="server.cancelGameMarker"
                />
              </div>
              <Button
                v-else
                label="Mark in game"
                icon="pi pi-map-marker"
                size="small"
                severity="contrast"
                :disabled="selectionCount === 0 || markInGameRunning"
                :aria-label="`Mark ${selectionCount} selected marker${selectionCount !== 1 ? 's' : ''} in game`"
                @click="markInGame"
              />
              <small v-if="!server.gameMarkerBusy" class="game-marker-hint">
                Open the Palworld map at maximum zoom in borderless mode. Focus, movement and
                confirmation are automatic.
              </small>
            </div>
          </div>
        </CompactPanel>
      </div>
      <div class="sidebar-footer">
        <span class="server-status"
          ><i class="status-dot" :class="{ online: server.online }" />{{
            server.online ? 'Server connected' : 'Server offline'
          }}</span
        >
        <span>{{ visibleCount }}/{{ checklist.layers.length }}</span>
      </div>
    </aside>

    <button
      type="button"
      class="sidebar-edge-toggle"
      :aria-label="preferences.values.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      :title="preferences.values.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      @click="toggleSidebar"
    >
      <i
        :class="preferences.values.sidebarCollapsed ? 'pi pi-angle-right' : 'pi pi-angle-left'"
        aria-hidden="true"
      />
    </button>

    <section class="map-stage" @click.self="popup.visible = false">
      <MapCanvas
        ref="canvas"
        :markers="map.markers"
        :camera="map.camera"
        :selected-ids="map.selectedIds"
        @camera-change="updateCamera"
        @select="handleSelect"
        @context="contextMarker"
        @hover="map.hoverText = $event"
      />
      <div class="map-status">
        {{ map.hoverText || 'Centered on (—, —)' }}
      </div>
      <div
        v-if="popup.visible && map.selectedMarker"
        class="marker-popup"
        :style="{ left: `${popup.x}px`, top: `${popup.y}px` }"
        role="dialog"
        aria-live="polite"
      >
        <button type="button" class="popup-close" aria-label="Close" @click="popup.visible = false">
          ×
        </button>
        <span class="popup-type">{{ map.selectedMarker.layerId }}</span>
        <strong>{{ map.selectedMarker.label }}</strong>
        <small>{{ map.selectedMarker.item.x }}, {{ map.selectedMarker.item.y }}</small>
        <div class="popup-actions">
          <Button
            :label="map.selectedMarker.done ? 'Pending' : 'Complete'"
            :icon="map.selectedMarker.done ? 'pi pi-undo' : 'pi pi-check'"
            size="small"
            @click="toggleSelected"
          />
          <Button
            label="Open list"
            icon="pi pi-list"
            size="small"
            severity="secondary"
            outlined
            @click="goToList"
          />
          <Button
            v-if="nearestMarker"
            :label="`Nearest · ${nearestMarker.distanceMeters.toLocaleString('en-US')} m`"
            icon="pi pi-directions"
            size="small"
            severity="secondary"
            outlined
            @click="goToNearest"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.map-sidebar {
  position: relative;
}

@media (min-width: 861px) {
  .map-sidebar {
    grid-row: 1;
    grid-column: 1;
  }

  .map-stage {
    grid-row: 1;
    grid-column: 1 / -1;
  }
}

.coordinate-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 38px;
  gap: 6px;
}

.quick-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px;
  margin: 5px 0;
}

.category-accordions,
.layer-browser,
.display-options {
  display: grid;
  gap: 5px;
}

.category-section {
  border: 1px solid transparent;
  border-radius: 8px;
}

.category-section[open] {
  border-color: var(--border);
  background: color-mix(in srgb, var(--accent) 6%, transparent);
}

.category-section > summary {
  display: flex;
  min-height: 34px;
  align-items: center;
  justify-content: space-between;
  padding: 6px 9px;
  color: var(--text);
  list-style: none;
  text-align: left;
  cursor: pointer;
}

.category-section > summary::-webkit-details-marker {
  display: none;
}

.category-section > summary::after {
  content: '›';
  font-size: 1.15rem;
  line-height: 1;
  transition: transform 140ms;
}

.category-section[open] > summary::after {
  transform: rotate(90deg);
}

.category-section > summary:hover {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.category-section .layer-browser {
  padding: 0 5px 6px;
}

.layer-check {
  display: flex;
  min-height: 34px;
  align-items: center;
  gap: 8px;
  padding: 4px 5px;
  color: var(--text);
  font-size: 0.8rem;
}

.layer-image {
  width: 24px;
  height: 24px;
  border-radius: 6px;
}

.layer-label {
  min-width: 0;
}

.search-meta {
  margin: 0;
  color: var(--muted);
  font-size: 0.72rem;
}

.search-results {
  display: grid;
  gap: 4px;
  max-height: min(52vh, 420px);
  overflow: auto;
  padding-right: 2px;
}

.search-result {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  cursor: default;
}

.search-result.active {
  outline: 1px solid rgba(120, 180, 255, 0.45);
  background: rgba(80, 140, 220, 0.12);
}

.search-result.done {
  opacity: 0.62;
}

.search-result-main {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px;
  align-items: center;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.search-result-text {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.search-result-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.82rem;
}

.search-result-text small {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.search-empty {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 0.78rem;
}

.layer-count {
  min-width: 2ch;
  margin-left: auto;
  color: var(--muted);
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.layer-swatch {
  flex: 0 0 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.slider-field {
  display: grid;
  grid-template-columns: 110px 1fr;
  align-items: center;
  gap: 10px;
  min-height: 32px;
  color: var(--muted);
  font-size: 0.76rem;
}

.tool-actions {
  display: grid;
  gap: 6px;
}

.mouse-loop-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 6px;
  align-items: center;
}

.mouse-loop-row :deep(.p-inputnumber) {
  width: 100%;
}

.tool-actions :deep(.mouse-loop-input) {
  width: 100%;
  font-variant-numeric: tabular-nums;
}

.mouse-loop-status {
  color: var(--muted);
  font-size: 0.72rem;
  line-height: 1.3;
}

.mark-in-game-section {
  display: grid;
  gap: 5px;
  padding-top: 4px;
  border-top: 1px solid var(--border);
}

.selection-count {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: var(--muted);
  font-size: 0.72rem;
}

.clear-selection {
  padding: 0 3px;
  border: 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1;
  background: transparent;
  cursor: pointer;
}

.clear-selection:hover {
  color: var(--text);
}

.game-marker-progress {
  display: grid;
  gap: 3px;
  color: var(--text);
  font-size: 0.68rem;
}

.game-marker-hint {
  max-width: 215px;
  color: var(--muted);
  font-size: 0.65rem;
  line-height: 1.25;
}

.server-status {
  display: flex;
  align-items: center;
  gap: 7px;
}

.map-stage {
  position: relative;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.map-status {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 5;
  max-width: min(440px, calc(100% - 24px));
  padding: 4px 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 4px;
  color: rgba(255, 255, 255, 0.9);
  font-family: Consolas, 'Courier New', monospace;
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  background: rgba(2, 6, 23, 0.72);
  backdrop-filter: blur(10px);
  pointer-events: none;
}

@media (min-width: 861px) {
  .map-status {
    left: calc(var(--sidebar-width, 320px) + 12px);
    max-width: min(440px, calc(100% - var(--sidebar-width, 320px) - 24px));
  }
}

:global(.app-shell.sidebar-collapsed) .map-status {
  left: 46px;
  max-width: min(440px, calc(100% - 58px));
}

.marker-popup {
  position: absolute;
  z-index: 20;
  display: grid;
  width: max-content;
  max-width: min(240px, calc(100vw - 24px));
  gap: 2px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  background: color-mix(in srgb, var(--panel-solid) 92%, transparent);
  box-shadow: 0 12px 32px rgba(2, 6, 23, 0.38);
  backdrop-filter: blur(14px);
}

.popup-close {
  position: absolute;
  top: 2px;
  right: 5px;
  border: 0;
  color: var(--muted);
  font-size: 1rem;
  background: transparent;
  cursor: pointer;
}

.marker-popup strong {
  padding-right: 12px;
  font-size: 0.82rem;
  line-height: 1.2;
}

.popup-type,
.marker-popup small {
  color: var(--muted);
  font-size: 0.65rem;
}

.popup-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 5px;
}

.marker-popup :deep(.p-button) {
  min-height: 24px;
  padding: 0.18rem 0.35rem;
  font-size: 0.62rem;
  line-height: 1;
}

.marker-popup :deep(.p-button-icon) {
  font-size: 0.62rem;
}

@media (max-width: 860px) {
  .marker-popup {
    position: fixed;
    right: 12px;
    bottom: 12px;
    left: auto !important;
    top: auto !important;
    width: max-content;
    max-width: calc(100vw - 24px);
  }
}
</style>