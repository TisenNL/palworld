<script setup lang="ts">
/**
 * MapView — vista principal do mapa interativo.
 * Usa LeafletMapView (op.gg replication) + opggMap store.
 * Mantém todas as integrações com o servidor helper Python.
 */
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'

import LeafletMapView from '@/components/map/LeafletMapView.vue'
import { useOpggMapStore } from '@/stores/opggMap'
import { useServerHudStore } from '@/stores/serverHud'
import { formatIngameCoords, toGamePoint, toLatLng, getMapWindow } from '@/domain/opggCoordinates'
import { markerDisplayName, markerTypeLabel, GROUPS, GROUP_LABELS } from '@/types/opggMarker'
import type { BatchQueueItem } from '@/types/batch'
import type { Marker } from '@/types/opggMarker'
import type { MapZone } from '@/stores/opggMap'

interface LeafletExposed {
  zoomIn: () => void
  zoomOut: () => void
  flyTo: (lat: number, lng: number, zoom?: number) => void
  centerIngame: (x: number, y: number) => void
  getMap: () => unknown
}

const mapStore = useOpggMapStore()
const server   = useServerHudStore()
const toast    = useToast()

const leafletRef = ref<LeafletExposed | null>(null)
const sidebarOpen       = ref(true)
const coordsText        = ref('X / Y')
const searchInput       = ref('')
const mouseLoopSeconds  = ref(40)
const markInGameRunning = ref(false)

let searchTimer: number | undefined

// ── Initialise ────────────────────────────────────────────────────────────
onMounted(async () => {
  await mapStore.initialize()
  void server.pollGameMarker()
  void server.pollMouseLoop()
})

// ── Search debounce ───────────────────────────────────────────────────────
watch(searchInput, (val) => {
  clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => { mapStore.search = val }, 250)
})

// ── Computed ──────────────────────────────────────────────────────────────
const activeZone = computed({
  get: () => mapStore.activeZone,
  set: (z: MapZone) => { mapStore.setZone(z) },
})

const markerSizeSliderStyle = computed(() => ({
  '--range-progress': `${mapStore.markerSize}%`,
}))

// Visible types for a group: true if at least one type in this group is visible
function isGroupPartiallyVisible(group: string): boolean {
  const types = mapStore.typesByGroup[group] ?? []
  if (types.length === 0) return false
  return types.some(t => !mapStore.visibleTypes.has(t))
}

function isTypeActive(type: string): boolean {
  return !mapStore.visibleTypes.has(type)
}

// ── Zone switch ───────────────────────────────────────────────────────────
async function switchZone(zone: MapZone) {
  await mapStore.setZone(zone)
}

// ── Fly to marker ─────────────────────────────────────────────────────────
function flyToMarker(marker: Marker) {
  leafletRef.value?.flyTo(marker.lat, marker.lng, 5)
  mapStore.selectMarker(marker)
}

// ── OCR ───────────────────────────────────────────────────────────────────
async function runOcr() {
  if (!server.online) {
    window.location.href = 'palchecklist://start'
    toast.add({ severity: 'info', summary: 'Starting local helper',
      detail: 'Wait a few seconds and try OCR again.', life: 4000 })
    return
  }
  try {
    const value = await server.readCoordinates()
    if (value) {
      searchInput.value = value
      // parse "X -612 · Y -17" or "-612, -17"
      const m = value.match(/(-?\d+)[,\s·]+\s*(?:Y\s*)?(-?\d+)/)
      if (m) {
        const x = parseInt(m[1]!), y = parseInt(m[2]!)
        const { gameX, gameY } = toGamePoint(x, y)
        const mw = getMapWindow(mapStore.activeZone)
        const [lat, lng] = toLatLng(mw, gameX, gameY)
        leafletRef.value?.flyTo(lat, lng, 5)
      }
    }
  } catch {
    toast.add({ severity: 'error', summary: 'OCR unavailable',
      detail: server.error || 'Could not read the coordinates.', life: 3500 })
  }
}

