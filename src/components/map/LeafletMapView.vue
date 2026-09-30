<script setup lang="ts">
/**
 * LeafletMapView — Mapa Leaflet replicando op.gg/palworld/map.
 *
 * Gerencia: tiles, marcadores, popup, smooth scroll, coordenadas.
 * Config exata extraída do JS do op.gg:
 *   CRS.Simple, WORLD_SIZE=256, tileSize=256, zoom 1-8, maxNativeZoom=4
 */

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useOpggMapStore } from '@/stores/opggMap'
import {
  latLngToIngame, formatIngameCoords, parseCoordinates,
  WORLD_SIZE, MAP_BOUNDS,
  toGamePoint, toLatLng, getMapWindow,
} from '@/domain/opggCoordinates'
import { getMarkerHtml, getMarkerColor } from '@/domain/opggMarkerIcons'
import { markerDisplayName, markerTypeLabel } from '@/types/opggMarker'
import type { Marker } from '@/types/opggMarker'
import type { MapZone } from '@/stores/opggMap'
import MarkerPopup from './MarkerPopup.vue'

const props = defineProps<{
  mapZone: MapZone
}>()

const emit = defineEmits<{
  coordsUpdate: [text: string]
  mapReady: []
}>()

const mapStore    = useOpggMapStore()
const mapContainer = ref<HTMLDivElement | null>(null)
const zoomPercent  = ref('100%')
const popupVisible = ref(false)
const popupX       = ref(0)
const popupY       = ref(0)
const coordsText   = ref('X / Y')
const gotoValue    = ref('')

let mapInstance: L.Map | null = null
let tileLayer:   L.TileLayer | null = null
// LayerGroup per type for efficient updates
const layerGroups = new Map<string, L.LayerGroup>()
// Marker → L.Marker lookup by id
const leafletMarkers = new Map<string, L.Marker>()

// ── Zoom percent ──────────────────────────────────────────────────────────
function updateZoomPercent(zoom: number) {
  zoomPercent.value = `${Math.round(Math.pow(2, zoom - 1) * 100)}%`
}

// ── Tile URL ──────────────────────────────────────────────────────────────
function tileUrl(zone: MapZone): string {
  return `/opgg-map-tiles/${zone}/{z}-{x}-{y}.webp`
}

// ── Smooth scroll wheel ───────────────────────────────────────────────────
let smoothZoomTarget: number | null = null
let smoothZoomCenter: L.Point | null = null
let smoothZoomRaf: number | null = null
let smoothZoomEndTimer: number | null = null

function cancelSmoothZoom() {
  if (smoothZoomRaf !== null) { cancelAnimationFrame(smoothZoomRaf); smoothZoomRaf = null }
  if (smoothZoomEndTimer !== null) { clearTimeout(smoothZoomEndTimer); smoothZoomEndTimer = null }
}

function smoothZoomStep(timestamp: number, prevTs: number) {
  const m = mapInstance
  if (!m || smoothZoomTarget === null || smoothZoomCenter === null) return

  const dt = Math.min(timestamp - prevTs, 64) || 16
  const currentZoom = m.getZoom()
  const diff = smoothZoomTarget - currentZoom
  const eased = diff * Math.max(1 - Math.exp(-dt / 70), 0.08)
  const nextZoom = Math.abs(diff) < 0.002 ? smoothZoomTarget : currentZoom + eased

  if (nextZoom !== currentZoom) {
    const scale = m.getZoomScale(nextZoom, currentZoom)
    const half = m.getSize().divideBy(2)
    const d = smoothZoomCenter.subtract(half).multiplyBy(1 - 1 / scale)
    const center = m.containerPointToLatLng(half.add(d))
    m._move(center, nextZoom, { pinch: true, round: false })
  }

  if (Math.abs(smoothZoomTarget - m.getZoom()) >= 0.002) {
    smoothZoomRaf = requestAnimationFrame(ts => smoothZoomStep(ts, timestamp))
  } else {
    smoothZoomTarget = null
    smoothZoomCenter = null
    m._moveEnd(true)
  }
}

