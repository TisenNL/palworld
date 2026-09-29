import type { BreedData, Pal } from '@/types/data'

export interface BreedStep {
  with: string
  result: string
}

export interface BreedPath {
  start: string
  steps: BreedStep[]
}

const pairKey = (a: string, b: string): string => (a < b ? `${a}|${b}` : `${b}|${a}`)

export function createBreedingEngine(data: BreedData) {
  const byCode = new Map(data.pals.map((pal) => [pal.code, pal]))
  const unique = new Map<string, string[]>()
  const uniqueChildren = new Set<string>()
  for (const combination of data.unique) {
    const key = pairKey(combination.a, combination.b)
    const values = unique.get(key) ?? []
    if (!values.includes(combination.child)) values.push(combination.child)
    unique.set(key, values)
    uniqueChildren.add(combination.child)
  }

  function results(codeA: string, codeB: string): string[] {
    const a = byCode.get(codeA)
    const b = byCode.get(codeB)
    if (!a || !b) return []
    if (codeA === codeB) return [codeA]
    const special = unique.get(pairKey(codeA, codeB))
    if (special?.length) return [...special]
    const power = Math.floor((a.rank + b.rank + 1) / 2)
    let best: Pal | undefined
    let distance = Number.POSITIVE_INFINITY
    for (const candidate of data.pals) {
      if (candidate.ignoreCombi || uniqueChildren.has(candidate.code)) continue
      const nextDistance = Math.abs(candidate.rank - power)
      // Em caso de empate de distância, prefere o pal com maior rank.
      // Isso garante resultado determinístico quando múltiplos pals têm o power exato
      // ou estão equidistantes do power alvo (ex: power=100, candidates com rank=90 e 110).
      if (
        nextDistance < distance ||
        (nextDistance === distance && candidate.rank > (best?.rank ?? -Infinity))
      ) {
        best = candidate
        distance = nextDistance
      }
    }
    return best ? [best.code] : []
  }

  function parentsFor(child: string, owned?: Set<string>): Array<[string, string]> {
    const pairs: Array<[string, string]> = []
    for (let i = 0; i < data.pals.length; i++) {
      for (let j = i; j < data.pals.length; j++) {
        const a = data.pals[i]!.code
        const b = data.pals[j]!.code
        if (owned && (!owned.has(a) || !owned.has(b))) continue
        if (results(a, b).includes(child)) pairs.push([a, b])
      }
    }
    return pairs
  }

  function path(
    from: string,
    to: string,
    includeTargetAsParent: boolean,
    hideIgnoreCombi: boolean,
  ): BreedPath | null {
    if (from === to) return { start: from, steps: [] }
    const partners = data.pals.filter((pal) => !hideIgnoreCombi || !pal.ignoreCombi)
    const queue: BreedPath[] = [{ start: from, steps: [] }]
    const seen = new Set([from])
    while (queue.length) {
      const current = queue.shift()!
      if (current.steps.length >= 5) continue
      const currentCode = current.steps.at(-1)?.result ?? from
      for (const partner of partners) {
        if (!includeTargetAsParent && partner.code === to) continue
        for (const child of results(currentCode, partner.code)) {
          if (seen.has(child)) continue
          const next = {
            start: from,
            steps: [...current.steps, { with: partner.code, result: child }],
          }
          if (child === to) return next
          seen.add(child)
          queue.push(next)
        }
      }
    }
    return null
  }

  function generations(ownedCodes: string[]): {
    generations: string[][]
    missing: string[]
  } {
    const owned = new Set(ownedCodes.filter((code) => byCode.has(code)))
    const closure = (pool: Set<string>): Set<string> => {
      const values = [...pool]
      const next = new Set<string>()
      for (let i = 0; i < values.length; i++) {
        for (let j = i; j < values.length; j++) {
          for (const child of results(values[i]!, values[j]!)) next.add(child)
        }
      }
      return next
    }
    const first = new Set([...closure(owned)].filter((code) => !owned.has(code)))
    const pool2 = new Set([...owned, ...first])
    const second = new Set(
      [...closure(pool2)].filter((code) => !owned.has(code) && !first.has(code)),
    )
    const pool3 = new Set([...pool2, ...second])
    const third = new Set(
      [...closure(pool3)].filter(
        (code) => !owned.has(code) && !first.has(code) && !second.has(code),
      ),
    )
    const reachable = new Set([...owned, ...first, ...second, ...third])
    const missing = data.pals
      .filter((pal) => !pal.ignoreCombi && !reachable.has(pal.code))
      .map((pal) => pal.code)
    return { generations: [[...owned], [...first], [...second], [...third]], missing }
  }

  return { byCode, results, parentsFor, path, generations }
}
