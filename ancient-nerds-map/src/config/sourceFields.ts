/**
 * Source-specific field display configuration.
 *
 * Defines which raw_data fields to display in the site popup
 * for each data source. This enables rich metadata display
 * without cluttering the UI for sources that don't have
 * specialized data.
 */

/** Format types for field values */
export type FieldFormat = 'text' | 'number' | 'currency' | 'boolean' | 'year'

/** Field configuration for display */
export interface FieldConfig {
  key: string           // Key in raw_data object
  label: string         // Display label
  format?: FieldFormat  // How to format the value
  precision?: number    // Decimal places for numbers
  unit?: string         // Unit suffix (e.g., 'km', 'm', 'Tg')
}

/**
 * Source-specific field configurations.
 *
 * Each source ID maps to an array of fields to display.
 * Sources not listed here will not show a metadata section.
 */
export const SOURCE_DISPLAY_FIELDS: Record<string, FieldConfig[]> = {
  // =============================================================================
  // NCEI Natural Hazards
  // =============================================================================

  ncei_earthquakes: [
    { key: 'magnitude', label: 'Magnitude', format: 'number', precision: 1 },
    { key: 'depth_km', label: 'Depth', format: 'number', unit: 'km' },
    { key: 'intensity', label: 'Intensity', format: 'number', precision: 1 },
    { key: 'deaths_total', label: 'Deaths', format: 'number' },
    { key: 'injuries_total', label: 'Injuries', format: 'number' },
    { key: 'damage_millions_usd', label: 'Damage', format: 'currency' },
    { key: 'houses_destroyed', label: 'Houses Destroyed', format: 'number' },
  ],

  ncei_tsunamis: [
    { key: 'cause', label: 'Cause', format: 'text' },
    { key: 'max_runup_m', label: 'Max Wave Height', format: 'number', unit: 'm' },
    { key: 'deaths_total', label: 'Deaths', format: 'number' },
    { key: 'injuries_total', label: 'Injuries', format: 'number' },
    { key: 'damage_millions_usd', label: 'Damage', format: 'currency' },
    { key: 'houses_destroyed_total', label: 'Houses Destroyed', format: 'number' },
    { key: 'eq_magnitude', label: 'Quake Magnitude', format: 'number', precision: 1 },
  ],

  ncei_tsunami_obs: [
    { key: 'water_height_m', label: 'Wave Height', format: 'number', unit: 'm' },
    { key: 'distance_from_source_km', label: 'Distance from Source', format: 'number', unit: 'km' },
    { key: 'arrival_time', label: 'Arrival Time', format: 'text' },
  ],

  ncei_volcanoes: [
    { key: 'vei', label: 'VEI', format: 'number' },
    { key: 'morphology', label: 'Type', format: 'text' },
    { key: 'elevation_m', label: 'Elevation', format: 'number', unit: 'm' },
    { key: 'deaths_total', label: 'Deaths', format: 'number' },
  ],

  // =============================================================================
  // Volcanic / Climate
  // =============================================================================

  volcanic_holvol: [
    { key: 'vei', label: 'VEI', format: 'number' },
    { key: 'sulfur_tg', label: 'Sulfur Emission', format: 'number', unit: 'Tg' },
    { key: 'hemisphere', label: 'Hemisphere', format: 'text' },
    { key: 'latitude_ice_core', label: 'Ice Core Lat', format: 'number', precision: 1 },
  ],

  // =============================================================================
  // Geological
  // =============================================================================

  earth_impacts: [
    { key: 'diameter_km', label: 'Crater Diameter', format: 'number', unit: 'km' },
    { key: 'age_millions_years_ago', label: 'Age', format: 'number', unit: 'Ma' },
    { key: 'target_rock', label: 'Target Rock', format: 'text' },
    { key: 'bolid_type', label: 'Meteorite Type', format: 'text' },
    { key: 'exposed', label: 'Exposed', format: 'boolean' },
    { key: 'drilled', label: 'Drilled', format: 'boolean' },
  ],

  // =============================================================================
  // Archaeological / Epigraphic
  // =============================================================================

  inscriptions_edh: [
    { key: 'inscription_type', label: 'Type', format: 'text' },
    { key: 'material', label: 'Material', format: 'text' },
    { key: 'object_type', label: 'Object', format: 'text' },
    { key: 'province', label: 'Province', format: 'text' },
  ],

  // =============================================================================
  // Numismatics
  // =============================================================================

  coins_nomisma: [
    { key: 'type', label: 'Type', format: 'text' },
    { key: 'denomination_uri', label: 'Denomination', format: 'text' },
    { key: 'material_uri', label: 'Material', format: 'text' },
  ],

  // =============================================================================
  // Maritime
  // =============================================================================

  shipwrecks_oxrep: [
    { key: 'cargo_type', label: 'Cargo', format: 'text' },
    { key: 'ship_size', label: 'Ship Size', format: 'text' },
    { key: 'depth_m', label: 'Depth', format: 'number', unit: 'm' },
    { key: 'amphora_count', label: 'Amphorae', format: 'number' },
  ],

  // =============================================================================
  // 3D Models
  // =============================================================================

  models_sketchfab: [
    { key: 'face_count', label: 'Faces', format: 'number' },
    { key: 'vertex_count', label: 'Vertices', format: 'number' },
    { key: 'animated', label: 'Animated', format: 'boolean' },
  ],

  // =============================================================================
  // Boundaries / Polities
  // =============================================================================

  boundaries_seshat: [
    { key: 'polity_name', label: 'Polity', format: 'text' },
    { key: 'ngo', label: 'NGO', format: 'text' },
    { key: 'area_km2', label: 'Area', format: 'number', unit: 'km²' },
  ],

  // =============================================================================
  // Archaeological / Heritage Sources
  // =============================================================================

  unesco: [
    { key: 'category', label: 'Category', format: 'text' },
    { key: 'criteria_txt', label: 'Criteria', format: 'text' },
    { key: 'date_inscribed', label: 'Date Inscribed', format: 'text' },
    { key: 'states_names', label: 'States', format: 'text' },
    { key: 'region_en', label: 'Region', format: 'text' },
    { key: 'area_hectares', label: 'Area', format: 'number', unit: 'ha' },
    { key: 'danger', label: 'In Danger', format: 'boolean' },
    { key: 'transboundary', label: 'Transboundary', format: 'boolean' },
  ],

  pleiades: [
    { key: 'featureTypes', label: 'Feature Types', format: 'text' },
    { key: 'timePeriodsKeys', label: 'Time Periods', format: 'text' },
    { key: 'minDate', label: 'Earliest Date', format: 'year' },
    { key: 'maxDate', label: 'Latest Date', format: 'year' },
    { key: 'locationPrecision', label: 'Precision', format: 'text' },
    { key: 'connectsWith', label: 'Connects With', format: 'text' },
    { key: 'extent', label: 'Extent', format: 'text' },
  ],

  historic_england: [
    { key: 'Name', label: 'Name', format: 'text' },
    { key: 'ListEntry', label: 'List Entry', format: 'text' },
    { key: 'SchedDate', label: 'Scheduled', format: 'text' },
    { key: 'AmendDate', label: 'Amended', format: 'text' },
    { key: 'NGR', label: 'Grid Ref', format: 'text' },
    { key: 'area_ha', label: 'Area', format: 'number', unit: 'ha' },
  ],

  wikidata: [
    { key: 'instance_type', label: 'Type', format: 'text' },
    { key: 'country', label: 'Country', format: 'text' },
    { key: 'inception', label: 'Inception', format: 'text' },
    { key: 'dissolution', label: 'Dissolution', format: 'text' },
    { key: 'website', label: 'Website', format: 'text' },
    { key: 'commons_category', label: 'Commons', format: 'text' },
  ],

  arachne: [
    { key: 'subtitle', label: 'Subtitle', format: 'text' },
    { key: 'category', label: 'Category', format: 'text' },
    { key: 'search_term', label: 'Search Term', format: 'text' },
  ],

  open_context: [
    { key: 'project label', label: 'Project', format: 'text' },
    { key: 'context label', label: 'Context', format: 'text' },
    { key: 'item_category', label: 'Category', format: 'text' },
    { key: 'uri', label: 'URI', format: 'text' },
  ],

  eamena: [
    { key: 'displaydescription', label: 'Description', format: 'text' },
    { key: 'site_function', label: 'Site Function', format: 'text' },
    { key: 'condition', label: 'Condition', format: 'text' },
  ],
}

