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

export type HealthState = z.infer<typeof healthSchema>
export type OcrState = z.infer<typeof ocrStateSchema>
export type GameMarkerState = z.infer<typeof gameMarkerStateSchema>
