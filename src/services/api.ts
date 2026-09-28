import type { ZodType } from 'zod'

import {
  breedDataSchema,
  gameDataSchema,
  mapIconsSchema,
  wtDataSchema,
  type BreedData,
  type GameData,
  type MapIconsData,
  type WtData,
} from '@/types/data'
import { progressSchema, type ProgressPayload } from '@/types/progress'
import {
  gameMarkerStateSchema,
  healthSchema,
  mouseLoopStateSchema,
  ocrStateSchema,
  type GameMarkerState,
  type HealthState,
  type MouseLoopState,
  type OcrState,
} from '@/types/server'

const configuredBase = String(import.meta.env.VITE_HELPER_URL ?? '').replace(/\/$/, '')
export const apiBase = configuredBase || ''

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request(
  path: string,
  init: RequestInit = {},
  timeoutMs = 10_000,
): Promise<Response> {
  const timeout = AbortSignal.timeout(timeoutMs)
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout
  const response = await fetch(`${apiBase}${path}`, { ...init, signal })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new ApiError(
      detail || `HTTP request failed with status ${response.status}`,
      response.status,
    )
  }
  return response
}

async function json<T>(path: string, schema: ZodType<T>, init?: RequestInit): Promise<T> {
  const response = await request(path, init)
  return schema.parse(await response.json())
}

export const api = {
  getData: (): Promise<GameData> => json('/data.json', gameDataSchema, { cache: 'no-store' }),
  getWtData: (): Promise<WtData> => json('/wt-data.json', wtDataSchema, { cache: 'no-store' }),
  getBreedData: (): Promise<BreedData> => json('/breed.json', breedDataSchema),
  getMapIcons: (): Promise<MapIconsData> => json('/map_icons.json', mapIconsSchema),
  getProgress: (): Promise<ProgressPayload> =>
    json('/progress', progressSchema, { cache: 'no-store' }),
  saveProgress: async (payload: ProgressPayload): Promise<void> => {
    await request('/progress', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  health: (): Promise<HealthState> => json('/health', healthSchema, { cache: 'no-store' }),
  setHud: async (x: number, y: number, label: string): Promise<void> => {
    await request('/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ x, y, label }),
    })
  },
  clearHud: async (): Promise<void> => {
    await request('/clear', { method: 'POST' })
  },
  startOcr: async (): Promise<void> => {
    await request('/ocr-select', { method: 'POST' })
  },
  getOcrState: (): Promise<OcrState> => json('/ocr-state', ocrStateSchema, { cache: 'no-store' }),
  startGameMarker: async (x: number, y: number, dryRun = false): Promise<void> => {
    await request('/game-marker/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ x, y, dryRun }),
    })
  },
  getGameMarkerState: (): Promise<GameMarkerState> =>
    json('/game-marker/state', gameMarkerStateSchema, { cache: 'no-store' }),
  cancelGameMarker: async (): Promise<void> => {
    await request('/game-marker/cancel', { method: 'POST' })
  },
  startMouseLoop: async (intervalSeconds: number): Promise<void> => {
    await request('/mouse-loop/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intervalSeconds }),
    })
  },
  stopMouseLoop: async (): Promise<void> => {
    await request('/mouse-loop/stop', { method: 'POST' })
  },
  getMouseLoopState: (): Promise<MouseLoopState> =>
    json('/mouse-loop/state', mouseLoopStateSchema, { cache: 'no-store' }),
  mapTileUrl: (z: number, x: number, y: number): string =>
    `${apiBase}/map-tile?z=${z}&x=${x}&y=${y}`,
  mapTileUrlWt: (z: number, x: number, y: number): string =>
    `${apiBase}/map-tile?z=${z}&x=${x}&y=${y}&map=wt`,
  mapIconUrl: (source: string): string => `${apiBase}/map-icon?src=${encodeURIComponent(source)}`,
}
