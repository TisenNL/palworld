<script setup lang="ts">
/**
 * MapView — main interactive map view.
 * Uses LeafletMapView (op.gg replication) + opggMap store.
 * Maintains all integrations with the Python helper server.
 */
import { useToast } from 'primevue/usetoast'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useRoute } from 'vue-router'
import ArenaLoopPanel from '@/components/map/ArenaLoopPanel.vue'
import AutoLoopPanel from '@/components/map/AutoLoopPanel.vue'
import LeafletMapView from '@/components/map/LeafletMapView.vue'
import { useOpggMapStore } from '@/stores/opggMap'
import { useServerHudStore } from '@/stores/serverHud'
import { getFilterIconUrl } from '@/domain/opggMarkerIcons'
import { toGamePoint, toLatLng, getMapWindow, type MapZone } from '@/domain/opggCoordinates'
import { markerDisplayName, markerFilterLabel, GROUPS, GROUP_LABELS } from '@/types/opggMarker'
import type { BatchQueueItem } from '@/types/batch'
import type { SpawnLocationOption } from '@/types/spawnLocation'

interface LeafletExposed {
  zoomIn: () => void
  zoomOut: () => void
  flyTo: (lat: number, lng: number, zoom?: number) => void
  centerIngame: (x: number, y: number) => void
  getMap: () => unknown
}

const route = useRoute()
const mapStore = useOpggMapStore()
const server   = useServerHudStore()
const toast    = useToast()

const leafletRef = ref<LeafletExposed | null>(null)
const sidebarOpen       = ref(true)
const coordsText        = ref('X / Y')
const searchInput       = ref('')
const mouseLoopSeconds  = ref(40)
const markInGameRunning = ref(false)
const spawnLocationsExpanded = ref(true)
const spawnTab = ref<'pals' | 'humans'>('pals')
const spawnSearch = ref('')

let searchTimer: number | undefined

async function focusRouteCoords(): Promise<void> {
  const x = Number(route.query.x)
  const y = Number(route.query.y)
  if (route.query.x !== undefined && route.query.y !== undefined && !isNaN(x) && !isNaN(y)) {
    await nextTick()
    leafletRef.value?.centerIngame(x, y)
  }
}

// ── Initialize ────────────────────────────────────────────────────────────
onMounted(async () => {
  await mapStore.initialize()
  void server.pollGameMarker()
  void server.pollMouseLoop()
  server.startPlayerPositionPolling()
  await focusRouteCoords()
})

watch(
  () => route.query,
  () => void focusRouteCoords(),
)

onBeforeUnmount(() => {
  server.stopPlayerPositionPolling()
})

// ── Search debounce ───────────────────────────────────────────────────────
watch(searchInput, (val) => {
  clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => { mapStore.search = val }, 250)
})

// ── Computed ──────────────────────────────────────────────────────────────
const markerSizeSliderStyle = computed(() => ({
  '--range-progress': `${mapStore.markerSize}%`,
}))

const playerPositionStatusText = computed(() => {
  if (!server.playerPositionTracking) return 'Live player position tracking is off'
  const status = server.playerPosition?.status
  if (!status) return 'Checking player position…'
  switch (status) {
    case 'ready': return 'Live player position'
    case 'not_running': return 'Palworld is not running'
    case 'access_denied': return 'Player position access denied'
    case 'unsupported': return 'Live position requires Windows'
    case 'unsupported_build': return 'Palworld build not validated'
    case 'waiting_for_player': return 'Waiting for player character'
    case 'invalid_position': return 'Player position needs revalidation'
    case 'probe_error': return 'Player position unavailable'
    default: return 'Player position unavailable'
  }
})

const allMarkersVisible = computed(() => mapStore.visibleTypes.size === 0)

function toggleAllMarkers(): void {
  mapStore.setAllVisible(!allMarkersVisible.value)
}

// Visible types for a group: true if at least one type in this group is visible
function isGroupPartiallyVisible(group: string): boolean {
  const types = mapStore.typesByGroup[group] ?? []
  if (types.length === 0) return false
  return types.some((t) => mapStore.isTypeVisible(t))
}

function isTypeActive(type: string): boolean {
  return mapStore.isTypeVisible(type)
}

function filterIconStyle(filterKey: string): Record<string, string> {
  const iconUrl = getFilterIconUrl(filterKey)
  return iconUrl ? { backgroundImage: `url('${iconUrl}')` } : {}
}

