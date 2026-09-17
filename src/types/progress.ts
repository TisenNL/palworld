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
  hideDone: z.boolean().default(false),
  mapLayers: z.record(z.string(), z.boolean()).default({}),
  mapHideDone: z.boolean().default(false),
  mapCam: mapCameraSchema.nullable().default(null),
  sidebarWidth: z.number().min(260).max(720).default(320),
  sidebarTransparency: z.number().min(0).max(100).default(26),
  sideBlockOpen: z.record(z.string(), z.boolean()).default({}),
  mapBrowseGroup: z.string().default(''),
  listBrowseGroup: z.string().default(''),
})

export const progressSchema = z.object({
  version: z.number().default(2),
  revision: z.number().nonnegative().default(0),
  updatedAt: z.string().default(''),
  checks: checksSchema,
  breedOwned: checkedItemsSchema.default({}),
  prefs: preferencesSchema,
})

export type Preferences = z.infer<typeof preferencesSchema>
export type ProgressPayload = z.infer<typeof progressSchema>

export function emptyChecks(): Checks {
  return Object.fromEntries(checkCategories.map((key) => [key, {}])) as Checks
}
