import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'

import { layerItems } from '@/domain/layers'
import type { CoordinateItem, MapLayer, MapMarker } from '@/types/data'
import { useChecklistStore } from './checklist'
import { usePreferencesStore } from './preferences'

const METERS_PER_MAP_COORDINATE = 4.59

export const useMapStore = defineStore('map', () => {
  const checklist = useChecklistStore()
  const preferences = usePreferencesStore()
  const search = ref('')
  const coordinates = ref('')
  const selectedMarker = ref<MapMarker | null>(null)
  const hoverText = ref('')
  const camera = reactive({ x: 0, y: 0, scale: 0.05 })

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

  const searchResults = computed<MapMarker[]>(() => {
    if (!checklist.data) return []
    const query = search.value.trim().toLocaleLowerCase()
    if (!query) return []
    const output: MapMarker[] = []
    for (const layer of checklist.layers) {
      for (const item of layerItems(checklist.data, layer)) {
        const marker = markerFor(layer, item)
        const haystack = `${marker.label} ${item.name ?? ''} ${item.type ?? ''} ${item.x} ${item.y}`
        if (!haystack.toLocaleLowerCase().includes(query)) continue
        output.push(marker)
      }
    }
    return output.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }))
  })

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
    if (saved) Object.assign(camera, { x: saved.ix, y: saved.iy, scale: saved.scaleCss })
  }

  function saveCamera(): void {
    preferences.values.mapCam = {
      ix: camera.x,
      iy: camera.y,
      scaleCss: camera.scale,
    }
  }

  function showMarker(marker: MapMarker | null): void {
    selectedMarker.value = marker
  }

  function setAllLayers(visible: boolean): void {
    for (const layer of checklist.layers) preferences.values.mapLayers[layer.id] = visible
  }

  return {
    search,
    coordinates,
    selectedMarker,
    hoverText,
    camera,
    markers,
    searchResults,
    restoreCamera,
    saveCamera,
    showMarker,
    nearestSameType,
    setAllLayers,
  }
})
