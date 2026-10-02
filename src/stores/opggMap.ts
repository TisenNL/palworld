/**
 * Store principal do novo mapa Palworld baseado no op.gg.
 * Gerencia: dados dos markers, filtros por tipo/grupo, progresso (checked),
 * busca, tamanho dos markers, câmera e marker selecionado.
 *
 * localStorage key: 'palworld:map:checked-collectibles'
 * Formato do op.gg: [{key: 'effigy:{lat}:{lng}' | 'collectible:{type}:{lat}:{lng}', x: lat, y: lng}]
 */

import { defineStore } from 'pinia'
import { computed, reactive, ref, shallowRef } from 'vue'
import { z } from 'zod'

import { isTreePoint } from '@/domain/opggCoordinates'
import {
  markersSchema,
  markerCountsSchema,
  markerDisplayName,
  markerTypeLabel,
  markerFilterKey,
  GROUPS,
  type Marker,
  type MarkerCounts,
  type MapZone,
} from '@/types/opggMarker'
import {
  spawnLocationCatalogSchema,
  spawnLocationPointsSchema,
  type SelectedSpawnLocation,
  type SpawnLocationCatalog,
  type SpawnLocationPoints,
  type SpawnMapPoint,
} from '@/types/spawnLocation'
import { formatIngameCoords } from '@/domain/opggCoordinates'

// ── localStorage keys (same as op.gg) ────────────────────────────────────────

const CHECKED_KEY = 'palworld:map:checked-collectibles'
const DISTINCT_CHECKED_KEY = 'palworld:map:checked-collectibles:distinct'
const CAMERA_KEY = 'palworld:map:camera'

// ── Checked item format (op.gg localStorage format) ──────────────────────────

interface CheckedItem {
  key: string // 'effigy:{lat}:{lng}' or 'collectible:{type}:{lat}:{lng}'
  x: number // lat (Leaflet)
  y: number // lng (Leaflet)
}

function makeCheckedKey(marker: Marker): string {
  if (marker.type === 'LifmunkEffigy') {
    return `effigy:${marker.lat}:${marker.lng}`
  }
  return `collectible:${marker.type}:${marker.lat}:${marker.lng}`
}

let checkedKeyIndexSource: Marker[] | null = null
let checkedKeyByMarkerId = new Map<string, string>()
let collisionMarkerIds = new Set<string>()

function checkedKeyFor(marker: Marker, markers: Marker[]): string {
  if (checkedKeyIndexSource !== markers) {
    const seen = new Set<string>()
    checkedKeyByMarkerId = new Map()
    collisionMarkerIds = new Set()
    for (const item of markers) {
      const baseKey = makeCheckedKey(item)
      if (seen.has(baseKey)) {
        checkedKeyByMarkerId.set(item.id, `${baseKey}#${encodeURIComponent(item.id)}`)
        collisionMarkerIds.add(item.id)
      } else {
        seen.add(baseKey)
        checkedKeyByMarkerId.set(item.id, baseKey)
      }
    }
    checkedKeyIndexSource = markers
  }
  return checkedKeyByMarkerId.get(marker.id) ?? makeCheckedKey(marker)
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
    return z
      .object({
        lat: z.number(),
        lng: z.number(),
        zoom: z.number(),
        zone: z.enum(['palpagos', 'world-tree']),
      })
      .parse(JSON.parse(raw))
  } catch {
    return null
  }
}

function saveCameraState(state: MapCameraState): void {
  try {
    localStorage.setItem(CAMERA_KEY, JSON.stringify(state))
  } catch {
    // storage cheio/bloqueado — a câmera é dispensável
  }
}

// ── Checked persistence ───────────────────────────────────────────────────────

/** Normaliza um item do formato on-disk do op.gg para o tipo do app. */
function toCheckedItem(value: unknown): CheckedItem | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  if (typeof record.key !== 'string') return null
  return {
    key: record.key,
    x: typeof record.x === 'number' ? record.x : 0,
    y: typeof record.y === 'number' ? record.y : 0,
  }
}

