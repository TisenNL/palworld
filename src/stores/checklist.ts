import { defineStore } from 'pinia'
import { computed, reactive, ref, shallowRef, toRaw } from 'vue'

import { buildLayers, layerItems } from '@/domain/layers'
import { api } from '@/services/api'
import type {
  BreedData,
  GameData,
  ListEntry,
  MapIconsData,
  MapLayer,
  StorageKey,
} from '@/types/data'
import {
  checkCategories,
  emptyChecks,
  progressSchema,
  type CheckedItems,
  type Checks,
  type ProgressPayload,
} from '@/types/progress'
import { usePreferencesStore } from './preferences'
import { useCakeStore } from './cake'

const storageKeys: Record<StorageKey, string> = {
  alphas: 'palworld-alpha-pals-checklist-v1',
  bounties: 'palworld-bounties-checklist-v1',
  effigies: 'palworld-effigies-checklist-v1',
  dungeons: 'palworld-dungeons-checklist-v1',
  towers: 'palworld-towers-checklist-v1',
  journals: 'palworld-journals-checklist-v1',
  oilrigs: 'palworld-oilrigs-checklist-v1',
  camps: 'palworld-camps-checklist-v1',
  collectibles: 'palworld-collectibles-checklist-v1',
  travel: 'palworld-travel-checklist-v1',
}
const PROGRESS_STORAGE_KEY = 'palworld-progress-v2'
const BREED_OWNED_STORAGE_KEY = 'palworld-breed-owned-v1'

function readChecked(key: string): CheckedItems {
  try {
    const raw = JSON.parse(localStorage.getItem(key) ?? '{}') as Record<string, unknown>
    return Object.fromEntries(Object.keys(raw).filter((id) => raw[id] === true)) as CheckedItems
  } catch {
    return {}
  }
}

function mergeChecked(a: CheckedItems, b: CheckedItems): CheckedItems {
  return { ...a, ...b }
}

function readLocalProgress(): ProgressPayload | null {
  try {
    return progressSchema.parse(JSON.parse(localStorage.getItem(PROGRESS_STORAGE_KEY) ?? 'null'))
  } catch {
    return null
  }
}

