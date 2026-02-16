import { useState, useEffect, useCallback } from 'react'
import { CATEGORY_COLORS, SORTED_PERIODS } from '../constants/colors'
import { parseAnyCoordinate, formatCoordinate, applyCoordMask } from '../utils/coordinateParser'
import '../styles/site-form.css'

export interface SiteFormValues {
  name: string
  description: string
  country: string
  coordinates: string
  validCoords: [number, number] | null  // [lng, lat]
  category: string
  period: string
  sourceUrl: string
}

interface SiteFormProps {
  initialValues?: {
    name?: string; description?: string; country?: string
    lat?: number; lon?: number
    category?: string; period?: string; sourceUrl?: string
  }
  onChange: (values: SiteFormValues) => void
  showMapPicker?: boolean       // "Set on globe" button (default: false)
  onEnableMapPicker?: () => void
  showPeriod?: boolean          // Period dropdown (default: false)
  externalCoords?: [number, number] | null  // For map picker live updates
}

const CATEGORY_OPTIONS = Object.keys(CATEGORY_COLORS)
  .filter(key => key !== 'default' && key !== 'unknown')
  .map(key => key.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '))
  .sort()

// Period select options sorted chronologically
const PERIOD_OPTIONS = SORTED_PERIODS

export default function SiteForm({
  initialValues,
  onChange,
  showMapPicker = false,
  onEnableMapPicker,
  showPeriod = false,
  externalCoords,
}: SiteFormProps) {
  // Derive initial coordinate display from lat/lon
  const initialCoordDisplay = initialValues?.lat != null && initialValues?.lon != null
    ? formatCoordinate(initialValues.lon, initialValues.lat)
    : ''
  const initialValidCoords = initialValues?.lat != null && initialValues?.lon != null
    ? [initialValues.lon, initialValues.lat] as [number, number]
    : null

  const [name, setName] = useState(initialValues?.name || '')
  const [description, setDescription] = useState(initialValues?.description || '')
  const [country, setCountry] = useState(initialValues?.country || '')
  const [coordinates, setCoordinates] = useState(initialCoordDisplay)
  const [validCoords, setValidCoords] = useState<[number, number] | null>(initialValidCoords)
  const [category, setCategory] = useState(initialValues?.category || '')
  const [period, setPeriod] = useState(initialValues?.period || 'Unknown')
  const [sourceUrl, setSourceUrl] = useState(initialValues?.sourceUrl || '')
  const [isEditingCoords, setIsEditingCoords] = useState(false)

  // Emit changes to parent
  useEffect(() => {
    onChange({ name, description, country, coordinates, validCoords, category, period, sourceUrl })
  // eslint-disable-next-line react-hooks/exhaustive-deps -- only emit on value changes, not on onChange ref
  }, [name, description, country, coordinates, validCoords, category, period, sourceUrl])

  // Handle external coordinates (map picker)
  useEffect(() => {
    if (externalCoords && !isEditingCoords) {
      setCoordinates(formatCoordinate(externalCoords[0], externalCoords[1]))
      setValidCoords(externalCoords)
    }
  }, [externalCoords, isEditingCoords])

  // Coordinate handlers (from ContributeModal)
  const handleCoordFocus = useCallback(() => {
    setIsEditingCoords(true)
    if (validCoords) {
      setCoordinates(formatCoordinate(validCoords[0], validCoords[1]))
    }
  }, [validCoords])

  const handleCoordChange = useCallback((value: string) => {
    const directParse = parseAnyCoordinate(value)
    if (directParse) {
      setCoordinates(formatCoordinate(directParse[0], directParse[1]))
      setValidCoords(directParse)
      setIsEditingCoords(false)
      return
    }
    const { formatted } = applyCoordMask(value)
    setCoordinates(formatted)
    const digitCount = formatted.replace(/\D/g, '').length
    if (digitCount >= 12) {
      const parsed = parseAnyCoordinate(formatted)
      if (parsed) {
        setValidCoords(parsed)
        setIsEditingCoords(false)
      }
    }
  }, [])

  const handleCoordBlur = useCallback(() => {
    setIsEditingCoords(false)
    const parsed = parseAnyCoordinate(coordinates)
    if (parsed) {
      setValidCoords(parsed)
    }
  }, [coordinates])

  const handleClearCoords = useCallback(() => {
    setCoordinates('')
    setValidCoords(null)
  }, [])

  return (
    <div className="site-form">
      {/* Name */}
      <div className="site-form-group">
        <label>Name</label>
        <input
          type="text"
          className="site-form-input"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="e.g., Temple of Apollo at Delphi"
          autoComplete="off"
        />
      </div>

      {/* Country + Category Row */}
      <div className="site-form-row">
        <div className="site-form-group">
          <label>Country</label>
          <input
            type="text"
            className="site-form-input"
            value={country}
            onChange={e => setCountry(e.target.value)}
            placeholder="e.g., Greece"
            autoComplete="off"
          />
        </div>
        <div className="site-form-group">
          <label>Category</label>
          <select
            className="site-form-select"
            value={category}
            onChange={e => setCategory(e.target.value)}
          >
            <option value="">-- none --</option>
            {CATEGORY_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {/* Coordinates */}
      <div className="site-form-group">
        <label>Coordinates</label>
        <div className="site-form-coord-row">
          <div className="site-form-coord-wrapper">
            <input
              type="text"
              className={`site-form-input ${validCoords ? 'valid' : ''}`}
              placeholder="45.1234° N, 12.5678° E"
              value={coordinates}
              onChange={e => handleCoordChange(e.target.value)}
              onFocus={handleCoordFocus}
              onBlur={handleCoordBlur}
              onPaste={e => {
                e.preventDefault()
                handleCoordChange(e.clipboardData.getData('text'))
              }}
              autoComplete="off"
            />
            {coordinates && (
              <button type="button" className="site-form-coord-clear" onClick={handleClearCoords} title="Clear">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            )}
          </div>
          {showMapPicker && onEnableMapPicker && (
            <button type="button" className="coord-set-btn" onClick={onEnableMapPicker}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
                <path d="M2 12h20" />
              </svg>
              Set on globe
            </button>
          )}
        </div>
      </div>

      {/* Period (optional) */}
      {showPeriod && (
        <div className="site-form-group">
          <label>Period</label>
          <select
            className="site-form-select"
            value={period}
            onChange={e => setPeriod(e.target.value)}
          >
            {PERIOD_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      )}

      {/* Description */}
      <div className="site-form-group">
        <label>Description</label>
        <textarea
          className="site-form-textarea"
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Brief description of the site..."
          rows={3}
        />
      </div>

      {/* Source URL */}
      <div className="site-form-group">
        <label>Source URL</label>
        <input
          type="text"
          className="site-form-input"
          value={sourceUrl}
          onChange={e => setSourceUrl(e.target.value)}
          placeholder="https://..."
          autoComplete="off"
        />
      </div>
    </div>
  )
}
