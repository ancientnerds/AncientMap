/**
 * App keeps its own SiteData copies in React state, so the detail fields that
 * arrive after the globe payload have to be merged there as well. The merge
 * must not disturb what is already on screen: sites without new details keep
 * their object (memo and tooltip identity), changed sites keep their
 * `coordinates` array (the search fly-to compares it by reference), and no
 * site is added or dropped (sites appended by the API search and admin edits
 * live only in App state).
 *
 * The popup paths that open from bulk data (`withSiteDetails`) wait for the
 * same detail load instead of showing a site without its description.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DataStore } from '../DataStore'
import { mergeSiteDetails, loadSiteDetails, withSiteDetails, fetchSites, type SiteData, type SiteDetails } from '../sites'
import { OfflineStorage } from '../../services/OfflineStorage'

function site(id: string, extra: Partial<SiteData> = {}): SiteData {
  return {
    id,
    title: id.toUpperCase(),
    location: 'Greece',
    category: 'Temple',
    period: 'Iron Age',
    periodStart: -500,
    description: '',
    sourceId: 'ancient_nerds',
    coordinates: [20, 10],
    ...extra,
  }
}

function details(extra: Partial<SiteDetails> = {}): SiteDetails {
  return {
    description: '',
    cardDescription: undefined,
    image: undefined,
    sourceUrl: undefined,
    altNames: undefined,
    bestWikiUrl: undefined,
    sourceLanguage: undefined,
    referenceLinks: undefined,
    descriptionCitations: undefined,
    ...extra,
  }
}

describe('mergeSiteDetails', () => {
  it('keeps unchanged elements identical and the array when nothing changed', () => {
    const prev = [site('a'), site('b')]
    expect(mergeSiteDetails(prev, new Map())).toBe(prev)
    expect(mergeSiteDetails(prev, new Map([['a', details()]]))).toBe(prev)
  })

  it('replaces changed elements with new objects that keep the same coordinates array', () => {
    const a = site('a')
    const b = site('b')
    const prev = [a, b]
    const next = mergeSiteDetails(prev, new Map([['a', details({ description: 'A temple', image: 'https://img/a.jpg' })]]))

    expect(next).not.toBe(prev)
    expect(next[0]).not.toBe(a)
    expect(next[0]).toMatchObject({ id: 'a', title: 'A', description: 'A temple', image: 'https://img/a.jpg' })
    expect(next[0].coordinates).toBe(a.coordinates)
    expect(next[1]).toBe(b)
  })

  it('never adds or drops a site', () => {
    const appended = site('from-api-search', { sourceId: 'pleiades' })
    const prev = [site('a'), appended]
    const next = mergeSiteDetails(prev, new Map([
      ['a', details({ description: 'x' })],
      ['unknown', details({ description: 'y' })],
    ]))
    expect(next.map(s => s.id)).toEqual(['a', 'from-api-search'])
    expect(next[1]).toBe(appended)
  })
})

describe('the singleton detail path', () => {
  const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response

  beforeEach(() => {
    vi.stubGlobal('navigator', { onLine: true })
    vi.spyOn(OfflineStorage, 'isOfflineEnabled').mockResolvedValue(false)
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.includes('/sources/')) return json({ sources: [{ id: 'ancient_nerds', name: 'AN', color: '#fff', count: 1 }] })
      if (url.includes('fields=globe')) {
        return json({ count: 1, dataSource: 'postgres', sites: [{ id: 'a', n: 'Alpha', la: 10, lo: 20, s: 'ancient_nerds', t: 'Temple', p: -500 }] })
      }
      return json({
        count: 1, dataSource: 'postgres',
        sites: [{ id: 'a', n: 'Alpha', la: 10, lo: 20, s: 'ancient_nerds', t: 'Temple', p: -500, d: 'On a hill', rf: [{ u: 'https://r', t: 'R', d: 'r', k: 'web' }] }],
      })
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('starts slim, then merges the fetched details and opens bulk popups with them', async () => {
    const [alpha] = await fetchSites('globe')
    expect(alpha).toMatchObject({ id: 'a', title: 'Alpha', description: '', coordinates: [20, 10] })
    expect(DataStore.detailsReady).toBe(false)

    // A popup opened from the bulk site waits for (and starts) the detail load.
    const opened = await withSiteDetails(alpha)
    expect(opened).toMatchObject({ id: 'a', title: 'Alpha', description: 'On a hill' })
    expect(opened.referenceLinks).toEqual([{ url: 'https://r', title: 'R', domain: 'r', kind: 'web' }])
    expect(opened.coordinates).toBe(alpha.coordinates)

    const byId = await loadSiteDetails()
    expect(byId.get('a')?.description).toBe('On a hill')
    const merged = mergeSiteDetails([alpha], byId)
    expect(merged[0]).toMatchObject({ description: 'On a hill' })
    expect(merged[0].coordinates).toBe(alpha.coordinates)

    // A second caller (StrictMode's second effect run) gets the same details, so
    // merging them again changes nothing and re-renders nothing.
    expect(await loadSiteDetails()).toBe(byId)
    expect(mergeSiteDetails(merged, await loadSiteDetails())).toBe(merged)

    // A site the store does not know (e.g. from the API search) opens as it is.
    const stranger = site('stranger', { sourceId: 'pleiades', description: 'kept' })
    await expect(withSiteDetails(stranger)).resolves.toBe(stranger)
  })
})
