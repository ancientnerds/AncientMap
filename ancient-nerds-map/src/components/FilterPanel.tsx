import { useState, useEffect, useRef, memo, useCallback } from 'react'
import { getCategoryColor, getCategoryGroup, CATEGORY_GROUP_ORDER, type CategoryGroup } from '../data/sites'
import { FilterMode } from '../App'
import { AnimatedCounter } from './AnimatedCounter'
import { useOffline } from '../contexts/OfflineContext'
import { getCountryFlatFlagUrl, getCountryContinent, CONTINENT_ORDER, Continent } from '../utils/countryFlags'
import { parseAnyCoordinate, formatCoordinate, applyCoordMask } from '../utils/coordinateParser'
import { haversineDistance } from '../utils/geoMath'

interface SourceInfo {
  id: string
  name: string
  color: string
  count: number
}

interface SearchResult {
  id: string
  title: string
  category?: string
  categoryColor?: string
  location?: string
  period?: string
  periodColor?: string
  sourceName?: string
  sourceColor?: string
}

interface FilterPanelProps {
  categories: string[]
  selectedCategories: string[]
  availableCategories: string[]  // Categories available given other filters
  countries: string[]
  selectedCountries: string[]
  availableCountries: string[]  // Countries available given other filters
  countryColors: Record<string, string>
  sources: SourceInfo[]
  selectedSources: string[]
  loadingSources?: Set<string>  // Sources currently loading in background
  searchQuery: string
  searchAllSources: boolean
  applyFiltersToSearch: boolean
  onApplyFiltersToSearchChange: (enabled: boolean) => void
  searchWithinProximity: boolean
  onSearchWithinProximityChange: (enabled: boolean) => void
  searchResults: SearchResult[]
  filterMode: FilterMode
  ageRange: [number, number]
  onCategoryChange: (categories: string[]) => void
  onCountryChange: (countries: string[]) => void
  onSourceChange: (sources: string[]) => void
  onSearchChange: (query: string) => void
  onSearchAllSourcesChange: (enabled: boolean) => void
  onSearchResultSelect: (id: string, openPopup: boolean) => void
  onRandomSite: () => void
  onFilterModeChange: (mode: FilterMode) => void
  onAgeRangeChange: (range: [number, number]) => void
  totalSites: number
  filteredCount: number
  // Proximity props
  proximityCenter: [number, number] | null
  proximityRadius: number
  isSettingProximityOnGlobe: boolean
  onProximityCenterChange: (center: [number, number] | null) => void
  onProximityRadiusChange: (radius: number) => void
  onSetProximityOnGlobeChange: (isActive: boolean) => void
  proximityResults: SearchResult[]
  proximityHoverCoords: [number, number] | null
  onSiteHover?: (siteId: string | null) => void
  onSiteListClick?: (siteId: string | null, ctrlKey?: boolean) => void  // When a result in the list is clicked (null to deselect, ctrlKey for multi-select)
  selectedSiteIds?: string[]  // Currently selected/frozen site IDs (supports multi-select)
  onResetAllFilters?: () => void  // Reset all filters to defaults
  defaultAgeRange?: [number, number]  // Default age range for detecting active filter
  loadedSourceIds?: Set<string>  // Which additional sources have been loaded
  onLoadSources?: (sourceIds: string[]) => void  // Callback to load specific sources
  // Empire filter props
  searchWithinEmpires: boolean
  onSearchWithinEmpiresChange: (enabled: boolean) => void
  hasVisibleEmpires: boolean  // true when at least one empire is visible
  // Measurement tool props
  measureMode?: boolean
  onMeasureModeChange?: (enabled: boolean) => void
  measurements?: Array<{ id: string; points: [[number, number], [number, number]]; snapped: [boolean, boolean]; color: string }>
  currentMeasurePoints?: Array<{ coords: [number, number]; snapped: boolean }>
  selectedMeasurementId?: string | null
  measureSnapEnabled?: boolean
  onMeasureSnapChange?: (enabled: boolean) => void
  onMeasurementSelect?: (id: string | null) => void
  onMeasurementDelete?: (id: string) => void
  onClearAllMeasurements?: () => void
  measureUnit?: 'km' | 'miles'
  onMeasureUnitChange?: (unit: 'km' | 'miles') => void
  onActiveTabChange?: (tab: 'search' | 'proximity' | 'measure') => void
}


// Helper to format year as BC/AD
function formatYear(year: number): string {
  if (year <= 0) return `${Math.abs(year)} BC`
  return `${year} AD`
}

