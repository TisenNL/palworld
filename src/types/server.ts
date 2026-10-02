import { z } from 'zod'

export const healthSchema = z.object({
  ok: z.boolean(),
  version: z.string(),
  anchor: z.tuple([z.number(), z.number()]),
  active: z.boolean(),
  x: z.number(),
  y: z.number(),
  label: z.string(),
})

export const ocrStateSchema = z.object({
  ok: z.boolean(),
  active: z.boolean().optional(),
  status: z.enum(['idle', 'selecting', 'reading', 'copied', 'error', 'cancelled']),
  text: z.string().default(''),
  error: z.string().default(''),
})

export const gameMarkerStateSchema = z.object({
  ok: z.boolean(),
  active: z.boolean(),
  status: z.enum([
    'idle',
    'selecting',
    'calibrating',
    'moving',
    'marking',
    'completed',
    'cancelled',
    'error',
  ]),
  target: z.tuple([z.number(), z.number()]).nullable(),
  current: z.tuple([z.number(), z.number()]).nullable(),
  distanceMeters: z.number().nullable(),
  message: z.string(),
  error: z.string(),
})

export const mouseLoopStateSchema = z.object({
  ok: z.boolean(),
  active: z.boolean(),
  status: z.enum(['idle', 'running', 'waiting', 'cancelled', 'error']),
  intervalSeconds: z.number().nonnegative().default(40),
  message: z.string().default(''),
  error: z.string().default(''),
})

export const playerPositionSchema = z.object({
  gameX: z.number().finite(),
  gameY: z.number().finite(),
  gameZ: z.number().finite(),
  mapZone: z.enum(['palpagos', 'world-tree']),
  updatedAt: z.string(),
})

export const playerPositionStateSchema = z.object({
  ok: z.boolean(),
  status: z.enum([
    'ready',
    'not_running',
    'access_denied',
    'unsupported',
    'unsupported_build',
    'waiting_for_player',
    'invalid_position',
    'probe_error',
  ]),
  processFound: z.boolean(),
  readAccess: z.boolean(),
  pid: z.number().int().nullable(),
  position: playerPositionSchema.nullable(),
  error: z.string(),
})

export type HealthState = z.infer<typeof healthSchema>
export type OcrState = z.infer<typeof ocrStateSchema>
export type GameMarkerState = z.infer<typeof gameMarkerStateSchema>
export type MouseLoopState = z.infer<typeof mouseLoopStateSchema>
export type PlayerPosition = z.infer<typeof playerPositionSchema>
export type PlayerPositionState = z.infer<typeof playerPositionStateSchema>
