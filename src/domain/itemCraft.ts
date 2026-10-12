import {
  recipeEntrySchema,
  recipesFileSchema,
  type RecipeEntry,
  type RecipesMeta,
} from '@/types/recipes'

export interface CraftMaterial {
  key: string
  name: string
  total: number
  /** Item icon from the generated file, when the fetch script captured one. */
  icon?: string
}

export interface CraftNode {
  key: string
  name: string
  /** Items needed at this point of the tree (already scaled by the requested quantity). */
  qty: number
  craftable: boolean
  /** True when the branch was cut because the recipes form a cycle. */
  cycle: boolean
  /** Item icon from the generated file, when the fetch script captured one. */
  icon?: string
  children: CraftNode[]
}

export interface CraftPlan {
  rootKey: string
  rootName: string
  /** Comment carried from the generated file (e.g. "2 workbenches …"). */
  note?: string
  /** Consolidated raw materials, biggest total first. */
  materials: CraftMaterial[]
  /** Root node(s) of the crafting tree, scaled by the requested quantity. */
  tree: CraftNode[]
  warnings: string[]
}

export interface RecipeBook {
  meta: RecipesMeta | null
  entries: Map<string, RecipeEntry>
}

/** Hard depth cap — belt and braces on top of the cycle guard. */
const MAX_DEPTH = 32
/** Quantity is clamped to this so a typo can never blow up the math. */
export const MAX_QUANTITY = 999_999

/** Display name → stable file key ("Soralite Ingot" → "soralite-ingot"). */
export function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/** Integers only, minimum 1, capped at MAX_QUANTITY. Accepts null/NaN from cleared inputs. */
export function sanitizeQuantity(value: number | null | undefined): number {
  const next = Math.floor(Number(value))
  if (!Number.isFinite(next) || next < 1) return 1
  return Math.min(next, MAX_QUANTITY)
}

function isEntry(value: unknown): value is RecipeEntry {
  const parsed = recipeEntrySchema.safeParse(value)
  return parsed.success
}

/** Validate the generated JSON (zod) and index it for O(1) lookups. */
export function loadRecipeBook(raw: unknown): RecipeBook {
  const file = recipesFileSchema.parse(raw)
  const entries = new Map<string, RecipeEntry>()
  let meta: RecipesMeta | null = null
  for (const [key, value] of Object.entries(file)) {
    if (key === '_meta' && !('ingredients' in value)) {
      meta = value
      continue
    }
    if (!isEntry(value)) {
      throw new Error(`Invalid recipe entry "${key}" in the recipes data file.`)
    }
    entries.set(key, value)
  }
  return { meta, entries }
}

/**
 * Selectable roots: whatever the fetch script declared, falling back to every
 * entry so the dropdown still works with hand-written files.
 */
export function listRootKeys(book: RecipeBook): string[] {
  const declared = (book.meta?.roots ?? []).filter((key) => book.entries.has(key))
  if (declared.length > 0) return declared
  return [...book.entries.keys()]
}

/**
 * Expand the whole recipe tree for `quantity` units of `rootKey`.
 * Returns null when the item is not in the book.
 */
