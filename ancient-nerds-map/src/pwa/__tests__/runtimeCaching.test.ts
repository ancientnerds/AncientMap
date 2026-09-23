/**
 * The service worker's runtime caching rules (vite.config.ts → VitePWA →
 * workbox). workbox-routing's RegExpRoute runs `regExp.exec(url.href)` on the
 * FULL href, query string included, takes the FIRST registered route that
 * matches, and accepts a cross-origin match only at index 0
 * (node_modules/workbox-routing/RegExpRoute.js). `ruleFor` below does the same,
 * so these tests read the table the way the worker will.
 */

import { describe, expect, it } from 'vitest'

import { API_SITES_CACHE_NAMES, RUNTIME_CACHING } from '../runtimeCaching'

const ORIGIN = 'https://ancientnerds.com'

type Rule = (typeof RUNTIME_CACHING)[number]

function patternOf(rule: Rule): RegExp {
  if (!(rule.urlPattern instanceof RegExp)) throw new Error('every urlPattern must be a RegExp')
  return rule.urlPattern
}

/** Index of the rule workbox would use for this URL, or -1. */
function ruleFor(url: string): number {
  const href = new URL(url, ORIGIN).href
  const sameOrigin = new URL(href).origin === ORIGIN
  return RUNTIME_CACHING.findIndex(rule => {
    const match = patternOf(rule).exec(href)
    if (!match) return false
    return sameOrigin || match.index === 0
  })
}

function ruleNamed(cacheName: string, handler: string): Rule {
  const found = RUNTIME_CACHING.filter(r => r.options?.cacheName === cacheName && r.handler === handler)
  expect(found).toHaveLength(1)
  return found[0]
}

