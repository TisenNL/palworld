#!/usr/bin/env node
/**
 * fetch-recipes.mjs — build src/data/recipes.json from paldb.cc item pages.
 *
 * Usage:
 *   node scripts/fetch-recipes.mjs [Item_Slug ...] [--refresh]
 *
 *   Item_Slug   Root items to expand (default: AI_Core). Slugs are the paldb
 *               page names, e.g. AI_Core, Computer, Soralite_Ingot.
 *   --refresh   Ignore the HTML cache in .cache/paldb and refetch everything.
 *
 * Rules (see task spec):
 *   - Only the "Production" section of a page is read; rows whose "Product" is
 *     the page's own item are used. The "Crafting Materials" section (recipes
 *     where this item is an ingredient) is ignored.
 *   - The number next to the work-tool icon inside a recipe row is the
 *     production time, never an ingredient.
 *   - An item with no "Production" section is a raw material: recursion stops.
 *   - Multiple recipes/benches → first Production row wins, a note is stored
 *     in the generated file (JSON has no comments, so notes live in the entry).
 *   - Every fetched page is cached in .cache/paldb and requests are throttled.
 *   - Any unreachable page or unrecognized layout aborts with exit code 1 —
 *     the script never invents data.
 *
 * Generated shape (the app only ever reads this JSON, never the network):
 *   {
 *     "_meta": { "source": "...", "generatedAt": "...", "roots": ["ai-core"] },
 *     "ai-core": {
 *       "name": "AI Core",
 *       "note": "optional comment about multiple recipes/benches",
 *       "ingredients": [{ "item": "Computer", "key": "computer", "qty": 5 }]
 *     },
 *     "ore": { "name": "Ore", "ingredients": [] }   // empty = raw material
 *   }
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(SCRIPT_DIR, '..')
const BASE_URL = 'https://paldb.cc/en/'
const CACHE_DIR = resolve(REPO_ROOT, '.cache/paldb')
const OUT_FILE = resolve(REPO_ROOT, 'src/data/recipes.json')
const DEFAULT_ROOTS = ['AI_Core']
const REQUEST_DELAY_MS = 400
const MAX_PAGES = 500

/** One "<a class="itemname">Name</a> <small class="itemQuantity">N</small>" pair. */
const LINK_QTY_RE =
  /<a class="itemname"[^>]*href="([^"]+)"[^>]*>(?:<[^>]+>)?([^<]*)<\/a>\s*<small class="itemQuantity">(\d+)<\/small>/g
const LINK_QTY_ONE_RE = new RegExp(LINK_QTY_RE.source)
/** Same pair without the quantity (item header, bench links). */
const LINK_RE = /<a class="itemname"[^>]*href="([^"]+)"[^>]*>(?:<[^>]+>)?([^<]*)<\/a>/
/** Bench links carry a trailing space in the class (class="itemname "). */
const BENCH_LINK_RE = /<a class="itemname\s*"[^>]*href="([^"]+)"[^>]*>(?:<[^>]+>)?([^<]*)<\/a>/g
const SLUG_RE = /^[A-Za-z0-9_]+$/