function handleWheel(e: WheelEvent) {
  e.preventDefault()
  e.stopImmediatePropagation()
  const m = mapInstance
  if (!m) return
  const delta = e.deltaMode === 1 ? e.deltaY * 16
    : e.deltaMode === 2 ? e.deltaY * m.getSize().y
    : e.deltaY
  const current = smoothZoomTarget ?? m.getZoom()
  smoothZoomTarget = Math.max(m.getMinZoom(), Math.min(m.getMaxZoom(), current - delta / 360))
  smoothZoomCenter = m.mouseEventToContainerPoint(e)
  cancelSmoothZoom()
  smoothZoomRaf = requestAnimationFrame(ts => smoothZoomStep(ts, ts))
  smoothZoomEndTimer = window.setTimeout(() => {
    smoothZoomTarget = null; smoothZoomCenter = null
  }, 400)
}

// ── Marker rendering ──────────────────────────────────────────────────────
function pixelSize(type: string): number {
  return mapStore.markerPixelSize(type)
}

function buildLeafletMarker(marker: Marker): L.Marker {
  const size    = pixelSize(marker.type)
  const checked = mapStore.isChecked(marker)
  const html    = getMarkerHtml(marker, size, checked)

  const icon = L.divIcon({
    html,
    className: 'palworld-map-marker',
    iconSize:   [size, size],
    iconAnchor: [size / 2, size / 2],
  })

  const displayName = markerDisplayName(marker)
  const typeLabel   = markerTypeLabel(marker.type, marker.subtype ?? null)
  const tooltipText = `${displayName} · ${formatIngameCoords(marker.ingameX, marker.ingameY)}`

  const lMarker = L.marker([marker.lat, marker.lng], { icon })
  lMarker.bindTooltip(tooltipText, { permanent: false, direction: 'top', offset: [0, -size / 2 - 4] })

  lMarker.on('click', (e: L.LeafletMouseEvent) => {
    L.DomEvent.stopPropagation(e)
    mapStore.selectMarker(marker)
    popupVisible.value = true
    // Position popup near click point
    if (mapContainer.value) {
      const rect = mapContainer.value.getBoundingClientRect()
      const pt = mapInstance!.latLngToContainerPoint([marker.lat, marker.lng])
      popupX.value = Math.min(pt.x + 10, rect.width - 300)
      popupY.value = Math.max(pt.y - 120, 10)
    }
  })

  return lMarker
}

function syncMarkers() {
  const m = mapInstance
  if (!m) return

  const current = mapStore.filteredMarkers
  const currentIds = new Set(current.map(mk => mk.id))

  // Remove markers no longer visible
  for (const [id, lm] of leafletMarkers) {
    if (!currentIds.has(id)) {
      const type = id.split(':')[0] ?? ''
      layerGroups.get(type)?.removeLayer(lm)
      leafletMarkers.delete(id)
    }
  }

  // Add new markers
  for (const marker of current) {
    if (leafletMarkers.has(marker.id)) continue
    const lm = buildLeafletMarker(marker)
    leafletMarkers.set(marker.id, lm)
    // Get or create LayerGroup for this type
    let lg = layerGroups.get(marker.type)
    if (!lg) {
      lg = L.layerGroup().addTo(m)
      layerGroups.set(marker.type, lg)
    }
    lg.addLayer(lm)
  }
}

function refreshMarkerIcons() {
  // Rebuild icons for all visible markers (called on size or checked change)
  for (const [id, lm] of leafletMarkers) {
    const marker = mapStore.filteredMarkers.find(mk => mk.id === id)
    if (!marker) continue
    const size    = pixelSize(marker.type)
    const checked = mapStore.isChecked(marker)
    const html    = getMarkerHtml(marker, size, checked)
    lm.setIcon(L.divIcon({
      html,
      className: 'palworld-map-marker',
      iconSize:   [size, size],
      iconAnchor: [size / 2, size / 2],
    }))
  }
}

