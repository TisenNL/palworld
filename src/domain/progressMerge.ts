import type { CakeState, CheckedItems, Preferences, ProgressPayload } from '@/types/progress'
import { checkCategories, emptyChecks } from '@/types/progress'
import { emptyStock, priceDefaults } from '@/domain/cakes'

const EMPTY_CAKE: CakeState = {
  recipe: 'cake',
  gold: 0,
  target: 0,
  prices: { ...priceDefaults },
  stock: { ...emptyStock },
}

function equal(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

function mergeBooleanMap<T extends boolean>(
  base: Record<string, T>,
  local: Record<string, T>,
  remote: Record<string, T>,
): Record<string, T> {
  const merged = { ...remote }
  for (const key of new Set([...Object.keys(base), ...Object.keys(local)])) {
    if (local[key] === base[key]) continue
    if (local[key] === undefined) delete merged[key]
    else merged[key] = local[key]
  }
  return merged
}

function mergeCheckedItems(
  base: CheckedItems,
  local: CheckedItems,
  remote: CheckedItems,
): CheckedItems {
  return mergeBooleanMap(base, local, remote)
}

function mergeNumberMap(
  base: Record<string, number>,
  local: Record<string, number>,
  remote: Record<string, number>,
): Record<string, number> {
  const merged = { ...remote }
  for (const key of new Set([...Object.keys(base), ...Object.keys(local)])) {
    if (local[key] === base[key]) continue
    if (local[key] === undefined) delete merged[key]
    else merged[key] = local[key]
  }
  return merged
}

function changed<T>(base: T, local: T, remote: T): T {
  return equal(base, local) ? remote : local
}

function mergePreferences(base: Preferences, local: Preferences, remote: Preferences): Preferences {
  return {
    mapLayers: mergeBooleanMap(base.mapLayers, local.mapLayers, remote.mapLayers),
    mapCam: changed(base.mapCam, local.mapCam, remote.mapCam),
    wtMapCam: changed(base.wtMapCam, local.wtMapCam, remote.wtMapCam),
    activeMap: changed(base.activeMap, local.activeMap, remote.activeMap),
    sidebarWidth: changed(base.sidebarWidth, local.sidebarWidth, remote.sidebarWidth),
    sidebarTransparency: changed(
      base.sidebarTransparency,
      local.sidebarTransparency,
      remote.sidebarTransparency,
    ),
    sidebarCollapsed: changed(
      base.sidebarCollapsed,
      local.sidebarCollapsed,
      remote.sidebarCollapsed,
    ),
    sideBlockOpen: mergeBooleanMap(base.sideBlockOpen, local.sideBlockOpen, remote.sideBlockOpen),
    mapBrowseGroup: changed(base.mapBrowseGroup, local.mapBrowseGroup, remote.mapBrowseGroup),
    listBrowseGroup: changed(base.listBrowseGroup, local.listBrowseGroup, remote.listBrowseGroup),
  }
}

function mergeCake(
  base: CakeState | undefined,
  local: CakeState | undefined,
  remote: CakeState | undefined,
): CakeState | undefined {
  if (equal(base, local)) return remote
  if (!local) return undefined
  if (!remote) return local
  const baseline = base ?? EMPTY_CAKE
  return {
    recipe: changed(baseline.recipe, local.recipe, remote.recipe),
    gold: changed(baseline.gold, local.gold, remote.gold),
    target: changed(baseline.target, local.target, remote.target),
    prices: mergeNumberMap(baseline.prices, local.prices, remote.prices),
    stock: mergeNumberMap(baseline.stock, local.stock, remote.stock),
  }
}

export function mergeProgressChanges(
  base: ProgressPayload,
  local: ProgressPayload,
  remote: ProgressPayload,
): ProgressPayload {
  const checks = emptyChecks()
  for (const key of checkCategories) {
    checks[key] = mergeCheckedItems(base.checks[key], local.checks[key], remote.checks[key])
  }
  return {
    version: Math.max(local.version, remote.version),
    revision: remote.revision,
    updatedAt: local.updatedAt,
    checks,
    breedOwned: mergeCheckedItems(base.breedOwned, local.breedOwned, remote.breedOwned),
    prefs: mergePreferences(base.prefs, local.prefs, remote.prefs),
    cake: mergeCake(base.cake, local.cake, remote.cake),
  }
}