describe('RUNTIME_CACHING', () => {
  it('uses RegExp patterns only (workbox-build serialises them into sw.js)', () => {
    for (const rule of RUNTIME_CACHING) expect(rule.urlPattern).toBeInstanceOf(RegExp)
  })

  it('caches the .webp basemaps CacheFirst in "basemaps", also with a query string', () => {
    const rule = ruleNamed('basemaps', 'CacheFirst')
    const index = RUNTIME_CACHING.indexOf(rule)
    for (const url of [
      '/data/basemaps/gray_dark_med.webp',
      '/data/basemaps/gray_dark_med.webp?_v=abc',
      '/data/basemaps/satellite_high.webp',
      '/data/basemaps/old_tile.png',
      '/data/basemaps/old_tile.jpg?x=1',
    ]) {
      expect(ruleFor(url), url).toBe(index)
    }
    expect(rule.options?.expiration).toEqual({ maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 })
    expect(rule.options?.cacheableResponse).toEqual({ statuses: [0, 200] })
  })

  it('caches the hashed globe layer files CacheFirst, before the generic layer rule', () => {
    const globe = ruleNamed('vector-layers', 'CacheFirst')
    const generic = ruleNamed('vector-layers', 'StaleWhileRevalidate')
    const globeIndex = RUNTIME_CACHING.indexOf(globe)
    expect(globeIndex).toBeLessThan(RUNTIME_CACHING.indexOf(generic))
    for (const url of [
      '/data/layers/globe/coast_start.1a2b3c4d.json',
      '/data/layers/globe/borders_detail.0f9e8d7c.json',
      '/data/layers/globe/coast_detail.1a2b3c4d.json?x=1',
    ]) {
      expect(ruleFor(url), url).toBe(globeIndex)
    }
    expect(globe.options?.expiration).toEqual({ maxEntries: 16 })
    expect(globe.options?.cacheableResponse).toEqual({ statuses: [0, 200] })
    // A layer file outside globe/ still goes to the generic rule.
    expect(ruleFor('/data/layers/other.json')).toBe(RUNTIME_CACHING.indexOf(generic))
  })

  // The globe's own payloads (DataStore, source=ancient_nerds), the opt-in
  // sources (SourceLoader, DownloadManager) and the small per-site/search
  // answers each get their own cache, so no kind can evict another's entries.
  const GLOBE_PAYLOADS = [
    '/api/sites/all?limit=100000&source=ancient_nerds&fields=globe&_v=abc',
    '/api/sites/all?limit=100000&source=ancient_nerds&_v=abc',
    '/api/sites/all?limit=100000&source=ancient_nerds&fields=all&_v=abc',
    '/api/sites/all?source=ancient_nerds&limit=100000',
  ]
  const SOURCE_PAYLOADS = [
    '/api/sites/all?source=pleiades&limit=100000&_v=abc',
    '/api/sites/all?source=ancient_nerds_extra&limit=100000&_v=abc',
    '/api/sites/all?source=historic_england&limit=100000',
  ]
  const SMALL_SITE_ANSWERS = [
    '/api/sites/123',
    '/api/sites/123/alternates',
    '/api/sites/search?q=giza&limit=20',
    '/api/sites/search?q=ancient_nerds&source=ancient_nerds',
  ]

  it.each([
    ['api-sites-globe', GLOBE_PAYLOADS, { maxEntries: 6 }],
    ['api-sites-sources', SOURCE_PAYLOADS, { maxEntries: 32 }],
    ['api-sites', SMALL_SITE_ANSWERS, { maxEntries: 200 }],
  ] as const)('routes to %s NetworkFirst with a 10 s timeout and a bound', (cacheName, urls, expiration) => {
    const rule = ruleNamed(cacheName, 'NetworkFirst')
    for (const url of urls) expect(ruleFor(url), url).toBe(RUNTIME_CACHING.indexOf(rule))
    expect(rule.options).toEqual({
      cacheName,
      networkTimeoutSeconds: 10,
      cacheableResponse: { statuses: [0, 200] },
      expiration,
    })
  })

  it('lists every api/sites cache in API_SITES_CACHE_NAMES (admin save clears them all)', () => {
    const fromTable = RUNTIME_CACHING.map(r => r.options?.cacheName).filter(n => n?.startsWith('api-sites'))
    expect([...API_SITES_CACHE_NAMES].sort()).toEqual([...fromTable].sort())
  })

  // workbox-expiration keeps, per cacheName, the newest `maxEntries` URLs it
  // wrote (CacheTimestampsModel.expireEntries); NetworkFirst writes on every
  // successful fetch. Replays a heavy session plus the next deploy's visit.
  it('keeps the globe payload of the current build through a heavy session', () => {
    const written = new Map<string, string[]>()
    const write = (url: string) => {
      const rule = RUNTIME_CACHING[ruleFor(url)]
      const cacheName = rule.options!.cacheName!
      const max = rule.options!.expiration!.maxEntries!
      const urls = (written.get(cacheName) ?? []).filter(u => u !== url)
      urls.push(url)
      written.set(cacheName, urls.slice(-max))
    }
    const visit = (v: string) => {
      write(`/api/sites/all?limit=100000&source=ancient_nerds&fields=globe&_v=${v}`)
      write(`/api/sites/all?limit=100000&source=ancient_nerds&fields=all&_v=${v}`)
      for (let i = 0; i < 40; i++) {
        write(`/api/sites/${i}`)
        write(`/api/sites/${i}/alternates`)
        write(`/api/sites/search?q=query${i}`)
      }
      for (let i = 0; i < 20; i++) write(`/api/sites/all?source=src${i}&limit=100000&_v=${v}`)
    }
    visit('build1')
    visit('build2')
    const kept = [...written.values()].flat()
    expect(kept).toContain('/api/sites/all?limit=100000&source=ancient_nerds&fields=globe&_v=build2')
    expect(kept).toContain('/api/sites/all?limit=100000&source=ancient_nerds&fields=all&_v=build2')
    expect(kept).toContain('/api/sites/all?limit=100000&source=ancient_nerds&fields=globe&_v=build1')
  })

  // The table of infra.md §1.1 (the rules as they were before this change).
  // Unchanged rules keep their exact pattern; the two that were `$`-anchored
  // (historical, generic layers) keep what they matched and now also match
  // the same URL with a query string.
  const EXISTING: Array<{ source: string | null; handler: string; cacheName: string; urls: string[] }> = [
    { source: '\\/api\\/sites\\/', handler: 'NetworkFirst', cacheName: 'api-sites', urls: ['/api/sites/123'] },
    { source: '\\/api\\/sources', handler: 'StaleWhileRevalidate', cacheName: 'api-sources', urls: ['/api/sources/?_v=dev'] },
    {
      source: null,
      handler: 'CacheFirst',
      cacheName: 'historical-data',
      urls: ['/data/historical/roman/100.geojson', '/data/historical/roman/100.geojson?x=1'],
    },
    {
      source: null,
      handler: 'StaleWhileRevalidate',
      cacheName: 'vector-layers',
      urls: ['/data/layers/paleo.json', '/data/layers/paleo.json?x=1'],
    },
    { source: '\\/data\\/sources\\.json', handler: 'StaleWhileRevalidate', cacheName: 'static-data', urls: ['/data/sources.json'] },
    {
      source: '^https:\\/\\/upload\\.wikimedia\\.org\\/',
      handler: 'NetworkFirst',
      cacheName: 'external-images',
      urls: ['https://upload.wikimedia.org/wikipedia/commons/a/ab/X.jpg'],
    },
    {
      source: '^https:\\/\\/raw\\.githubusercontent\\.com\\/nvkelso\\/natural-earth-vector\\/',
      handler: 'CacheFirst',
      cacheName: 'natural-earth',
      urls: ['https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/x.geojson'],
    },
  ]

  it.each(EXISTING)('keeps the $cacheName rule ($handler)', ({ source, handler, cacheName, urls }) => {
    const rule = ruleNamed(cacheName, handler)
    if (source !== null) expect(patternOf(rule).source).toBe(source)
    for (const url of urls) expect(ruleFor(url), url).toBe(RUNTIME_CACHING.indexOf(rule))
  })

  it('keeps the options of the rules it does not change', () => {
    expect(ruleNamed('external-images', 'NetworkFirst').options).toEqual({
      cacheName: 'external-images',
      networkTimeoutSeconds: 5,
      cacheableResponse: { statuses: [0, 200] },
      expiration: { maxEntries: 1000, maxAgeSeconds: 60 * 60 * 24 * 30 },
    })
    expect(ruleNamed('natural-earth', 'CacheFirst').options).toEqual({
      cacheName: 'natural-earth',
      cacheableResponse: { statuses: [0, 200] },
      expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 * 24 * 365 },
    })
    for (const [cacheName, handler] of [
      ['api-sources', 'StaleWhileRevalidate'],
      ['historical-data', 'CacheFirst'],
      ['vector-layers', 'StaleWhileRevalidate'],
      ['static-data', 'StaleWhileRevalidate'],
    ]) {
      expect(ruleNamed(cacheName, handler).options).toEqual({ cacheName, cacheableResponse: { statuses: [0, 200] } })
    }
  })

  it('has exactly the eleven rules (seven kept, basemaps fixed, globe layers and two sites payload caches new)', () => {
    expect(RUNTIME_CACHING.map(r => `${r.options?.cacheName}:${r.handler}`)).toEqual([
      'api-sites-globe:NetworkFirst',
      'api-sites-sources:NetworkFirst',
      'api-sites:NetworkFirst',
      'api-sources:StaleWhileRevalidate',
      'basemaps:CacheFirst',
      'historical-data:CacheFirst',
      'vector-layers:CacheFirst',
      'vector-layers:StaleWhileRevalidate',
      'static-data:StaleWhileRevalidate',
      'external-images:NetworkFirst',
      'natural-earth:CacheFirst',
    ])
  })

  it('never anchors a same-origin pattern at the end without allowing a query string', () => {
    for (const rule of RUNTIME_CACHING) {
      const pattern = patternOf(rule)
      if (!pattern.source.includes('$')) continue
      expect(pattern.source, pattern.source).toMatch(/\(\\\?\|\$\)$/)
    }
  })
})
