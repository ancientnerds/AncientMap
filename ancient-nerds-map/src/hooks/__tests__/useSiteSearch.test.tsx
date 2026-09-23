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
