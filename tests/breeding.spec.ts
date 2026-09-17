import { describe, expect, it } from 'vitest'

import rawBreedData from '../breed.json'
import { createBreedingEngine } from '@/domain/breeding'
import type { BreedData, Pal } from '@/types/data'
import { breedDataSchema } from '@/types/data'

const pal = (code: string, rank: number, ignoreCombi = false): Pal => ({
  code,
  name: code,
  id: code,
  rank,
  ignoreCombi,
  mutation: false,
  male: '',
  female: '',
  icon: `https://example.com/${code}.webp`,
  order: rank,
})

const data: BreedData = {
  version: 1,
  source: 'test',
  pals: [pal('a', 10), pal('b', 20), pal('c', 15), pal('slime', 1, true)],
  unique: [{ a: 'a', b: 'b', child: 'c' }],
}

describe('breeding', () => {
  const engine = createBreedingEngine(data)

  it('prioritizes unique combinations', () => {
    expect(engine.results('a', 'b')).toEqual(['c'])
  })

  it('respects IgnoreCombi restrictions', () => {
    expect(engine.results('slime', 'a')).toEqual([])
    expect(engine.results('slime', 'slime')).toEqual(['slime'])
  })

  it('finds parents for an offspring', () => {
    expect(engine.parentsFor('c')).toContainEqual(['a', 'b'])
  })
})

describe('PalDB breeding data', () => {
  const paldbData = breedDataSchema.parse(rawBreedData)
  const engine = createBreedingEngine(paldbData)

  it('matches the current PalDB roster and usable unique combinations', () => {
    expect(paldbData.pals).toHaveLength(297)
    expect(paldbData.unique).toHaveLength(160)
    expect(new Set(paldbData.pals.map((item) => item.code)).size).toBe(297)
  })

  it('reproduces representative PalDB results', () => {
    expect(engine.results('SheepBall', 'SheepBall')).toEqual(['SheepBall'])
    expect(engine.results('DomeArmorDragon', 'ClioneTwins')).toEqual(['HerculesBeetle'])
    expect(engine.results('LazyDragon', 'ElecCat')).toEqual(['LazyDragon_Electric'])
    expect(engine.results('CatMage', 'FoxMage')).toEqual(
      expect.arrayContaining(['FoxMage_Dark', 'CatMage_Fire']),
    )
  })

  it('keeps every pair symmetric and every result valid', () => {
    const validCodes = new Set(paldbData.pals.map((item) => item.code))
    for (let first = 0; first < paldbData.pals.length; first += 1) {
      const parentA = paldbData.pals[first]!
      expect(engine.results(parentA.code, parentA.code)).toEqual([parentA.code])
      for (let second = first; second < paldbData.pals.length; second += 1) {
        const parentB = paldbData.pals[second]!
        const result = engine.results(parentA.code, parentB.code)
        expect(engine.results(parentB.code, parentA.code)).toEqual(result)
        expect(result.every((code) => validCodes.has(code))).toBe(true)
      }
    }
  })

  it('applies all PalDB unique combinations', () => {
    for (const combination of paldbData.unique) {
      expect(engine.results(combination.a, combination.b)).toContain(combination.child)
    }
  })

  it('returns only valid parent combinations and breeding paths', () => {
    for (const [parentA, parentB] of engine.parentsFor('HerculesBeetle')) {
      expect(engine.results(parentA, parentB)).toContain('HerculesBeetle')
    }

    const path = engine.path('SheepBall', 'Anubis', false, true)
    expect(path).not.toBeNull()
    let current = path!.start
    for (const step of path!.steps) {
      expect(step.with).not.toBe('Anubis')
      expect(engine.results(current, step.with)).toContain(step.result)
      current = step.result
    }
    expect(current).toBe('Anubis')
  })

  it('separates multi-generation results without duplicates', () => {
    const result = engine.generations(['SheepBall', 'Cat'])
    const allGroups = [...result.generations, result.missing]
    const allCodes = allGroups.flat()
    expect(new Set(allCodes).size).toBe(allCodes.length)
    expect(allCodes.every((code) => engine.byCode.has(code))).toBe(true)
  })
})