export const useChecklistStore = defineStore('checklist', () => {
  const data = shallowRef<GameData | null>(null)
  const breedData = shallowRef<BreedData | null>(null)
  const mapIcons = shallowRef<MapIconsData | null>(null)
  const checked = reactive<Checks>(emptyChecks())
  const breedOwned = reactive<CheckedItems>({})
  const loading = ref(false)
  const error = ref('')
  const initialized = ref(false)
  let revision = 0
  let saveTimer: number | undefined

  const layers = computed<MapLayer[]>(() => {
    if (!data.value) return []
    return buildLayers(data.value).map((layer) => {
      const source = mapIcons.value?.icons[layer.iconKey ?? layer.label]
      return source ? { ...layer, iconUrl: source } : layer
    })
  })

  const entries = computed<ListEntry[]>(() => {
    if (!data.value) return []
    return layers.value.flatMap((layer) =>
      layerItems(data.value!, layer).map((item) => ({
        ...item,
        uid: `${layer.storage}:${item.id}`,
        storage: layer.storage,
        layerId: layer.id,
        layerLabel: layer.label,
        color: layer.color,
      })),
    )
  })

  function isDone(storage: StorageKey, id: string): boolean {
    return checked[storage][id] === true
  }

  function setDone(storage: StorageKey, id: string, done: boolean): void {
    if (done) checked[storage][id] = true
    else delete checked[storage][id]
    localStorage.setItem(storageKeys[storage], JSON.stringify(checked[storage]))
    scheduleSave()
  }

  function toggleDone(storage: StorageKey, id: string): boolean {
    const next = !isDone(storage, id)
    setDone(storage, id, next)
    return next
  }

  function setBreedOwned(code: string, owned: boolean): void {
    if (owned) breedOwned[code] = true
    else delete breedOwned[code]
    localStorage.setItem(BREED_OWNED_STORAGE_KEY, JSON.stringify(breedOwned))
    scheduleSave()
  }

  function payload(): ProgressPayload {
    const preferences = usePreferencesStore()
    const cake = useCakeStore()
    const result: ProgressPayload = {
      version: 2,
      revision: ++revision,
      updatedAt: new Date().toISOString(),
      checks: structuredClone(toRaw(checked)),
      breedOwned: structuredClone(toRaw(breedOwned)),
      prefs: structuredClone(toRaw(preferences.values)),
      cake: cake.snapshot(),
    }
    localStorage.setItem(PROGRESS_STORAGE_KEY, JSON.stringify(result))
    return result
  }

  function scheduleSave(): void {
    const next = payload()
    window.clearTimeout(saveTimer)
    saveTimer = window.setTimeout(() => {
      void api.saveProgress(next).catch(() => undefined)
    }, 350)
  }

  function exportProgress(): ProgressPayload {
    return payload()
  }

  function replaceProgress(next: ProgressPayload): void {
    revision = Math.max(revision, next.revision)
    for (const key of checkCategories) {
      Object.keys(checked[key]).forEach((id) => delete checked[key][id])
      Object.assign(checked[key], next.checks[key])
      localStorage.setItem(storageKeys[key], JSON.stringify(checked[key]))
    }
    Object.keys(breedOwned).forEach((code) => delete breedOwned[code])
    Object.assign(breedOwned, next.breedOwned)
    localStorage.setItem(BREED_OWNED_STORAGE_KEY, JSON.stringify(breedOwned))
    usePreferencesStore().apply(next.prefs)
    if (next.cake) useCakeStore().hydrate(next.cake)
    scheduleSave()
  }

  async function initialize(): Promise<void> {
    if (initialized.value || loading.value) return
    loading.value = true
    error.value = ''
    let recoveredBreedSelection = false
    try {
      const hasLocalPreferences = localStorage.getItem('palworld-prefs-v1') !== null
      for (const key of checkCategories) Object.assign(checked[key], readChecked(storageKeys[key]))
      const locallyOwned = readChecked(BREED_OWNED_STORAGE_KEY)
      Object.assign(breedOwned, locallyOwned)

      const [game, breeds, icons, remote] = await Promise.all([
        api.getData(),
        api.getBreedData(),
        api.getMapIcons(),
        api.getProgress().catch(() => null),
      ])
      data.value = game
      breedData.value = breeds
      mapIcons.value = icons
      const local = readLocalProgress()
      const current = local && (!remote || local.revision >= remote.revision) ? local : remote
      if (current) {
        revision = current.revision
        for (const key of checkCategories) {
          const next =
            current.version >= 2
              ? current.checks[key]
              : mergeChecked(checked[key], current.checks[key])
          Object.keys(checked[key]).forEach((id) => delete checked[key][id])
          Object.assign(checked[key], next)
          localStorage.setItem(storageKeys[key], JSON.stringify(checked[key]))
        }
        Object.keys(breedOwned).forEach((code) => delete breedOwned[code])
        recoveredBreedSelection = Object.keys(locallyOwned).some(
          (code) => current.breedOwned[code] !== true,
        )
        Object.assign(breedOwned, mergeChecked(current.breedOwned, locallyOwned))
        if (!hasLocalPreferences || current === local) {
          usePreferencesStore().apply(current.prefs)
        }
        if (current.cake) {
          useCakeStore().hydrate(current.cake)
        }
      }
      localStorage.setItem(BREED_OWNED_STORAGE_KEY, JSON.stringify(breedOwned))
      const preferences = usePreferencesStore()
      for (const layer of layers.value) {
        if (typeof preferences.values.mapLayers[layer.id] !== 'boolean') {
          preferences.values.mapLayers[layer.id] = true
        }
      }
      initialized.value = true
      const needsCakeMirror =
        !current?.cake && Boolean(localStorage.getItem('palworld-cake-state-v1'))
      if (recoveredBreedSelection || needsCakeMirror) scheduleSave()
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Failed to load application data'
      throw cause
    } finally {
      loading.value = false
    }
  }

  function flush(): void {
    if (!initialized.value) return
    window.clearTimeout(saveTimer)
    const body = JSON.stringify(payload())
    navigator.sendBeacon('/progress', new Blob([body], { type: 'application/json' }))
  }

  return {
    data,
    breedData,
    mapIcons,
    checked,
    breedOwned,
    loading,
    error,
    initialized,
    layers,
    entries,
    initialize,
    isDone,
    setDone,
    toggleDone,
    setBreedOwned,
    scheduleSave,
    exportProgress,
    replaceProgress,
    flush,
  }
})
