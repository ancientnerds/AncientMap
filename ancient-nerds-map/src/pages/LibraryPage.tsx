import { useState, useEffect, useCallback, useRef } from 'react'
import { config } from '../config'
import { getPeriodColor } from '../data/sites'
import PageHeader from '../components/layout/PageHeader'
import LibraryCard from '../components/library/LibraryCard'
import LibraryDetailCard from '../components/library/LibraryDetailCard'
import type { LibrarySource, LibraryPeriod, LibraryPeriodData, LibraryStats, LibrarySearchResponse } from '../types/library'
import '../styles/library.css'

const INITIAL_SHOW = 12

interface PeriodSection {
  meta: LibraryPeriod
  data: LibraryPeriodData | null
  loading: boolean
  expanded: boolean
}

export default function LibraryPage() {
  const [periods, setPeriods] = useState<PeriodSection[]>([])
  const [stats, setStats] = useState<LibraryStats | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<LibrarySource[] | null>(null)
  const [searchTotal, setSearchTotal] = useState(0)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState(false)
  const [activeType, setActiveType] = useState<string | null>(null)
  const [selectedSource, setSelectedSource] = useState<LibrarySource | null>(null)
  const sectionRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  const searchTimer = useRef<ReturnType<typeof setTimeout>>()

  // Load index + stats on mount
  useEffect(() => {
    fetch('/data/library/index.json')
      .then(r => r.ok ? r.json() : [])
      .then((index: LibraryPeriod[]) => {
        setPeriods(index.map(meta => ({ meta, data: null, loading: false, expanded: false })))
      })
      .catch(() => {})

    fetch('/data/library/stats.json')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setStats(data) })
      .catch(() => {})
  }, [])

  // Lazy-load period data when section scrolls into view
  useEffect(() => {
    const observers: IntersectionObserver[] = []

    periods.forEach((section, idx) => {
      const el = sectionRefs.current.get(section.meta.slug)
      if (!el || section.data || section.loading) return

      const observer = new IntersectionObserver(
        entries => {
          if (entries[0].isIntersecting) {
            observer.disconnect()
            setPeriods(prev => prev.map((s, i) => i === idx ? { ...s, loading: true } : s))
            fetch(`/data/library/periods/${section.meta.slug}.json`)
              .then(r => r.ok ? r.json() : null)
              .then((data: LibraryPeriodData | null) => {
                setPeriods(prev => prev.map((s, i) => i === idx ? { ...s, data, loading: false } : s))
              })
              .catch(() => {
                setPeriods(prev => prev.map((s, i) => i === idx ? { ...s, loading: false } : s))
              })
          }
        },
        { rootMargin: '300px' }
      )
      observer.observe(el)
      observers.push(observer)
    })

    return () => observers.forEach(o => o.disconnect())
  }, [periods])

  // Fetch from search API (used by both text search and type filter)
  const fetchSearch = useCallback(async (q: string, type: string | null) => {
    setSearchLoading(true)
    setSearchError(false)
    try {
      const params = new URLSearchParams({ page_size: '50' })
      if (q) params.set('q', q)
      if (type) params.set('type', type)
      const resp = await fetch(`${config.api.baseUrl}/library/search?${params}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data: LibrarySearchResponse = await resp.json()
      setSearchResults(data.items)
      setSearchTotal(data.total)
    } catch {
      setSearchResults([])
      setSearchTotal(0)
      setSearchError(true)
    } finally {
      setSearchLoading(false)
    }
  }, [])

  // Search with debounce
  const handleSearch = useCallback((value: string) => {
    setSearchQuery(value)
    if (searchTimer.current) clearTimeout(searchTimer.current)

    if (!value.trim() && !activeType) {
      setSearchResults(null)
      return
    }

    searchTimer.current = setTimeout(() => fetchSearch(value, activeType), 300)
  }, [activeType, fetchSearch])

  // Type filter chip toggle
  const handleTypeFilter = useCallback((type: string) => {
    const newType = activeType === type ? null : type
    setActiveType(newType)
    if (!newType && !searchQuery.trim()) {
      setSearchResults(null)
    } else {
      fetchSearch(searchQuery, newType)
    }
  }, [activeType, searchQuery, fetchSearch])

  const clearSearch = () => {
    setSearchQuery('')
    setActiveType(null)
    setSearchResults(null)
    setSearchError(false)
  }

  const toggleExpand = (slug: string) => {
    setPeriods(prev => prev.map(s =>
      s.meta.slug === slug ? { ...s, expanded: !s.expanded } : s
    ))
  }

  const isSearchActive = searchResults !== null

  return (
    <div className="library-page">
      <PageHeader currentPage="library">
        <span className="page-header-title">Library</span>
      </PageHeader>

      <div className="library-content">
        {/* Search bar */}
        <div className="library-search-bar">
          <svg className="library-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
          </svg>
          <input
            type="text"
            className="library-search-input"
            placeholder="Search sources..."
            value={searchQuery}
            onChange={e => handleSearch(e.target.value)}
          />
          {searchQuery && (
            <button className="library-search-clear" onClick={clearSearch}>&times;</button>
          )}
        </div>

        {/* Stats + filter chips — single row on desktop */}
        <div className="library-toolbar">
          {stats && !isSearchActive && (
            <span className="library-stats-bar">
              {stats.total_sources.toLocaleString()} sources across {stats.period_count} periods in {Object.keys(stats.by_type).length} categories
            </span>
          )}
          <div className="library-filter-chips">
            {['story', 'journal', 'research', 'site'].map(type => (
              <button
                key={type}
                className={`library-filter-chip${activeType === type ? ' active' : ''}`}
                onClick={() => handleTypeFilter(type)}
              >
                {type === 'story' ? 'Stories' : type === 'journal' ? 'Journals' : type === 'research' ? 'Research' : 'Sites'}
                {stats && <span className="library-filter-chip-count">{stats.by_type[type] || 0}</span>}
              </button>
            ))}
          </div>
        </div>

        {/* Search results mode */}
        {isSearchActive && (
          <div className="library-search-results">
            <div className="library-stats-bar">
              {searchLoading ? 'Searching...' : `${searchTotal.toLocaleString()} results${searchQuery ? ` for "${searchQuery}"` : ''}${activeType ? ` in ${activeType}` : ''}`}
            </div>
            <div className="library-card-grid">
              {searchResults?.map(source => (
                <LibraryCard key={source.id} source={source} onClick={() => setSelectedSource(source)} />
              ))}
            </div>
            {!searchLoading && searchResults?.length === 0 && !searchError && (
              <div className="library-empty">No sources found.</div>
            )}
            {searchError && (
              <div className="library-empty">Search unavailable. Try browsing by period instead.</div>
            )}
          </div>
        )}

        {/* Browse mode — period sections */}
        {!isSearchActive && periods.map(section => (
          <div
            key={section.meta.slug}
            className="library-period-section"
            ref={el => { if (el) sectionRefs.current.set(section.meta.slug, el) }}
          >
            <div className="library-period-header" style={{ borderBottomColor: getPeriodColor(section.meta.period) + '40' }}>
              <h2 className="library-period-title" style={{ color: getPeriodColor(section.meta.period) }}>{section.meta.period}</h2>
              <span className="library-period-count">{section.meta.count} sources</span>
            </div>

            {section.loading && (
              <div className="library-loading">Loading...</div>
            )}

            {section.data && (
              <>
                <div className="library-card-grid">
                  {(section.expanded ? section.data.sources : section.data.sources.slice(0, INITIAL_SHOW))
                    .map(source => (
                      <LibraryCard key={source.id} source={source} onClick={() => setSelectedSource(source)} />
                    ))
                  }
                </div>
                {section.data.sources.length > INITIAL_SHOW && (
                  <button className="library-show-more" onClick={() => toggleExpand(section.meta.slug)}>
                    {section.expanded
                      ? 'Show less'
                      : `Show all ${section.data.sources.length} sources`
                    }
                  </button>
                )}
              </>
            )}
          </div>
        ))}

        {!isSearchActive && periods.length === 0 && (
          <div className="library-empty">No library data available yet. Run the pipeline to populate.</div>
        )}
      </div>

      {/* Detail overlay */}
      {selectedSource && (
        <LibraryDetailCard source={selectedSource} onClose={() => setSelectedSource(null)} />
      )}
    </div>
  )
}