const spawnMapKey = computed(() => (mapStore.activeZone === 'world-tree' ? 'tree' : 'world'))
const spawnOptions = computed(() => {
  const options = mapStore.spawnCatalog?.[spawnTab.value] ?? []
  const query = spawnSearch.value.trim().toLowerCase()
  return options.filter(
    (option) =>
      option.mapKeys.includes(spawnMapKey.value) &&
      (!query || option.name.toLowerCase().includes(query)),
  )
})

function spawnOptionImage(option: SpawnLocationOption): string {
  const imageId = spawnTab.value === 'pals' ? option.id : (option.iconId ?? option.id)
  const imageType = spawnTab.value === 'pals' ? 'pals' : 'icons'
  return `https://s-stats-platform-cdn.op.gg/palworld/images/${imageType}/${encodeURIComponent(imageId)}.png`
}

function onSpawnImageError(event: Event): void {
  const image = event.currentTarget
  if (!(image instanceof HTMLImageElement)) return
  const fallback = image.dataset.fallback
  if (fallback) image.src = fallback
}

function selectSpawnLocation(option: SpawnLocationOption): void {
  void mapStore.toggleSpawnLocation(spawnTab.value, option.id)
}

// ── Zone switch ───────────────────────────────────────────────────────────
async function switchZone(zone: MapZone) {
  await mapStore.setZone(zone)
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
    const enabled = await server.toggleHud(fakeItem, label)
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

// ── Mark queue (batch) ────────────────────────────────────────────────────
const batchActionCount = computed(() => server.pendingBatchCount + mapStore.selectionCount)
const useQueueAction = computed(() => mapStore.selectionCount > 1 || server.pendingBatchCount > 0)

const markButtonText = computed(() => {
  if (server.batchRunning) {
    const current = Math.min(server.batchCurrentIndex + 1, server.batchTotal)
    return `Processing ${current} of ${server.batchTotal}…`
  }
  if (useQueueAction.value) return `Mark queue (${batchActionCount.value})`
  return 'Mark in game'
})

const markButtonDisabled = computed(() => {
  if (useQueueAction.value) {
    return server.batchRunning || markInGameRunning.value || server.gameMarkerBusy
  }
  return !mapStore.selectedMarker || markInGameRunning.value || server.gameMarkerBusy
})

async function runMarkAction(): Promise<void> {
  if (useQueueAction.value) {
    await markAllInGame()
  } else {
    await markInGame()
  }
}

async function markAllInGame() {
  if (server.batchRunning || markInGameRunning.value) return
  if (batchActionCount.value === 0) return
  if (!server.online) {
    window.location.href = 'palchecklist://start'
    toast.add({ severity: 'info', summary: 'Starting local helper',
      detail: 'Keep the Palworld map open, then try again.', life: 4000 })
    return
  }
  // Current selection enters queue (homogeneous zone validation inside store)
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
          <button type="button" class="action-btn" @click="toggleAllMarkers">
            {{ allMarkersVisible ? 'Hide' : 'All' }}
          </button>
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

        <div
          class="player-position-status"
          :class="{
            'player-position-status--ready': server.playerPosition?.status === 'ready',
            'player-position-status--off': !server.playerPositionTracking,
          }"
          role="status"
        >
          <span class="player-position-status__dot" />
          <span>{{ playerPositionStatusText }}</span>
        </div>
        <button
          type="button"
          class="player-position-toggle"
          :aria-pressed="server.playerPositionTracking"
          @click="server.setPlayerPositionTracking(!server.playerPositionTracking)"
        >
          {{ server.playerPositionTracking ? 'Disable position tracking' : 'Enable position tracking' }}
        </button>

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
                <span class="filter-group__progress">
                  {{ mapStore.groupProgress[group]?.checked ?? 0 }}/{{ mapStore.groupProgress[group]?.total ?? 0 }}
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
                  <span class="filter-type-btn__icon" :style="filterIconStyle(type)" aria-hidden="true" />
                  <span class="filter-type-btn__label">
                    {{ markerFilterLabel(type) }}
                  </span>
                  <span class="filter-type-btn__count">
                    {{ mapStore.countsByType[type] ?? 0 }}
                  </span>
                </button>
              </li>
            </ul>
          </div>
          <section class="filter-group map-locations-group">
            <div class="filter-group__header">
              <button
                class="filter-group__toggle"
                type="button"
                :aria-expanded="spawnLocationsExpanded"
                @click="spawnLocationsExpanded = !spawnLocationsExpanded"
              >
                <svg
                  class="filter-group__chevron"
                  :class="{ 'filter-group__chevron--open': spawnLocationsExpanded }"
                  xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="m6 9 6 6 6-6"/>
                </svg>
                Map Locations
                <span v-if="mapStore.selectedSpawnLocation" class="filter-group__progress">
                  {{ mapStore.spawnPoints.length }} points
                </span>
              </button>
            </div>

            <div v-if="spawnLocationsExpanded" class="map-locations__body">
              <div class="map-locations__tabs" role="tablist" aria-label="Map locations">
                <button
                  type="button"
                  role="tab"
                  :aria-selected="spawnTab === 'pals'"
                  :class="{ 'map-locations__tab--active': spawnTab === 'pals' }"
                  @click="spawnTab = 'pals'; spawnSearch = ''"
                >
                  Pal Locations
                </button>
                <button
                  type="button"
                  role="tab"
                  :aria-selected="spawnTab === 'humans'"
                  :class="{ 'map-locations__tab--active': spawnTab === 'humans' }"
                  @click="spawnTab = 'humans'; spawnSearch = ''"
                >
                  Human Locations
                </button>
              </div>

              <input
                v-model="spawnSearch"
                type="search"
                class="map-locations__search"
                :placeholder="spawnTab === 'pals' ? 'Search Pals by name' : 'Search humans by name'"
                :aria-label="spawnTab === 'pals' ? 'Search Pals by name' : 'Search humans by name'"
              />

              <div
                v-if="mapStore.spawnCatalogLoading"
                class="map-locations__status"
                role="status"
              >
                Loading locations…
              </div>
              <div
                v-else-if="mapStore.spawnCatalogError"
                class="map-locations__status map-locations__status--error"
                role="alert"
              >
                {{ mapStore.spawnCatalogError }}
                <button type="button" @click="mapStore.loadSpawnCatalog()">Retry</button>
              </div>
              <div
                v-else-if="mapStore.spawnLocationLoading"
                class="map-locations__status"
                role="status"
              >
                Loading spawn points…
              </div>
              <div
                v-if="mapStore.spawnLocationError"
                class="map-locations__status map-locations__status--error"
                role="alert"
              >
                {{ mapStore.spawnLocationError }}
              </div>

              <ul v-if="!mapStore.spawnCatalogError" class="spawn-location-grid">
                <li v-for="option in spawnOptions" :key="option.id">
                  <button
                    type="button"
                    class="spawn-location-card"
                    :class="{
                      'spawn-location-card--active':
                        mapStore.selectedSpawnLocation?.kind === spawnTab &&
                        mapStore.selectedSpawnLocation.id === option.id,
                    }"
                    :aria-pressed="
                      mapStore.selectedSpawnLocation?.kind === spawnTab &&
                      mapStore.selectedSpawnLocation.id === option.id
                    "
                    :title="option.name"
                    @click="selectSpawnLocation(option)"
                  >
                    <img
                      :src="spawnOptionImage(option)"
                      :data-fallback="spawnTab === 'pals'
                        ? '/opgg-icons/markers/field-boss.webp'
                        : '/opgg-icons/resources/human.webp'"
                      :alt="option.name"
                      loading="lazy"
                      decoding="async"
                      @error="onSpawnImageError"
                    />
                    <span>{{ option.name }}</span>
                  </button>
                </li>
                <li v-if="spawnOptions.length === 0" class="spawn-location-grid__empty">
                  No locations found.
                </li>
              </ul>
            </div>
          </section>
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

            <AutoLoopPanel />
            <ArenaLoopPanel />

            <!-- Mark selected marker(s) in game -->
            <div class="tools-section-label">{{ markButtonText }}</div>
            <div class="tools-row">
              <span class="coords-display">
                <template v-if="mapStore.selectedMarker">
                  {{ markerDisplayName(mapStore.selectedMarker) }}
                </template>
                <template v-else>
                  <em style="color:#444466">Click a marker first</em>
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
                :disabled="markButtonDisabled"
                @click="runMarkAction"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <polygon points="6 3 20 12 6 21 6 3"/>
                </svg>
                {{ markButtonText }}
              </button>
            </div>
            <div v-if="server.gameMarkerBusy" class="tools-status">
              {{ server.gameMarker?.message }}
              <button type="button" class="link-btn" @click="server.cancelGameMarker">Cancel</button>
            </div>

            <div v-if="server.batchQueue.length || server.batchRunning" class="mark-queue">
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
        :player-position="server.playerPosition?.position ?? null"
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

