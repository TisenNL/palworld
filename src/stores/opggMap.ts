/**
 * Store principal do novo mapa Palworld baseado no op.gg.
 * Gerencia: dados dos markers, filtros por tipo/grupo, progresso (checked),
 * busca, tamanho dos markers, câmera e marker selecionado.
 *
 * localStorage key: 'palworld:map:checked-collectibles'
 * Formato do op.gg: [{key: 'effigy:{lat}:{lng}' | 'collectible:{type}:{lat}:{lng}', x: lat, y: lng}]
 */

import { defineStore } from 'pinia'
import {
  computed,
  reactive,
  ref,
  shallowRef,
  watch,
} from 'vue'
import { z } from 'zod'

import {
  markersSchema,
  markerCountsSchema,
  markerDisplayName,
  markerTypeLabel,
  GROUPS,
  type Marker,
  type MarkerCounts,
  type MapZone,
  type GroupId,
} from '@/types/opggMarker'
import { formatIngameCoords } from '@/domain/opggCoordinates'

// ── localStorage keys (same as op.gg) ────────────────────────────────────────

const CHECKED_KEY = 'palworld:map:checked-collectibles'
const CAMERA_KEY  = 'palworld:map:camera'

// ── Checked item format (op.gg localStorage format) ──────────────────────────

interface CheckedItem {
  key: string   // 'effigy:{lat}:{lng}' or 'collectible:{type}:{lat}:{lng}'
  x: number     // lat (Leaflet)
  y: number     // lng (Leaflet)
}

function makeCheckedKey(marker: Marker): string {
  if (marker.type === 'LifmunkEffigy') {
    return `effigy:${marker.lat}:${marker.lng}`
  }
  return `collectible:${marker.type}:${marker.lat}:${marker.lng}`
}

// ── Camera state ──────────────────────────────────────────────────────────────

export interface MapCameraState {
  lat: number
  lng: number
  zoom: number
  zone: MapZone
}

function loadCameraState(): MapCameraState | null {
  try {
    const raw = localStorage.getItem(CAMERA_KEY)
    if (!raw) return null
    return z.object({
      lat:  z.number(),
      lng:  z.number(),
      zoom: z.number(),
      zone: z.enum(['palpagos', 'world-tree']),
    }).parse(JSON.parse(raw))
  } catch {
    return null
  }
}

function saveCameraState(state: MapCameraState): void {
  try {
    localStorage.setItem(CAMERA_KEY, JSON.stringify(state))
  } catch {}
}

// ── Checked persistence ───────────────────────────────────────────────────────

function loadChecked(): Map<string, CheckedItem> {
  try {
    const raw = localStorage.getItem(CHECKED_KEY)
    if (!raw) return new Map()
    const items = JSON.parse(raw)
    if (!Array.isArray(items)) return new Map()
    const map = new Map<string, CheckedItem>()
    for (const item of items) {
      if (item && typeof item.key === 'string') {
        map.set(item.key, item as CheckedItem)
      }
    }
    return map
  } catch {
    return new Map()
  }
}

function persistChecked(checkedMap: Map<string, CheckedItem>): void {
  try {
    localStorage.setItem(CHECKED_KEY, JSON.stringify([...checkedMap.values()]))
  } catch {}
}

// ── Store ─────────────────────────────────────────────────────────────────────

