import { z } from 'zod'

export const checkCategories = [
  'alphas',
  'bounties',
  'effigies',
  'dungeons',
  'towers',
  'journals',
  'oilrigs',
  'camps',
  'collectibles',
  'travel',
] as const

export type CheckCategory = (typeof checkCategories)[number]
export type CheckedItems = Record<string, true>
export type Checks = Record<CheckCategory, CheckedItems>

const checkedItemsSchema = z.record(z.string(), z.literal(true))

export const checksSchema = z.object(
  Object.fromEntries(checkCategories.map((key) => [key, checkedItemsSchema])) as Record<
    CheckCategory,
    typeof checkedItemsSchema
  >,
)

export const mapCameraSchema = z.object({
  ix: z.number(),
  iy: z.number(),
  scaleCss: z.number().positive(),
})

export const preferencesSchema = z.object({
  mapLayers: z.record(z.string(), z.boolean()).default({}),
  mapCam: mapCameraSchema.nullable().default(null),
  wtMapCam: mapCameraSchema.nullable().default(null),
  activeMap: z.enum(['palpagos', 'world-tree']).default('palpagos'),
  sidebarWidth: z.number().min(260).max(720).default(320),
  sidebarTransparency: z.number().min(0).max(100).default(26),
  sidebarCollapsed: z.boolean().default(false),
  sideBlockOpen: z.record(z.string(), z.boolean()).default({}),
  mapBrowseGroup: z.string().default(''),
  listBrowseGroup: z.string().default(''),
})

const cakeValuesSchema = z.record(z.string(), z.number().nonnegative()).default({})

export const cakeStateSchema = z.object({
  recipe: z.string().default('cake'),
  gold: z.number().nonnegative().default(0),
  target: z.number().nonnegative().default(0),
  prices: cakeValuesSchema,
  stock: cakeValuesSchema,
})

export const progressSchema = z.object({
  version: z.number().default(2),
  revision: z.number().nonnegative().default(0),
  updatedAt: z.string().default(''),
  checks: checksSchema,
  breedOwned: checkedItemsSchema.default({}),
  prefs: preferencesSchema,
  cake: cakeStateSchema.optional(),
})

export type Preferences = z.infer<typeof preferencesSchema>
export type CakeState = z.infer<typeof cakeStateSchema>
export type ProgressPayload = z.infer<typeof progressSchema>

export function emptyChecks(): Checks {
  return Object.fromEntries(checkCategories.map((key) => [key, {}])) as Checks
}
