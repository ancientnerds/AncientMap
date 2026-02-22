import { useState, useMemo } from 'react'
import { getCategoryGroup, CATEGORY_GROUP_ORDER, type CategoryGroup, getCategoryColor } from '../constants/colors'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
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
    source: true, category: false, country: false, age: false,
  })
  const [countrySearch, setCountrySearch] = useState('')

  const toggle = (key: string) => setOpenSections(prev => ({ ...prev, [key]: !prev[key] }))

  // Group categories
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

  // Filtered countries
  const filteredCountries = useMemo(() => {
    if (!countrySearch.trim()) return countries
    const q = countrySearch.toLowerCase()
    return countries.filter(c => c.toLowerCase().includes(q))
  }, [countries, countrySearch])

  const toggleSource = (id: string) => {
    onSourceChange(
      selectedSources.includes(id)
        ? selectedSources.filter(s => s !== id)
        : [...selectedSources, id]
    )
  }

  const toggleCategory = (cat: string) => {
    onCategoryChange(
      selectedCategories.includes(cat)
        ? selectedCategories.filter(c => c !== cat)
        : [...selectedCategories, cat]
    )
  }

  const toggleCountry = (country: string) => {
    onCountryChange(
      selectedCountries.includes(country)
        ? selectedCountries.filter(c => c !== country)
        : [...selectedCountries, country]
    )
  }

  const selectAllSources = () => onSourceChange(sources.map(s => s.id))
  const selectNoneSources = () => onSourceChange([])
  const selectAllCategories = () => onCategoryChange([...categories])
  const selectNoneCategories = () => onCategoryChange([])
  const selectAllCountries = () => onCountryChange([...countries])
  const selectNoneCountries = () => onCountryChange([])

  return (
    <div className="search-filters">
      {/* Sources */}
      <FilterSection title={`Source (${selectedSources.length}/${sources.length})`} open={!!openSections.source} onToggle={() => toggle('source')}>
        <div className="sf-toggle-row">
          <button className="sf-text-btn" onClick={selectAllSources}>All</button>
          <button className="sf-text-btn" onClick={selectNoneSources}>None</button>
        </div>
        <div className="sf-check-list">
          {sources.map(source => {
            const isLoading = loadingSources?.has(source.id)
            const isLoaded = loadedSourceIds?.has(source.id)
            return (
              <label key={source.id} className="sf-check-item">
                <input type="checkbox" checked={selectedSources.includes(source.id)} onChange={() => toggleSource(source.id)} />
                <span className="sf-color-dot" style={{ background: source.color }} />
                <span className="sf-check-label">
                  {source.name}
                  {isLoading && <span className="sf-loading-indicator"> ...</span>}
                  {!isLoaded && !isLoading && <span className="sf-not-loaded"> (click to load)</span>}
                </span>
                <span className="sf-check-count">{source.count.toLocaleString()}</span>
              </label>
            )
          })}
        </div>
      </FilterSection>

      {/* Categories */}
      <FilterSection title={`Category (${selectedCategories.length}/${categories.length})`} open={!!openSections.category} onToggle={() => toggle('category')}>
        <div className="sf-toggle-row">
          <button className="sf-text-btn" onClick={selectAllCategories}>All</button>
          <button className="sf-text-btn" onClick={selectNoneCategories}>None</button>
        </div>
        <div className="sf-check-list">
          {groupedCategories.map(({ group, items }) => (
            <div key={group} className="sf-group">
              <div className="sf-group-label">{group}</div>
              {items.map(cat => (
                <label key={cat} className="sf-check-item">
                  <input type="checkbox" checked={selectedCategories.includes(cat)} onChange={() => toggleCategory(cat)} />
                  <span className="sf-color-dot" style={{ background: getCategoryColor(cat) }} />
                  <span className="sf-check-label">{cat}</span>
                </label>
              ))}
            </div>
          ))}
        </div>
      </FilterSection>

      {/* Countries */}
      <FilterSection title={`Country (${selectedCountries.length}/${countries.length})`} open={!!openSections.country} onToggle={() => toggle('country')}>
        <div className="sf-toggle-row">
          <button className="sf-text-btn" onClick={selectAllCountries}>All</button>
          <button className="sf-text-btn" onClick={selectNoneCountries}>None</button>
        </div>
        <input
          type="text"
          className="sf-country-search"
          placeholder="Search countries..."
          value={countrySearch}
          onChange={e => setCountrySearch(e.target.value)}
        />
        <div className="sf-check-list sf-check-list-scroll">
          {filteredCountries.map(country => {
            const flagUrl = getCountryFlatFlagUrl(country)
            return (
              <label key={country} className="sf-check-item">
                <input type="checkbox" checked={selectedCountries.includes(country)} onChange={() => toggleCountry(country)} />
                {flagUrl && <img src={flagUrl} alt="" className="sf-flag" loading="lazy" />}
                <span className="sf-check-label">{country}</span>
              </label>
            )
          })}
        </div>
      </FilterSection>

      {/* Age Range */}
      <FilterSection title="Age Range" open={!!openSections.age} onToggle={() => toggle('age')}>
        <div className="sf-age-range">
          <div className="sf-age-labels">
            <span>{ageRange[0] < 0 ? `${Math.abs(ageRange[0])} BC` : `${ageRange[0]} AD`}</span>
            <span>{ageRange[1] < 0 ? `${Math.abs(ageRange[1])} BC` : `${ageRange[1]} AD`}</span>
          </div>
          <div className="sf-dual-slider">
            <input
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
        </div>
      </FilterSection>
    </div>
  )
}