export function buildCraftPlan(
  book: RecipeBook,
  rootKey: string,
  quantity: number | null | undefined,
): CraftPlan | null {
  const root = book.entries.get(rootKey)
  if (!root) return null
  const needed = sanitizeQuantity(quantity)

  const totals = new Map<string, CraftMaterial>()
  const warnings = new Set<string>()

  const accumulate = (key: string, name: string, amount: number, icon?: string): void => {
    const current = totals.get(key)
    if (current) {
      current.total += amount
      return
    }
    const material: CraftMaterial = { key, name, total: amount }
    if (icon) material.icon = icon
    totals.set(key, material)
  }

  const expand = (
    key: string,
    name: string,
    amount: number,
    depth: number,
    path: Set<string>,
  ): CraftNode => {
    const entry = book.entries.get(key)
    const cycle = path.has(key)
    const tooDeep = depth >= MAX_DEPTH

    if (entry && entry.ingredients.length > 0 && !cycle && !tooDeep) {
      const nextPath = new Set(path)
      nextPath.add(key)
      const children = entry.ingredients.map((ingredient) => {
        const childKey = ingredient.key ?? slugify(ingredient.item)
        const childName = book.entries.get(childKey)?.name ?? ingredient.item
        return expand(childKey, childName, amount * ingredient.qty, depth + 1, nextPath)
      })
      const node: CraftNode = { key, name, qty: amount, craftable: true, cycle: false, children }
      if (entry.icon) node.icon = entry.icon
      return node
    }

    // Leaf: raw material, an unknown item, a cycle or a runaway branch.
    if (cycle) {
      warnings.add(`Recipe cycle detected at "${name}" — branch stopped to avoid a loop.`)
    } else if (tooDeep) {
      warnings.add(`Recipe nesting deeper than ${MAX_DEPTH} levels at "${name}" — branch stopped.`)
    } else if (!entry) {
      warnings.add(`No recipe data for "${name}" — counted as a raw material.`)
    }
    accumulate(key, name, amount, entry?.icon)
    const leaf: CraftNode = { key, name, qty: amount, craftable: false, cycle, children: [] }
    if (entry?.icon) leaf.icon = entry.icon
    return leaf
  }

  const tree = [expand(rootKey, root.name, needed, 0, new Set<string>())]
  const materials = [...totals.values()].sort(
    (a, b) => b.total - a.total || a.name.localeCompare(b.name),
  )

  const plan: CraftPlan = {
    rootKey,
    rootName: root.name,
    materials,
    tree,
    warnings: [...warnings],
  }
  if (root.note) plan.note = root.note
  return plan
}

// ─── Tournament bracket projection ───────────────────────────────────────────

export interface BracketTile {
  /** Unique within its round: "`level`:`key`". */
  id: string
  key: string
  name: string
  icon?: string
  /** Units needed in this round (occurrences of the item at this depth summed). */
  qty: number
  /** 0 = deepest round (leftmost), maxLevel = champion column (rightmost). */
  level: number
  /** The item being crafted — the tournament champion. */
  champion: boolean
  /** Leaf of the tree (raw material / cycle cut / unknown recipe). */
  raw: boolean
}

export interface BracketEdge {
  /** Ingredient tile (left round) → product tile (right round). */
  from: string
  to: string
}

export interface CraftBracket {
  /** Tiles per round, left (raw) to right (champion). Never sparse. */
  levels: BracketTile[][]
  edges: BracketEdge[]
  maxLevel: number
}

/**
 * Turn a recipe tree into a tournament bracket: every depth becomes a round,
 * items repeated inside one round are merged (their quantities summed) and the
 * crafted item stands alone in the last column as the champion.
 */
export function buildBracket(tree: CraftNode[]): CraftBracket | null {
  const root = tree[0]
  if (!root) return null

  // Pass 1 — deepest root→leaf path sets how many rounds the bracket has.
  let maxDepth = 0
  const measure = (node: CraftNode, depth: number): void => {
    if (depth > maxDepth) maxDepth = depth
    for (const child of node.children) measure(child, depth + 1)
  }
  measure(root, 0)

  const tiles = new Map<string, BracketTile>()
  const order = new Map<string, number>()
  const edges = new Map<string, BracketEdge>()
  let visits = 0

  // Pass 2 — place every occurrence: level = maxDepth - depth keeps the
  // champion on the right and always connects neighbouring rounds.
  const place = (node: CraftNode, depth: number, parentId: string | null): void => {
    const level = maxDepth - depth
    const id = `${level}:${node.key}`
    const existing = tiles.get(id)
    if (existing) {
      existing.qty += node.qty
    } else {
      const tile: BracketTile = {
        id,
        key: node.key,
        name: node.name,
        qty: node.qty,
        level,
        champion: depth === 0,
        raw: !node.craftable,
      }
      if (node.icon) tile.icon = node.icon
      tiles.set(id, tile)
      order.set(id, visits)
    }
    visits += 1
    if (parentId) {
      const edgeId = `${id}>${parentId}`
      if (!edges.has(edgeId)) edges.set(edgeId, { from: id, to: parentId })
    }
    for (const child of node.children) place(child, depth + 1, id)
  }
  place(root, 0, null)

  const levels: BracketTile[][] = Array.from({ length: maxDepth + 1 }, () => [])
  for (const tile of tiles.values()) {
    levels[tile.level]!.push(tile)
  }
  // Pre-order first-visit keeps children below their parents' column order,
  // so edges between neighbouring rounds never cross.
  for (const level of levels) {
    level.sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0))
  }

  return { levels, edges: [...edges.values()], maxLevel: maxDepth }
}