class StructureError extends Error {}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** paldb slug / display name → stable JSON key ("AI_Core" → "ai-core"). */
function keyFor(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function assertSlug(slug, context) {
  if (!SLUG_RE.test(slug)) {
    throw new StructureError(
      `Unrecognized link target "${slug}" in ${context} (expected an item slug like "AI_Core").`,
    )
  }
}

// ─── Fetching (cached) ────────────────────────────────────────────────────────

async function loadPage(slug, refresh) {
  const cachePath = resolve(CACHE_DIR, `${slug}.html`)
  if (!refresh && existsSync(cachePath)) return readFileSync(cachePath, 'utf8')

  let response
  try {
    response = await fetch(`${BASE_URL}${slug}`, {
      headers: { 'user-agent': 'Mozilla/5.0 (compatible; fetch-recipes.mjs)' },
      redirect: 'follow',
    })
  } catch (error) {
    throw new Error(`Could not reach paldb.cc for "${slug}": ${error.message}`)
  }
  if (!response.ok) {
    throw new Error(`paldb.cc returned HTTP ${response.status} for "${slug}" — aborting.`)
  }
  const html = await response.text()
  if (!html.includes('Palworld Database Wiki')) {
    throw new Error(`Unexpected response for "${slug}" (not a paldb item page) — aborting.`)
  }
  mkdirSync(CACHE_DIR, { recursive: true })
  writeFileSync(cachePath, html)
  await sleep(REQUEST_DELAY_MS)
  return html
}

// ─── Parsing ─────────────────────────────────────────────────────────────────

function firstLink(text, context) {
  const match = text.match(LINK_RE)
  if (!match) throw new StructureError(`Item link not found in ${context}.`)
  assertSlug(match[1], context)
  const name = match[2].trim()
  if (!name) throw new StructureError(`Empty item name in ${context}.`)
  return { slug: match[1], name }
}

/**
 * Parse one paldb item page.
 * Returns { slug, name, benches, recipeCount, recipe } where `recipe` is null
 * for raw materials (no "Production" section).
 */
function parseItemPage(html) {
  const bannerStart = html.indexOf('hover_banner')
  if (bannerStart === -1) {
    throw new StructureError('Item header banner (hover_banner) not found.')
  }
  const header = firstLink(html.slice(bannerStart, bannerStart + 600), 'the item header')
  // Item icon lives right under the banner (hover_icon_bg block).
  const icon = extractIcon(html, header.slug)

  const prodStart = html.indexOf('convert_item_product_tab_title')
  if (prodStart === -1) {
    // No "Production" section → not craftable → raw material.
    return { ...header, icon, benches: [], recipeCount: 0, recipe: null }
  }

  const tableEnd = html.indexOf('</table>', prodStart)
  if (tableEnd === -1) throw new StructureError('Production section without a closing </table>.')
  const block = html.slice(prodStart, tableEnd)
  if (!block.includes('<tbody>')) throw new StructureError('Production table has no <tbody>.')

  // Workbenches listed above the recipe table.
  const headEnd = block.indexOf('<div class="table-responsive">')
  const head = headEnd === -1 ? '' : block.slice(0, headEnd)
  const benches = [...head.matchAll(BENCH_LINK_RE)].map((m) => m[2].trim())

  // Recipe rows. Row markup is loose ("<tr><td>…<td>…<td>…"), so split by cell
  // openers: [0] pre-row text, [1] materials, [2] product, [3] schematic.
  const rows = []
  for (const chunk of block.split('<tr>').slice(1)) {
    const cells = chunk.split('<td>')
    if (cells.length < 3) continue // header row uses <th>, not <td>
    const product = parseProduct(cells[2])
    if (!product) continue
    const ingredients = []
    for (const match of cells[1].matchAll(LINK_QTY_RE)) {
      assertSlug(match[1], 'a Production ingredient')
      ingredients.push({ slug: match[1], name: match[2].trim(), qty: Number(match[3]) })
    }
    if (ingredients.length === 0) continue
    rows.push({ product, ingredients })
  }
  if (rows.length === 0) {
    throw new StructureError('Production section found but no recipe row could be parsed.')
  }

  const own = rows.filter((row) => row.product.slug === header.slug)
  if (own.length === 0) {
    const seen = rows.map((row) => row.product.slug).join(', ')
    throw new StructureError(
      `Production rows exist but none produce ${header.slug} (found: ${seen}).`,
    )
  }
  return { ...header, icon, benches, recipeCount: own.length, recipe: own[0] }
}

/** Item icon (CDN URL) from the header block; null when the page has none. */
function extractIcon(html, slug) {
  const start = html.indexOf('hover_icon_bg')
  if (start === -1) return null
  const match = /<a href="([^"]+)"><img[^>]*src="([^"]+)"/.exec(html.slice(start, start + 600))
  if (!match) return null
  if (match[1] !== slug) {
    throw new StructureError(`Icon block points to ${match[1]} on the ${slug} page.`)
  }
  if (!match[2].startsWith('https://cdn.paldb.cc/')) return null
  return match[2]
}

/** Product cell: item link + produced quantity. Null when unparseable. */
function parseProduct(text) {
  const match = LINK_QTY_ONE_RE.exec(text)
  if (!match || !SLUG_RE.test(match[1])) return null
  return { slug: match[1], name: match[2].trim(), qty: Number(match[3]) }
}

// ─── Walk ────────────────────────────────────────────────────────────────────

async function buildRecipes(rootSlugs, refresh) {
  /** @type {Map<string, any>} key → entry (insertion order = BFS order) */
  const entries = new Map()
  const queue = [...rootSlugs]
  const queued = new Set(rootSlugs.map(keyFor))

  while (queue.length > 0) {
    const slug = queue.shift()
    const key = keyFor(slug)
    if (entries.has(key)) continue
    if (entries.size >= MAX_PAGES) {
      throw new Error(`Refusing to crawl more than ${MAX_PAGES} pages — possible runaway tree.`)
    }

    process.stderr.write(`fetching ${slug}… `)
    const html = await loadPage(slug, refresh)
    const page = parseItemPage(html)
    const pageKey = keyFor(page.slug)
    if (pageKey !== key) {
      process.stderr.write(`(redirected: ${slug} → ${page.slug}) `)
    }
    if (entries.has(pageKey)) continue

    const entryNotes = []
    if (page.benches.length > 1) {
      entryNotes.push(
        `${page.benches.length} workbenches (${page.benches.join(', ')}); using the first Production recipe.`,
      )
    }
    if (page.recipeCount > 1) {
      entryNotes.push(`${page.recipeCount} recipes in Production; using the first one.`)
    }

    const ingredients = []
    if (page.recipe) {
      if (page.recipe.product.qty > 1) {
        entryNotes.push(
          `Recipe yields ${page.recipe.product.qty} per craft; totals assume one unit per craft.`,
        )
      }
      for (const ing of page.recipe.ingredients) {
        const ingKey = keyFor(ing.slug)
        if (ingKey === pageKey) {
          entryNotes.push(`Recipe lists ${page.name} as its own ingredient; branch cut.`)
          continue
        }
        ingredients.push({ item: ing.name, key: ingKey, qty: ing.qty })
        if (!entries.has(ingKey) && !queued.has(ingKey)) {
          queue.push(ing.slug)
          queued.add(ingKey)
        }
      }
    }

    const entry = { name: page.name, ingredients }
    if (page.icon) entry.icon = page.icon
    else process.stderr.write(`  WARNING: no icon found for ${page.slug}\n`)
    if (entryNotes.length > 0) entry.note = entryNotes.join(' ')
    entries.set(pageKey, entry)
    process.stderr.write(`${ingredients.length} ingredient(s)\n`)
  }

  return { entries }
}

function parseArgs(argv) {
  const roots = []
  let refresh = false
  for (const arg of argv) {
    if (arg === '--refresh') refresh = true
    else if (arg.startsWith('--')) {
      console.error(`Unknown option "${arg}".`)
      process.exit(2)
    } else roots.push(arg)
  }
  for (const slug of roots) {
    if (!SLUG_RE.test(slug)) {
      console.error(`Invalid item slug "${slug}" (expected e.g. AI_Core).`)
      process.exit(2)
    }
  }
  return { roots: roots.length > 0 ? roots : DEFAULT_ROOTS, refresh }
}

async function main() {
  const { roots, refresh } = parseArgs(process.argv.slice(2))
  const { entries } = await buildRecipes(roots, refresh)

  const rootKeys = roots.map(keyFor)
  for (const rootKey of rootKeys) {
    if (!entries.has(rootKey)) {
      throw new Error(`Root item "${rootKey}" missing from collected data.`)
    }
  }

  const output = {
    _meta: {
      source: BASE_URL,
      generatedAt: new Date().toISOString(),
      roots: rootKeys,
    },
  }
  for (const [key, entry] of entries) {
    if (key === '_meta') throw new Error('Item key "_meta" is reserved.')
    output[key] = entry
  }

  mkdirSync(dirname(OUT_FILE), { recursive: true })
  writeFileSync(OUT_FILE, `${JSON.stringify(output, null, 2)}\n`)

  console.log(`\nWrote ${entries.size} items to ${OUT_FILE}`)
  for (const rootKey of rootKeys) {
    const entry = entries.get(rootKey)
    const list = entry.ingredients.map((i) => `${i.item} x${i.qty}`).join(', ') || '(raw material)'
    console.log(`  ${entry.name} x1 → ${list}`)
  }
  const noted = [...entries.values()].filter((e) => e.note)
  if (noted.length > 0) {
    console.log('Notes recorded in the generated file:')
    for (const entry of noted) console.log(`  ${entry.name}: ${entry.note}`)
  }
}

main().catch((error) => {
  if (error instanceof StructureError) {
    console.error(`\nStructure not recognized — aborting without writing data.\n  ${error.message}`)
  } else {
    console.error(`\n${error.message}`)
  }
  process.exit(1)
})
