import { describe, expect, it } from 'vitest'

import rawBreedData from '../public/breed.json'
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

  it('excludes IgnoreCombi Pals only from ordinary offspring', () => {
    expect(engine.results('slime', 'a')).toEqual(['a'])
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
    expect(engine.results('KingSunfish', 'KendoFrog_Dark')).toEqual(['BirdDragon'])
  })

  it('keeps exclusive offspring out of ordinary rank calculations', () => {
    const uniqueChildren = new Set(paldbData.unique.map((combination) => combination.child))
    for (let first = 0; first < paldbData.pals.length; first += 1) {
      for (let second = first + 1; second < paldbData.pals.length; second += 1) {
        const parentA = paldbData.pals[first]!
        const parentB = paldbData.pals[second]!
        const isUniquePair = paldbData.unique.some(
          (combination) =>
            (combination.a === parentA.code && combination.b === parentB.code) ||
            (combination.a === parentB.code && combination.b === parentA.code),
        )
        if (isUniquePair) continue
        expect(
          engine.results(parentA.code, parentB.code).every((code) => !uniqueChildren.has(code)),
        ).toBe(true)
      }
    }
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


describe('breeding - tie-breaking logic', () => {
  it('returns deterministic result when multiple pals have exact power match', () => {
    // Cria dados de teste onde múltiplos pals têm o mesmo rank
    const testData: BreedData = {
      version: 1,
      source: 'test',
      pals: [
        pal('lowRank', 50),
        pal('exactMatch1', 100),
        pal('exactMatch2', 100),
        pal('exactMatch3', 100),
        pal('highRank', 150),
      ],
      unique: [],
    }
    
    const engine = createBreedingEngine(testData)
    
    // Quando power = 100, deve escolher um dos exact matches de forma determinística
    // Como todos têm rank = 100, a lógica de desempate por maior rank escolhe o último na lista
    const result1 = engine.childrenFor([100])
    const result2 = engine.childrenFor([100])
    const result3 = engine.childrenFor([100])
    
    // Resultados devem ser idênticos (determinístico)
    expect(result1).toEqual(result2)
    expect(result2).toEqual(result3)
    
    // Deve retornar um dos pals com rank = 100
    expect([100]).toContain(testData.pals.find(p => p.code === result1[0])?.rank)
  })

  it('prefers higher rank when distance is tied', () => {
    // Cria cenário onde dois pals estão equidistantes do power alvo
    const testData: BreedData = {
      version: 1,
      source: 'test',
      pals: [
        pal('lower', 90),   // distância = 10 do power 100
        pal('higher', 110), // distância = 10 do power 100
      ],
      unique: [],
    }
    
    const engine = createBreedingEngine(testData)
    
    // Com power = 100, ambos estão a distância 10
    // Deve escolher 'higher' (rank 110) por ter maior rank
    const result = engine.childrenFor([100])
    expect(result).toEqual(['higher'])
  })

  it('handles edge case with power = 0', () => {
    const testData: BreedData = {
      version: 1,
      source: 'test',
      pals: [
        pal('zero', 0),
        pal('one', 1),
        pal('ten', 10),
      ],
      unique: [],
    }
    
    const engine = createBreedingEngine(testData)
    
    // Com power = 0, deve escolher o pal com rank = 0
    const result = engine.childrenFor([0])
    expect(result).toEqual(['zero'])
  })

  it('consistently selects same pal across multiple calls', () => {
    // Dados mais realistas com muitos pals
    const testData: BreedData = {
      version: 1,
      source: 'test',
      pals: Array.from({ length: 20 }, (_, i) => pal(`pal${i}`, i * 10)),
      unique: [],
    }
    
    const engine = createBreedingEngine(testData)
    
    // Chama childrenFor múltiplas vezes com mesmo power
    const results = Array.from({ length: 10 }, () => engine.childrenFor([75]))
    
    // Todos os resultados devem ser idênticos
    const firstResult = results[0]
    expect(results.every(r => JSON.stringify(r) === JSON.stringify(firstResult))).toBe(true)
  })
})
