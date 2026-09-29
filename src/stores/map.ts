import { defineStore } from 'pinia'
import { computed, reactive, ref, shallowRef } from 'vue'

import { buildWtLayers, layerItems } from '@/domain/layers'
import { api } from '@/services/api'
import type { CoordinateItem, MapLayer, MapMarker, WtData } from '@/types/data'
import { useChecklistStore } from './checklist'
import { usePreferencesStore } from './preferences'

const METERS_PER_MAP_COORDINATE = 4.59
const SEARCH_MIN_LENGTH = 3

export const useMapStore = defineStore('map', () => {
  const checklist = useChecklistStore()
  const preferences = usePreferencesStore()
  const search = ref('')
  const coordinates = ref('')
  const selectedMarker = ref<MapMarker | null>(null)
  const hoverText = ref('')
  const camera = reactive({ x: 0, y: 0, scale: 0.05 })
  const wtData = shallowRef<WtData | null>(null)

  // Multi-selection: reactive Set so .has() / .size triggers computed updates
  const selectedIds = reactive(new Set<string>())

  const palIcons = computed(() => {
    const values = checklist.breedData?.pals ?? []
    return new Map(values.map((pal) => [pal.name.toLocaleLowerCase(), pal.icon]))
  })

  function markerFor(layer: MapLayer, item: CoordinateItem): MapMarker {
    const done = checklist.isDone(layer.storage, item.id)
    const baseLabel =
      layer.storage === 'effigies'
        ? `${item.type ?? ''} Effigy #${item.n ?? ''}`
        : `${item.n ? `${item.n}. ` : ''}${item.name ?? item.type ?? layer.label}`
    const sealedLabel =
      item.tag === 'Sealed Realm'
        ? `${baseLabel} · Sealed Realm${item.type ? ` (${item.type})` : ''}`
        : baseLabel
    const label = item.volume ? `${sealedLabel} · ${item.volume} nodes` : sealedLabel
    const alphaIcon =
      layer.storage === 'alphas'
        ? item.icon || palIcons.value.get((item.name ?? '').toLocaleLowerCase())
        : undefined
    return {
      id: `${layer.id}:${item.id}`,
      layerId: layer.id,
      storage: layer.storage,
      item,
      label,
      color: layer.color,
      done,
      ...(alphaIcon || layer.iconUrl ? { iconUrl: alphaIcon || layer.iconUrl } : {}),
    }
  }

  const markers = computed<MapMarker[]>(() => {
    if (!checklist.data) return []
    const output: MapMarker[] = []
    for (const layer of checklist.layers) {
      if (!preferences.values.mapLayers[layer.id]) continue
      for (const item of layerItems(checklist.data, layer)) {
        output.push(markerFor(layer, item))
      }
    }
    const priority = (marker: MapMarker): number => {
      if (marker.storage === 'alphas') return 3
      if (marker.storage === 'bounties' || marker.storage === 'towers') return 2
      if (marker.done) return 0
      return 1
    }
    return output.sort((a, b) => {
      const byPriority = priority(a) - priority(b)
      if (byPriority !== 0) return byPriority
      return Number(a.done) - Number(b.done)
    })
  })

  /**
   * Search index built once when data loads. Haystack is pre-lowercased so
   * each search query does not re-allocate strings. Does NOT call markerFor or
   * read reactive checked state, so it only invalidates when raw data changes,
   * not on every checkbox toggle.
   */
  const searchIndex = computed<Array<{ layer: MapLayer; item: CoordinateItem; haystack: string }>>(
    () => {
      if (!checklist.data) return []
      const index: Array<{ layer: MapLayer; item: CoordinateItem; haystack: string }> = []
      const seen = new Set<string>()
      for (const layer of checklist.layers) {
        for (const item of layerItems(checklist.data, layer)) {
          const key = `${layer.id}:${item.id}`
          if (seen.has(key)) continue
          seen.add(key)
          const baseLabel =
            layer.storage === 'effigies'
              ? `${item.type ?? ''} effigy ${item.n ?? ''}`
              : `${item.n ? `${item.n} ` : ''}${item.name ?? item.type ?? layer.label}`
          const haystack =
            `${baseLabel} ${item.name ?? ''} ${item.type ?? ''} ${item.x} ${item.y} ${layer.label}`.toLocaleLowerCase()
          index.push({ layer, item, haystack })
        }
      }
      return index
    },
  )

  const searchResults = computed<MapMarker[]>(() => {
    const query = search.value.trim().toLocaleLowerCase()
    if (query.length < SEARCH_MIN_LENGTH || !checklist.data) return []
    const output: MapMarker[] = []
    for (const entry of searchIndex.value) {
      if (!entry.haystack.includes(query)) continue
      // Only call markerFor (reads reactive checked state) for matched items.
      output.push(markerFor(entry.layer, entry.item))
    }
    return output.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }))
  })

  /** Markers currently selected (left-click toggled). Preserves markers order. */
  const selectedMarkers = computed<MapMarker[]>(() =>
    markers.value.filter((marker) => selectedIds.has(marker.id)),
  )

  function nearestSameType(
    source: MapMarker,
  ): { marker: MapMarker; distanceMeters: number } | null {
    if (!checklist.data) return null
    const layer = checklist.layers.find((candidate) => candidate.id === source.layerId)
    if (!layer) return null
    let nearest: CoordinateItem | null = null
    let nearestDistance = Number.POSITIVE_INFINITY
    for (const item of layerItems(checklist.data, layer)) {
      if (item.id === source.item.id) continue
      if (checklist.isDone(layer.storage, item.id)) continue
      const distance = Math.hypot(item.x - source.item.x, item.y - source.item.y)
      if (distance < nearestDistance) {
        nearest = item
        nearestDistance = distance
      }
    }
    if (!nearest) return null
    return {
      marker: markerFor(layer, nearest),
      distanceMeters: Math.round(nearestDistance * METERS_PER_MAP_COORDINATE),
    }
  }

  function restoreCamera(): void {
    const saved = preferences.values.mapCam
    if (!saved) return
    // Sanity-check: camera x/y are screen-space offsets. If the stored values
    // would place the map entirely off-screen at the saved scale, discard them
    // and let fitMarkers() centre the view instead.
    const { ix: x, iy: y, scaleCss: scale } = saved
    if (
      !Number.isFinite(x) ||
      !Number.isFinite(y) ||
      !Number.isFinite(scale) ||
      scale <= 0 ||
      // The map image is ~16M px wide; at minimum scale 0.004 that's ~65k screen px.
      // Any offset beyond ±200k is clearly stale/corrupt.
      Math.abs(x) > 200_000 ||
      Math.abs(y) > 200_000
    ) {
      preferences.values.mapCam = null
      return
    }
    Object.assign(camera, { x, y, scale })
  }

  function saveCamera(): void {
    if (preferences.values.activeMap === 'world-tree') {
      saveWtCamera()
      return
    }
    preferences.values.mapCam = {
      ix: camera.x,
      iy: camera.y,
      scaleCss: camera.scale,
    }
  }

  function showMarker(marker: MapMarker | null): void {
    selectedMarker.value = marker
  }

  /** Toggle map-icon selection. Returns true if now selected, false if deselected. */
  function toggleSelected(id: string): boolean {
    if (selectedIds.has(id)) {
      selectedIds.delete(id)
      return false
    }
    selectedIds.add(id)
    return true
  }

  function isSelected(id: string): boolean {
    return selectedIds.has(id)
  }

  function clearSelected(): void {
    selectedIds.clear()
  }

  function setAllLayers(visible: boolean): void {
    for (const layer of checklist.layers) preferences.values.mapLayers[layer.id] = visible
  }

  // ── World Tree ──────────────────────────────────────────────────────────────

  const activeMap = computed(() => preferences.values.activeMap)

  async function loadWtData(): Promise<void> {
    if (wtData.value) return
    try {
      const data = await api.getWtData()
      wtData.value = data
      // Initialize visibility defaults for WT layers (default: all visible)
      const wtLayerList = buildWtLayers(data)
      for (const layer of wtLayerList) {
        if (typeof preferences.values.mapLayers[layer.id] !== 'boolean') {
          preferences.values.mapLayers[layer.id] = true
        }
      }
    } catch {
      // non-fatal — WT map simply shows no markers if unavailable
    }
  }

  /** Computed WT layers built from wtData (mirrors checklist.layers for Palpagos). */
  const wtLayers = computed<MapLayer[]>(() => {
    const data = wtData.value
    if (!data) return []
    return buildWtLayers(data)
  })

  /** Flat list of all WT markers, filtered by per-layer visibility preferences. */
  const wtMarkers = computed<MapMarker[]>(() => {
    const data = wtData.value
    if (!data) return []
    const out: MapMarker[] = []
    for (const layer of wtLayers.value) {
      // Respect visibility toggle (default: show all layers until user hides one)
      if (preferences.values.mapLayers[layer.id] === false) continue
      for (const item of layerItems(data, layer)) {
        const isAlpha = layer.storage === 'alphas'
        const label = isAlpha
          ? `${item.name ?? item.type ?? 'Alpha'} Lv.${item.lv ?? '?'}`
          : (item.name ?? item.type ?? layer.label)
        const done = checklist.isDone(layer.storage, item.id)
        out.push({
          id: `wt:${layer.id}:${item.id}`,
          layerId: layer.id,
          storage: layer.storage,
          item,
          label,
          color: layer.color,
          done,
          ...(item.icon ? { iconUrl: item.icon } : {}),
        })
      }
    }
    return out
  })

  function saveWtCamera(): void {
    preferences.values.wtMapCam = { ix: camera.x, iy: camera.y, scaleCss: camera.scale }
  }

  function restoreWtCamera(): void {
    const saved = preferences.values.wtMapCam
    if (!saved) return
    const { ix: x, iy: y, scaleCss: scale } = saved
    if (
      !Number.isFinite(x) ||
      !Number.isFinite(y) ||
      !Number.isFinite(scale) ||
      scale <= 0 ||
      Math.abs(x) > 200_000 ||
      Math.abs(y) > 200_000
    ) {
      preferences.values.wtMapCam = null
      return
    }
    Object.assign(camera, { x, y, scale })
  }

  function setActiveMap(map: 'palpagos' | 'world-tree'): void {
    if (preferences.values.activeMap === map) return
    // Save current camera before switching
    if (preferences.values.activeMap === 'world-tree') {
      saveWtCamera()
    } else {
      saveCamera()
    }
    // Reset camera to default so fitMarkers() fires on mount
    Object.assign(camera, { x: 0, y: 0, scale: 0.05 })
    preferences.values.activeMap = map
    // Restore saved camera for the new map
    if (map === 'world-tree') {
      restoreWtCamera()
      void loadWtData()
    } else {
      restoreCamera()
    }
    // Clear selection when switching maps
    selectedIds.clear()
  }

  return {
    search,
    coordinates,
    selectedMarker,
    selectedIds,
    selectedMarkers,
    hoverText,
    camera,
    markers,
    wtMarkers,
    wtLayers,
    activeMap,
    searchResults,
    restoreCamera,
    saveCamera,
    showMarker,
    toggleSelected,
    isSelected,
    clearSelected,
    nearestSameType,
    setAllLayers,
    setActiveMap,
    loadWtData,
  }
})