function loadChecked(storageKey: string): Map<string, CheckedItem> {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return new Map()
    const items: unknown = JSON.parse(raw)
    if (!Array.isArray(items)) return new Map()
    const map = new Map<string, CheckedItem>()
    for (const item of items as unknown[]) {
      const checkedItem = toCheckedItem(item)
      if (checkedItem) map.set(checkedItem.key, checkedItem)
    }
    return map
  } catch {
    return new Map()
  }
}

function persistChecked(storageKey: string, checkedMap: Map<string, CheckedItem>): void {
  try {
    localStorage.setItem(storageKey, JSON.stringify([...checkedMap.values()]))
  } catch {
    // storage cheio/bloqueado — o progresso fica só em memória nesta sessão
  }
}

// ── Store ─────────────────────────────────────────────────────────────────────

export const useOpggMapStore = defineStore('opggMap', () => {
  // ── State ─────────────────────────────────────────────────────────────────

  /** Active map zone */
  const activeZone = ref<MapZone>('palpagos')

  /** Raw markers for the active zone (loaded from JSON) */
  const rawMarkers = shallowRef<Marker[]>([])

  /** Keep only the active zone's full marker objects; retain compact filter metadata for both. */
  let markerDataZone: MapZone | null = null
  const filterKeysByZone = new Map<MapZone, Set<string>>()
  const filterKeysByGroupByZone = new Map<MapZone, Map<string, Set<string>>>()
  const zoneErrors = ref<Partial<Record<MapZone, string>>>({})
  const zoneLoads = new Map<MapZone, Promise<void>>()

  /** Marker counts by type, both zones */
  const counts = ref<MarkerCounts>({ palpagos: {}, worldtree: {} })

  /** Loading/error state */
  const loading = ref(false)
  const error = ref('')

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

  /**
   * Ids dos markers selecionados para a fila de "mark in game" (Ctrl/Cmd + Click).
   * O Set preserva a ordem de clique = ordem de execução da fila.
   * Vive em paralelo a selectedMarker (popup/HUD) para não afetar os fluxos existentes.
   */
  const selectedMarkerIds = reactive(new Set<string>())

  /** Camera state, persisted in localStorage */
  const cameraState = ref<MapCameraState | null>(loadCameraState())

  /** Checked items map: key → CheckedItem */
  const checkedMap = reactive(loadChecked(CHECKED_KEY))
  const distinctCheckedMap = reactive(loadChecked(DISTINCT_CHECKED_KEY))

  /** OP.GG Pal/human spawn locations, selected independently of marker filters. */
  const spawnCatalog = shallowRef<SpawnLocationCatalog | null>(null)
  const spawnCatalogLoading = ref(false)
  const spawnCatalogError = ref('')
  const selectedSpawnLocation = ref<SelectedSpawnLocation | null>(null)
  const spawnLocationCache = reactive(new Map<string, SpawnLocationPoints>())
  const spawnLocationLoading = ref(false)
  const spawnLocationError = ref('')
  let spawnCatalogLoad: Promise<void> | null = null
  let spawnLocationLoadId = 0

  // ── Load data ────────────────────────────────────────────────────────────

  async function loadZone(zone: MapZone): Promise<void> {
    if (markerDataZone === zone) return
    const existingLoad = zoneLoads.get(zone)
    if (existingLoad) return existingLoad

    const fileName =
      zone === 'palpagos' ? '/opgg-markers-palpagos.json' : '/opgg-markers-worldtree.json'
    const load = (async () => {
      try {
        const resp = await fetch(fileName)
        if (!resp.ok) throw new Error(`Failed to load ${fileName}: HTTP ${resp.status}`)
        const json: unknown = await resp.json()
        const markers = import.meta.env.DEV ? markersSchema.parse(json) : (json as Marker[])
        const filterKeys = new Set<string>()
        const filterKeysByGroup = new Map<string, Set<string>>()
        for (const marker of markers) {
          const key = markerFilterKey(marker)
          filterKeys.add(key)
          let groupKeys = filterKeysByGroup.get(marker.group)
          if (!groupKeys) {
            groupKeys = new Set<string>()
            filterKeysByGroup.set(marker.group, groupKeys)
          }
          groupKeys.add(key)
        }
        filterKeysByZone.set(zone, filterKeys)
        filterKeysByGroupByZone.set(zone, filterKeysByGroup)
        const nextErrors = { ...zoneErrors.value }
        delete nextErrors[zone]
        zoneErrors.value = nextErrors
        if (activeZone.value === zone) {
          rawMarkers.value = markers
          markerDataZone = zone
        }
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : 'Failed to load markers'
        zoneErrors.value = { ...zoneErrors.value, [zone]: message }
        if (activeZone.value === zone) {
          error.value = message
          rawMarkers.value = []
        }
      }
    })()
    zoneLoads.set(zone, load)
    await load
    zoneLoads.delete(zone)
  }

  async function loadCounts(): Promise<void> {
    try {
      const resp = await fetch('/opgg-marker-counts.json')
      if (!resp.ok) return
      counts.value = markerCountsSchema.parse(await resp.json())
    } catch {
      // contagens são um acessório — o mapa funciona sem elas
    }
  }

  async function loadSpawnCatalog(): Promise<void> {
    if (spawnCatalog.value) return
    if (spawnCatalogLoad) return spawnCatalogLoad

    spawnCatalogLoading.value = true
    spawnCatalogError.value = ''
    spawnCatalogLoad = (async () => {
      try {
        const response = await fetch('/opgg-spawn-locations/catalog.json')
        if (!response.ok) {
          throw new Error(`Failed to load Pal and human locations: HTTP ${response.status}`)
        }
        spawnCatalog.value = spawnLocationCatalogSchema.parse(await response.json())
      } catch (cause) {
        spawnCatalogError.value =
          cause instanceof Error ? cause.message : 'Failed to load Pal and human locations'
      } finally {
        spawnCatalogLoading.value = false
        spawnCatalogLoad = null
      }
    })()
    return spawnCatalogLoad
  }

  async function toggleSpawnLocation(kind: SelectedSpawnLocation['kind'], id: string): Promise<void> {
    const selected = selectedSpawnLocation.value
    if (selected?.kind === kind && selected.id === id) {
      selectedSpawnLocation.value = null
      spawnLocationLoadId++
      spawnLocationLoading.value = false
      spawnLocationError.value = ''
      return
    }

    selectedSpawnLocation.value = { kind, id }
    spawnLocationError.value = ''
    const key = `${kind}:${id}`
    if (spawnLocationCache.has(key)) {
      spawnLocationLoading.value = false
      spawnLocationLoadId++
      return
    }

    const loadId = ++spawnLocationLoadId
    spawnLocationLoading.value = true
    try {
      const response = await fetch(
        `/opgg-spawn-locations/${kind}/${encodeURIComponent(id)}.json`,
      )
      if (!response.ok) {
        throw new Error(`Failed to load ${kind} location ${id}: HTTP ${response.status}`)
      }
      spawnLocationCache.set(key, spawnLocationPointsSchema.parse(await response.json()))
    } catch (cause) {
      if (spawnLocationLoadId === loadId) {
        spawnLocationError.value =
          cause instanceof Error ? cause.message : `Failed to load ${kind} location ${id}`
      }
    } finally {
      if (spawnLocationLoadId === loadId) spawnLocationLoading.value = false
    }
  }

  const spawnPoints = computed<SpawnMapPoint[]>(() => {
    const selection = selectedSpawnLocation.value
    if (!selection) return []
    const data = spawnLocationCache.get(`${selection.kind}:${selection.id}`)
    if (!data) return []

    const points = new Map<string, SpawnMapPoint>()
    const isWorldTree = activeZone.value === 'world-tree'
    for (const [period, values] of [
      ['day', data.day],
      ['night', data.night],
    ] as const) {
      for (const [gameX, gameY] of values) {
        if (isTreePoint(gameX, gameY) !== isWorldTree) continue
        const key = `${gameX},${gameY}`
        const point = points.get(key) ?? { gameX, gameY, day: false, night: false }
        point[period] = true
        points.set(key, point)
      }
    }
    return [...points.values()]
  })

  /** Initialize both zones so All/Hide and group actions stay synchronized. */
  async function initialize(): Promise<void> {
    loading.value = true
    error.value = ''
    await Promise.all([
      loadCounts(),
      loadZone('palpagos'),
      loadZone('world-tree'),
      loadSpawnCatalog(),
    ])
    if (markerDataZone !== activeZone.value) rawMarkers.value = []
    error.value = zoneErrors.value[activeZone.value] ?? ''
    loading.value = false
  }

  /** Switch active map zone */
  async function setZone(zone: MapZone): Promise<void> {
    if (zone === activeZone.value && markerDataZone === zone) return
    activeZone.value = zone
    selectedMarker.value = null
    selectedMarkerIds.clear()
    rawMarkers.value = []
    markerDataZone = null
    checkedKeyIndexSource = null
    checkedKeyByMarkerId.clear()
    collisionMarkerIds.clear()
    loading.value = true
    error.value = zoneErrors.value[zone] ?? ''
    await loadZone(zone)
    if (activeZone.value !== zone) return
    error.value = zoneErrors.value[zone] ?? ''
    loading.value = false
  }

  // ── Visibility filters ───────────────────────────────────────────────────

  /** `visibleTypes` guarda os tipos **ocultos** (vazio = tudo visível). */
  function isTypeVisible(type: string): boolean {
    return !visibleTypes.has(type)
  }

  /** Alterna a visibilidade de um tipo (o set guarda os **ocultos**). */
  function toggleType(type: string): void {
    if (visibleTypes.has(type)) visibleTypes.delete(type)
    else visibleTypes.add(type)
  }

  /** Show only one specific type */
  function showOnlyType(type: string): void {
    visibleTypes.clear()
    for (const t of allFilterKeys()) {
      if (t !== type) visibleTypes.add(t)
    }
  }

  function allFilterKeys(): Set<string> {
    const keys = new Set<string>()
    for (const zoneKeys of filterKeysByZone.values()) {
      for (const key of zoneKeys) keys.add(key)
    }
    return keys
  }

  /** Toggle all types in a group visible/hidden */
  function setGroupVisible(group: string, visible: boolean): void {
    const typesInGroup = new Set<string>()
    for (const zoneGroups of filterKeysByGroupByZone.values()) {
      for (const key of zoneGroups.get(group) ?? []) typesInGroup.add(key)
    }
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
      for (const key of allFilterKeys()) visibleTypes.add(key)
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
    return rawMarkers.value.filter((m) => {
      // Type visibility
      if (visibleTypes.size > 0 && visibleTypes.has(markerFilterKey(m))) return false
      // Search
      if (q.length >= 2) {
        const label = markerDisplayName(m).toLowerCase()
        const type = markerTypeLabel(m.type, m.subtype ?? null).toLowerCase()
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
      const key = markerFilterKey(m)
      if (seen.has(key)) continue
      seen.add(key)
      const bucket = (result[m.group] ||= [])
      bucket.push(key)
    }
    return result
  })

  /** Count of markers per type in current zone (raw, not filtered) */
  const countsByType = computed<Record<string, number>>(() => {
    const result: Record<string, number> = {}
    for (const marker of rawMarkers.value) {
      const key = markerFilterKey(marker)
      result[key] = (result[key] ?? 0) + 1
    }
    return result
  })

  const groupProgress = computed<Record<string, { checked: number; total: number }>>(() => {
    const result: Record<string, { checked: number; total: number }> = {}
    for (const marker of rawMarkers.value) {
      const progress = result[marker.group] ?? { checked: 0, total: 0 }
      progress.total++
      if (isChecked(marker)) progress.checked++
      result[marker.group] = progress
    }
    return result
  })

  // ── Checked (progress) ───────────────────────────────────────────────────

  function isChecked(marker: Marker): boolean {
    const key = checkedKeyFor(marker, rawMarkers.value)
    const map = collisionMarkerIds.has(marker.id) ? distinctCheckedMap : checkedMap
    return map.has(key)
  }

  function toggleChecked(marker: Marker): boolean {
    const key = checkedKeyFor(marker, rawMarkers.value)
    const isCollision = collisionMarkerIds.has(marker.id)
    const map = isCollision ? distinctCheckedMap : checkedMap
    const storageKey = isCollision ? DISTINCT_CHECKED_KEY : CHECKED_KEY
    if (map.has(key)) {
      map.delete(key)
      persistChecked(storageKey, map)
      return false
    } else {
      map.set(key, { key, x: marker.lat, y: marker.lng })
      persistChecked(storageKey, map)
      return true
    }
  }

  function checkedCountForType(type: string): number {
    let n = 0
    for (const map of [checkedMap, distinctCheckedMap]) {
      for (const [key] of map) {
        const isEffigy = key.startsWith('effigy:')
        const isCollectible = key.startsWith(`collectible:${type}:`)
        if (isEffigy && type === 'LifmunkEffigy') n++
        else if (isCollectible) n++
      }
    }
    return n
  }

  const totalChecked = computed(() => checkedMap.size + distinctCheckedMap.size)

  // ── Selected marker / popup ───────────────────────────────────────────────

  function selectMarker(marker: Marker | null): void {
    selectedMarker.value = marker
  }

  // ── Seleção múltipla (fila de mark in game) ───────────────────────────────

  /** Ctrl/Cmd + Click: adiciona/remove o marker da seleção do lote */
  function toggleBatchSelection(marker: Marker): boolean {
    if (selectedMarkerIds.has(marker.id)) {
      selectedMarkerIds.delete(marker.id)
      return false
    }
    selectedMarkerIds.add(marker.id)
    return true
  }

  function clearBatchSelection(): void {
    selectedMarkerIds.clear()
  }

  /** Resolve os ids selecionados contra os markers carregados, na ordem de clique */
  const selectionMarkers = computed<Marker[]>(() => {
    if (selectedMarkerIds.size === 0) return []
    const byId = new Map<string, Marker>()
    for (const m of rawMarkers.value) byId.set(m.id, m)
    const out: Marker[] = []
    for (const id of selectedMarkerIds) {
      const mk = byId.get(id)
      if (mk) out.push(mk)
    }
    return out
  })

  const selectionCount = computed(() => selectedMarkerIds.size)

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
    selectedMarkerIds,
    cameraState,
    spawnCatalog,
    spawnCatalogLoading,
    spawnCatalogError,
    selectedSpawnLocation,
    spawnLocationLoading,
    spawnLocationError,

    // Actions
    initialize,
    setZone,
    loadSpawnCatalog,
    toggleSpawnLocation,
    toggleType,
    isTypeVisible,
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
    toggleBatchSelection,
    clearBatchSelection,
    updateCamera,
    markerPixelSize,

    // Computed
    filteredMarkers,
    selectionMarkers,
    selectionCount,
    typesByGroup,
    countsByType,
    groupProgress,
    totalChecked,
    spawnPoints,

    // Helpers (re-exported for convenience in templates)
    markerDisplayName,
    markerTypeLabel,
    formatIngameCoords,
  }
})
