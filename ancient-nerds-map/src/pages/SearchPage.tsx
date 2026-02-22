import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import PageHeader from '../components/layout/PageHeader'
import { SiteCard, ViewOnGlobeLink } from '../components/SiteCard'
import { SearchFilters } from '../components/SearchFilters'
import { SitePopupOverlay } from '../components/SitePopupOverlay'
import { useSiteSearch, type SourceInfo } from '../hooks/useSiteSearch'
import { extractCountry } from '../utils/searchUtils'
import { SiteData, fetchSites, getCurrentSites, addSourceSites, getSourceColor, getDefaultEnabledSourceIds } from '../data/sites'
import { DataStore } from '../data/DataStore'
import { SourceLoader } from '../services/SourceLoader'
import { config } from '../config'
import { apiDetailToSiteData } from '../utils/siteApi'
import type { SourceMeta } from '../types/data'
import '../styles/search-page.css'

export default function SearchPage() {
  const searchInputRef = useRef<HTMLInputElement>(null)
  const [sites, setSites] = useState<SiteData[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [countries, setCountries] = useState<string[]>([])
  const [selectedCountries, setSelectedCountries] = useState<string[]>([])
  const [selectedSources, setSelectedSources] = useState<string[]>([])
  const [ageRange, setAgeRange] = useState<[number, number]>([-5000, 1500])
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [selectedSite, setSelectedSite] = useState<SiteData | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const [sourcesMeta, setSourcesMeta] = useState<Record<string, SourceMeta>>({})
  const [loadedSourceIds, setLoadedSourceIds] = useState<Set<string>>(new Set())
  const [loadingSources, setLoadingSources] = useState<Set<string>>(new Set())
  const [searchAllSources, setSearchAllSources] = useState(false)
  const [randomSites, setRandomSites] = useState<SiteData[]>([])

  // Load default source on mount
  useEffect(() => {
    async function loadData() {
      const data = await fetchSites()
      setSites(data)

      const sources = DataStore.getSources()
      const metaMap: Record<string, SourceMeta> = {}
      for (const source of sources) metaMap[source.id] = source
      setSourcesMeta(metaMap)

      const cats = [...new Set(data.map(s => s.category).filter(Boolean))].sort()
      setCategories(cats)
      setSelectedCategories(cats)

      const ctry = [...new Set(data.map(s => extractCountry(s.location)).filter(c => c !== 'Unknown'))].sort()
      setCountries(ctry)
      setSelectedCountries(ctry)

      const defaultIds = getDefaultEnabledSourceIds()
      setSelectedSources(defaultIds)
      setLoadedSourceIds(new Set(defaultIds))
      setIsLoading(false)
    }
    loadData()
  }, [])

  const sources: SourceInfo[] = useMemo(() => {
    const result: SourceInfo[] = []
    for (const [sourceId, meta] of Object.entries(sourcesMeta)) {
      if ((!meta?.recordCount || meta.recordCount === 0) && !meta?.isPrimary) continue
      result.push({
        id: sourceId,
        name: meta?.name || sourceId.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
        color: meta?.color || getSourceColor(sourceId),
        count: meta.recordCount || 0,
      })
    }
    return result.sort((a, b) => {
      const PRIMARY: Record<string, number> = { 'ancient_nerds': 0, 'lyra': 1 }
      const ao = PRIMARY[a.id] ?? 99, bo = PRIMARY[b.id] ?? 99
      if (ao !== bo) return ao - bo
      return b.count - a.count
    })
  }, [sourcesMeta])

  const sourceNameMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const s of sources) map[s.id] = s.name
    return map
  }, [sources])

  const handleLoadSources = useCallback((sourceIdsToLoad: string[]) => {
    const toLoad = sourceIdsToLoad.filter(id => !loadedSourceIds.has(id) && !loadingSources.has(id))
    if (toLoad.length === 0) return
    setLoadingSources(prev => { const next = new Set(prev); toLoad.forEach(id => next.add(id)); return next })
    SourceLoader.loadSources(toLoad, {
      onSourceLoaded: (sourceId, loadedSites) => {
        addSourceSites(sourceId, loadedSites)
        setLoadedSourceIds(prev => new Set([...prev, sourceId]))
        setLoadingSources(prev => { const next = new Set(prev); next.delete(sourceId); return next })
        const allSites = getCurrentSites()
        setSites(allSites)
        const newCats = [...new Set(allSites.map(s => s.category).filter(Boolean))].sort()
        setCategories(newCats)
        setSelectedCategories(prev => { const missing = newCats.filter(c => !prev.includes(c)); return missing.length > 0 ? [...prev, ...missing] : prev })
        const newCtry = [...new Set(allSites.map(s => extractCountry(s.location)).filter(c => c !== 'Unknown'))].sort()
        setCountries(newCtry)
        setSelectedCountries(prev => { const missing = newCtry.filter(c => !prev.includes(c)); return missing.length > 0 ? [...prev, ...missing] : prev })
      },
      onSourceError: (sourceId) => {
        setLoadingSources(prev => { const next = new Set(prev); next.delete(sourceId); return next })
      },
    })
  }, [loadedSourceIds, loadingSources])

  const handleSourceChange = useCallback((newSources: string[]) => {
    setSelectedSources(newSources)
    const unloaded = newSources.filter(id => !loadedSourceIds.has(id) && !loadingSources.has(id))
    if (unloaded.length > 0) handleLoadSources(unloaded)
  }, [loadedSourceIds, loadingSources, handleLoadSources])

  const categoriesFromActiveSources = useMemo(() => {
    const activeSites = sites.filter(s => selectedSources.includes(s.sourceId))
    return [...new Set(activeSites.map(s => s.category).filter(Boolean))].sort()
  }, [sites, selectedSources])

  const search = useSiteSearch({
    sites, sourceNameMap, selectedSources, selectedCategories,
    allCategories: categoriesFromActiveSources, selectedCountries,
    allCountries: countries, ageRange, searchAllSources, applyFiltersToSearch: true,
  })

  // Card click — show popup overlay
  const handleCardClick = useCallback(async (result: { id: string }) => {
    let site = sites.find(s => s.id === result.id)
    if (site) {
      try {
        const res = await fetch(`${config.api.baseUrl}/sites/${result.id}`)
        if (res.ok) {
          const detail = await res.json()
          const apiData = apiDetailToSiteData(detail)
          site = { ...site, ...apiData, title: site.title || apiData.title }
        }
      } catch { /* use existing */ }
      setSelectedSite(site)
      return
    }
    try {
      const res = await fetch(`${config.api.baseUrl}/sites/${result.id}`)
      if (res.ok) {
        const detail = await res.json()
        setSelectedSite(apiDetailToSiteData(detail))
      }
    } catch { /* ignore */ }
  }, [sites])

  const handleRandom = useCallback(() => {
    if (sites.length === 0) return
    const colWidth = 296 // 280px card + 16px gap
    const rowHeight = 280 // approximate card height + gap
    const headerHeight = 130 // sticky header + bar
    const cols = Math.max(1, Math.floor(window.innerWidth / colWidth))
    const rows = Math.max(1, Math.floor((window.innerHeight - headerHeight) / rowHeight))
    const count = Math.min(50, Math.max(10, cols * rows))
    const shuffled = [...sites].sort(() => Math.random() - 0.5)
    setRandomSites(shuffled.slice(0, count))
    search.setSearchQuery('')
  }, [sites, search])

  const hasActiveFilters = selectedSources.length !== sources.length ||
    selectedCategories.length !== categories.length ||
    selectedCountries.length !== countries.length ||
    ageRange[0] !== -5000 || ageRange[1] !== 1500

  return (
    <div className="search-page">
      <div className="search-top-sticky">
        <PageHeader currentPage="search" speechBubble="Search 750K+ archaeological sites instantly — click any card to see details or view it on the globe">
          <span className="page-header-title">Search</span>
        </PageHeader>
        <div className="search-bar-wrap">
          <div className="search-bar-inner">
            <svg className="search-bar-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              ref={searchInputRef}
              type="text"
              className="search-bar-input"
              placeholder={isLoading ? 'Loading sites...' : 'Search archaeological sites...'}
              value={search.searchQuery}
              onChange={e => { search.setSearchQuery(e.target.value); if (randomSites.length) setRandomSites([]) }}
              disabled={isLoading}
              autoFocus
            />
            {(search.searchQuery || randomSites.length > 0) && (
              <button
                className="search-bar-clear"
                onClick={() => { search.setSearchQuery(''); setRandomSites([]); searchInputRef.current?.focus() }}
                title="Clear search"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            )}
            <button
              className={`news-page-chip${searchAllSources ? ' active' : ''}`}
              onClick={() => setSearchAllSources(!searchAllSources)}
            >
              All sources
            </button>
            <button
              className="search-bar-filter-btn"
              onClick={handleRandom}
              disabled={isLoading}
              title="Show random sites"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="16 3 21 3 21 8" /><line x1="4" y1="20" x2="21" y2="3" />
                <polyline points="21 16 21 21 16 21" /><line x1="15" y1="15" x2="21" y2="21" />
                <line x1="4" y1="4" x2="9" y2="9" />
              </svg>
              Random
            </button>
            <button
              className={`search-bar-filter-btn${filtersOpen ? ' active' : ''}${hasActiveFilters ? ' has-filters' : ''}`}
              onClick={() => setFiltersOpen(!filtersOpen)}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              Filters
            </button>
          </div>
        </div>
      </div>

      <div className="search-page-content">
        {filtersOpen && (
          <div className="search-filters-panel">
            <SearchFilters
              sources={sources} selectedSources={selectedSources} onSourceChange={handleSourceChange}
              categories={categories} selectedCategories={selectedCategories} onCategoryChange={setSelectedCategories}
              countries={countries} selectedCountries={selectedCountries} onCountryChange={setSelectedCountries}
              ageRange={ageRange} onAgeRangeChange={setAgeRange}
              loadedSourceIds={loadedSourceIds} loadingSources={loadingSources}
            />
          </div>
        )}

        {search.searchQuery.trim().length >= 3 && (
          <div className="search-results-count">
            {search.isSearching ? <span>Searching...</span> : <span>{search.searchResults.length} site{search.searchResults.length !== 1 ? 's' : ''} found</span>}
          </div>
        )}

        {search.searchQuery.trim().length < 3 && !isLoading && randomSites.length === 0 && (
          <div className="search-prompt">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" opacity="0.3">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <p>Type at least 3 characters to search{searchAllSources ? ' across all sources' : ' Ancient Nerds originals'}, or hit Random</p>
          </div>
        )}

        {isLoading && <div className="search-prompt"><p>Loading sites...</p></div>}

        {search.searchResults.length > 0 && (
          <div className="search-card-grid">
            {search.searchResults.map(result => {
              const siteForCard: SiteData = sites.find(s => s.id === result.id) || {
                id: result.id, title: result.title, location: result.location || '',
                category: result.category || 'Unknown', period: result.period || 'Unknown',
                periodStart: result.periodStart, description: result.description || '',
                image: result.image, sourceId: result.sourceId || '', coordinates: result.coordinates || [0, 0],
              }
              return (
                <SiteCard
                  key={result.id}
                  site={siteForCard}
                  sourceName={result.sourceName}
                  sourceColor={result.sourceColor}
                  onClick={() => handleCardClick(result)}
                  actions={<ViewOnGlobeLink siteId={result.id} />}
                />
              )
            })}
          </div>
        )}

        {search.searchQuery.trim().length < 3 && randomSites.length > 0 && (
          <>
            <div className="search-results-count">
              <span>{randomSites.length} random sites</span>
            </div>
            <div className="search-card-grid">
              {randomSites.map(site => (
                <SiteCard
                  key={site.id}
                  site={site}
                  sourceName={sourceNameMap[site.sourceId]}
                  sourceColor={getSourceColor(site.sourceId)}
                  onClick={() => handleCardClick(site)}
                  actions={<ViewOnGlobeLink siteId={site.id} />}
                />
              ))}
            </div>
          </>
        )}

        {search.searchQuery.trim().length >= 3 && !search.isSearching && search.searchResults.length === 0 && (
          <div className="search-prompt">
            <p>No sites found matching "{search.searchQuery}"{!searchAllSources && ' — try enabling "All sources"'}</p>
          </div>
        )}
      </div>

      {selectedSite && <SitePopupOverlay site={selectedSite} onClose={() => setSelectedSite(null)} />}
    </div>
  )
}
