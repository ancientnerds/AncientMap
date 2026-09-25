/**
 * The detail load covers only the default source (`source=ancient_nerds`).
 * A popup for any other site - one appended by the 'All sources' API search,
 * or from an opt-in source SourceLoader added - has nothing to wait for, so
 * withSiteDetails() hands it back at once, without starting the detail load
 * and even when that load has failed. Only a default-source site waits, and
 * is refused when its details failed.
 *
 * Node 20 (CI) has no global `navigator`: stubbed per test.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchSites, addSourceSites, withSiteDetails, type SiteData } from '../sites'
import { OfflineStorage } from '../../services/OfflineStorage'

const json = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response

let fetchMock: { mock: { calls: unknown[][] } }

function detailCalls(): string[] {
  return fetchMock.mock.calls.map(([input]) => String(input)).filter(url => url.includes('fields=all'))
}

function site(id: string, sourceId: string, description = ''): SiteData {
  return {
    id, title: id, location: '', category: 'Temple', period: 'Unknown', periodStart: null,
    description, sourceId, coordinates: [0, 0],
  }
}

beforeEach(() => {
  vi.stubGlobal('navigator', { onLine: true })
  vi.spyOn(OfflineStorage, 'isOfflineEnabled').mockResolvedValue(false)
  fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/sources/')) return json({ sources: [{ id: 'ancient_nerds', name: 'AN', color: '#fff', count: 1 }] })
    if (url.includes('fields=globe')) {
      return json({ count: 1, dataSource: 'postgres', sites: [{ id: 'a', n: 'Alpha', la: 10, lo: 20, s: 'ancient_nerds' }] })
    }
    if (url.includes('fields=all')) return json({ error: 'unavailable' }, 503)
    throw new Error(`unexpected fetch ${url}`)
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('withSiteDetails for sites the detail load does not cover', () => {
  it('opens them at once and refuses only a default-source site whose details failed', async () => {
    const [alpha] = await fetchSites('globe')
    addSourceSites('pleiades', [{ id: 'p1', name: 'P1', lat: 1, lon: 2, sourceId: 'pleiades', description: 'From Pleiades' }])

    // An opt-in source's site the store holds, and an API search result it does not.
    const optIn = site('p1', 'pleiades', 'From Pleiades')
    const fromSearch = site('stranger', 'ancient_nerds', 'kept')
    await expect(withSiteDetails(optIn)).resolves.toBe(optIn)
    await expect(withSiteDetails(fromSearch)).resolves.toBe(fromSearch)
    // Neither waited for (or started) the default source's detail load.
    expect(detailCalls()).toHaveLength(0)

    await expect(withSiteDetails(alpha)).rejects.toThrow('Failed to load site details: HTTP 503')
    // After the failure the other sources still open.
    await expect(withSiteDetails(optIn)).resolves.toBe(optIn)
    expect(detailCalls()).toHaveLength(1)
  })
})
