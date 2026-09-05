/**
 * The homepage hub lists are static HTML built at build time from
 * src/data/hubs.snapshot.json (vite.config.ts → landingHubs). This is the
 * pure builder: it must escape text, keep the snapshot's order, and refuse
 * to build from an empty snapshot instead of shipping an empty section.
 */

import { describe, expect, it } from 'vitest'

import { countryLinksHtml, paperLinksHtml, pickSnapshotPath } from '../hubsHtml'

describe('countryLinksHtml', () => {
  it('one link per country with the site count, in snapshot order', () => {
    const html = countryLinksHtml([
      { country: 'England', path: '/sites/england', sites: 1053 },
      { country: 'Türkiye', path: '/sites/türkiye', sites: 218 },
    ])
    expect(html).toBe(
      '<a href="/sites/england">England <span>1053</span></a>' +
        '<a href="/sites/türkiye">Türkiye <span>218</span></a>',
    )
  })

  it('escapes markup in names', () => {
    const html = countryLinksHtml([{ country: 'A & B <x>', path: '/sites/a-b', sites: 1 }])
    expect(html).toContain('A &amp; B &lt;x&gt;')
    expect(html).not.toContain('<x>')
  })

  it('throws on an empty snapshot rather than rendering nothing', () => {
    expect(() => countryLinksHtml([])).toThrow(/snapshot/)
  })
})

describe('paperLinksHtml', () => {
  it('one link per paper, title escaped', () => {
    const html = paperLinksHtml([
      { slug: 'a', path: '/research/a', title: 'Solar "Superflares" & Myth' },
    ])
    expect(html).toBe('<a href="/research/a">Solar &quot;Superflares&quot; &amp; Myth</a>')
  })

  it('throws on an empty snapshot', () => {
    expect(() => paperLinksHtml([])).toThrow(/snapshot/)
  })
})

describe('pickSnapshotPath', () => {
  it('the first existing candidate wins (pipeline copy before committed baseline)', () => {
    const exists = (p: string) => p.endsWith('public/data/hubs.snapshot.json') || p.endsWith('src/data/hubs.snapshot.json')
    expect(pickSnapshotPath(['/x/public/data/hubs.snapshot.json', '/x/src/data/hubs.snapshot.json'], exists))
      .toBe('/x/public/data/hubs.snapshot.json')
  })

  it('falls through to the committed baseline when the pipeline copy is absent', () => {
    const exists = (p: string) => p.endsWith('src/data/hubs.snapshot.json')
    expect(pickSnapshotPath(['/x/public/data/hubs.snapshot.json', '/x/src/data/hubs.snapshot.json'], exists))
      .toBe('/x/src/data/hubs.snapshot.json')
  })

  it('throws, naming both candidates, when neither exists', () => {
    expect(() => pickSnapshotPath(['/a', '/b'], () => false)).toThrow(/\/a, \/b/)
  })
})
