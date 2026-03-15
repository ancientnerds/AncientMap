import { useState, useMemo } from 'react'
import { getCategoryGroup, CATEGORY_GROUP_ORDER, type CategoryGroup, getCategoryColor } from '../constants/colors'
import { getCountryFlatFlagUrl, getCountryContinent, CONTINENT_ORDER, type Continent } from '../utils/countryFlags'
import type { SourceInfo } from '../hooks/useSiteSearch'
import './search-filters.css'

interface SearchFiltersProps {
  sources: SourceInfo[]
  selectedSources: string[]
  onSourceChange: (sources: string[]) => void
  categories: string[]
  selectedCategories: string[]
  onCategoryChange: (categories: string[]) => void
  countries: string[]
  selectedCountries: string[]
  onCountryChange: (countries: string[]) => void
  ageRange: [number, number]
  onAgeRangeChange: (range: [number, number]) => void
  loadedSourceIds?: Set<string>
  loadingSources?: Set<string>
}

function FilterSection({ title, open, onToggle, children }: {
  title: string
  open: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  return (
    <div className={`sf-section${open ? ' sf-section-open' : ''}`}>
      <button className="sf-section-header" onClick={onToggle}>
        <span>{title}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && <div className="sf-section-body">{children}</div>}
    </div>
  )
}

