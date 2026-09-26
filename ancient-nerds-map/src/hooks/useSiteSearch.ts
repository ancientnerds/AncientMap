/**
 * Shared search hook used by both the globe (App.tsx) and standalone search page.
 * Encapsulates search query state, debouncing, API search, and client-side filtering.
 */

import { useState, useEffect, useMemo, useRef } from 'react'
import { SiteData, getCategoryColor, getPeriodColor, getSourceColor, resolvePeriod } from '../data/sites'
import {
  normalizeForSearch,
  periodToYear,
  extractCountry,
  searchWords,
  startsAWord,
  trigramSimilarity,
  trigrams,
  TYPO_MIN_LENGTH,
  TYPO_SIMILARITY,
} from '../utils/searchUtils'
import { haversineDistance } from '../utils/geoMath'
import { EmpirePolygonData, isSiteInEmpirePolygons } from '../utils/geometry'
import { config } from '../config'
import { apiDetailToSiteData } from '../utils/siteApi'
import { pageType, searchTerm, track } from '../analytics'

export interface SearchResult {
  id: string
  title: string
  category?: string
  categoryColor?: string
  location?: string
  period?: string
  periodStart?: number | null
  periodColor?: string
  sourceName?: string
  sourceColor?: string
  sourceId?: string
  sourceUrl?: string
  description?: string
  cardDescription?: string
  image?: string
  coordinates?: [number, number]
}

export interface SourceInfo {
  id: string
  name: string
  color: string
  count: number
  primary?: boolean
  priority: number
}

interface SpatialFilter {
  center: [number, number]  // [lng, lat]
  radius: number            // km
}

interface EmpireFilter {
  visibleEmpireIds: Set<string>
  empireSliderYears: Record<string, number>
  empirePolygons: Map<string, EmpirePolygonData>
}

export interface UseSiteSearchOptions {
  sites: SiteData[]
  sourceNameMap: Record<string, string>
  selectedSources: string[]
  selectedCategories: string[]
  allCategories: string[]
  selectedCountries: string[]
  allCountries: string[]
  ageRange: [number, number]
  searchAllSources: boolean
  applyFiltersToSearch: boolean
  /**
   * The sites carry their detail fields (description etc.). The globe starts without
   * them; until they arrive a query answers nothing and reports `isSearching` instead of
   * results matched on half the data. The search page loads them up front: `true`.
   */
  detailsReady: boolean
  // Globe-only (optional — search page omits)
  spatialFilter?: SpatialFilter | null
  empireFilter?: EmpireFilter | null
}

export interface UseSiteSearchReturn {
  searchQuery: string
  setSearchQuery: (q: string) => void
  debouncedQuery: string
  searchResults: SearchResult[]
  apiSearchResults: SiteData[]
  isSearching: boolean
  /** The "All sources" API search for the current query failed (no answer): what to show instead of a count. */
  searchError: string | null
  handleSearchResultSelect: (siteId: string, openPopup: boolean, onSiteClick: (site: SiteData) => void) => Promise<void>
}

/** A site's names and place, normalized: worked out once per site object, not
 *  once per keystroke. */
interface SiteWords {
  names: string[]
  place: string
}

const SITE_WORDS = new WeakMap<SiteData, SiteWords>()

function siteWords(site: SiteData): SiteWords {
  const known = SITE_WORDS.get(site)
  if (known) return known
  const words = {
    names: [normalizeForSearch(site.title), ...(site.altNames ?? []).map(normalizeForSearch)],
    place: site.location ? normalizeForSearch(site.location) : '',
  }
  SITE_WORDS.set(site, words)
  return words
}

/** The trigrams of every name word of a site, for the typo search only - kept
 *  apart from siteWords so the first word search does not build them for
 *  every site (1366x768, CPU x4, 2026-09-26: a 391 ms task). */
const NAME_TRIGRAMS = new WeakMap<SiteData, Set<string>[]>()

function nameTrigrams(site: SiteData): Set<string>[] {
  const known = NAME_TRIGRAMS.get(site)
  if (known) return known
  const nameWords = siteWords(site).names.flatMap(n => n.split(/[^\p{L}\p{N}]+/u)).filter(w => w.length >= 3)
  const sets = nameWords.map(trigrams)
  NAME_TRIGRAMS.set(site, sets)
  return sets
}