// ── HUD toggle for selected marker ────────────────────────────────────────
async function toggleHudForSelected() {
  const mk = mapStore.selectedMarker
  if (!mk) return
  if (!server.online) {
    toast.add({ severity: 'warn', summary: 'Server offline',
      detail: 'Start the local helper first.', life: 3000 })
    return
  }
  // serverHud.toggleHud expects a CoordinateItem-like {x, y}
  // we pass ingame coords
  const fakeItem = { id: mk.id, x: mk.ingameX, y: mk.ingameY }
  const label = markerDisplayName(mk)
  try {
    const enabled = await server.toggleHud(fakeItem as any, label)
    toast.add({ severity: 'info',
      summary: enabled ? 'HUD enabled' : 'HUD disabled', detail: label, life: 2200 })
  } catch {
    toast.add({ severity: 'error', summary: 'HUD failed',
      detail: 'The local helper did not respond.', life: 3000 })
  }
}

// ── Mark in game (single) ─────────────────────────────────────────────────
async function markInGame() {
  const mk = mapStore.selectedMarker
  if (!mk || markInGameRunning.value) return
  if (!server.online) {
    window.location.href = 'palchecklist://start'
    toast.add({ severity: 'info', summary: 'Starting local helper',
      detail: 'Keep the Palworld map open, then try again.', life: 4000 })
    return
  }
  markInGameRunning.value = true
  try {
    const status = await server.runSingleMark(
      { id: mk.id, x: mk.ingameX, y: mk.ingameY },
      {
        onStarted: () => toast.add({ severity: 'info', summary: 'Automation started',
          detail: `${markerDisplayName(mk)} — Press Esc to cancel.`, life: 5000 }),
      },
    )
    if (status !== 'completed') {
      toast.add({ severity: status === 'cancelled' ? 'warn' : 'error',
        summary: status === 'cancelled' ? 'Automation cancelled' : 'Automation failed',
        detail: server.gameMarker?.message || '', life: 5000 })
    }
  } finally {
    markInGameRunning.value = false
  }
}

// ── Mark queue (lote) ─────────────────────────────────────────────────────
const batchActionCount = computed(() => server.pendingBatchCount + mapStore.selectionCount)

const batchButtonText = computed(() => {
  if (server.batchRunning) {
    const current = Math.min(server.batchCurrentIndex + 1, server.batchTotal)
    return `Processing ${current} of ${server.batchTotal}…`
  }
  return batchActionCount.value > 0
    ? `Mark all in game (${batchActionCount.value})`
    : 'Mark all in game'
})

async function markAllInGame() {
  if (server.batchRunning || markInGameRunning.value) return
  if (batchActionCount.value === 0) return
  if (!server.online) {
    window.location.href = 'palchecklist://start'
    toast.add({ severity: 'info', summary: 'Starting local helper',
      detail: 'Keep the Palworld map open, then try again.', life: 4000 })
    return
  }
  // Seleção atual entra na fila (validação de zona homogênea dentro do store)
  if (mapStore.selectionCount > 0) {
    const drafts = mapStore.selectionMarkers.map((mk) => ({
      id: mk.id,
      zone: mapStore.activeZone,
      type: mk.type,
      subtype: mk.subtype ?? null,
      name: markerDisplayName(mk),
      x: mk.ingameX,
      y: mk.ingameY,
    }))
    const result = server.enqueueBatch(drafts)
    if (result === 'mixed-zone') {
      toast.add({ severity: 'warn', summary: 'Mixed map zones',
        detail: 'The queue already has markers from another map zone — clear the queue first.',
        life: 4500 })
      return
    }
    if (result === 'running') return
    mapStore.clearBatchSelection()
  }
  const summary = await server.startBatchMark()
  if (summary.cancelled) {
    toast.add({ severity: 'warn', summary: 'Batch cancelled',
      detail: `${summary.completed} marker(s) marked. Remaining items stay in the queue.`,
      life: 4500 })
  } else if (summary.failed > 0) {
    toast.add({ severity: 'error', summary: 'Batch stopped on failure',
      detail: `${summary.completed} completed, ${summary.failed} failed. Remaining items stay in the queue.`,
      life: 5000 })
  } else if (summary.completed > 0) {
    toast.add({ severity: 'success', summary: 'Batch completed',
      detail: `${summary.completed} marker(s) marked in game.`, life: 4000 })
  }
}

function flyToQueueItem(item: BatchQueueItem) {
  leafletRef.value?.centerIngame(item.x, item.y)
}

