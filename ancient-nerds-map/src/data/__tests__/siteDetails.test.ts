/**
 * The globe starts on the slim `fields=globe` payload (id, name, position,
 * source, type, period, country) and fetches the detail fields afterwards.
 * DataStore.loadSiteDetails() is that second step: one fetch of the full
 * payload, merged onto the sites it already holds, never moving or adding a
 * dot. SearchPage keeps the full payload from the start (`initialize()`), and
 * offline mode has no network to fetch them from (its records carry whatever
 * DownloadManager downloaded, normally the full payload), so both count as
 * ready at once.
 *
 * Node 20 (CI) has no global `navigator`, and OfflineStorage opens IndexedDB,
 * which neither node nor jsdom has: both are stubbed per test.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DataStoreClass } from '../DataStore'
import { OfflineStorage, type DownloadState } from '../../services/OfflineStorage'

const SOURCES = { sources: [{ id: 'ancient_nerds', name: 'Ancient Nerds', color: '#fff', count: 2, enabledByDefault: true }] }

/** fields=globe: only the keys the dots draw; a pinned snapshot may lack t, p, pn and c. */
const GLOBE_SITES = {
  count: 2,
  dataSource: 'postgres',
  sites: [
    { id: 'a', n: 'Alpha', la: 10, lo: 20, s: 'ancient_nerds', t: 'Temple', p: -500, pn: 'Iron Age', c: 'Greece' },
    { id: 'b', n: 'Beta', la: 30, lo: 40, s: 'ancient_nerds' },
  ],
}

/** fields=all: the same sites with their details, plus a site the globe never saw. */
const FULL_SITES = {
  count: 3,
  dataSource: 'postgres',
  sites: [
    {
      id: 'a', n: 'Alpha (renamed)', la: 11, lo: 21, s: 'ancient_nerds', t: 'Tomb', p: -900, pn: 'Bronze Age', c: 'Italy',
      d: 'A temple on a hill', cd: 'Card text', i: 'https://img/a.jpg', u: 'https://src/a',
      rf: [{ u: 'https://ref/a', t: 'Ref A', d: 'ref', k: 'wiki' }],
      dc: [{ n: 1, url: 'https://cite/a', title: 'Cite A', domain: 'cite' }],
    },
    { id: 'b', n: 'Beta', la: 30, lo: 40, s: 'ancient_nerds', d: 'Only a description' },
    { id: 'new', n: 'Newcomer', la: 1, lo: 2, s: 'ancient_nerds', d: 'Arrived between the two reads' },
  ],
}

const json = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response

let fetchMock: { mock: { calls: unknown[][] } }

/** Answers /sources/ and /sites/all by URL; `fields=globe` gets the slim payload. */
function routeFetch(options: { detailsStatus?: number } = {}) {
  fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/sources/')) return json(SOURCES)
    if (url.includes('/sites/all?') && url.includes('fields=globe')) return json(GLOBE_SITES)
    if (url.includes('/sites/all?')) return json(FULL_SITES, options.detailsStatus ?? 200)
    throw new Error(`unexpected fetch ${url}`)
  })
}

function sitesAllCalls(): string[] {
  return fetchMock.mock.calls.map(([input]) => String(input)).filter((url: string) => url.includes('/sites/all?'))
}

