import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PalChip from '@/components/breeding/PalChip.vue'
import { emptyChecks, progressSchema } from '@/types/progress'

describe('progress contract', () => {
  it('hydrates missing preferences while preserving deletions', () => {
    const payload = progressSchema.parse({
      version: 2,
      revision: 4,
      updatedAt: '2026-09-16T00:00:00Z',
      checks: { ...emptyChecks(), effigies: { ativo: true } },
      breedOwned: {},
      prefs: {},
    })
    expect(payload.checks.effigies).toEqual({ ativo: true })
    expect(payload.checks.alphas).toEqual({})
    expect(payload.prefs.sidebarWidth).toBe(320)
    expect(payload.cake).toBeUndefined()
  })

  it('preserves cake calculator state in the progress payload', () => {
    const payload = progressSchema.parse({
      version: 2,
      revision: 5,
      updatedAt: '2026-09-19T00:00:00Z',
      checks: emptyChecks(),
      breedOwned: {},
      prefs: {},
      cake: {
        recipe: 'mushroom',
        gold: 12000,
        target: 40,
        prices: { wheat: 59, berry: 42 },
        stock: { flour: 12, honey: 3 },
      },
    })
    expect(payload.cake?.recipe).toBe('mushroom')
    expect(payload.cake?.gold).toBe(12000)
    expect(payload.cake?.stock.flour).toBe(12)
  })
})

describe('PalChip', () => {
  it('emits a toggle event when interactive', async () => {
    const wrapper = mount(PalChip, {
      props: {
        interactive: true,
        owned: true,
        pal: {
          code: 'lamball',
          name: 'Lamball',
          id: '001',
          rank: 10,
          ignoreCombi: false,
          mutation: false,
          male: '',
          female: '',
          icon: 'https://cdn.paldb.cc/image/lamball.webp',
          order: 1,
        },
      },
    })
    expect(wrapper.get('img').attributes('src')).toContain('/map-icon?src=')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
    expect(wrapper.classes()).toContain('owned')
    await wrapper.get('img').trigger('error')
    expect(wrapper.get('.safe-image-fallback').text()).toBe('LA')
  })
})
