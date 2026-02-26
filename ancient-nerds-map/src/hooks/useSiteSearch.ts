/**
 * Shared search hook used by both the globe (App.tsx) and standalone search page.
 * Encapsulates search query state, debouncing, API search, and client-side filtering.
 */

import { useState, useEffect, useMemo, useRef } from 'react'
import { SiteData, getCategoryColor, getPeriodColor, getSourceColor, resolvePeriod } from '../data/sites'
import { normalizeForSearch, periodToYear, extractCountry } from '../utils/searchUtils'
import { haversineDistance } from '../utils/geoMath'
import { EmpirePolygonData, isSiteInEmpirePolygons } from '../utils/geometry'
import { config } from '../config'
import { apiDetailToSiteData } from '../utils/siteApi'

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
  handleSearchResultSelect: (siteId: string, openPopup: boolean, onSiteClick: (site: SiteData) => void) => Promise<void>
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
    spatialFilter,
    empireFilter,
  } = options

  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [apiSearchResults, setApiSearchResults] = useState<SiteData[]>([])
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
      return
    }

    apiSearchAbortRef.current?.abort()
    const controller = new AbortController()
    apiSearchAbortRef.current = controller

    const encoded = encodeURIComponent(debouncedQuery.trim())
    fetch(`${config.api.baseUrl}/sites/search?q=${encoded}&limit=50`, { signal: controller.signal })
      .then(res => res.json())
      .then(data => {
        if (controller.signal.aborted) return
        const parsed: SiteData[] = (data.sites || []).map((s: { id: string; n: string; la: number; lo: number; s: string; t?: string; p?: number; pn?: string; d?: string; c?: string; u?: string }) => ({
          id: s.id,
          title: s.n,
          coordinates: [s.lo, s.la] as [number, number],
          category: s.t || 'Unknown',
          period: resolvePeriod(s.pn, s.p),
          periodStart: s.p ?? null,
          location: s.c || '',
          description: s.d || '',
          sourceId: s.s,
          sourceUrl: s.u,
        }))
        setApiSearchResults(parsed)
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.warn('API search failed:', err)
          setApiSearchResults([])
        }
      })

    return () => controller.abort()
  }, [searchAllSources, debouncedQuery])

  // Generate search results
  const searchResults = useMemo((): SearchResult[] => {
    if (!debouncedQuery.trim()) return []

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

    // Filter and sort by relevance
    const matchingSites = sitesToSearch
      .filter(site => {
        const titleNorm = normalizeForSearch(site.title)
        return titleNorm.includes(query) ||
          titleNorm.replace(/ /g, '').includes(querySpaceless) ||
          (site.altNames && site.altNames.some(an => normalizeForSearch(an).includes(query) || normalizeForSearch(an).replace(/ /g, '').includes(querySpaceless))) ||
          (site.location && normalizeForSearch(site.location).includes(query)) ||
          (site.description && normalizeForSearch(site.description).includes(query))
      })
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
        } else if (site.location && normalizeForSearch(site.location).includes(query)) {
          score = 40
        } else {
          score = 20
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
  }, [debouncedQuery, searchAllSources, apiSearchResults, sites, selectedSources, sourceNameMap, applyFiltersToSearch, ageRange, selectedCategories, allCategories, selectedCountries, allCountries, spatialFilter, empireFilter])

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

  const isSearching = searchAllSources && debouncedQuery.trim().length >= 3 && apiSearchResults.length === 0

  return {
    searchQuery,
    setSearchQuery,
    debouncedQuery,
    searchResults,
    apiSearchResults,
    isSearching,
    handleSearchResultSelect,
  }
}