/**
 * Format a field value for display.
 */
export function formatFieldValue(
  value: unknown,
  config: FieldConfig
): string | null {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const { format = 'text', precision, unit } = config

  switch (format) {
    case 'number': {
      const num = typeof value === 'number' ? value : parseFloat(String(value))
      if (isNaN(num)) return null
      const formatted = precision !== undefined ? num.toFixed(precision) : num.toLocaleString()
      return unit ? `${formatted} ${unit}` : formatted
    }

    case 'currency': {
      const num = typeof value === 'number' ? value : parseFloat(String(value))
      if (isNaN(num)) return null
      return `$${num.toFixed(1)}M`
    }

    case 'boolean': {
      // Only show boolean fields if true - don't clutter UI with "No" values
      return value ? 'Yes' : null
    }

    case 'year': {
      const num = typeof value === 'number' ? value : parseInt(String(value), 10)
      if (isNaN(num)) return null
      if (num < 0) {
        return `${Math.abs(num)} BCE`
      }
      return `${num} CE`
    }

    case 'text':
    default: {
      const str = String(value)
      // Clean up URI values
      if (str.startsWith('http://') || str.startsWith('https://')) {
        const parts = str.split('/')
        return parts[parts.length - 1] || str
      }
      // Capitalize first letter
      return str.charAt(0).toUpperCase() + str.slice(1)
    }
  }
}

