import { z } from 'zod'

/** One ingredient line of a recipe, as written by scripts/fetch-recipes.mjs. */
export const recipeIngredientSchema = z.object({
  /** Display name, exactly as on paldb (e.g. "Soralite Ingot"). */
  item: z.string(),
  /** Join key into the recipe file ("soralite-ingot"); falls back to slugifying `item`. */
  key: z.string().optional(),
  qty: z.number().int().positive(),
})

/** A recipe entry: craftable when `ingredients` is non-empty, raw material otherwise. */
export const recipeEntrySchema = z.object({
  name: z.string(),
  ingredients: z.array(recipeIngredientSchema),
  /** Item icon scraped from the paldb page header (cdn.paldb.cc CDN). */
  icon: z.string().url().optional(),
  /** Comment recorded by the fetch script (multiple recipes/benches, cycles, …). */
  note: z.string().optional(),
})

/** Reserved "_meta" key: which keys are selectable roots and where data came from. */
export const recipesMetaSchema = z.object({
  source: z.string().optional(),
  generatedAt: z.string().optional(),
  roots: z.array(z.string()).default([]),
})

/** Whole generated file. `_meta` is distinguished from entries by its `roots` field. */
export const recipesFileSchema = z.record(
  z.string(),
  z.union([recipeEntrySchema, recipesMetaSchema]),
)

export type RecipeIngredient = z.infer<typeof recipeIngredientSchema>
export type RecipeEntry = z.infer<typeof recipeEntrySchema>
export type RecipesMeta = z.infer<typeof recipesMetaSchema>
export type RecipesFile = z.infer<typeof recipesFileSchema>
