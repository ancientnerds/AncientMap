/**
 * The globe's search results header while a search cannot answer yet (site
 * details still loading, or the "All sources" API search in flight): it reads
 * "Searching..." (the search page's wording) instead of "0 results found" /
 * "No sites found". When the details failed to load, the header says so
 * instead of pretending nothing matched. No new elements or classes.
 *
 * @vitest-environment jsdom
 */

import { act, type ComponentProps } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import FilterPanel from '../FilterPanel'

vi.mock('../../contexts/OfflineContext', () => ({
  useOffline: () => ({ isOffline: false, cachedSourceIds: new Set<string>() }),
}))

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

type Props = ComponentProps<typeof FilterPanel>

const RESULT = { id: 'a', title: 'Alpha', category: 'Temple', location: 'Greece', period: 'Iron Age' }

function props(extra: Partial<Props>): Props {
  const noop = () => {}
  return {
    categories: [], selectedCategories: [], availableCategories: [],
    countries: [], selectedCountries: [], availableCountries: [], countryColors: {},
    sources: [], selectedSources: ['ancient_nerds'],
    searchQuery: 'hill', searchAllSources: false,
    applyFiltersToSearch: true, onApplyFiltersToSearchChange: noop,
    searchWithinProximity: false, onSearchWithinProximityChange: noop,
    searchResults: [], isSearching: false, searchError: null,
    filterMode: 'age', ageRange: [-5000, 1500],
    onCategoryChange: noop, onCountryChange: noop, onSourceChange: noop, onSearchChange: noop,
    onSearchAllSourcesChange: noop, onSearchResultSelect: noop, onRandomSite: noop,
    onFilterModeChange: noop, onAgeRangeChange: noop,
    totalSites: 1, filteredCount: 1,
    proximityCenter: null, proximityRadius: 100, isSettingProximityOnGlobe: false,
    onProximityCenterChange: noop, onProximityRadiusChange: noop, onSetProximityOnGlobeChange: noop,
    proximityResults: [], proximityHoverCoords: null,
    searchWithinEmpires: false, onSearchWithinEmpiresChange: noop, hasVisibleEmpires: false,
    ...extra,
  }
}

let root: Root | null = null
let container: HTMLElement

function render(extra: Partial<Props>) {
  act(() => {
    root!.render(<FilterPanel {...props(extra)} />)
  })
}

const header = () => container.querySelector('.search-results-header span')?.textContent
const empty = () => container.querySelector('.search-results-empty')
const items = () => container.querySelectorAll('.search-results-list > *').length

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root!.unmount())
  container.remove()
  root = null
})

describe('FilterPanel search results header', () => {
  it('reads "Searching..." while the search is pending, without "No sites found"', () => {
    render({ isSearching: true })
    expect(header()).toBe('Searching...')
    expect(empty()).toBeNull()
  })

  it('keeps the preview list under "Searching..." when it has one', () => {
    render({ isSearching: true, searchAllSources: true, searchResults: [RESULT] })
    expect(header()).toBe('Searching...')
    expect(items()).toBe(1)
  })

  it('counts results and says "No sites found" once the search has answered', () => {
    render({ isSearching: false })
    expect(header()).toBe('0 results found')
    expect(empty()?.textContent).toBe('No sites found')

    render({ isSearching: false, searchResults: [RESULT] })
    expect(header()).toBe('1 result found')
  })

  it('names the failure when the site details could not be loaded', () => {
    render({ isSearching: true, searchError: 'Search unavailable: site details failed to load. Reload the page.' })
    expect(header()).toBe('Search unavailable: site details failed to load. Reload the page.')
    expect(empty()).toBeNull()
  })
})