export const useOpggMapStore = defineStore('opggMap', () => {
  // ── State ─────────────────────────────────────────────────────────────────

  /** Active map zone */
  const activeZone = ref<MapZone>('palpagos')

  /** Raw markers for the active zone (loaded from JSON) */
  const rawMarkers = shallowRef<Marker[]>([])

  /** Marker counts by type, both zones */
  const counts = ref<MarkerCounts>({ palpagos: {}, worldtree: {} })

  /** Loading/error state */
  const loading  = ref(false)
  const error    = ref('')

  /** Set of currently visible types (key = type string, empty = all visible) */
  const visibleTypes = reactive(new Set<string>())

  /** Set of hidden groups (collapsed in sidebar but still tracked) */
  const expandedGroups = reactive(new Set<string>(GROUPS as unknown as string[]))

  /** Marker size: 0–100, default 50 (maps to 20–48px in the renderer) */
  const markerSize = ref(50)

  /** Search string (debounced in the view) */
  const search = ref('')

  /** Currently shown in popup */
  const selectedMarker = ref<Marker | null>(null)

  /** Camera state, persisted in localStorage */
  const cameraState = ref<MapCameraState | null>(loadCameraState())

  /** Checked items map: key → CheckedItem */
  const checkedMap = reactive(loadChecked())

  // ── Load data ────────────────────────────────────────────────────────────

  async function loadZone(zone: MapZone): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const fileName = zone === 'palpagos'
        ? '/opgg-markers-palpagos.json'
        : '/opgg-markers-worldtree.json'
      const resp = await fetch(fileName, { cache: 'no-store' })
      if (!resp.ok) throw new Error(`Failed to load ${fileName}: HTTP ${resp.status}`)
      const json = await resp.json()
      rawMarkers.value = markersSchema.parse(json)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load markers'
      rawMarkers.value = []
    } finally {
      loading.value = false
    }
  }

  async function loadCounts(): Promise<void> {
    try {
      const resp = await fetch('/opgg-marker-counts.json')
      if (!resp.ok) return
      counts.value = markerCountsSchema.parse(await resp.json())
    } catch {}
  }

  /** Initialize: load counts + active zone markers */
  async function initialize(): Promise<void> {
    await Promise.all([loadCounts(), loadZone(activeZone.value)])
  }

  /** Switch active map zone */
  async function setZone(zone: MapZone): Promise<void> {
    if (zone === activeZone.value && rawMarkers.value.length > 0) return
    activeZone.value = zone
    selectedMarker.value = null
    await loadZone(zone)
  }

  // ── Visibility filters ───────────────────────────────────────────────────

  function isTypeVisible(type: string): boolean {
    return visibleTypes.size === 0 || visibleTypes.has(type)
  }

  function toggleType(type: string): void {
    if (visibleTypes.size === 0) {
      // All visible → hide all except this one
      const allTypes = [...new Set(rawMarkers.value.map(m => m.type))]
      for (const t of allTypes) {
        if (t !== type) visibleTypes.add(t)
      }
    } else if (visibleTypes.has(type)) {
      visibleTypes.delete(type)
      // If nothing hidden now, treat as all-visible
      if (visibleTypes.size === 0) visibleTypes.clear()
    } else {
      visibleTypes.delete(type)
    }
  }

  /** Show only one specific type */
  function showOnlyType(type: string): void {
    visibleTypes.clear()
    const allTypes = [...new Set(rawMarkers.value.map(m => m.type))]
    for (const t of allTypes) {
      if (t !== type) visibleTypes.add(t)
    }
  }

  /** Toggle all types in a group visible/hidden */
  function setGroupVisible(group: string, visible: boolean): void {
    const typesInGroup = [...new Set(
      rawMarkers.value.filter(m => m.group === group).map(m => m.type)
    )]
    if (visible) {
      for (const t of typesInGroup) visibleTypes.delete(t)
    } else {
      for (const t of typesInGroup) visibleTypes.add(t)
    }
  }

  function setAllVisible(visible: boolean): void {
    if (visible) {
      visibleTypes.clear()
    } else {
      for (const m of rawMarkers.value) visibleTypes.add(m.type)
    }
  }

  function resetFilters(): void {
    visibleTypes.clear()
  }

  // ── Expanded groups ──────────────────────────────────────────────────────

  function toggleGroup(group: string): void {
    if (expandedGroups.has(group)) expandedGroups.delete(group)
    else expandedGroups.add(group)
  }

  function collapseAllGroups(): void {
    expandedGroups.clear()
  }

  function expandAllGroups(): void {
    for (const g of GROUPS) expandedGroups.add(g)
  }

  // ── Computed: filtered markers ───────────────────────────────────────────

  const filteredMarkers = computed<Marker[]>(() => {
    const q = search.value.trim().toLowerCase()
    return rawMarkers.value.filter(m => {
      // Type visibility
      if (visibleTypes.size > 0 && visibleTypes.has(m.type)) return false
      // Search
      if (q.length >= 2) {
        const label = markerDisplayName(m).toLowerCase()
        const type  = markerTypeLabel(m.type, m.subtype ?? null).toLowerCase()
        const coords = `${m.ingameX} ${m.ingameY}`
        if (!label.includes(q) && !type.includes(q) && !coords.includes(q)) return false
      }
      return true
    })
  })

  // ── Computed: types/groups for sidebar ───────────────────────────────────

  /** All distinct types in the current zone, grouped */
  const typesByGroup = computed<Record<string, string[]>>(() => {
    const result: Record<string, string[]> = {}
    const seen = new Set<string>()
    for (const m of rawMarkers.value) {
      if (seen.has(m.type)) continue
      seen.add(m.type)
      if (!result[m.group]) result[m.group] = []
      result[m.group].push(m.type)
    }
    return result
  })

  /** Count of markers per type in current zone (raw, not filtered) */
  const countsByType = computed<Record<string, number>>(() => {
    const key = activeZone.value === 'palpagos' ? 'palpagos' : 'worldtree'
    return counts.value[key] ?? {}
  })

  // ── Checked (progress) ───────────────────────────────────────────────────

  function isChecked(marker: Marker): boolean {
    return checkedMap.has(makeCheckedKey(marker))
  }

  function toggleChecked(marker: Marker): boolean {
    const key = makeCheckedKey(marker)
    if (checkedMap.has(key)) {
      checkedMap.delete(key)
      persistChecked(checkedMap)
      return false
    } else {
      checkedMap.set(key, { key, x: marker.lat, y: marker.lng })
      persistChecked(checkedMap)
      return true
    }
  }

  function checkedCountForType(type: string): number {
    let n = 0
    for (const [key] of checkedMap) {
      const isEffigy = key.startsWith('effigy:')
      const isCollectible = key.startsWith(`collectible:${type}:`)
      if (isEffigy && type === 'LifmunkEffigy') n++
      else if (isCollectible) n++
    }
    return n
  }

  const totalChecked = computed(() => checkedMap.size)

  // ── Selected marker / popup ───────────────────────────────────────────────

  function selectMarker(marker: Marker | null): void {
    selectedMarker.value = marker
  }

  // ── Camera ───────────────────────────────────────────────────────────────

  function updateCamera(state: MapCameraState): void {
    cameraState.value = state
    saveCameraState(state)
  }

  // ── Marker size → pixel size ─────────────────────────────────────────────

  /** Maps markerSize 0–100 to pixel dimensions. Enemies are larger. */
  function markerPixelSize(type: string): number {
    const base = 12 + (markerSize.value / 100) * 16 // 12–28px (was 20–48)
    const isLarge = ['FieldBoss', 'BossTower', 'FastTravels', 'WatchTower'].includes(type)
    return Math.round(isLarge ? base * 1.3 : base)
  }

  // ── Watch for zone changes to auto-load ───────────────────────────────────

  // (Manual via setZone — no auto-watcher to keep load explicit)

  return {
    // State
    activeZone,
    rawMarkers,
    counts,
    loading,
    error,
    visibleTypes,
    expandedGroups,
    markerSize,
    search,
    selectedMarker,
    cameraState,

    // Actions
    initialize,
    setZone,
    toggleType,
    showOnlyType,
    setGroupVisible,
    setAllVisible,
    resetFilters,
    toggleGroup,
    collapseAllGroups,
    expandAllGroups,
    toggleChecked,
    isChecked,
    checkedCountForType,
    selectMarker,
    updateCamera,
    markerPixelSize,

    // Computed
    filteredMarkers,
    typesByGroup,
    countsByType,
    totalChecked,

    // Helpers (re-exported for convenience in templates)
    markerDisplayName,
    markerTypeLabel,
    formatIngameCoords,
  }
})
