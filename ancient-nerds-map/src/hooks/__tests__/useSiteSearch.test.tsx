/**
 * The globe starts without site descriptions, so a query typed (or set by a
 * focus link) before the details arrive must not answer from half the data:
 * no results, "searching" instead, and no `search` / `search_empty` event with
 * an understated count. Once the details are in, the search answers and the
 * event is sent once, with the real count.
 *
 * `isSearching` also covers the "All sources" API search; it must end when the
 * API has answered, also when the answer is empty (otherwise the globe's
 * results header would read "Searching..." forever).
 *
 * With `widenToAllSources` a query the visitor's own sources cannot answer at
 * all is answered from the whole database, and the results are ordered
 * described sites first: production 2026-10-04 holds 1,595,613 sites with no
 * text at all, and "great zimbabwe" answered with bare names first.
 *
 * @vitest-environment jsdom
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSiteSearch, type UseSiteSearchOptions, type UseSiteSearchReturn } from '../useSiteSearch'
import type { SiteData } from '../../data/sites'

const { track } = vi.hoisted(() => ({ track: vi.fn() }))
vi.mock('../../analytics', () => ({
  track,
  pageType: () => 'globe',
  searchTerm: (q: string) => q,
}))

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const TEMPLE: SiteData = {
  id: 'a',
  title: 'Alpha',
  location: 'Greece',
  category: 'Temple',
  period: 'Iron Age',
  periodStart: -500,
  description: '',
  sourceId: 'ancient_nerds',
  coordinates: [20, 10],
}

const baseOptions = (sites: SiteData[], extra: Partial<UseSiteSearchOptions> = {}): UseSiteSearchOptions => ({
  sites,
  sourceNameMap: {},
  selectedSources: ['ancient_nerds'],
  selectedCategories: [],
  allCategories: [],
  selectedCountries: [],
  allCountries: [],
  ageRange: [-5000, 1500],
  searchAllSources: false,
  applyFiltersToSearch: true,
  detailsReady: true,
  ...extra,
})

let root: Root | null = null
let latest: UseSiteSearchReturn | null = null

function Harness({ options }: { options: UseSiteSearchOptions }) {
  latest = useSiteSearch(options)
  return null
}

function render(options: UseSiteSearchOptions) {
  act(() => {
    root!.render(<Harness options={options} />)
  })
}

function type(query: string) {
  act(() => latest!.setSearchQuery(query))
  act(() => { vi.advanceTimersByTime(200) }) // debounce
}

beforeEach(() => {
  vi.useFakeTimers()
  track.mockClear()
  root = createRoot(document.createElement('div'))
})

afterEach(() => {
  act(() => root!.unmount())
  root = null
  latest = null
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('useSiteSearch while the site details are pending', () => {
  it('answers nothing, reports searching, and sends no search event', () => {
    render(baseOptions([TEMPLE], { detailsReady: false }))
    type('hill')

    expect(latest!.searchResults).toEqual([])
    expect(latest!.isSearching).toBe(true)
    act(() => { vi.advanceTimersByTime(5000) })
    expect(track).not.toHaveBeenCalled()
  })

  it('answers from the details once they arrive and sends one event with the real count', () => {
    render(baseOptions([TEMPLE], { detailsReady: false }))
    type('hill')
    act(() => { vi.advanceTimersByTime(2000) })

    const withDetails = { ...TEMPLE, description: 'A temple on a hill' }
    render(baseOptions([withDetails], { detailsReady: true }))

    expect(latest!.isSearching).toBe(false)
    expect(latest!.searchResults.map(r => r.id)).toEqual(['a'])
    act(() => { vi.advanceTimersByTime(1200) })
    expect(track).toHaveBeenCalledTimes(1)
    expect(track).toHaveBeenCalledWith('search', expect.objectContaining({ q: 'hill', results: 1 }))
  })

  it('without a query nothing is pending', () => {
    render(baseOptions([TEMPLE], { detailsReady: false }))
    expect(latest!.isSearching).toBe(false)
    expect(latest!.searchResults).toEqual([])
  })

  it('searches at once when the details are there from the start', () => {
    render(baseOptions([{ ...TEMPLE, description: 'A temple on a hill' }]))
    type('hill')
    expect(latest!.isSearching).toBe(false)
    expect(latest!.searchResults.map(r => r.id)).toEqual(['a'])
  })
})

describe('useSiteSearch with "All sources"', () => {
  it('stops searching when the API answers with no sites', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ sites: [] }), { status: 200 })))
    render(baseOptions([TEMPLE], { searchAllSources: true }))
    type('zzzz')
    expect(latest!.isSearching).toBe(true)

    // Let the mocked fetch -> json -> setState chain settle (microtasks only).
    await act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve() })
    expect(latest!.isSearching).toBe(false)
    act(() => { vi.advanceTimersByTime(1200) })
    expect(track).toHaveBeenCalledWith('search_empty', expect.objectContaining({ q: 'zzzz', results: 0 }))
  })

  // A 429 from the search limiter (20/min per IP), a 5xx or a network error is
  // no answer: not a finished search with the local preview as its result, and
  // no `search` / `search_empty` event for it.
  it.each([
    ['a rate-limited request', () => new Response(JSON.stringify({ detail: 'Too many requests' }), { status: 429 }), 'HTTP 429'],
    ['a server error', () => new Response('boom', { status: 502 }), 'HTTP 502'],
    ['a network error', () => { throw new TypeError('Failed to fetch') }, 'Failed to fetch'],
  ])('reports %s as a failed search, not as an answer', async (_what, respond, reason) => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => respond()))
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    render(baseOptions([TEMPLE], { searchAllSources: true }))
    type('alpha')
    await act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve() })
    expect(latest!.isSearching).toBe(false)
    expect(latest!.searchError).toBe(`All-sources search failed (${reason}). Try again.`)
    expect(latest!.searchResults).toEqual([]) // not the local preview (Alpha) as the final answer
    act(() => { vi.advanceTimersByTime(5000) })
    expect(track).not.toHaveBeenCalled()
  })

  it('a new query after a failed one searches again and clears the error', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 429 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ sites: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    render(baseOptions([TEMPLE], { searchAllSources: true }))
    type('alph')
    await act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve() })
    expect(latest!.searchError).not.toBe(null)
    type('alpha')
    expect(latest!.searchError).toBe(null)
    expect(latest!.isSearching).toBe(true)
    await act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve() })
    expect(latest!.isSearching).toBe(false)
    expect(latest!.searchError).toBe(null)
  })

  it('treats a 200 without a sites list as a failure (no silent empty answer)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'x' }), { status: 200 })))
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    render(baseOptions([TEMPLE], { searchAllSources: true }))
    type('zzzz')
    await act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve() })
    expect(latest!.isSearching).toBe(false)
    expect(latest!.searchError).toMatch(/^All-sources search failed \(/)
    act(() => { vi.advanceTimersByTime(5000) })
    expect(track).not.toHaveBeenCalled()
  })

  it('is searching again when "All sources" is switched off and on for the same query', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response(JSON.stringify({ sites: [] }), { status: 200 })))
    render(baseOptions([TEMPLE], { searchAllSources: true }))
    type('zzzz')
    await act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve() })
    expect(latest!.isSearching).toBe(false)

    render(baseOptions([TEMPLE], { searchAllSources: false }))
    render(baseOptions([TEMPLE], { searchAllSources: true }))
    expect(latest!.isSearching).toBe(true)
  })
})

describe('useSiteSearch word by word', () => {
  const site = (id: string, title: string, location: string): SiteData => ({ ...TEMPLE, id, title, location })
  const VALLEY = site('valley', 'Valley of the Kings', 'Egypt')
  const GIZA = site('giza', 'Great Pyramid of Giza', 'Egypt')
  const COLLIERY = site('colliery', 'Afan Valley, Upper Workings', 'Wales')

  it('finds the Valley of the Kings for the queries visitors typed (Umami, 2026-09-17..25)', () => {
    render(baseOptions([VALLEY, GIZA, COLLIERY]))
    for (const q of ['the valley of kings', 'the valley of kings, egypt', 'valley kings']) {
      type(q)
      expect(latest!.searchResults.map(r => r.id)).toEqual(['valley'])
    }
  })

  it('lets a word name the place, ranked below a name that holds every word', () => {
    const giza2 = site('giza2', 'Giza Plateau Egypt', 'Egypt')
    render(baseOptions([GIZA, giza2]))
    type('giza, egypt')
    expect(latest!.searchResults.map(r => r.id)).toEqual(['giza2', 'giza'])
  })

  it('needs a word to start a word: "kings" is not in "workings"', () => {
    render(baseOptions([COLLIERY]))
    type('valley kings')
    expect(latest!.searchResults).toEqual([])
  })
})

describe('useSiteSearch with a typo', () => {
  const site = (id: string, title: string, location: string): SiteData => ({ ...TEMPLE, id, title, location })
  const BAALBEK = site('baalbek', 'Baalbek', 'Lebanon')
  const GIZA = site('giza', 'Giza Necropolis', 'Egypt')
  const CRETE = site('knossos', 'Knossos', 'Crete, Greece')

  it('finds a name one letter off, as the visitors of 2026-09-17..26 typed it', () => {
    render(baseOptions([BAALBEK, GIZA, CRETE]))
    type('baalk')
    expect(latest!.searchResults.map(r => r.id)).toEqual(['baalbek'])
    type('gize, egy')
    expect(latest!.searchResults.map(r => r.id)).toEqual(['giza'])
  })

  it('looks for typos only when nothing matched as typed', () => {
    // A typo never outranks an exact match, and checking every site for one
    // doubled the time a search takes
    const exact = site('gizeh', 'Gize Plateau', 'Egypt')
    render(baseOptions([GIZA, exact]))
    type('gize')
    expect(latest!.searchResults.map(r => r.id)).toEqual(['gizeh'])
  })

  it('leaves a word too far off, and a short one, unmatched', () => {
    render(baseOptions([BAALBEK, GIZA, CRETE]))
    type('notswa')
    expect(latest!.searchResults).toEqual([])
    type('gix')
    expect(latest!.searchResults).toEqual([])
  })
})

// The order the visitor reads. Production 2026-10-04: 1,595,613 of the 1,759,573
// shown sites carry neither a card description nor a description, so "how well it
// matched" alone put bare names from the big gazetteers first.
describe('useSiteSearch orders described sites before bare ones', () => {
  const site = (id: string, title: string, text: Partial<SiteData> = {}): SiteData =>
    ({ ...TEMPLE, id, title, ...text })

  it('puts a described site before a better-matching bare one', () => {
    // "Great Zimbabwe" bare (geonames) and described (wikidata), as production
    // returned them on 2026-10-04 - the sources are the same one here, only
    // the text differs, which is what the order reads
    const bare = site('bare', 'Great Zimbabwe')
    const described = site('described', 'Great Zimbabwe Ruins National', {
      description: 'Ruined city in the south-eastern hills of Zimbabwe',
    })
    render(baseOptions([bare, described]))
    type('great zimbabwe')
    expect(latest!.searchResults.map(r => r.id)).toEqual(['described', 'bare'])
  })

  it('keeps the match order inside the described sites', () => {
    const bare = site('bare', 'Alpha of the South')
    const exact = site('exact', 'Alpha', { description: 'A temple on a hill' })
    const starts = site('starts', 'Alpha North Gate', { cardDescription: 'A gate' })
    render(baseOptions([bare, exact, starts]))
    type('alpha')
    // "Alpha" (score 100) before "Alpha North Gate" (80) before the bare one
    expect(latest!.searchResults.map(r => r.id)).toEqual(['exact', 'starts', 'bare'])
  })

  it('treats a card teaser as text, and a blank one as none', () => {
    const blank = site('blank', 'Beta Hill', { description: '   ' })
    const teaser = site('teaser', 'Beta Hill', { cardDescription: 'A hill above the valley' })
    render(baseOptions([blank, teaser]))
    type('beta')
    expect(latest!.searchResults.map(r => r.id)).toEqual(['teaser', 'blank'])
  })
})

// A query the visitor's own sources cannot answer at all is answered from the
// whole database, and the button says so. The search page passes
// `widenToAllSources`; the globe does not, because there the same flag decides
// which dots the map draws.
describe('useSiteSearch widens to all sources when the visitor\'s sources have no match', () => {
  const API_SITE = {
    id: 'api-1', n: 'Great Zimbabwe National Monument', la: -20.27, lo: 30.93,
    s: 'unesco', t: 'Monument', p: null, d: 'The ruins of Great Zimbabwe',
  }

  function stubApi(sites: unknown[] = [API_SITE]) {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ sites }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  const settle = () => act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve() })

  it('searches the whole database and reports it, where the own sources found nothing', async () => {
    const fetchMock = stubApi()
    render(baseOptions([{ ...TEMPLE, id: 'curated', title: 'Alpha' }], { widenToAllSources: true }))
    type('great zimbabwe')

    expect(latest!.autoAllSources).toBe(true)
    expect(latest!.allSourcesActive).toBe(true)
    expect(latest!.isSearching).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toContain('q=great%20zimbabwe')

    await settle()
    expect(latest!.isSearching).toBe(false)
    expect(latest!.searchResults.map(r => r.id)).toEqual(['api-1'])
  })

  it('leaves the search alone where the visitor\'s own sources do have the match', () => {
    const fetchMock = stubApi()
    render(baseOptions([{ ...TEMPLE, id: 'curated', title: 'Great Zimbabwe' }], { widenToAllSources: true }))
    type('great zimbabwe')
    expect(latest!.autoAllSources).toBe(false)
    expect(latest!.allSourcesActive).toBe(false)
    expect(latest!.searchResults.map(r => r.id)).toEqual(['curated'])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('stays off without the option, so the globe keeps the choice to the visitor', () => {
    const fetchMock = stubApi()
    render(baseOptions([{ ...TEMPLE, id: 'curated', title: 'Alpha' }]))
    type('great zimbabwe')
    expect(latest!.autoAllSources).toBe(false)
    expect(latest!.allSourcesActive).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not widen a query the visitor is still typing', () => {
    const fetchMock = stubApi()
    render(baseOptions([{ ...TEMPLE, id: 'curated', title: 'Alpha' }], { widenToAllSources: true }))
    type('gr') // two characters: the results row answers nothing yet either
    expect(latest!.autoAllSources).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('a click on the button stops the widening for that query', async () => {
    stubApi()
    render(baseOptions([{ ...TEMPLE, id: 'curated', title: 'Alpha' }], { widenToAllSources: true }))
    type('great zimbabwe')
    expect(latest!.allSourcesActive).toBe(true)

    act(() => latest!.dismissAutoAllSources())
    expect(latest!.autoAllSources).toBe(false)
    expect(latest!.allSourcesActive).toBe(false)
    expect(latest!.searchResults).toEqual([])
    await settle()
    // The answer that was already in flight is not shown as the result of a
    // search the visitor turned off
    expect(latest!.allSourcesActive).toBe(false)
  })

  it('widens again for the next query, and forgets the dismissal', async () => {
    stubApi()
    render(baseOptions([{ ...TEMPLE, id: 'curated', title: 'Alpha' }], { widenToAllSources: true }))
    type('great zimbabwe')
    act(() => latest!.dismissAutoAllSources())
    type('stonehenge walls')
    expect(latest!.autoAllSources).toBe(true)
    await settle()
  })

  it('does not widen a query the whole database could not answer either', async () => {
    stubApi([])
    render(baseOptions([{ ...TEMPLE, id: 'curated', title: 'Alpha' }], { widenToAllSources: true }))
    type('qqqq zzzz')
    await settle()
    expect(latest!.searchResults).toEqual([])
    expect(latest!.autoAllSources).toBe(true) // the button stays on: it is the wider search
  })
})