// ── Initialize map ────────────────────────────────────────────────────────
function initMap() {
  const el = mapContainer.value
  if (!el) return

  const saved = mapStore.cameraState
  const defaultCenter: [number, number] = [-(WORLD_SIZE / 2), WORLD_SIZE / 2]
  const center: [number, number] = saved?.zone === props.mapZone
    ? [saved.lat, saved.lng] : defaultCenter
  const zoom = saved?.zone === props.mapZone ? saved.zoom : 3

  mapInstance = L.map(el, {
    crs:              L.CRS.Simple,
    center,
    zoom,
    minZoom:          1,
    maxZoom:          8,
    zoomSnap:         0,
    zoomDelta:        1,
    zoomAnimation:    true,
    fadeAnimation:    true,
    inertia:          true,
    scrollWheelZoom:  false,
    zoomControl:      false,
    attributionControl: false,
    maxBounds:        MAP_BOUNDS,
    maxBoundsViscosity: 0.8,
  })

  tileLayer = L.tileLayer(tileUrl(props.mapZone), {
    tileSize:        256,
    maxNativeZoom:   4,
    minZoom:         0,
    maxZoom:         8,
    noWrap:          true,
    updateWhenZooming: false,
    keepBuffer:      2,
    bounds: [[-(WORLD_SIZE), 0], [0, WORLD_SIZE]],
  }).addTo(mapInstance)

  el.addEventListener('wheel', handleWheel, { passive: false })

  mapInstance.on('mousemove', (e: L.LeafletMouseEvent) => {
    const { ingameX, ingameY } = latLngToIngame(e.latlng.lat, e.latlng.lng, props.mapZone)
    const text = formatIngameCoords(ingameX, ingameY)
    coordsText.value = text
    emit('coordsUpdate', text)
  })

  mapInstance.on('click', () => {
    popupVisible.value = false
    mapStore.selectMarker(null)
  })

  mapInstance.on('moveend zoomend', () => {
    if (!mapInstance) return
    updateZoomPercent(mapInstance.getZoom())
    const c = mapInstance.getCenter()
    mapStore.updateCamera({ lat: c.lat, lng: c.lng, zoom: mapInstance.getZoom(), zone: props.mapZone })
  })

  updateZoomPercent(zoom)
  nextTick(syncMarkers)
  emit('mapReady')
}

// ── Watch filteredMarkers for changes ────────────────────────────────────
watch(() => mapStore.filteredMarkers, () => { syncMarkers() }, { deep: false })

// ── Watch markerSize for icon rebuild ─────────────────────────────────────
watch(() => mapStore.markerSize, () => { refreshMarkerIcons() })

// ── Watch checked state ───────────────────────────────────────────────────
watch(() => mapStore.totalChecked, () => { refreshMarkerIcons() })

// ── Swap tile layer on zone change ────────────────────────────────────────
watch(() => props.mapZone, async (newZone) => {
  if (!mapInstance) return
  if (tileLayer) { mapInstance.removeLayer(tileLayer); tileLayer = null }
  tileLayer = L.tileLayer(tileUrl(newZone), {
    tileSize: 256, maxNativeZoom: 4, minZoom: 0, maxZoom: 8,
    noWrap: true, updateWhenZooming: false, keepBuffer: 2,
    bounds: [[-(WORLD_SIZE), 0], [0, WORLD_SIZE]],
  }).addTo(mapInstance)

  // Clear all markers
  for (const lg of layerGroups.values()) lg.clearLayers()
  layerGroups.clear()
  leafletMarkers.clear()
  popupVisible.value = false
  mapStore.selectMarker(null)

  const saved = mapStore.cameraState
  if (saved?.zone === newZone) {
    mapInstance.setView([saved.lat, saved.lng], saved.zoom, { animate: false })
  } else {
    mapInstance.setView([-(WORLD_SIZE / 2), WORLD_SIZE / 2], 2, { animate: false })
  }
  updateZoomPercent(mapInstance.getZoom())
  await nextTick()
  syncMarkers()
})

// ── Exposed API ───────────────────────────────────────────────────────────
function zoomIn()  { mapInstance?.zoomIn(1) }
function zoomOut() { mapInstance?.zoomOut(1) }

function flyTo(lat: number, lng: number, zoom?: number) {
  mapInstance?.flyTo([lat, lng], zoom ?? mapInstance.getZoom(), { animate: true, duration: 0.5 })
}