export function SearchFilters({
  sources, selectedSources, onSourceChange,
  categories, selectedCategories, onCategoryChange,
  countries, selectedCountries, onCountryChange,
  ageRange, onAgeRangeChange,
  loadedSourceIds, loadingSources,
}: SearchFiltersProps) {
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    age: true, country: false, category: false, source: false,
  })
  const [countrySearch, setCountrySearch] = useState('')

  const toggle = (key: string) => setOpenSections(prev => ({ ...prev, [key]: !prev[key] }))

  const groupedCategories = useMemo(() => {
    const groups = new Map<CategoryGroup, string[]>()
    for (const cat of categories) {
      const group = getCategoryGroup(cat)
      if (!groups.has(group)) groups.set(group, [])
      groups.get(group)!.push(cat)
    }
    return CATEGORY_GROUP_ORDER
      .filter(g => groups.has(g))
      .map(g => ({ group: g, items: groups.get(g)!.sort() }))
  }, [categories])

  const filteredCountries = useMemo(() => {
    const list = countrySearch.trim()
      ? countries.filter(c => c.toLowerCase().includes(countrySearch.toLowerCase()))
      : countries
    // Group by continent
    const grouped = new Map<Continent | 'Other', string[]>()
    list.forEach(c => {
      const cont = getCountryContinent(c) || 'Other'
      if (!grouped.has(cont)) grouped.set(cont, [])
      grouped.get(cont)!.push(c)
    })
    return [...CONTINENT_ORDER, 'Other' as const]
      .filter(c => grouped.has(c))
      .map(c => ({ continent: c, countries: grouped.get(c)! }))
  }, [countries, countrySearch])

  const toggleSource = (id: string) => {
    onSourceChange(selectedSources.includes(id) ? selectedSources.filter(s => s !== id) : [...selectedSources, id])
  }
  const toggleCategory = (cat: string) => {
    if (selectedCategories.length === categories.length) { onCategoryChange([cat]); return }
    if (selectedCategories.length === 1 && selectedCategories.includes(cat)) { onCategoryChange([...categories]); return }
    onCategoryChange(selectedCategories.includes(cat) ? selectedCategories.filter(c => c !== cat) : [...selectedCategories, cat])
  }
  const toggleCountry = (country: string) => {
    if (selectedCountries.length === countries.length) { onCountryChange([country]); return }
    if (selectedCountries.length === 1 && selectedCountries.includes(country)) { onCountryChange([...countries]); return }
    onCountryChange(selectedCountries.includes(country) ? selectedCountries.filter(c => c !== country) : [...selectedCountries, country])
  }

  return (
    <div className="search-filters">
      {/* Age Range — colored gradient track, same as globe */}
      <FilterSection title="Age Range" open={!!openSections.age} onToggle={() => toggle('age')}>
        <div className="age-range-slider">
          <div className="age-range-track" />
          <input
            className="age-slider age-slider-min"
            type="range"
            min={-5000}
            max={1500}
            step={100}
            value={ageRange[0]}
            onChange={e => {
              const val = parseInt(e.target.value)
              if (val < ageRange[1]) onAgeRangeChange([val, ageRange[1]])
            }}
          />
          <input
            className="age-slider age-slider-max"
            type="range"
            min={-5000}
            max={1500}
            step={100}
            value={ageRange[1]}
            onChange={e => {
              const val = parseInt(e.target.value)
              if (val > ageRange[0]) onAgeRangeChange([ageRange[0], val])
            }}
          />
        </div>
        <div className="sf-age-labels">
          <span>{ageRange[0] < 0 ? `${Math.abs(ageRange[0])} BC` : `${ageRange[0]} AD`}</span>
          <span>{ageRange[1] < 0 ? `${Math.abs(ageRange[1])} BC` : `${ageRange[1]} AD`}</span>
        </div>
      </FilterSection>

      {/* Countries — flags only, same as globe country-flag-item */}
      <FilterSection title={`Country (${selectedCountries.length}/${countries.length})`} open={!!openSections.country} onToggle={() => toggle('country')}>
        <div className="sf-toggle-row">
          <button className="legend-action-btn" onClick={() => onCountryChange([...countries])}>All</button>
          <button className="legend-action-btn" onClick={() => onCountryChange([])}>None</button>
        </div>
        <input
          type="text"
          className="sf-country-search"
          placeholder="Filter countries..."
          value={countrySearch}
          onChange={e => setCountrySearch(e.target.value)}
        />
        <div className="country-legend-list flag-mode sf-chips-scroll">
          {filteredCountries.map(({ continent, countries: ctryList }) => (
            <div key={continent} className="continent-group">
              <div className="continent-label">{continent}</div>
              <div className="continent-countries flag-mode">
                {ctryList.map(country => {
                  const flagUrl = getCountryFlatFlagUrl(country)
                  const isActive = selectedCountries.includes(country)
                  if (!flagUrl) return null
                  return (
                    <button
                      key={country}
                      className={`country-flag-item ${isActive ? 'active' : 'inactive'}`}
                      onClick={() => toggleCountry(country)}
                      title={country}
                    >
                      <img src={flagUrl} alt={country} />
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </FilterSection>

      {/* Categories — same as globe category-legend-item */}
      <FilterSection title={`Category (${selectedCategories.length}/${categories.length})`} open={!!openSections.category} onToggle={() => toggle('category')}>
        <div className="sf-toggle-row">
          <button className="legend-action-btn" onClick={() => onCategoryChange([...categories])}>All</button>
          <button className="legend-action-btn" onClick={() => onCategoryChange([])}>None</button>
        </div>
        <div className="category-legend-list">
          {groupedCategories.map(({ group, items }) => (
            <div key={group} className="category-group">
              <div className="category-group-label">{group}</div>
              <div className="category-group-items">
                {items.map(cat => {
                  const color = getCategoryColor(cat)
                  const isActive = selectedCategories.includes(cat)
                  return (
                    <button
                      key={cat}
                      className={`category-legend-item ${isActive ? 'active' : 'inactive'}`}
                      onClick={() => toggleCategory(cat)}
                      title={cat}
                      style={{ borderColor: color, color: color }}
                    >
                      {cat}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </FilterSection>

      {/* Sources — same as globe source-legend-item */}
      <FilterSection title={`Source (${selectedSources.length}/${sources.length})`} open={!!openSections.source} onToggle={() => toggle('source')}>
        <div className="sf-toggle-row">
          <button className="legend-action-btn" onClick={() => onSourceChange(sources.map(s => s.id))}>All</button>
          <button className="legend-action-btn" onClick={() => onSourceChange([])}>None</button>
        </div>
        <div className="source-legend-list">
          {sources.map(source => {
            const isActive = selectedSources.includes(source.id)
            const isSourceLoading = loadingSources?.has(source.id)
            const isLoaded = loadedSourceIds?.has(source.id)
            const needsLoading = !isLoaded && !isSourceLoading
            return (
              <button
                key={source.id}
                className={`source-legend-item ${isActive ? 'active' : 'inactive'} ${isSourceLoading ? 'loading' : ''} ${needsLoading ? 'not-loaded' : ''}`}
                onClick={() => toggleSource(source.id)}
                title={`${source.name}: ${source.count.toLocaleString()} sites`}
              >
                <span className="source-legend-dot" style={{ background: isActive ? source.color : '#444' }} />
                <span className="source-legend-name">{source.name}</span>
                {isSourceLoading ? (
                  <span className="source-legend-loading"><span className="loading-dots"><span>.</span><span>.</span><span>.</span></span></span>
                ) : needsLoading ? (
                  <span className="source-legend-load-icon" title="Click to load">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                  </span>
                ) : (
                  <span className="source-legend-count">{source.count.toLocaleString()}</span>
                )}
              </button>
            )
          })}
        </div>
      </FilterSection>
    </div>
  )
}
