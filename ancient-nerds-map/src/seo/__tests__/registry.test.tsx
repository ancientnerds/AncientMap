import { describe, expect, it } from 'vitest'

import { ROUTE_TYPES, registry } from '../registry'

describe('registry', () => {
  it('kennt genau die 9 indexierten Seitentypen', () => {
    expect([...ROUTE_TYPES].sort()).toEqual(
      [
        'article',
        'articleIndex',
        'country',
        'research',
        'researchIndex',
        'site',
        'sitesIndex',
        'story',
        'storyArchive',
      ].sort(),
    )
  })

  it('hat für jeden Typ Komponente und meta()', () => {
    for (const type of ROUTE_TYPES) {
      expect(registry[type].Component, type).toBeTypeOf('function')
      expect(registry[type].meta, type).toBeTypeOf('function')
    }
  })
})
