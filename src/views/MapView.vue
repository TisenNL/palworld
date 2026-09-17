<script setup lang="ts">
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
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
let cameraTimer: number | undefined

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

async function markInGame(): Promise<void> {
  const marker = map.selectedMarker
  if (!marker) return
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
  try {
    await server.startGameMarker(marker.item)
    toast.add({
      severity: 'info',
      summary: 'Automation started',
      detail: 'Palworld will receive focus automatically. Press Esc to cancel.',
      life: 5000,
    })
  } catch {
    toast.add({
      severity: 'error',
      summary: 'Automation unavailable',
      detail: server.error || 'Could not start game marker automation.',
      life: 4000,
    })
  }
}

function setAll(visible: boolean): void {
  map.setAllLayers(visible)
}

map.restoreCamera()
void server.pollGameMarker()
</script>

<template>
  <div class="workspace map-view">
    <h1 class="sr-only">Interactive map</h1>
    <aside class="sidebar map-sidebar">
      <div class="sidebar-scroll">
        <CompactPanel
          title="Categories"
          :open="panelOpen('map-categories')"
          @update:open="setPanelOpen('map-categories', $event)"
        >
          <InputText v-model="map.search" fluid placeholder="Search the map…" />
          <div class="quick-actions">
            <Button label="All" size="small" text @click="setAll(true)" />
            <Button label="None" size="small" text severity="secondary" @click="setAll(false)" />
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
        </CompactPanel>

        <CompactPanel
          title="Display"
          :open="panelOpen('map-display', false)"
          @update:open="setPanelOpen('map-display', $event)"
        >
          <div class="display-options">
            <label class="layer-check">
              <Checkbox v-model="preferences.values.mapHideDone" binary />
              <span>Hide completed</span>
            </label>
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
          :open="panelOpen('map-tools', false)"
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
                icon="pi pi-crosshairs"
                aria-label="Center coordinates"
                @click="centerTyped"
              />
              <Button
                icon="pi pi-camera"
                severity="secondary"
                aria-label="Read coordinates from screen"
                :loading="server.ocrBusy"
                @click="runOcr"
              />
            </div>
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

    <section class="map-stage" @click.self="popup.visible = false">
      <MapCanvas
        ref="canvas"
        :markers="map.markers"
        :camera="map.camera"
        @camera-change="updateCamera"
        @select="openPopup"
        @context="contextMarker"
        @hover="map.hoverText = $event"
      />
      <div class="map-status">
        {{ map.hoverText || `${map.markers.length.toLocaleString('en-US')} visible markers` }}
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
        <div v-else class="popup-actions">
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
          <Button
            label="Mark in game"
            icon="pi pi-map-marker"
            size="small"
            severity="contrast"
            @click="markInGame"
          />
        </div>
        <small v-if="!server.gameMarkerBusy" class="game-marker-hint">
          Open the Palworld map at maximum zoom in borderless mode. Focus, movement and confirmation
          are automatic.
        </small>
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
  grid-template-columns: minmax(0, 1fr) 38px 38px;
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
  right: 12px;
  bottom: 10px;
  max-width: min(440px, calc(100% - 24px));
  padding: 6px 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 999px;
  color: rgba(255, 255, 255, 0.82);
  font-size: 0.72rem;
  background: rgba(2, 6, 23, 0.76);
  backdrop-filter: blur(10px);
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

.game-marker-progress {
  display: grid;
  gap: 3px;
  margin-top: 5px;
  color: var(--text);
  font-size: 0.68rem;
}

.game-marker-progress :deep(.p-button) {
  justify-self: start;
}

.game-marker-hint {
  max-width: 215px;
  margin-top: 4px;
  line-height: 1.25;
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