export function useSiteSearch(options: UseSiteSearchOptions): UseSiteSearchReturn {
  const {
    sites,
    sourceNameMap,
    selectedSources,
    selectedCategories,
    allCategories,
    selectedCountries,
    allCountries,
    ageRange,
    searchAllSources,
    applyFiltersToSearch,
    detailsReady,
    spatialFilter,
    empireFilter,
  } = options

  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [apiSearchResults, setApiSearchResults] = useState<SiteData[]>([])
  // The query the API last answered (with or without sites); pending while it differs.
  const [apiAnsweredQuery, setApiAnsweredQuery] = useState<string | null>(null)
  // The query whose API search failed (HTTP error, network, no sites list): no answer, not pending.
  const [apiFailure, setApiFailure] = useState<{ query: string; reason: string } | null>(null)
  const apiSearchAbortRef = useRef<AbortController | null>(null)

  // Debounce search query (200ms)
  useEffect(() => {
    if (searchDebounceRef.current) {
      clearTimeout(searchDebounceRef.current)
    }
    searchDebounceRef.current = setTimeout(() => {
      setDebouncedQuery(searchQuery)
    }, 200)
    return () => {
      if (searchDebounceRef.current) {
        clearTimeout(searchDebounceRef.current)
      }
    }
  }, [searchQuery])

  // API search: fetch from backend when "All sources" is checked and query is long enough
  useEffect(() => {
    if (!searchAllSources || debouncedQuery.trim().length < 3) {
      setApiSearchResults([])
      setApiAnsweredQuery(null)
      setApiFailure(null)
      return
    }

    apiSearchAbortRef.current?.abort()
    const controller = new AbortController()
    apiSearchAbortRef.current = controller

    const query = debouncedQuery.trim()
    const encoded = encodeURIComponent(query)
    setApiFailure(null)
    fetch(`${config.api.baseUrl}/sites/search?q=${encoded}&limit=50`, { signal: controller.signal })
      .then(res => {
        // A 429 from the search limiter or a 5xx carries no sites: no answer
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(data => {
        if (controller.signal.aborted) return
        const parsed: SiteData[] = data.sites.map((s: { id: string; n: string; la: number; lo: number; s: string; t?: string; p?: number; pn?: string; d?: string; cd?: string; c?: string; u?: string }) => ({
          id: s.id,
          title: s.n,
          coordinates: [s.lo, s.la] as [number, number],
          category: s.t || 'Unknown',
          period: resolvePeriod(s.pn, s.p),
          periodStart: s.p ?? null,
          location: s.c || '',
          description: s.d || '',
          cardDescription: s.cd,
          sourceId: s.s,
          sourceUrl: s.u,
        }))
        setApiSearchResults(parsed)
        setApiAnsweredQuery(query)
      })
      .catch(err => {
        if (err.name === 'AbortError') return
        console.warn('API search failed:', err)
        setApiSearchResults([])
        setApiFailure({ query, reason: err.message })
      })

    return () => controller.abort()
  }, [searchAllSources, debouncedQuery])

  // Generate search results
  const detailsPending = !detailsReady && debouncedQuery.trim().length > 0
  const apiFailureReason = searchAllSources && apiFailure?.query === debouncedQuery.trim() ? apiFailure.reason : null
  const apiFailed = apiFailureReason !== null

  const searchResults = useMemo((): SearchResult[] => {
    if (!debouncedQuery.trim()) return []
    if (detailsPending) return []
    // The local preview is no answer to an all-sources query the API failed on
    if (apiFailed) return []

    // When "All sources" is checked and API results have arrived, use them.
    if (searchAllSources && apiSearchResults.length > 0) {
      return apiSearchResults.slice(0, 100).map(site => {
        const category = site.category || 'Unknown'
        const period = site.period || 'Unknown'
        return {
          id: site.id,
          title: site.title,
          category,
          categoryColor: getCategoryColor(category),
          location: site.location,
          period,
          periodStart: site.periodStart,
          periodColor: getPeriodColor(period),
          sourceName: sourceNameMap[site.sourceId] || site.sourceId,
          sourceColor: getSourceColor(site.sourceId),
          sourceId: site.sourceId,
          sourceUrl: site.sourceUrl,
          description: site.description,
          cardDescription: site.cardDescription,
          image: site.image,
          coordinates: site.coordinates,
        }
      })
    }

    const query = normalizeForSearch(debouncedQuery)
    // When "All sources" is checked (API loading), search all loaded sites as preview
    let sitesToSearch = searchAllSources
      ? sites
      : sites.filter(s => selectedSources.includes(s.sourceId))

    // Apply filters to search results only if "Apply filters" is checked
    if (applyFiltersToSearch) {
      // Apply age range filter
      if (ageRange[0] > -5000 || ageRange[1] < 1500) {
        sitesToSearch = sitesToSearch.filter(site => {
          const year = site.periodStart ?? periodToYear(site.period)
          return year >= ageRange[0] && year <= ageRange[1]
        })
      }
      // Apply category filter
      if (selectedCategories.length < allCategories.length && selectedCategories.length > 0) {
        sitesToSearch = sitesToSearch.filter(site => selectedCategories.includes(site.category))
      }
      // Apply country filter
      if (selectedCountries.length > 0 && selectedCountries.length < allCountries.length) {
        sitesToSearch = sitesToSearch.filter(site => {
          const country = extractCountry(site.location)
          return selectedCountries.includes(country)
        })
      }
    }

    // Apply proximity filter (globe-only)
    if (spatialFilter) {
      const [centerLng, centerLat] = spatialFilter.center
      sitesToSearch = sitesToSearch.filter(site => {
        const [siteLng, siteLat] = site.coordinates
        const distance = haversineDistance(centerLat, centerLng, siteLat, siteLng)
        return distance <= spatialFilter.radius
      })
    }

    // Apply empire filter (globe-only)
    if (empireFilter && empireFilter.visibleEmpireIds.size > 0) {
      const activeEmpirePolygons: EmpirePolygonData[] = []
      for (const empireId of empireFilter.visibleEmpireIds) {
        const currentYear = empireFilter.empireSliderYears[empireId]
        if (currentYear !== undefined) {
          const polygonData = empireFilter.empirePolygons.get(`${empireId}:${currentYear}`)
          if (polygonData) {
            activeEmpirePolygons.push(polygonData)
          }
        }
      }

      if (activeEmpirePolygons.length > 0) {
        sitesToSearch = sitesToSearch.filter(site => {
          const siteYear = site.periodStart ?? periodToYear(site.period)
          for (const empireData of activeEmpirePolygons) {
            if (siteYear > empireData.year) {
              continue
            }
            if (isSiteInEmpirePolygons(site.coordinates, [empireData])) {
              return true
            }
          }
          return false
        })
      }
    }

    // Spaceless variants for matching "göbekli tepe" → "gobeklitepe"
    const querySpaceless = query.replace(/ /g, '')
    // Word by word, for a query of two words or more: every word starts a word
    // of the name (or an alternative name) or of the location. One word alone
    // is what the phrase match already does.
    const words = searchWords(query)
    const byWords = words.length >= 2
    const wordsInNames = (site: SiteData) => {
      const { names } = siteWords(site)
      return words.every(w => names.some(n => startsAWord(n, w)))
    }
    const wordsInNamesOrPlace = (site: SiteData) => {
      const { names, place } = siteWords(site)
      return words.every(w => names.some(n => startsAWord(n, w)) || startsAWord(place, w))
    }
    // Last, a mistyped word: every word found as above, or - from four letters
    // on - close enough to a word of the name ("baalk" -> Baalbek, "gize, egy"
    // -> Giza in Egypt). Only for a query nothing matched as typed: a typo
    // never outranks an exact match, and checking every site for one doubled
    // the time a search takes (1366x768, CPU x4, 2026-09-26: 111 -> 237 ms).
    const typoTrigrams = words.map(w => (w.length >= TYPO_MIN_LENGTH ? trigrams(w) : null))
    const byTypos = typoTrigrams.some(t => t !== null)
    const wordsWithTypos = (site: SiteData) => {
      const { names, place } = siteWords(site)
      return words.every((w, i) => {
        if (names.some(n => startsAWord(n, w)) || startsAWord(place, w)) return true
        const typed = typoTrigrams[i]
        return typed !== null && nameTrigrams(site).some(t => trigramSimilarity(typed, t) >= TYPO_SIMILARITY)
      })
    }

    // Filter and sort by relevance
    const asTyped = sitesToSearch.filter(site => {
      const titleNorm = normalizeForSearch(site.title)
      return titleNorm.includes(query) ||
        titleNorm.replace(/ /g, '').includes(querySpaceless) ||
        (site.altNames && site.altNames.some(an => normalizeForSearch(an).includes(query) || normalizeForSearch(an).replace(/ /g, '').includes(querySpaceless))) ||
        (site.location && normalizeForSearch(site.location).includes(query)) ||
        (site.description && normalizeForSearch(site.description).includes(query)) ||
        (byWords && wordsInNamesOrPlace(site))
    })
    const found = asTyped.length > 0 || !byTypos ? asTyped : sitesToSearch.filter(wordsWithTypos)
    const matchingSites = found
      .map(site => {
        const titleNorm = normalizeForSearch(site.title)
        const titleSpaceless = titleNorm.replace(/ /g, '')
        let score = 0
        if (titleNorm === query) {
          score = 100
        } else if (titleSpaceless === querySpaceless) {
          score = 95
        } else if (titleNorm.startsWith(query)) {
          score = 80
        } else if (titleNorm.includes(query)) {
          score = 60
        } else if (titleSpaceless.includes(querySpaceless)) {
          score = 55
        } else if (site.altNames && site.altNames.some(an => normalizeForSearch(an).includes(query) || normalizeForSearch(an).replace(/ /g, '').includes(querySpaceless))) {
          score = 50
        } else if (byWords && wordsInNames(site)) {
          score = 45
        } else if (site.location && normalizeForSearch(site.location).includes(query)) {
          score = 40
        } else if (byWords && wordsInNamesOrPlace(site)) {
          score = 35
        } else if (site.description && normalizeForSearch(site.description).includes(query)) {
          score = 20
        } else {
          score = 10 // a typo
        }
        return { site, score }
      })
      .sort((a, b) => b.score - a.score)
      .map(({ site }) => site)

    return matchingSites
      .slice(0, 100)
      .map(site => {
        const category = site.category || 'Unknown'
        const period = site.period || 'Unknown'
        return {
          id: site.id,
          title: site.title,
          category,
          categoryColor: getCategoryColor(category),
          location: site.location,
          period,
          periodStart: site.periodStart,
          periodColor: getPeriodColor(period),
          sourceName: sourceNameMap[site.sourceId] || site.sourceId,
          sourceColor: getSourceColor(site.sourceId),
          sourceId: site.sourceId,
          sourceUrl: site.sourceUrl,
          description: site.description,
          cardDescription: site.cardDescription,
          image: site.image,
          coordinates: site.coordinates,
        }
      })
  }, [debouncedQuery, detailsPending, apiFailed, searchAllSources, apiSearchResults, sites, selectedSources, sourceNameMap, applyFiltersToSearch, ageRange, selectedCategories, allCategories, selectedCountries, allCountries, spatialFilter, empireFilter])

  // Handle search result selection — resolves site data and calls the provided click handler
  const handleSearchResultSelect = async (siteId: string, openPopup: boolean, onSiteClick: (site: SiteData) => void) => {
    let site = sites.find(s => s.id === siteId)

    if (!site) {
      site = apiSearchResults.find(s => s.id === siteId)
      if (!site) {
        try {
          const res = await fetch(`${config.api.baseUrl}/sites/${siteId}`)
          if (res.ok) {
            const detail = await res.json()
            site = apiDetailToSiteData(detail)
          }
        } catch { /* site stays undefined */ }
      }
    }

    if (!site) return

    if (openPopup) {
      onSiteClick(site)
    }
  }

  const apiPending = searchAllSources && debouncedQuery.trim().length >= 3 && apiAnsweredQuery !== debouncedQuery.trim() && !apiFailed
  const isSearching = detailsPending || apiPending
  const searchError = apiFailed ? `All-sources search failed (${apiFailureReason}). Try again.` : null

  // One `search` event per query the user actually settled on (1.2 s without
  // further typing), with the result count; `search_empty` on top when
  // nothing matched — the clearest "did not find it" signal we have.
  // The count is read through a ref, not a dep: results keep changing while data
  // loads, and every change would restart the timer and swallow the event. While
  // details or API results are pending there is no count to report; the timer
  // starts once `isSearching` turns false. A failed API search has no count either.
  const trackedQueryRef = useRef('')
  const resultCountRef = useRef(0)
  resultCountRef.current = searchResults.length
  useEffect(() => {
    const q = debouncedQuery.trim()
    if (isSearching || apiFailed || q.length < 2 || trackedQueryRef.current === q) return
    const timer = setTimeout(() => {
      trackedQueryRef.current = q
      const results = resultCountRef.current
      const props = { q: searchTerm(q), chars: q.length, results, context: pageType(window.location.pathname) }
      track('search', props)
      if (results === 0) track('search_empty', props)
    }, 1200)
    return () => clearTimeout(timer)
  }, [debouncedQuery, isSearching, apiFailed])

  return {
    searchQuery,
    setSearchQuery,
    debouncedQuery,
    searchResults,
    apiSearchResults,
    isSearching,
    searchError,
    handleSearchResultSelect,
  }
}