beforeEach(() => {
  vi.stubGlobal('navigator', { onLine: true })
  vi.spyOn(OfflineStorage, 'isOfflineEnabled').mockResolvedValue(false)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('DataStore.initialize(fields)', () => {
  it("asks for fields=globe when the globe starts", async () => {
    routeFetch()
    const store = new DataStoreClass()
    await store.initialize('globe')

    const [url] = sitesAllCalls()
    expect(url).toContain('fields=globe')
    // The service worker's api-sites-globe rule keys on this query shape.
    expect(url).toMatch(/\/sites\/all\?limit=100000&source=ancient_nerds&fields=globe&_v=/)
    expect(store.detailsReady).toBe(false)
  })

  it('defaults to the full payload (SearchPage) and counts details as ready', async () => {
    routeFetch()
    const store = new DataStoreClass()
    await store.initialize()

    const [url] = sitesAllCalls()
    expect(url).toContain('fields=all')
    expect(url).not.toContain('fields=globe')
    expect(store.detailsReady).toBe(true)
    expect(store.getSiteById('a')?.description).toBe('A temple on a hill')
  })

  it('treats the keys a pinned snapshot leaves out like null', async () => {
    routeFetch()
    const store = new DataStoreClass()
    await store.initialize('globe')

    const beta = store.getSiteById('b')!
    expect(beta.type).toBeUndefined()
    expect(beta.periodStart).toBeNull()
    expect(beta.period).toBeUndefined()
    expect(beta.location).toBeUndefined()
  })

  it('counts details as ready in offline mode, where there is no network to fetch them', async () => {
    vi.stubGlobal('navigator', { onLine: false })
    vi.spyOn(OfflineStorage, 'isOfflineEnabled').mockResolvedValue(true)
    vi.spyOn(OfflineStorage, 'getDownloadState').mockResolvedValue({
      sources: { ancient_nerds: { cached: true, downloadedAt: '', siteCount: 1 } },
      lastUpdated: '2026-09-01',
    } as unknown as DownloadState)
    // DownloadManager stores the full /sites/all records: period name and description included.
    const offlineSites = [
      { id: 'a', n: 'Alpha', la: 10, lo: 20, s: 'ancient_nerds', pn: 'Iron Age', d: 'Stored offline' },
    ]
    vi.spyOn(OfflineStorage, 'getAllSites').mockResolvedValue(offlineSites)
    fetchMock = vi.spyOn(globalThis, 'fetch')

    const store = new DataStoreClass()
    await store.initialize('globe')

    expect(store.isOffline()).toBe(true)
    expect(store.detailsReady).toBe(true)
    // Mapped like the API payload, so offline uses the stored period name and description.
    expect(store.getSiteById('a')).toMatchObject({ period: 'Iron Age', description: 'Stored offline', periodStart: null })
    await expect(store.loadSiteDetails()).resolves.toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('DataStore.loadSiteDetails()', () => {
  it('fetches the full payload once and merges only detail fields onto known sites', async () => {
    routeFetch()
    const store = new DataStoreClass()
    await store.initialize('globe')
    const alpha = store.getSiteById('a')!

    const [first, second] = await Promise.all([store.loadSiteDetails(), store.loadSiteDetails()])
    await store.loadSiteDetails()

    const detailCalls = sitesAllCalls().filter(url => !url.includes('fields=globe'))
    expect(detailCalls).toHaveLength(1)
    expect(detailCalls[0]).toMatch(/\/sites\/all\?limit=100000&source=ancient_nerds&fields=all&_v=/)
    expect(second).toBe(first)

    // Same object, details assigned in place.
    expect(store.getSiteById('a')).toBe(alpha)
    expect(alpha).toMatchObject({
      description: 'A temple on a hill',
      cardDescription: 'Card text',
      image: 'https://img/a.jpg',
      sourceUrl: 'https://src/a',
      referenceLinks: [{ u: 'https://ref/a', t: 'Ref A', d: 'ref', k: 'wiki' }],
      descriptionCitations: [{ n: 1, url: 'https://cite/a', title: 'Cite A', domain: 'cite' }],
    })
    // The globe fields stay as the dots drew them.
    expect(alpha).toMatchObject({
      name: 'Alpha', lat: 10, lon: 20, type: 'Temple', periodStart: -500, period: 'Iron Age', location: 'Greece',
    })
    // No new dot for a site the globe payload did not have.
    expect(store.getSiteById('new')).toBeUndefined()
    expect(store.getSites().map(s => s.id)).toEqual(['a', 'b'])
    expect(first.map(s => s.id)).toEqual(['a', 'b'])
    expect(store.detailsReady).toBe(true)
  })

  it('resolves at once without a fetch when the full payload came first', async () => {
    routeFetch()
    const store = new DataStoreClass()
    await store.initialize('all')
    const before = sitesAllCalls().length

    await expect(store.loadSiteDetails()).resolves.toEqual([])
    expect(sitesAllCalls()).toHaveLength(before)
  })

  it('rejects with the status when the full payload fails, and does not retry', async () => {
    routeFetch({ detailsStatus: 503 })
    const store = new DataStoreClass()
    await store.initialize('globe')

    await expect(store.loadSiteDetails()).rejects.toThrow('Failed to load site details: HTTP 503')
    await expect(store.loadSiteDetails()).rejects.toThrow('HTTP 503')
    expect(sitesAllCalls().filter(url => url.includes('fields=all'))).toHaveLength(1)
    expect(store.detailsReady).toBe(false)
  })

  it('rejects when called before initialize()', async () => {
    await expect(new DataStoreClass().loadSiteDetails()).rejects.toThrow('before initialize()')
  })
})