.player-position-status {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 10px 10px;
  color: #8888aa;
  font-size: 11px;
}

.player-position-status__dot {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #f59e0b;
}

.player-position-status--ready {
  color: #cbd5e1;
}

.player-position-status--ready .player-position-status__dot {
  background: #22c55e;
}
.player-position-status--off {
  color: #7777aa;
}
.player-position-status--off .player-position-status__dot {
  background: #7777aa;
}
.player-position-toggle {
  width: 100%;
  margin: 0.45rem 0 0.7rem;
  padding: 0.45rem 0.6rem;
  border: 1px solid #34344d;
  border-radius: 6px;
  background: #171727;
  color: #c5c5df;
  cursor: pointer;
  font: inherit;
  font-size: 0.76rem;
  font-weight: 700;
}
.player-position-toggle:hover {
  background: #252535;
  box-shadow: 0 0 7px #22c55e88;
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
.map-search-input::placeholder { color: #444466; }

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

.map-locations__body {
  display: grid;
  gap: 8px;
  padding: 4px 10px 10px;
}

.map-locations__tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  padding: 3px;
  border: 1px solid #3c3c4d;
  border-radius: 8px;
  background: #151522;
}

.map-locations__tabs button {
  min-width: 0;
  padding: 6px 4px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #9999bb;
  font-size: 10px;
  font-weight: 800;
  cursor: pointer;
}

.map-locations__tabs button:hover {
  color: #e0e0f0;
}

.map-locations__tabs .map-locations__tab--active {
  background: #6c5ce7;
  color: #fff;
}

.map-locations__search {
  width: 100%;
  padding: 6px 9px;
  border: 1px solid #3c3c4d;
  border-radius: 6px;
  outline: none;
  background: #1a1a2e;
  color: #e6e6ff;
  font-size: 10px;
}

.map-locations__search:focus {
  border-color: #6c5ce7;
}

.map-locations__status {
  color: #9999bb;
  font-size: 10px;
}

.map-locations__status--error {
  color: #f87171;
  overflow-wrap: anywhere;
}

.map-locations__status--error button {
  margin-left: 6px;
  border: 0;
  background: none;
  color: #c4b5fd;
  text-decoration: underline;
  cursor: pointer;
}

.spawn-location-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 4px;
  max-height: 270px;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
  scrollbar-width: thin;
  scrollbar-color: #3c3c4d transparent;
}

