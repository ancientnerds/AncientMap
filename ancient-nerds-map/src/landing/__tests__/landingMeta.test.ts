import { describe, expect, it } from 'vitest'

import { landingMeta, renderHead, sitesShort } from '../../seo/meta'
import type { LandingRoute } from '../../types/anRoute'

const route: LandingRoute = {
  type: 'landing',
  stats: { sites: 1_759_673, stories: 3189, journals: 23, papers: 24 },
  journals: null,
  papers: null,
}

describe('sitesShort', () => {
  it('floors to one decimal so the count never overstates the database', () => {
    expect(sitesShort(1_759_673)).toBe('1.7M')
    expect(sitesShort(2_000_000)).toBe('2M')
    expect(sitesShort(999_999)).toBe('0.9M')
  })
})

describe('landingMeta', () => {
  const m = landingMeta(route)

  it('carries the site count in title and description', () => {
    expect(m.title).toBe('Interactive Archaeological Map | Explore 1.7M+ Ancient Sites')
    expect(m.description).toContain('1.7 million archaeological sites')
    expect(m.canonical).toBe('https://ancientnerds.com/')
  })

  it('renders exactly one title with the brand suffix and one canonical', () => {
    const head = renderHead(m)
    expect(head.match(/<title>/g)).toHaveLength(1)
    expect(head).toContain('Explore 1.7M+ Ancient Sites | Ancient Nerds</title>')
    expect(head.match(/<link rel="canonical"/g)).toHaveLength(1)
    expect(head).toContain('/landing/og-image.png')
  })
})
