import { z } from 'zod'

const mapKeySchema = z.enum(['world', 'tree'])

export const spawnLocationOptionSchema = z.object({
  id: z.string(),
  name: z.string(),
  mapKeys: z.array(mapKeySchema),
  iconId: z.string().optional(),
  slug: z.string().optional(),
  isNewIn10: z.boolean().optional(),
})

export const spawnLocationCatalogSchema = z.object({
  revision: z.string(),
  pals: z.array(spawnLocationOptionSchema),
  humans: z.array(spawnLocationOptionSchema),
})

export const spawnLocationPointsSchema = z.object({
  day: z.array(z.tuple([z.number(), z.number()])),
  night: z.array(z.tuple([z.number(), z.number()])),
})

export type SpawnLocationOption = z.infer<typeof spawnLocationOptionSchema>
export type SpawnLocationCatalog = z.infer<typeof spawnLocationCatalogSchema>
export type SpawnLocationPoints = z.infer<typeof spawnLocationPointsSchema>

export interface SelectedSpawnLocation {
  kind: 'pals' | 'humans'
  id: string
}

export interface SpawnMapPoint {
  gameX: number
  gameY: number
  day: boolean
  night: boolean
}