.spawn-location-card {
  display: flex;
  width: 100%;
  min-width: 0;
  height: 70px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 4px;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 6px;
  background: #222228b3;
  color: #9999bb;
  font-size: 9px;
  cursor: pointer;
}

.spawn-location-card:hover {
  border-color: #4a4a5a;
  color: #fff;
}

.spawn-location-card--active {
  border-color: #8b7cf6;
  background: #6c5ce733;
  color: #fff;
}

.spawn-location-card img {
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  border-radius: 50%;
  object-fit: contain;
  background: #17171b;
}

.spawn-location-card span {
  width: 100%;
  overflow: hidden;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spawn-location-grid__empty {
  grid-column: 1 / -1;
  padding: 8px 4px;
  color: #7777aa;
  font-size: 10px;
  text-align: center;
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
  color: #e6e6ff;
  font-size: 10px;
  font-weight: 900;
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
  color: #555577;
}
.filter-group__chevron--open { transform: rotate(180deg); }

.filter-group__count {
  margin-left: auto;
  color: #555577;
  font-weight: 500;
  font-size: 9px;
}

.filter-group__progress {
  margin-left: 2px;
  color: #f0f0ff;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0;
  white-space: nowrap;
}

.filter-group__all-btn {
  padding: 2px 8px;
  border-radius: 999px;
  border: none;
  background: #1e1e30;
  color: #f0f0ff;
  font-size: 10px;
  font-weight: 900;
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
  font-weight: 800;
  cursor: pointer;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
  text-align: left;
  line-height: 1.2;
}
.filter-type-btn__icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  border-radius: 50%;
  background-color: #0f1428;
  background-size: 75%;
  background-repeat: no-repeat;
  background-position: center;
  border: 1px solid #3c3c4d;
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
  color: #555577;
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
  color: #555577;
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
  color: #555577;
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