function centerIngame(ingameX: number, ingameY: number) {
  const { gameX, gameY } = toGamePoint(ingameX, ingameY)
  const mw = getMapWindow(props.mapZone)
  const [lat, lng] = toLatLng(mw, gameX, gameY)
  flyTo(lat, lng, Math.max(mapInstance?.getZoom() ?? 3, 3))
}

function getMap(): L.Map | null { return mapInstance }

// Go-to coordinates
function handleGoTo() {
  const text = gotoValue.value.trim()
  if (!text) return
  const pt = parseCoordinates(text)
  if (!pt) return
  centerIngame(pt.x, pt.y)
  gotoValue.value = ''
}

// Fullscreen
function toggleFullscreen() {
  const el = mapContainer.value?.parentElement ?? document.documentElement
  if (!document.fullscreenElement) {
    el.requestFullscreen?.().catch(() => {})
  } else {
    document.exitFullscreen?.()
  }
}

defineExpose({ zoomIn, zoomOut, flyTo, centerIngame, getMap })

// ── Lifecycle ─────────────────────────────────────────────────────────────
onMounted(initMap)

onBeforeUnmount(() => {
  cancelSmoothZoom()
  mapContainer.value?.removeEventListener('wheel', handleWheel)
  for (const lg of layerGroups.values()) lg.clearLayers()
  layerGroups.clear()
  leafletMarkers.clear()
  if (mapInstance) { mapInstance.remove(); mapInstance = null }
})
</script>

<template>
  <div class="leaflet-map-root">
    <!-- Map container -->
    <div ref="mapContainer" class="palworld-map" />

    <!-- Fullscreen button -->
    <button
      class="palworld-map-fullscreen-btn palworld-map-control-blur"
      type="button"
      aria-label="Toggle fullscreen"
      title="Fullscreen"
      @click="toggleFullscreen"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
           fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/>
        <path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>
      </svg>
    </button>

    <!-- Zoom controls -->
    <div class="palworld-map-zoom palworld-map-control-blur">
      <button type="button" aria-label="Zoom in"  title="Zoom in"  @click="zoomIn">+</button>
      <button type="button" aria-label="Zoom out" title="Zoom out" @click="zoomOut">−</button>
    </div>

    <!-- Zoom percent -->
    <div class="palworld-map-zoom-pct palworld-map-control-blur">{{ zoomPercent }}</div>

    <!-- Coordinates bar -->
    <div class="palworld-map-coords palworld-map-control-blur">{{ coordsText }}</div>

    <!-- Go-to coordinates form -->
    <form class="palworld-map-goto palworld-map-control-blur" @submit.prevent="handleGoTo">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
           fill="none" stroke="#6666aa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
           aria-hidden="true">
        <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/>
        <circle cx="12" cy="10" r="3"/>
      </svg>
      <input
        v-model="gotoValue"
        type="text"
        placeholder="X, Y (e.g. -612, -17)"
        aria-label="Go to coordinates"
      />
      <button type="submit">Go</button>
    </form>

    <!-- Marker popup (absolute over map) -->
    <Teleport to="body">
      <div
        v-if="popupVisible && mapStore.selectedMarker"
        class="map-popup-outer"
        :style="{ left: `${popupX + (mapContainer?.getBoundingClientRect().left ?? 0)}px`, top: `${popupY + (mapContainer?.getBoundingClientRect().top ?? 0)}px` }"
      >
        <MarkerPopup
          :marker="mapStore.selectedMarker"
          :checked="mapStore.isChecked(mapStore.selectedMarker)"
          @close="() => { popupVisible = false; mapStore.selectMarker(null) }"
          @toggle-checked="() => { if (mapStore.selectedMarker) mapStore.toggleChecked(mapStore.selectedMarker) }"
        />
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.leaflet-map-root {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.palworld-map {
  width: 100%;
  height: 100%;
  background: #0c1822;
}
</style>

<style>
/* Global: popup positioned via Teleport */
.map-popup-outer {
  position: fixed;
  z-index: 9999;
  pointer-events: auto;
}
</style>