/** Keys to skip in generic fallback rendering */
const SKIP_KEYS = new Set(['description_citations', 'description', 'short_description', 'name', 'title'])

/** Prettify a raw_data key: snake_case/camelCase → Title Case */
function prettifyKey(key: string): string {
  // snake_case → space-separated
  let result = key.replace(/_/g, ' ')
  // camelCase → space-separated
  result = result.replace(/([a-z])([A-Z])/g, '$1 $2')
  // Title case
  return result.replace(/\b\w/g, c => c.toUpperCase())
}

/** Format a generic value for display. Returns null if not displayable. */
function formatGenericValue(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'boolean') return value ? 'Yes' : null
  if (typeof value === 'number') return value.toLocaleString()
  if (Array.isArray(value)) {
    const items = value.filter(v => v !== null && v !== undefined && v !== '')
    if (items.length === 0) return null
    // Flatten simple arrays to comma-separated
    if (items.every(v => typeof v === 'string' || typeof v === 'number')) {
      return items.join(', ')
    }
    return null // Skip complex nested arrays
  }
  if (typeof value === 'object') return null // Skip nested objects
  const str = String(value)
  if (str.length === 0) return null
  // Truncate very long strings
  if (str.length > 200) return str.slice(0, 197) + '...'
  return str
}

/**
 * Get displayable fields for a source.
 *
 * Uses curated config if available, otherwise falls back to generic rendering
 * of all raw_data keys.
 */
export function getDisplayableFields(
  sourceId: string,
  rawData: Record<string, unknown> | null | undefined
): Array<{ config: FieldConfig; value: string }> {
  if (!rawData) return []

  const fieldConfigs = SOURCE_DISPLAY_FIELDS[sourceId]

  // Curated path: use defined field configs
  if (fieldConfigs) {
    const result: Array<{ config: FieldConfig; value: string }> = []
    for (const config of fieldConfigs) {
      const value = rawData[config.key]
      const formatted = formatFieldValue(value, config)
      if (formatted !== null) {
        result.push({ config, value: formatted })
      }
    }
    return result
  }

  // Generic fallback: auto-render all raw_data keys
  const result: Array<{ config: FieldConfig; value: string }> = []
  for (const [key, value] of Object.entries(rawData)) {
    if (SKIP_KEYS.has(key) || key.startsWith('_')) continue
    const formatted = formatGenericValue(value)
    if (formatted !== null) {
      result.push({
        config: { key, label: prettifyKey(key) },
        value: formatted,
      })
    }
  }
  return result
}

/**
 * Check if a source has curated metadata fields.
 */
export function hasMetadataFields(sourceId: string): boolean {
  return sourceId in SOURCE_DISPLAY_FIELDS
}

/**
 * Check if rawData would produce displayable fields (curated or generic).
 * Used to control "More Info" button visibility.
 */
export function hasDisplayableRawData(
  sourceId: string,
  rawData: Record<string, unknown> | null | undefined
): boolean {
  if (!rawData) return false
  return getDisplayableFields(sourceId, rawData).length > 0
}