// ── Mouse loop ────────────────────────────────────────────────────────────
async function toggleMouseLoop() {
  if (!server.online) {
    window.location.href = 'palchecklist://start'
    toast.add({ severity: 'info', summary: 'Starting local helper',
      detail: 'Wait a few seconds and try again.', life: 4000 })
    return
  }
  try {
    if (server.mouseLoopBusy) {
      await server.stopMouseLoop()
      toast.add({ severity: 'info', summary: 'Mouse loop stopped', life: 2500 })
    } else {
      const seconds = Math.max(1, Math.round(Number(mouseLoopSeconds.value) || 40))
      mouseLoopSeconds.value = seconds
      await server.startMouseLoop(seconds)
      toast.add({ severity: 'success', summary: 'Mouse loop started',
        detail: `Every ${seconds}s: focus Palworld, hold RMB, click MMB.`, life: 4500 })
    }
  } catch {
    toast.add({ severity: 'error', summary: 'Mouse loop unavailable',
      detail: server.error || 'Could not start.', life: 4000 })
  }
}
</script>

<template>
  <div class="map-view">
    <!-- ── Sidebar ─────────────────────────────────────────────────────── -->
    <aside class="map-sidebar" :class="{ 'map-sidebar--open': sidebarOpen }">

      <!-- Sidebar header -->
      <div class="map-sidebar__header">
        <div class="map-sidebar__zone-btns">
          <button
            class="zone-btn"
            :class="{ 'zone-btn--active': mapStore.activeZone === 'palpagos' }"
            type="button"
            @click="switchZone('palpagos')"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/>
              <path d="M15 5.764v15"/><path d="M9 3.236v15"/>
            </svg>
            Palpagos Islands
          </button>
          <button
            class="zone-btn"
            :class="{ 'zone-btn--active': mapStore.activeZone === 'world-tree' }"
            type="button"
            @click="switchZone('world-tree')"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M17 14c.7-.7 3-1.8 3-5 0-3.5-3-5-5-5"/><path d="M7 14c-.7-.7-3-1.8-3-5 0-3.5 3-5 5-5"/>
              <path d="M12 22V8"/><path d="M9 22h6"/>
            </svg>
            World Tree
          </button>
        </div>

        <!-- Action buttons -->
        <div class="map-sidebar__actions">
          <button type="button" class="action-btn" @click="mapStore.setAllVisible(true)">All</button>
          <button type="button" class="action-btn action-btn--secondary" @click="mapStore.resetFilters()">Reset</button>
          <button type="button" class="action-btn action-btn--icon" title="Collapse all groups"
                  @click="mapStore.collapseAllGroups()">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="m7 20 5-5 5 5"/><path d="m7 4 5 5 5-5"/>
            </svg>
          </button>
          <button type="button" class="action-btn action-btn--icon" title="Hide sidebar"
                  @click="sidebarOpen = false">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="m15 18-6-6 6-6"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Scrollable content -->
      <div class="map-sidebar__scroll">

        <!-- Search -->
        <div class="map-sidebar__search">
          <input
            v-model="searchInput"
            type="search"
            class="map-search-input"
            placeholder="Search markers…"
            aria-label="Search markers"
          />
        </div>

        <!-- Loading / error -->
        <div v-if="mapStore.loading" class="map-sidebar__status">Loading…</div>
        <div v-else-if="mapStore.error" class="map-sidebar__status map-sidebar__status--error">
          {{ mapStore.error }}
        </div>

        <!-- Category groups -->
        <template v-else>
          <div
            v-for="group in GROUPS"
            :key="group"
            class="filter-group"
          >
            <!-- Group header -->
            <div class="filter-group__header">
              <button
                class="filter-group__toggle"
                type="button"
                :aria-expanded="mapStore.expandedGroups.has(group)"
                @click="mapStore.toggleGroup(group)"
              >
                <svg
                  class="filter-group__chevron"
                  :class="{ 'filter-group__chevron--open': mapStore.expandedGroups.has(group) }"
                  xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="m6 9 6 6 6-6"/>
                </svg>
                {{ GROUP_LABELS[group] }}
                <span class="filter-group__count">
                  {{ mapStore.countsByType[group] ?? Object.entries(mapStore.countsByType).filter(([k]) => (mapStore.typesByGroup[group] ?? []).includes(k)).reduce((s, [, v]) => s + v, 0) }}
                </span>
              </button>
              <button
                class="filter-group__all-btn"
                type="button"
                @click="mapStore.setGroupVisible(group, isGroupPartiallyVisible(group) ? false : true)"
              >
                {{ isGroupPartiallyVisible(group) ? 'Hide' : 'All' }}
              </button>
            </div>

            <!-- Type list -->
            <ul
              v-show="mapStore.expandedGroups.has(group)"
              class="filter-group__list"
            >
              <li
                v-for="type in (mapStore.typesByGroup[group] ?? [])"
                :key="type"
              >
                <button
                  class="filter-type-btn"
                  :class="{ 'filter-type-btn--active': isTypeActive(type), 'filter-type-btn--inactive': !isTypeActive(type) }"
                  type="button"
                  :aria-pressed="isTypeActive(type)"
                  @click="mapStore.toggleType(type)"
                >
                  <span class="filter-type-btn__icon" v-if="true">
                    <!-- Icon slot: inline background-image -->
                  </span>
                  <span class="filter-type-btn__label">
                    {{ markerTypeLabel(type) }}
                  </span>
                  <span class="filter-type-btn__count">
                    {{ mapStore.countsByType[type] ?? 0 }}
                  </span>
                </button>
              </li>
            </ul>
          </div>
        </template>

        <!-- Marker size slider -->
        <div class="map-sidebar__size-row">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
               fill="none" stroke="#6666aa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>
          </svg>
          <input
            v-model.number="mapStore.markerSize"
            type="range"
            class="palworld-map-range"
            min="0"
            max="100"
            :style="markerSizeSliderStyle"
            aria-label="Marker size"
          />
        </div>

        <!-- Tools section -->
        <details class="tools-panel" open>
          <summary>Tools</summary>
          <div class="tools-panel__body">
            <!-- Coordinates / OCR -->
            <div class="tools-row">
              <input
                v-model="searchInput"
                type="text"
                class="coords-input"
                placeholder="-612, -17"
                aria-label="Go to coordinates"
              />
              <button
                class="icon-btn"
                type="button"
                :disabled="server.ocrBusy"
                title="Read coordinates from screen (OCR)"
                aria-label="OCR coordinates"
                @click="runOcr"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M2 13a2 2 0 0 0 2-2V7a2 2 0 0 1 2-2h16"/>
                  <path d="M22 11a2 2 0 0 0-2 2v4a2 2 0 0 1-2 2H4"/>
                  <path d="m7 15 5 5 5-5"/>
                </svg>
              </button>
            </div>

            <!-- Mouse loop -->
            <div class="tools-row">
              <input
                v-model.number="mouseLoopSeconds"
                type="number"
                class="coords-input"
                :min="1" :max="3600"
                :disabled="server.mouseLoopBusy"
                aria-label="Mouse loop interval (seconds)"
              />
              <button
                class="icon-btn"
                :class="{ 'icon-btn--danger': server.mouseLoopBusy }"
                type="button"
                :title="server.mouseLoopBusy ? 'Stop mouse loop' : 'Start mouse loop'"
                :aria-label="server.mouseLoopBusy ? 'Stop' : 'Start loop'"
                @click="toggleMouseLoop"
              >
                <svg v-if="!server.mouseLoopBusy" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <polygon points="6 3 20 12 6 21 6 3"/>
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect width="4" height="16" x="6" y="4"/><rect width="4" height="16" x="14" y="4"/>
                </svg>
              </button>
            </div>

            <!-- Mark in game -->
            <div class="tools-section-label">Mark in game</div>
            <div class="tools-row">
              <span class="coords-display">
                <template v-if="mapStore.selectedMarker">
                  {{ markerDisplayName(mapStore.selectedMarker) }}
                </template>
                <template v-else>
                  <em style="color:#4444660">Click a marker first</em>
                </template>
              </span>
              <button
                class="icon-btn"
                :class="{ 'icon-btn--danger': server.health?.active }"
                type="button"
                :disabled="!mapStore.selectedMarker"
                :title="server.health?.active ? 'Stop HUD' : 'Toggle HUD in-game'"
                @click="toggleHudForSelected"
              >
                <!-- map-pin icon -->
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>
                </svg>
              </button>
            </div>
            <div class="tools-row">
              <button
                class="primary-btn"
                style="width:100%"
                type="button"
                :disabled="!mapStore.selectedMarker || markInGameRunning || server.gameMarkerBusy"
                @click="markInGame"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <polygon points="6 3 20 12 6 21 6 3"/>
                </svg>
                Mark in game
              </button>
            </div>
            <div v-if="server.gameMarkerBusy" class="tools-status">
              {{ server.gameMarker?.message }}
              <button type="button" class="link-btn" @click="server.cancelGameMarker">Cancel</button>
            </div>

            <!-- Mark queue (batch) -->
            <div class="tools-section-label">
              Mark queue <span v-if="server.batchQueue.length">({{ server.batchQueue.length }})</span>
            </div>
            <div class="mark-queue">
              <div v-if="server.batchQueue.length === 0" class="mark-queue__empty">
                <em>Ctrl + Click markers to queue them</em>
              </div>
              <template v-else>
                <ul class="mark-queue__list">
                  <li
                    v-for="item in server.batchQueue"
                    :key="item.id"
                    class="mark-queue__item"
                    :class="{ 'mark-queue__item--current': item.status === 'processing' }"
                    :title="item.error || item.name"
                  >
                    <span class="mark-queue__status" :data-status="item.status" />
                    <button type="button" class="mark-queue__name" @click="flyToQueueItem(item)">
                      {{ item.name }}
                    </button>
                    <span class="mark-queue__coords">{{ item.x }}, {{ item.y }}</span>
                    <button
                      v-if="!server.batchRunning"
                      type="button"
                      class="mark-queue__remove"
                      aria-label="Remove from queue"
                      @click="server.removeBatchItem(item.id)"
                    >×</button>
                  </li>
                </ul>
                <div class="mark-queue__footer">
                  <button
                    type="button"
                    class="link-btn link-btn--muted"
                    :disabled="server.batchRunning"
                    @click="server.clearBatchQueue()"
                  >Clear queue</button>
                </div>
              </template>
              <div class="mark-queue__actions">
                <button
                  class="primary-btn"
                  type="button"
                  :disabled="batchActionCount === 0 || server.batchRunning || markInGameRunning || server.gameMarkerBusy"
                  @click="markAllInGame"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                       fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <polygon points="6 3 20 12 6 21 6 3"/>
                  </svg>
                  {{ batchButtonText }}
                </button>
                <button
                  v-if="server.batchRunning"
                  class="icon-btn icon-btn--danger"
                  type="button"
                  title="Cancel batch"
                  aria-label="Cancel batch"
                  @click="server.cancelBatchMark()"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                       fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <rect width="4" height="16" x="6" y="4"/><rect width="4" height="16" x="14" y="4"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </details>
      </div>

      <!-- Footer -->
      <div class="map-sidebar__footer">
        <span class="server-dot" :class="{ 'server-dot--online': server.online }" />
        <span>{{ server.online ? 'Connected' : 'Offline' }}</span>
        <span class="map-sidebar__footer-count">
          {{ mapStore.filteredMarkers.length.toLocaleString() }} markers
        </span>
      </div>
    </aside>

    <!-- Show sidebar button (when hidden) -->
    <button
      v-if="!sidebarOpen"
      class="sidebar-show-btn"
      type="button"
      aria-label="Show sidebar"
      @click="sidebarOpen = true"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
           fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="m9 18 6-6-6-6"/>
      </svg>
    </button>

    <!-- ── Map viewport ─────────────────────────────────────────────────── -->
    <div class="palworld-map-viewport">
      <LeafletMapView
        ref="leafletRef"
        :map-zone="mapStore.activeZone"
        @coords-update="coordsText = $event"
        @map-ready="() => {}"
      />
    </div>
  </div>