function FilterPanel({
  categories,
  selectedCategories,
  availableCategories,
  countries,
  selectedCountries,
  availableCountries,
  countryColors,
  sources,
  selectedSources,
  loadingSources,
  searchQuery,
  searchAllSources,
  applyFiltersToSearch,
  onApplyFiltersToSearchChange,
  searchWithinProximity,
  onSearchWithinProximityChange,
  searchResults,
  filterMode,
  ageRange,
  onCategoryChange,
  onCountryChange,
  onSourceChange,
  onSearchChange,
  onSearchAllSourcesChange,
  onSearchResultSelect,
  onRandomSite,
  onFilterModeChange,
  onAgeRangeChange,
  totalSites,
  filteredCount,
  proximityCenter,
  proximityRadius,
  isSettingProximityOnGlobe,
  onProximityCenterChange,
  onProximityRadiusChange,
  onSetProximityOnGlobeChange,
  proximityResults,
  proximityHoverCoords,
  onSiteHover,
  onSiteListClick,
  selectedSiteIds = [],
  onResetAllFilters,
  defaultAgeRange = [-5000, 500],
  loadedSourceIds = new Set<string>(),
  onLoadSources,
  searchWithinEmpires,
  onSearchWithinEmpiresChange,
  hasVisibleEmpires,
  measureMode: _measureMode,
  onMeasureModeChange: _onMeasureModeChange,
  measurements = [],
  currentMeasurePoints = [],
  selectedMeasurementId,
  measureSnapEnabled,
  onMeasureSnapChange,
  onMeasurementSelect,
  onMeasurementDelete,
  onClearAllMeasurements,
  measureUnit = 'km',
  onMeasureUnitChange,
  onActiveTabChange,
}: FilterPanelProps) {
  const [searchResultsMinimized, setSearchResultsMinimized] = useState(false)
  const [filterByMinimized, setFilterByMinimized] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState('')
  const [countryFilter, setCountryFilter] = useState('')
  const [countryDisplayMode, setCountryDisplayMode] = useState<'flags' | 'badges'>('flags')

  // Tab state
  const [activeTab, setActiveTab] = useState<'search' | 'proximity' | 'measure'>('search')
  const [coordInput, setCoordInput] = useState('')
  const [isGettingLocation, setIsGettingLocation] = useState(false)
  const [isEditingCoords, setIsEditingCoords] = useState(false)
  const prevProximityCenterRef = useRef<[number, number] | null>(null)

  // Offline mode context - for greying out unavailable sources
  const { isOffline, cachedSourceIds } = useOffline()

  // Switch to proximity tab when proximity center is set externally (e.g. from popup)
  useEffect(() => {
    if (proximityCenter && !prevProximityCenterRef.current) {
      setActiveTab('proximity')
    }
    prevProximityCenterRef.current = proximityCenter
  }, [proximityCenter])

  // Handle coordinate search - when user enters coordinates in search box and presses Enter
  const handleCoordinateSearch = useCallback(() => {
    const coords = parseAnyCoordinate(searchQuery)
    if (coords) {
      // Set proximity center (this auto-flies to location via App.tsx effect)
      onProximityCenterChange(coords)
      // Set radius to 10km
      onProximityRadiusChange(10)
      // Enable search within proximity to show results
      onSearchWithinProximityChange(true)
      // Clear search query since we're now showing proximity results
      onSearchChange('')
      // Switch to proximity tab to show results
      setActiveTab('proximity')
      onActiveTabChange?.('proximity')
    }
  }, [searchQuery, onProximityCenterChange, onProximityRadiusChange, onSearchWithinProximityChange, onSearchChange, onActiveTabChange])

  // Determine display value for coordinate input
  const getCoordDisplayValue = (): string => {
    // When user is actively editing, show their input
    if (isEditingCoords) {
      return coordInput
    }
    // When in "set on globe" mode and hovering, show hover coords
    if (isSettingProximityOnGlobe && proximityHoverCoords) {
      return formatCoordinate(proximityHoverCoords[0], proximityHoverCoords[1])
    }
    // When proximity is set, show the set coordinates
    if (proximityCenter) {
      return formatCoordinate(proximityCenter[0], proximityCenter[1])
    }
    // Otherwise show manual input
    return coordInput
  }

  const isDisplayingLiveCoords = !!(isSettingProximityOnGlobe && proximityHoverCoords && !isEditingCoords)

  const toggleCategory = (category: string) => {
    // If all categories are active, clicking one selects only that one
    if (selectedCategories.length === categories.length) {
      onCategoryChange([category])
    // If only one category is active and we click it, activate all
    } else if (selectedCategories.length === 1 && selectedCategories.includes(category)) {
      onCategoryChange([...categories])
    } else if (selectedCategories.includes(category)) {
      onCategoryChange(selectedCategories.filter(c => c !== category))
    } else {
      onCategoryChange([...selectedCategories, category])
    }
  }

  const selectAllCategories = () => {
    onCategoryChange([...categories])
  }

  const clearCategories = () => {
    onCategoryChange([])
  }

  const invertCategories = () => {
    const inverted = categories.filter(c => !selectedCategories.includes(c))
    onCategoryChange(inverted)
  }

  // Helper: check if a source needs to be loaded (not default, not loaded, not loading)
  const sourceNeedsLoading = (sourceId: string) =>
    sourceId !== 'ancient_nerds' && sourceId !== 'lyra' &&
    !loadedSourceIds.has(sourceId) &&
    !loadingSources?.has(sourceId)

  const toggleSource = (sourceId: string) => {
    if (selectedSources.includes(sourceId)) {
      onSourceChange(selectedSources.filter(s => s !== sourceId))
    } else {
      // Select immediately, trigger load if needed
      onSourceChange([...selectedSources, sourceId])
      if (sourceNeedsLoading(sourceId) && onLoadSources) {
        onLoadSources([sourceId])
      }
    }
  }

  const selectAllSources = () => {
    onSourceChange(sources.map(s => s.id))
    // Load any sources that need loading
    const toLoad = sources.filter(s => sourceNeedsLoading(s.id))
    if (toLoad.length > 0 && onLoadSources) {
      onLoadSources(toLoad.map(s => s.id))
    }
  }

  const clearSources = () => {
    onSourceChange([])
  }

  const toggleCountry = (country: string) => {
    // If all countries are active, clicking one selects only that one
    if (selectedCountries.length === countries.length) {
      onCountryChange([country])
    // If only one country is active and we click it, activate all
    } else if (selectedCountries.length === 1 && selectedCountries.includes(country)) {
      onCountryChange([...countries])
    } else if (selectedCountries.includes(country)) {
      onCountryChange(selectedCountries.filter(c => c !== country))
    } else {
      onCountryChange([...selectedCountries, country])
    }
  }

  const selectAllCountries = () => {
    onCountryChange([...countries])
  }

  const clearCountries = () => {
    onCountryChange([])
  }

  const invertCountries = () => {
    const inverted = countries.filter(c => !selectedCountries.includes(c))
    onCountryChange(inverted)
  }

  // Proximity handlers
  const [locationError, setLocationError] = useState<string | null>(null)

  // IP-based geolocation using ipwho.is
  const getLocationByIP = async () => {
    try {
      const response = await fetch('https://ipwho.is/')
      if (!response.ok) throw new Error('IP lookup failed')
      const data = await response.json()
      if (data.success && typeof data.latitude === 'number' && typeof data.longitude === 'number') {
        setCoordInput(formatCoordinate(data.longitude, data.latitude))
        onProximityCenterChange([data.longitude, data.latitude])
        setLocationError(null)
      } else {
        setLocationError('Could not determine location')
      }
    } catch {
      setLocationError('Location lookup failed')
    } finally {
      setIsGettingLocation(false)
    }
  }

  const handleUseMyLocation = () => {
    setIsGettingLocation(true)
    setIsEditingCoords(false)
    setLocationError(null)
    // Always use IP-based geolocation (no browser permission prompts)
    getLocationByIP()
  }

  const handleCoordinateFocus = () => {
    // When focusing, start editing with current value
    setIsEditingCoords(true)
    if (proximityCenter) {
      setCoordInput(formatCoordinate(proximityCenter[0], proximityCenter[1]))
    }
  }

  const handleCoordinateChange = (value: string) => {
    // First try universal parser (handles Google Maps URLs, DMS, DDM, decimal, etc.)
    const directParse = parseAnyCoordinate(value)
    if (directParse) {
      setCoordInput(formatCoordinate(directParse[0], directParse[1]))
      onProximityCenterChange(directParse)
      setIsEditingCoords(false)
      return
    }

    // Apply mask to format input automatically (for manual typing)
    const { formatted } = applyCoordMask(value)
    setCoordInput(formatted)

    // Auto-submit when complete (12-13 digits = full coordinate)
    const digitCount = formatted.replace(/\D/g, '').length
    if (digitCount >= 12) {
      const parsed = parseAnyCoordinate(formatted)
      if (parsed) {
        onProximityCenterChange(parsed)
        setIsEditingCoords(false)
      }
    }
  }

  const handleCoordinateSubmit = () => {
    setIsEditingCoords(false)
    const parsed = parseAnyCoordinate(coordInput)
    if (parsed) {
      onProximityCenterChange(parsed)
    }
  }

  const handleClearProximity = () => {
    setCoordInput('')
    setIsEditingCoords(false)
    onProximityCenterChange(null)
    onSetProximityOnGlobeChange(false)
    onSiteListClick?.(null)  // Deselect any selected nearby site
  }

  return (
    <div className="filter-panel">
      {/* Header */}
      <div className="panel-header">
        <div className="logo-wrapper">
          <div className="glass-panel logo-panel">
            <div className="logo-main">ANCIENT NERDS</div>
            <div className="logo-sub">RESEARCH PLATFORM</div>
          </div>
          <span className="beta-badge">BETA</span>
        </div>
      </div>

      {/* Search/Proximity Section */}
      <div className="glass-panel">
        {/* Tab buttons */}
        <div className="search-proximity-tabs">
          <button
            className={`tab-btn ${activeTab === 'search' ? 'active' : ''}`}
            onClick={() => { setActiveTab('search'); onActiveTabChange?.('search') }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"></circle>
              <path d="m21 21-4.35-4.35"></path>
            </svg>
            Search
          </button>
          <button
            className={`tab-btn ${activeTab === 'proximity' ? 'active' : ''} ${proximityCenter ? 'has-value' : ''}`}
            onClick={() => { setActiveTab('proximity'); onActiveTabChange?.('proximity') }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <circle cx="12" cy="12" r="3"></circle>
            </svg>
            Proximity
          </button>
          <button
            className={`tab-btn ${activeTab === 'measure' ? 'active' : ''} ${measurements.length > 0 ? 'has-value' : ''}`}
            onClick={() => { setActiveTab('measure'); onActiveTabChange?.('measure') }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M2 12h20"></path>
              <path d="M6 8v8"></path>
              <path d="M18 8v8"></path>
              <path d="M10 10v4"></path>
              <path d="M14 10v4"></path>
            </svg>
            Measure
          </button>
        </div>

        {/* Search Tab Content */}
        {activeTab === 'search' && (
          <div className="search-tab-content">
            <div className="search-container">
              <div className="search-input-wrapper">
                <svg className="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8"></circle>
                  <path d="m21 21-4.35-4.35"></path>
                </svg>
                <input
                  type="text"
                  className="search-input"
                  placeholder="Search sites..."
                  value={searchQuery}
                  onChange={(e) => onSearchChange(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      handleCoordinateSearch()
                    }
                  }}
                />
                {searchQuery && (
                  <button className="search-clear-btn" onClick={() => {
                    onSearchChange('')
                    onSiteListClick?.(null)  // Deselect any selected search result
                  }} title="Clear search">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="6" x2="6" y2="18"></line>
                      <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                  </button>
                )}
              </div>
              <button
                className="random-site-btn-icon"
                onClick={onRandomSite}
                title="Go to random site"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M16 3h5v5"></path>
                  <path d="M8 3H3v5"></path>
                  <path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"></path>
                  <path d="m15 9 6-6"></path>
                  <path d="m3 21 6-6"></path>
                </svg>
              </button>
            </div>
            <div className="search-options-column">
              <div className="search-options-row">
                <label className="search-option-toggle">
                  <input
                    type="checkbox"
                    checked={searchAllSources}
                    onChange={(e) => onSearchAllSourcesChange(e.target.checked)}
                  />
                  <span>All sources</span>
                </label>
                <label className="search-option-toggle">
                  <input
                    type="checkbox"
                    checked={applyFiltersToSearch}
                    onChange={(e) => onApplyFiltersToSearchChange(e.target.checked)}
                  />
                  <span>Apply filters</span>
                </label>
              </div>
              <div className="search-options-row">
                <label
                  className={`search-option-toggle ${!proximityCenter ? 'disabled' : ''}`}
                  title={!proximityCenter ? 'Set a proximity circle in the Proximity tab first' : 'Only show results within the proximity circle'}
                >
                  <input
                    type="checkbox"
                    checked={searchWithinProximity}
                    onChange={(e) => onSearchWithinProximityChange(e.target.checked)}
                    disabled={!proximityCenter}
                  />
                  <span>Within proximity</span>
                </label>
                <label
                  className={`search-option-toggle ${!hasVisibleEmpires ? 'disabled' : ''}`}
                  title={!hasVisibleEmpires ? 'Enable an empire overlay in Historical Borders first' : 'Only show sites within visible empire boundaries from the correct time period'}
                >
                  <input
                    type="checkbox"
                    checked={searchWithinEmpires}
                    onChange={(e) => onSearchWithinEmpiresChange(e.target.checked)}
                    disabled={!hasVisibleEmpires}
                  />
                  <span>Within empires</span>
                </label>
              </div>
            </div>
          </div>
        )}

        {/* Proximity Tab Content */}
        {activeTab === 'proximity' && (
          <div className="proximity-tab-content">
            {/* Action buttons */}
            <div className="proximity-actions">
              <button
                className="proximity-btn my-location"
                onClick={handleUseMyLocation}
                disabled={isGettingLocation}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="3"></circle>
                  <path d="M12 2v4"></path>
                  <path d="M12 18v4"></path>
                  <path d="M2 12h4"></path>
                  <path d="M18 12h4"></path>
                </svg>
                {isGettingLocation ? 'Getting...' : 'My location'}
              </button>

              <button
                className={`proximity-btn set-on-globe ${isSettingProximityOnGlobe ? 'active' : ''}`}
                onClick={() => {
                  setLocationError(null)
                  onSetProximityOnGlobeChange(!isSettingProximityOnGlobe)
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"></path>
                  <path d="M2 12h20"></path>
                </svg>
                Set on globe
              </button>
            </div>

            {/* Location error message */}
            {locationError && (
              <div className="location-error">{locationError}</div>
            )}

            {/* Coordinate input */}
            <div className="coordinate-input-wrapper">
              <input
                type="text"
                className={`coordinate-input ${isDisplayingLiveCoords ? 'live-coords' : ''}`}
                placeholder="45.1234° N, 12.5678° E"
                value={getCoordDisplayValue()}
                onFocus={handleCoordinateFocus}
                onChange={(e) => handleCoordinateChange(e.target.value)}
                onPaste={(e) => {
                  e.preventDefault()
                  const pasted = e.clipboardData.getData('text')
                  handleCoordinateChange(pasted)
                }}
                onBlur={handleCoordinateSubmit}
                onKeyDown={(e) => e.key === 'Enter' && handleCoordinateSubmit()}
                readOnly={isDisplayingLiveCoords}
              />
              {(coordInput || proximityCenter) && !isDisplayingLiveCoords && (
                <button
                  className="coord-clear-btn"
                  onClick={handleClearProximity}
                  title="Clear coordinates"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                  </svg>
                </button>
              )}
            </div>

            {/* Radius slider */}
            <div className="radius-section">
              <label className="radius-label">
                Radius: <span className="radius-value">{proximityRadius} km</span>
              </label>
              <input
                type="range"
                className="radius-slider"
                min="10"
                max="2000"
                step="10"
                value={proximityRadius}
                onChange={(e) => onProximityRadiusChange(Number(e.target.value))}
              />
              <div className="radius-labels">
                <span>10 km</span>
                <span>2000 km</span>
              </div>
            </div>

            {/* Clear button */}
            {proximityCenter && (
              <button
                className="proximity-btn clear"
                onClick={handleClearProximity}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
                Clear proximity filter
              </button>
            )}
          </div>
        )}

        {/* Measure Tab Content */}
        {activeTab === 'measure' && (
          <div className="proximity-tab-content">
            {/* Options row */}
            <div className="proximity-actions">
              <label className="search-option-toggle" style={{ flex: 1 }}>
                <input
                  type="checkbox"
                  checked={measureSnapEnabled || false}
                  onChange={(e) => onMeasureSnapChange?.(e.target.checked)}
                />
                <span>Snap to sites</span>
              </label>
              <div className="unit-toggle">
                <button
                  className={`unit-btn ${measureUnit === 'km' ? 'active' : ''}`}
                  onClick={() => onMeasureUnitChange?.('km')}
                >
                  km
                </button>
                <button
                  className={`unit-btn ${measureUnit === 'miles' ? 'active' : ''}`}
                  onClick={() => onMeasureUnitChange?.('miles')}
                >
                  mi
                </button>
              </div>
            </div>

            {/* Current measurement status */}
            {currentMeasurePoints.length === 1 && (
              <div className="radius-label" style={{ justifyContent: 'center', color: 'var(--primary)' }}>
                Click to set end point...
              </div>
            )}

            {/* Measurements list */}
            {measurements.length > 0 && (
              <>
                <div className="search-results-header" style={{ padding: '8px 0 4px' }}>
                  <span>{measurements.length} measurement{measurements.length !== 1 ? 's' : ''}</span>
                  <button
                    className="panel-minimize-btn"
                    onClick={() => onClearAllMeasurements?.()}
                    title="Clear all measurements"
                    style={{ fontSize: '9px', padding: '2px 6px' }}
                  >
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="6" x2="6" y2="18"></line>
                      <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                  </button>
                </div>
                <div className="search-results-list" style={{ maxHeight: '150px' }}>
                  {measurements.map((measurement, index) => {
                    const [start, end] = measurement.points
                    const distanceKm = haversineDistance(start[1], start[0], end[1], end[0])
                    const distanceMiles = distanceKm * 0.621371
                    const isSelected = selectedMeasurementId === measurement.id
                    return (
                      <div
                        key={measurement.id}
                        className={`search-result-item ${isSelected ? 'selected' : ''}`}
                        onClick={() => onMeasurementSelect?.(isSelected ? null : measurement.id)}
                      >
                        <div className="search-result-main" style={{ flex: 1, display: 'flex', alignItems: 'center', gap: '10px' }}>
                          {/* Color indicator */}
                          <span
                            style={{
                              width: '12px',
                              height: '12px',
                              borderRadius: '50%',
                              backgroundColor: measurement.color || '#32CD32',
                              flexShrink: 0
                            }}
                          />
                          <div className="search-result-content">
                            <div className="search-result-title" style={{ color: 'var(--text-secondary)' }}>
                              <span style={{ color: measurement.color || '#32CD32', marginRight: '8px' }}>#{index + 1}</span>
                              {measureUnit === 'km'
                                ? `${distanceKm.toFixed(1)} km`
                                : `${distanceMiles.toFixed(1)} mi`
                              }
                              <span style={{ marginLeft: '8px', opacity: 0.6, fontSize: '11px' }}>
                                {measurement.snapped[0] ? 'site' : 'coord'} → {measurement.snapped[1] ? 'site' : 'coord'}
                              </span>
                            </div>
                          </div>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            onMeasurementDelete?.(measurement.id)
                          }}
                          title="Delete (DEL)"
                          style={{
                            background: 'none',
                            border: 'none',
                            padding: '4px',
                            cursor: 'pointer',
                            color: 'var(--text-secondary)',
                            opacity: 0.7,
                            transition: 'opacity 0.2s'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
                          onMouseLeave={(e) => e.currentTarget.style.opacity = '0.7'}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                          </svg>
                        </button>
                      </div>
                    )
                  })}
                </div>
              </>
            )}

            {/* Help text */}
            {measurements.length === 0 && currentMeasurePoints.length === 0 && (
              <div className="radius-label" style={{ justifyContent: 'center' }}>
                Click two points on the globe to measure distance
              </div>
            )}
          </div>
        )}
      </div>

      {/* Search Results List - only show when on Search tab */}
      {activeTab === 'search' && searchQuery.trim() && (
        <div className={`glass-panel search-results-panel ${searchResultsMinimized ? 'minimized' : ''} ${searchResults.length <= 3 ? 'few-results' : 'many-results'}`}>
          <div className="search-results-header">
            <span>{searchResults.length} result{searchResults.length !== 1 ? 's' : ''} found</span>
            <button
              className="panel-minimize-btn"
              onClick={() => setSearchResultsMinimized(prev => !prev)}
              title={searchResultsMinimized ? "Maximize" : "Minimize"}
            >
              {searchResultsMinimized ? (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                </svg>
              ) : (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
              )}
            </button>
          </div>
          {!searchResultsMinimized && (
            <>
              {searchResults.length > 0 ? (
                <div
                  className="search-results-list"
                >
                  {searchResults.slice(0, 100).map((result) => (
                    <div
                      key={result.id}
                      className={`search-result-item${selectedSiteIds.includes(result.id) ? ' selected' : ''}`}
                      onMouseEnter={() => onSiteHover?.(result.id)}
                      onMouseLeave={() => onSiteHover?.(null)}
                    >
                      <div
                        className="search-result-main"
                        onClick={(e) => {
                          // Ctrl+click for multi-select, normal click for single select/toggle
                          onSiteListClick?.(result.id, e.ctrlKey || e.metaKey)
                          // Fly to site
                          onSearchResultSelect(result.id, false)
                        }}
                      >
                        <div className="search-result-content">
                          <div className="search-result-title">{result.title}</div>
                          {result.location && (
                            <div className="search-result-location">
                              {result.location}
                              {getCountryFlatFlagUrl(result.location) && (
                                <img
                                  src={getCountryFlatFlagUrl(result.location)!}
                                  alt=""
                                  className="search-result-flag"
                                />
                              )}
                            </div>
                          )}
                          <div className="search-result-meta">
                            {result.category && (
                              <span className="search-result-badge" style={{ borderColor: result.categoryColor, color: result.categoryColor }}>{result.category}</span>
                            )}
                            {result.period && (
                              <span className="search-result-badge" style={{ borderColor: result.periodColor, color: result.periodColor }}>{result.period}</span>
                            )}
                            {searchAllSources && result.sourceName && (
                              <span className="search-result-badge search-result-source" style={{ borderColor: result.sourceColor, color: result.sourceColor }}>{result.sourceName}</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <button
                        className="search-result-info-btn"
                        onClick={() => {
                          // Select and open popup (deselects when popup opens)
                          onSiteListClick?.(null)  // Clear selection since popup will open
                          onSearchResultSelect(result.id, true)
                        }}
                        title="Open details"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                          <polyline points="15 3 21 3 21 9"></polyline>
                          <line x1="10" y1="14" x2="21" y2="3"></line>
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="search-results-empty">No sites found</div>
              )}
            </>
          )}
        </div>
      )}

      {/* Proximity Results List - show when on Proximity tab with center set */}
      {activeTab === 'proximity' && proximityCenter && (
        <div className={`glass-panel search-results-panel ${searchResultsMinimized ? 'minimized' : ''} ${proximityResults.length <= 3 ? 'few-results' : 'many-results'}`}>
          <div className="search-results-header">
            <span>{proximityResults.length} site{proximityResults.length !== 1 ? 's' : ''} nearby</span>
            <button
              className="panel-minimize-btn"
              onClick={() => setSearchResultsMinimized(prev => !prev)}
              title={searchResultsMinimized ? "Maximize" : "Minimize"}
            >
              {searchResultsMinimized ? (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                </svg>
              ) : (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
              )}
            </button>
          </div>
          {!searchResultsMinimized && (
            <>
              {proximityResults.length > 0 ? (
                <div
                  className="search-results-list"
                >
                  {proximityResults.map((result) => (
                    <div
                      key={result.id}
                      className={`search-result-item${selectedSiteIds.includes(result.id) ? ' selected' : ''}`}
                      onMouseEnter={() => onSiteHover?.(result.id)}
                      onMouseLeave={() => onSiteHover?.(null)}
                    >
                      <div
                        className="search-result-main"
                        onClick={(e) => {
                          // Ctrl+click for multi-select, normal click for single select/toggle
                          onSiteListClick?.(result.id, e.ctrlKey || e.metaKey)
                          // Fly to site
                          onSearchResultSelect(result.id, false)
                        }}
                      >
                        <div className="search-result-content">
                          <div className="search-result-title">{result.title}</div>
                          {result.location && (
                            <div className="search-result-location">
                              {result.location}
                              {getCountryFlatFlagUrl(result.location) && (
                                <img
                                  src={getCountryFlatFlagUrl(result.location)!}
                                  alt=""
                                  className="search-result-flag"
                                />
                              )}
                            </div>
                          )}
                          <div className="search-result-meta">
                            {result.category && (
                              <span className="search-result-badge" style={{ borderColor: result.categoryColor, color: result.categoryColor }}>{result.category}</span>
                            )}
                            {result.period && (
                              <span className="search-result-badge" style={{ borderColor: result.periodColor, color: result.periodColor }}>{result.period}</span>
                            )}
                            {result.sourceName && (
                              <span className="search-result-badge search-result-source" style={{ borderColor: result.sourceColor, color: result.sourceColor }}>{result.sourceName}</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <button
                        className="search-result-info-btn"
                        onClick={() => {
                          // Select and open popup (deselects when popup opens)
                          onSiteListClick?.(null)  // Clear selection since popup will open
                          onSearchResultSelect(result.id, true)
                        }}
                        title="Open details"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                          <polyline points="15 3 21 3 21 9"></polyline>
                          <line x1="10" y1="14" x2="21" y2="3"></line>
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="search-results-empty">No sites in this area</div>
              )}
            </>
          )}
        </div>
      )}

      {/* Filter Mode Toggle - reordered: Age, Category, Source, Country */}
      {(() => {
        // Compute which filters are active (not at default values)
        const isAgeFilterActive = ageRange[0] !== defaultAgeRange[0] || ageRange[1] !== defaultAgeRange[1]
        const isCategoryFilterActive = selectedCategories.length > 0 && selectedCategories.length < categories.length
        const isCountryFilterActive = selectedCountries.length > 0 && selectedCountries.length < countries.length
        // Source default is "ancient_nerds" only - any other selection is an active filter
        const defaultSources = new Set(['ancient_nerds'])
        const isSourceFilterActive = !(selectedSources.length === 1 && defaultSources.has(selectedSources[0]))
        const hasAnyActiveFilter = isAgeFilterActive || isCategoryFilterActive || isCountryFilterActive || isSourceFilterActive

        return (
      <div className={`glass-panel filter-mode-toggle ${filterByMinimized ? 'minimized' : ''} ${filterMode === 'source' ? 'source-active' : ''} ${filterMode === 'category' ? 'category-active' : ''} ${filterMode === 'country' ? 'country-active' : ''}`}>
        <div className="filter-mode-header">
          <div className="filter-label">
            Filter By
            {hasAnyActiveFilter && <span className="filter-active-indicator" title="Filters active" />}
            {filterByMinimized && (
              <span className="minimized-info">
                {filterMode === 'category' && ` · ${searchQuery.trim()
                  ? [...new Set(searchResults.map(r => r.category).filter(Boolean))].length
                  : categories.length} categories`}
                {filterMode === 'source' && ` · ${sources.length} sources`}
                {filterMode === 'country' && ` · ${countries.length} countries`}
                {filterMode === 'age' && ` · ${formatYear(ageRange[0])} to ${formatYear(ageRange[1])}`}
              </span>
            )}
          </div>
          <div className="filter-header-buttons">
            {hasAnyActiveFilter && onResetAllFilters && (
              <button
                className="filter-reset-btn"
                onClick={onResetAllFilters}
                title="Reset all filters"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                  <path d="M3 3v5h5" />
                </svg>
              </button>
            )}
            <button
              className="panel-minimize-btn"
              onClick={() => setFilterByMinimized(prev => !prev)}
              title={filterByMinimized ? "Maximize" : "Minimize"}
            >
              {filterByMinimized ? (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                </svg>
              ) : (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
              )}
            </button>
          </div>
        </div>
        {!filterByMinimized && (
          <>
            <div className="toggle-buttons">
              <button
                className={`toggle-btn ${filterMode === 'age' ? 'active' : ''} ${isAgeFilterActive ? 'has-filter' : ''}`}
                onClick={() => onFilterModeChange('age')}
              >
                Age
                {isAgeFilterActive && <span className="filter-dot" />}
              </button>
              <button
                className={`toggle-btn ${filterMode === 'country' ? 'active' : ''} ${isCountryFilterActive ? 'has-filter' : ''}`}
                onClick={() => onFilterModeChange('country')}
              >
                Country
                {isCountryFilterActive && <span className="filter-dot" />}
              </button>
              <button
                className={`toggle-btn ${filterMode === 'category' ? 'active' : ''} ${isCategoryFilterActive ? 'has-filter' : ''}`}
                onClick={() => onFilterModeChange('category')}
              >
                Category
                {isCategoryFilterActive && <span className="filter-dot" />}
              </button>
              <button
                className={`toggle-btn ${filterMode === 'source' ? 'active' : ''} ${isSourceFilterActive ? 'has-filter' : ''}`}
                onClick={() => onFilterModeChange('source')}
              >
                Source
                {isSourceFilterActive && <span className="filter-dot" />}
              </button>
            </div>

            {/* Source Legend - Interactive */}
        {filterMode === 'source' && sources.length > 0 && (() => {
          // Split into primary (ancient_nerds + lyra) and secondary sources
          const PRIMARY_IDS = new Set(['ancient_nerds', 'lyra'])
          const primarySources = sources.filter(s => PRIMARY_IDS.has(s.id))
          const secondarySources = sources.filter(s => !PRIMARY_IDS.has(s.id))

          return (
            <div className="source-legend-interactive">
              <div className="source-legend-header">
                <span className="source-legend-title">Sources ({sources.length})</span>
                <div className="source-legend-actions">
                  <button className="legend-action-btn" onClick={selectAllSources} title="Select All">All</button>
                  <button className="legend-action-btn" onClick={clearSources} title="Clear All">None</button>
                </div>
              </div>
              <div className="source-legend-list">
                {/* Primary Source */}
                {primarySources.map(source => {
                  const isActive = selectedSources.includes(source.id)
                  return (
                    <button
                      key={source.id}
                      className={`source-legend-item ${isActive ? 'active' : 'inactive'}`}
                      onClick={() => toggleSource(source.id)}
                      title={`${source.name}: ${source.count.toLocaleString()} sites (Primary)`}
                    >
                      <span className="source-legend-dot" style={{ background: isActive ? source.color : '#444' }} />
                      <span className="source-legend-name">{source.name}</span>
                      <span className="source-legend-count">{source.count.toLocaleString()}</span>
                    </button>
                  )
                })}

                {/* Divider between primary and secondary */}
                {primarySources.length > 0 && secondarySources.length > 0 && (() => {
                  const unloadedSources = secondarySources.filter(s => !loadedSourceIds.has(s.id) && !loadingSources?.has(s.id))
                  const hasUnloadedSources = unloadedSources.length > 0

                  return (
                    <div className="source-legend-divider">
                      <span className="divider-line" />
                      <span className="divider-label">Other Sources</span>
                      <span className="divider-line" />
                      {hasUnloadedSources && onLoadSources && (
                        <button
                          className="load-all-sources-btn"
                          onClick={() => onLoadSources(unloadedSources.map(s => s.id))}
                          title={`Load all ${unloadedSources.length} remaining sources`}
                        >
                          Load All
                        </button>
                      )}
                    </div>
                  )
                })()}

                {/* Secondary Sources - always show, with load state */}
                {secondarySources.map(source => {
                  const isActive = selectedSources.includes(source.id)
                  const isSourceLoading = loadingSources?.has(source.id)
                  const isSourceLoaded = loadedSourceIds.has(source.id)
                  const needsLoading = !isSourceLoaded && !isSourceLoading
                  // Offline unavailable: in offline mode and source not cached
                  const isOfflineUnavailable = isOffline && !cachedSourceIds.has(source.id)

                  // Only block if loading OR (offline unavailable AND not currently active)
                  // This allows unchecking active sources even when offline
                  const shouldDisable = isSourceLoading || (isOfflineUnavailable && !isActive)

                  return (
                    <button
                      key={source.id}
                      className={`source-legend-item ${isActive ? 'active' : 'inactive'} ${isSourceLoading ? 'loading' : ''} ${needsLoading ? 'not-loaded' : ''} ${isOfflineUnavailable ? 'offline-unavailable' : ''}`}
                      onClick={() => {
                        if (isSourceLoading) return
                        // Always allow unchecking, only block checking when unavailable
                        if (isActive || !isOfflineUnavailable) {
                          toggleSource(source.id)
                        }
                      }}
                      title={
                        isOfflineUnavailable && !isActive ? `${source.name}: Not available offline. Open Download Manager or go online.` :
                        isSourceLoading ? `${source.name}: Loading...` :
                        needsLoading ? `Click to load ${source.name} (${source.count.toLocaleString()} sites)` :
                        `${source.name}: ${source.count.toLocaleString()} sites`
                      }
                      disabled={shouldDisable}
                    >
                      <span className="source-legend-dot" style={{ background: isActive ? source.color : '#444' }} />
                      <span className="source-legend-name">{source.name}</span>
                      {isSourceLoading ? (
                        <span className="source-legend-loading">
                          <span className="loading-dots">
                            <span>.</span><span>.</span><span>.</span>
                          </span>
                        </span>
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
            </div>
          )
        })()}

        {/* Category Legend - Interactive (Grouped) */}
        {filterMode === 'category' && (categories.length > 0 || (searchQuery.trim() && searchResults.length > 0)) && (() => {
          // When searching, only show categories from search results
          const baseCategories = searchQuery.trim()
            ? [...new Set(searchResults.map(r => r.category).filter(Boolean))].sort() as string[]
            : [...categories].sort()

          // Filter by category filter input
          const displayCategories = categoryFilter.trim()
            ? baseCategories.filter(c => c.toLowerCase().includes(categoryFilter.toLowerCase()))
            : baseCategories

          // Group categories by their group
          const grouped = new Map<CategoryGroup, string[]>()
          displayCategories.forEach(category => {
            const group = getCategoryGroup(category)
            if (!grouped.has(group)) grouped.set(group, [])
            grouped.get(group)!.push(category)
          })

          return (
            <div className="category-legend-interactive">
              <div className="category-legend-header">
                <span className="category-legend-title">Categories ({baseCategories.length})</span>
                <div className="category-legend-actions">
                  <button className="legend-action-btn" onClick={selectAllCategories} title="Select All">All</button>
                  <button className="legend-action-btn" onClick={clearCategories} title="Clear All">None</button>
                  <button className="legend-action-btn" onClick={invertCategories} title="Invert Selection">Invert</button>
                </div>
              </div>
              <div className="legend-filter-container">
                <input
                  type="text"
                  className="legend-filter-input"
                  placeholder="Filter categories..."
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                />
                {categoryFilter && (
                  <button className="legend-filter-clear" onClick={() => setCategoryFilter('')}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="6" x2="6" y2="18"></line>
                      <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                  </button>
                )}
              </div>
              <div className="category-legend-list">
                {CATEGORY_GROUP_ORDER.map(group => {
                  const categoriesInGroup = grouped.get(group)
                  if (!categoriesInGroup || categoriesInGroup.length === 0) return null

                  return (
                    <div key={group} className="category-group">
                      <div className="category-group-label">{group}</div>
                      <div className="category-group-items">
                        {categoriesInGroup.map(category => {
                          const color = getCategoryColor(category)
                          const isActive = selectedCategories.includes(category)
                          const isAvailable = availableCategories.includes(category)
                          return (
                            <button
                              key={category}
                              className={`category-legend-item ${isActive ? 'active' : 'inactive'} ${!isAvailable ? 'unavailable' : ''}`}
                              onClick={() => toggleCategory(category)}
                              title={isAvailable ? category : `${category} (no results with current filters)`}
                              style={{ borderColor: color, color: color }}
                            >
                              {category}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })()}

        {/* Country Legend - Interactive */}
        {filterMode === 'country' && (countries.length > 0 || (searchQuery.trim() && searchResults.length > 0)) && (() => {
          // When searching, only show countries from search results
          const baseCountries = searchQuery.trim()
            ? [...new Set(searchResults.map(r => r.location).filter(Boolean))].sort() as string[]
            : [...countries].sort()

          // Filter by country filter input
          const displayCountries = countryFilter.trim()
            ? baseCountries.filter(c => c.toLowerCase().includes(countryFilter.toLowerCase()))
            : baseCountries

          return (
            <div className="country-legend-interactive">
              <div className="country-legend-header">
                <span className="country-legend-title">Countries ({baseCountries.length})</span>
                <div className="country-legend-actions">
                  <button className="legend-action-btn" onClick={selectAllCountries} title="Select All">All</button>
                  <button className="legend-action-btn" onClick={clearCountries} title="Clear All">None</button>
                  <button className="legend-action-btn" onClick={invertCountries} title="Invert Selection">Invert</button>
                </div>
              </div>
              <div className="legend-filter-container country-filter-row">
                <div className="country-filter-input-wrapper">
                  <input
                    type="text"
                    className="legend-filter-input"
                    placeholder="Filter..."
                    value={countryFilter}
                    onChange={(e) => setCountryFilter(e.target.value)}
                  />
                  {countryFilter && (
                    <button className="legend-filter-clear" onClick={() => setCountryFilter('')}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                      </svg>
                    </button>
                  )}
                </div>
                <button
                  className="country-display-toggle"
                  onClick={() => setCountryDisplayMode(m => m === 'flags' ? 'badges' : 'flags')}
                >
                  {countryDisplayMode === 'flags' ? 'Badges' : 'Flags'}
                </button>
              </div>
              <div className={`country-legend-list ${countryDisplayMode === 'flags' ? 'flag-mode' : ''}`}>
                {(() => {
                  // Group countries by continent
                  const grouped = new Map<Continent | 'Other', string[]>()
                  displayCountries.forEach(country => {
                    const continent = getCountryContinent(country)
                    const key = continent || 'Other'
                    if (!grouped.has(key)) grouped.set(key, [])
                    grouped.get(key)!.push(country)
                  })

                  // Render in continent order
                  const orderedContinents: (Continent | 'Other')[] = [...CONTINENT_ORDER, 'Other']
                  return orderedContinents.map(continent => {
                    const countriesInContinent = grouped.get(continent)
                    if (!countriesInContinent || countriesInContinent.length === 0) return null

                    return (
                      <div key={continent} className="continent-group">
                        <div className="continent-label">{continent}</div>
                        <div className={`continent-countries ${countryDisplayMode === 'flags' ? 'flag-mode' : ''}`}>
                          {countriesInContinent.map(country => {
                            const flagUrl = getCountryFlatFlagUrl(country)
                            const color = countryColors[country] || '#a855f7'
                            const isActive = selectedCountries.includes(country)
                            const isAvailable = availableCountries.includes(country)

                            return countryDisplayMode === 'flags' && flagUrl ? (
                              <button
                                key={country}
                                className={`country-flag-item ${isActive ? 'active' : 'inactive'} ${!isAvailable ? 'unavailable' : ''}`}
                                onClick={() => toggleCountry(country)}
                                title={country}
                              >
                                <img src={flagUrl} alt={country} />
                              </button>
                            ) : (
                              <button
                                key={country}
                                className={`country-legend-item ${isActive ? 'active' : 'inactive'} ${!isAvailable ? 'unavailable' : ''}`}
                                onClick={() => toggleCountry(country)}
                                title={isAvailable ? country : `${country} (no results with current filters)`}
                                style={{ borderColor: color, color: color }}
                              >
                                {country}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    )
                  })
                })()}
              </div>
            </div>
          )
        })()}

        {/* Age Range Slider */}
        {filterMode === 'age' && (
          <div className="age-legend">
            <div className="age-range-slider">
              <div className="age-range-track" />
              <div className="age-zero-marker" />
              <input
                type="range"
                className="age-slider age-slider-min"
                min={-5000}
                max={1500}
                step={100}
                value={ageRange[0]}
                onChange={(e) => {
                  const newMin = Number(e.target.value)
                  if (newMin < ageRange[1]) {
                    onAgeRangeChange([newMin, ageRange[1]])
                  }
                }}
              />
              <input
                type="range"
                className="age-slider age-slider-max"
                min={-5000}
                max={1500}
                step={100}
                value={ageRange[1]}
                onChange={(e) => {
                  const newMax = Number(e.target.value)
                  if (newMax > ageRange[0]) {
                    onAgeRangeChange([ageRange[0], newMax])
                  }
                }}
              />
              <div className="age-range-labels">
                <span className="age-label-min">{formatYear(ageRange[0])}</span>
                <span className="age-label-max">{formatYear(ageRange[1])}</span>
              </div>
            </div>
          </div>
        )}
          </>
        )}
      </div>
        )
      })()}

      {/* Count */}
      <div className="site-count">
        Showing <AnimatedCounter value={filteredCount} /> of <AnimatedCounter value={totalSites} isLoading={loadingSources && loadingSources.size > 0} /> sites
      </div>
    </div>
  )
}

// Memoize to prevent unnecessary re-renders when parent state changes
export default memo(FilterPanel)
