import { z } from 'zod'

const coordinateSchema = z.object({
  id: z.string(),
  x: z.number(),
  y: z.number(),
  z: z.number().nullable().optional(),
  n: z.number().nullable().optional(),
  name: z.string().nullable().optional(),
  lv: z.number().nullable().optional(),
  type: z.string().nullable().optional(),
  kind: z.string().nullable().optional(),
  series: z.string().nullable().optional(),
  tag: z.string().nullable().optional(),
  icon: z.string().nullable().optional(),
  volume: z.number().int().positive().nullable().optional(),
})

export const gameDataSchema = z.object({
  alphas: z.array(coordinateSchema).default([]),
  bounties: z.array(coordinateSchema).default([]),
  effigies: z.array(coordinateSchema).default([]),
  dungeons: z.array(coordinateSchema).default([]),
  towers: z.array(coordinateSchema).default([]),
  journals: z.array(coordinateSchema).default([]),
  oilrigs: z.array(coordinateSchema).default([]),
  camps: z.array(coordinateSchema).default([]),
  collectibles: z.array(coordinateSchema).default([]),
  travel: z.array(coordinateSchema).default([]),
})

export const palSchema = z.object({
  code: z.string(),
  name: z.string(),
  id: z.string(),
  rank: z.number(),
  ignoreCombi: z.boolean(),
  mutation: z.boolean(),
  male: z.string(),
  female: z.string(),
  icon: z.string().url(),
  order: z.number(),
})

export const breedDataSchema = z.object({
  version: z.number(),
  source: z.string(),
  pals: z.array(palSchema),
  unique: z.array(z.object({ a: z.string(), b: z.string(), child: z.string() })),
})

export const mapIconsSchema = z.object({
  version: z.number(),
  source: z.string(),
  icons: z.record(z.string(), z.string().url()),
})

export type CoordinateItem = z.infer<typeof coordinateSchema>
export type GameData = z.infer<typeof gameDataSchema>
export type Pal = z.infer<typeof palSchema>
export type BreedData = z.infer<typeof breedDataSchema>
export type MapIconsData = z.infer<typeof mapIconsSchema>

export type StorageKey = keyof GameData

export interface ListEntry extends CoordinateItem {
  uid: string
  storage: StorageKey
  layerId: string
  layerLabel: string
  color: string
}

export interface MapLayer {
  id: string
  label: string
  color: string
  storage: StorageKey
  group: string
  iconKey?: string
  typeIn?: string[]
  kindIn?: string[]
  iconUrl?: string
}

export interface MapMarker {
  id: string
  layerId: string
  storage: StorageKey
  item: CoordinateItem
  label: string
  color: string
  iconUrl?: string
  done: boolean
}

// ── World Tree zone data ──────────────────────────────────────────────────────
// Same 10-bucket shape as Palpagos so buildLayers()/layerItems() work unmodified.

export const wtDataSchema = gameDataSchema

export type WtData = GameData