</template>

<style scoped>
/* ── Layout ────────────────────────────────────────────────────────────── */
.map-view {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.palworld-map-viewport {
  flex: 1;
  min-width: 0;
  min-height: 0;
  position: relative;
}

/* ── Sidebar ───────────────────────────────────────────────────────────── */
.map-sidebar {
  display: flex;
  flex-direction: column;
  width: 22rem;
  flex-shrink: 0;
  height: 100%;
  background: rgba(15, 18, 32, 0.97);
  border-right: 1px solid #2a2a3e;
  overflow: hidden;
  transform: translateX(-100%);
  transition: transform 0.2s ease;
  position: absolute;
  top: 0; left: 0;
  z-index: 100;
}

@media (min-width: 1024px) {
  .map-sidebar {
    position: relative;
    transform: none;
  }
  .map-sidebar--open {
    transform: none;
  }
}

.map-sidebar--open {
  transform: translateX(0);
}

.map-sidebar__header {
  flex-shrink: 0;
  border-bottom: 1px solid #2a2a3e;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: rgba(15, 18, 32, 0.99);
  position: sticky;
  top: 0;
  z-index: 2;
}

.map-sidebar__zone-btns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.zone-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: center;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid #3c3c4d;
  background: transparent;
  color: #7777aa;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.zone-btn:hover { background: #1e1e30; color: #ccccee; }
.zone-btn--active {
  background: linear-gradient(135deg, #0ea5e9, #4f46e5);
  border-color: transparent;
  color: #fff;
}

.map-sidebar__actions {
  display: flex;
  gap: 4px;
  align-items: center;
}

.action-btn {
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid #3c3c4d;
  background: #1a1a2e;
  color: #ccccee;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s;
}
.action-btn:hover { background: #252535; }
.action-btn--secondary { background: transparent; color: #7777aa; }
.action-btn--secondary:hover { color: #ccccee; background: #1a1a2e; }
.action-btn--icon {
  padding: 4px 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.action-btn--icon:last-child { margin-left: auto; }

.map-sidebar__scroll {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #3c3c4d transparent;
  padding: 8px 0;
}

.map-sidebar__search {
  padding: 0 10px 6px;
}

.map-search-input {
  width: 100%;
  background: #1a1a2e;
  border: 1px solid #3c3c4d;
  border-radius: 8px;
  color: #ccccee;
  font-size: 12px;
  padding: 6px 10px;
  outline: none;
  transition: border-color 0.15s;
}
.map-search-input:focus { border-color: #6c5ce7; }
.map-search-input::placeholder { color: #4444660; }

.map-sidebar__status {
  padding: 16px;
  text-align: center;
  color: #7777aa;
  font-size: 12px;
}
.map-sidebar__status--error { color: #f87171; }

/* ── Filter groups ─────────────────────────────────────────────────────── */
.filter-group {
  border-bottom: 1px solid #1e1e2e;
}

.filter-group__header {
  display: flex;
  align-items: center;
  padding: 0 4px 0 10px;
}

.filter-group__toggle {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 0;
  background: none;
  border: none;
  color: #9999bb;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  cursor: pointer;
  transition: color 0.15s;
  text-align: left;
}
.filter-group__toggle:hover { color: #e0e0f0; }

.filter-group__chevron {
  transition: transform 0.15s;
  flex-shrink: 0;
  color: #5555770;
}
.filter-group__chevron--open { transform: rotate(180deg); }

.filter-group__count {
  margin-left: auto;
  color: #5555770;
  font-weight: 500;
  font-size: 9px;
}

.filter-group__all-btn {
  padding: 2px 8px;
  border-radius: 999px;
  border: none;
  background: #1e1e30;
  color: #8888aa;
  font-size: 9px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  flex-shrink: 0;
  margin-right: 6px;
}
.filter-group__all-btn:hover { background: #2a2a40; color: #ccccee; }

.filter-group__list {
  list-style: none;
  margin: 0;
  padding: 2px 6px 6px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3px;
}

.filter-type-btn {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 5px 7px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: #1a1a2e;
  color: #7777aa;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
  text-align: left;
  line-height: 1.2;
}
.filter-type-btn--active {
  background: #1e1e2e;
  border-color: #3c3c4d;
  color: #ccccee;
}
.filter-type-btn--inactive {
  opacity: 0.5;
}
.filter-type-btn:hover {
  background: #252538;
  border-color: #4a4a5e;
  color: #e0e0f0;
  opacity: 1;
}

.filter-type-btn__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.filter-type-btn__count {
  color: #5555770;
  font-size: 9px;
  flex-shrink: 0;
}

/* ── Size slider ───────────────────────────────────────────────────────── */
.map-sidebar__size-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid #1e1e2e;
}

.map-sidebar__size-row .palworld-map-range {
  flex: 1;
}

/* ── Tools panel ───────────────────────────────────────────────────────── */
.tools-panel {
  border-top: 1px solid #1e1e2e;
  font-size: 11px;
}

.tools-panel > summary {
  padding: 8px 12px;
  color: #9999bb;
  font-weight: 700;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
.tools-panel > summary::-webkit-details-marker { display: none; }

.tools-panel__body {
  padding: 4px 10px 10px;
  display: grid;
  gap: 6px;
}

.tools-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 6px;
  align-items: center;
}

.coords-input {
  background: #1a1a2e;
  border: 1px solid #3c3c4d;
  border-radius: 6px;
  color: #ccccee;
  font-size: 11px;
  padding: 5px 8px;
  outline: none;
  width: 100%;
  transition: border-color 0.15s;
}
.coords-input:focus { border-color: #6c5ce7; }

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid #3c3c4d;
  background: #1a1a2e;
  color: #8888aa;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}
.icon-btn:hover { background: #252538; color: #ccccee; }
.icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.icon-btn--danger { color: #f87171; border-color: rgba(248,113,113,0.3); }
.icon-btn--danger:hover { background: rgba(248,113,113,0.15); }

.primary-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 6px;
  border: none;
  background: rgba(108, 92, 231, 0.8);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s;
}
.primary-btn:hover { background: #6c5ce7; }
.primary-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.tools-status {
  font-size: 10px;
  color: #8888aa;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.tools-section-label {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: #5555770;
  padding-top: 4px;
}

.coords-display {
  font-size: 10px;
  color: #aaaacc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.link-btn {
  background: none;
  border: none;
  color: #f87171;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
}
.link-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.link-btn--muted { color: #7777aa; }
.link-btn--muted:hover { color: #ccccee; }

/* ── Mark queue (batch) ────────────────────────────────────────────────── */
.mark-queue {
  display: grid;
  gap: 6px;
}

.mark-queue__empty {
  font-size: 10px;
  color: #555577;
  padding: 2px 0;
}

.mark-queue__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 3px;
  max-height: 180px;
  overflow-y: auto;
}

.mark-queue__item {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border-radius: 6px;
  background: #1a1a2e;
  border: 1px solid transparent;
  font-size: 10px;
}

.mark-queue__item--current {
  border-color: #6c5ce7;
}

.mark-queue__status {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #55556e;
  flex-shrink: 0;
}
.mark-queue__status[data-status='pending'] { background: #55556e; }
.mark-queue__status[data-status='processing'] {
  background: #38bdf8;
  animation: mark-queue-pulse 1s ease-in-out infinite;
}
.mark-queue__status[data-status='completed'] { background: #34d399; }
.mark-queue__status[data-status='failed'] { background: #f87171; }

@keyframes mark-queue-pulse {
  50% { opacity: 0.3; }
}

.mark-queue__name {
  background: none;
  border: none;
  padding: 0;
  color: #ccccee;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mark-queue__name:hover { color: #e0e0f0; text-decoration: underline; }

.mark-queue__coords {
  color: #7777aa;
  font-size: 9px;
}

.mark-queue__remove {
  background: none;
  border: none;
  color: #7777aa;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  padding: 0 2px;
}
.mark-queue__remove:hover { color: #f87171; }

.mark-queue__actions {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 6px;
  align-items: center;
}

.mark-queue__footer {
  display: flex;
  justify-content: flex-end;
}

/* ── Footer ────────────────────────────────────────────────────────────── */
.map-sidebar__footer {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-top: 1px solid #1e1e2e;
  font-size: 10px;
  color: #6666aa;
}

.server-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #ef4444;
  flex-shrink: 0;
}
.server-dot--online { background: #22c55e; }

.map-sidebar__footer-count {
  margin-left: auto;
  font-weight: 700;
  color: #5555770;
}

/* ── Show sidebar btn (mobile/collapsed) ────────────────────────────────── */
.sidebar-show-btn {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid #3c3c4d;
  background: rgba(20, 20, 40, 0.92);
  color: #ccccee;
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition: background 0.15s;
}
.sidebar-show-btn:hover { background: rgba(108, 92, 231, 0.3); border-color: #6c5ce7; }

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media (min-width: 1024px) {
  .map-sidebar {
    position: relative;
    transform: none;
    width: 22rem;
  }
  .sidebar-show-btn { display: none; }
}

@media (max-width: 1023px) {
  .map-sidebar--open {
    box-shadow: 4px 0 20px rgba(0, 0, 0, 0.5);
  }
}

@media (min-width: 1280px) {
  .map-sidebar { width: 24rem; }
}
</style>
