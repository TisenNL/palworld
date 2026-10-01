/**
 * Tipos para a fila de "Mark in game" em lote.
 *
 * Itens são value objects copiados do Marker no momento do enqueue, para que
 * a fila sobreviva a trocas de zona e a reloads da página (localStorage key:
 * 'palworld:map:mark-queue', gerida pelo store serverHud).
 */

import { z } from 'zod'

export const batchQueueItemSchema = z.object({
  /** ID estável do marker de origem: '{type}:{lat}:{lng}' */
  id: z.string(),
  /** Zona do mapa de onde o marker veio — a fila nunca mistura zonas */
  zone: z.enum(['palpagos', 'world-tree']),
  type: z.string(),
  subtype: z.string().nullable(),
  /** Nome de exibição resolvido no enqueue (markerDisplayName) */
  name: z.string(),
  /** Coordenadas do pause menu do jogo */
  x: z.number(),
  y: z.number(),
  status: z.enum(['pending', 'processing', 'completed', 'failed']),
  /** Detalhe do erro quando status = 'failed' */
  error: z.string().optional(),
})

export type BatchQueueItem = z.infer<typeof batchQueueItemSchema>
export type BatchQueueStatus = BatchQueueItem['status']

/** Item novo, ainda sem status, ao entrar na fila */
export type BatchQueueDraft = Omit<BatchQueueItem, 'status'>

export type BatchEnqueueResult = 'ok' | 'mixed-zone' | 'running'

export interface BatchRunSummary {
  completed: number
  failed: number
  cancelled: boolean
}
