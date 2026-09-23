/**
 * A focus deep link (#focus= on every site and story page, ?focus= from
 * SiteCard) searches for its site's title as soon as the sites arrive. On the
 * slim globe payload that search would wait for the details (every dot plus
 * "Searching..." until they land), so a focus load takes the full payload and
 * its details count as ready at once: the first frame shows only the matches,
 * as it did before the globe payload existed.
 *
 * Node 20 (CI) has no global `navigator`: stubbed per test.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DataStore } from '../DataStore'
import { fetchSites, globeSiteFields } from '../sites'
import { OfflineStorage } from '../../services/OfflineStorage'

const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response

let fetchMock: { mock: { calls: unknown[][] } }

beforeEach(() => {
  vi.stubGlobal('navigator', { onLine: true })
  vi.spyOn(OfflineStorage, 'isOfflineEnabled').mockResolvedValue(false)
  fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/sources/')) return json({ sources: [{ id: 'ancient_nerds', name: 'AN', color: '#fff', count: 1 }] })
    if (url.includes('fields=all')) {
      return json({ count: 1, dataSource: 'postgres', sites: [{ id: 'a', n: 'Alpha', la: 10, lo: 20, s: 'ancient_nerds', d: 'On a hill' }] })
    }
    throw new Error(`unexpected fetch ${url}`)
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('globeSiteFields', () => {
  it('starts a plain globe load on the globe payload', () => {
    expect(globeSiteFields(null)).toBe('globe')
  })

  it('starts a focus deep link on the full payload, with its details ready at once', async () => {
    expect(globeSiteFields('a')).toBe('all')

    const [alpha] = await fetchSites(globeSiteFields('a'))

    expect(DataStore.detailsReady).toBe(true)
    expect(alpha).toMatchObject({ id: 'a', title: 'Alpha', description: 'On a hill' })
    const sitesAll = fetchMock.mock.calls.map(([input]) => String(input)).filter(url => url.includes('/sites/all?'))
    expect(sitesAll).toHaveLength(1)
    // The service worker's api-sites-globe rule keys on this query shape.
    expect(sitesAll[0]).toMatch(/\/sites\/all\?limit=100000&source=ancient_nerds&fields=all&_v=/)
  })
})
