/**
 * 1:1-Übersetzung von tests/pipeline/test_seo_country_extras.py::TestTypeSections
 * (plus die _period_span-Fälle aus TestCountryPageHead) nach Vitest — die
 * Python-Tests bleiben bestehen, bis pipeline/seo_pages.py stirbt (Task 16).
 */

import { describe, expect, it } from 'vitest'

import { MAX_TYPE_SECTIONS, OTHER_TYPES_LABEL, periodSpan, typeSections } from '../grouping'
import type { CountrySite } from '../../types/anRoute'

function site(name: string, over: Partial<CountrySite> = {}): CountrySite {
  return {
    name,
    path: `/sites/turkiye/${name.toLowerCase()}-abc12345`,
    description: `${name} is a place worth visiting.`,
    site_type: 'Temple complex',
    period_name: '500 BC - 1 AD',
    period_start: -500,
    thumbnail_url: '/data/images/wiki/abc12345/hero.webp',
    ...over,
  }
}

describe('typeSections', () => {
  it('gruppiert nach Typ, größte zuerst', () => {
    const sections = typeSections([
      site('A', { site_type: 'Theatre' }),
      site('B', { site_type: 'Barrow' }),
      site('C', { site_type: 'Barrow' }),
    ])
    expect(sections.map(s => s.label)).toEqual(['Barrow', 'Theatre'])
    expect(sections[0].sites.map(s => s.name)).toEqual(['B', 'C'])
  })

  it('der Long Tail landet in einer Sektion', () => {
    // England trägt 30+ Typen; eine Sektion je Typ würde die Liste begraben.
    const sites = Array.from({ length: MAX_TYPE_SECTIONS + 5 }, (_, i) =>
      site(`S${i}`, { site_type: `Type${String(i).padStart(2, '0')}` }),
    )
    const sections = typeSections(sites)
    expect(sections).toHaveLength(MAX_TYPE_SECTIONS + 1)
    expect(sections[sections.length - 1].label).toBe(OTHER_TYPES_LABEL)
    expect(sections[sections.length - 1].sites).toHaveLength(5)
  })

  it('jede Site landet in genau einer Sektion', () => {
    const sites = Array.from({ length: 60 }, (_, i) =>
      site(`S${i}`, { site_type: `Type${String(i % 20).padStart(2, '0')}` }),
    )
    const placed = typeSections(sites)
      .flatMap(s => s.sites)
      .map(s => s.name)
    expect([...placed].sort()).toEqual(sites.map(s => s.name).sort())
  })

  it('typlose Sites gehen nach Other', () => {
    const sections = typeSections([site('A', { site_type: null })])
    expect(sections).toEqual([
      { label: OTHER_TYPES_LABEL, sites: [site('A', { site_type: null })] },
    ])
  })
})

describe('periodSpan', () => {
  // Sollwerte aus TestCountryPageHead — dort über den gerenderten Head geprüft.
  it('spannt vom frühesten zum spätesten Startjahr', () => {
    expect(
      periodSpan([
        site('A', { period_start: -9000 }),
        site('B', { period_start: -500 }),
        site('C', { period_start: 1964 }),
      ]),
    ).toBe('9000 BC – 1964 AD')
  })

  it('kollabiert, wenn alle Sites ein Jahr teilen', () => {
    expect(periodSpan([site('A'), site('B')])).toBe('500 BC')
  })

  it('undatierte Sites lassen die Spanne leer', () => {
    expect(periodSpan([site('A', { period_start: null, period_name: null })])).toBe('')
  })

  it('das Jahr 0 zählt als datiert', () => {
    // Python: `is not None` — 0 ist ein gültiges Startjahr, kein Fehlen.
    expect(periodSpan([site('A', { period_start: 0 })])).toBe('0 AD')
  })
})
