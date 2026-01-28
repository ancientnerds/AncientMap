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

/**
 * Get displayable fields for a source.
 *
 * Filters to only fields that have non-null values in the raw_data.
 */
export function getDisplayableFields(
  sourceId: string,
  rawData: Record<string, unknown> | null | undefined
): Array<{ config: FieldConfig; value: string }> {
  if (!rawData) return []

  const fieldConfigs = SOURCE_DISPLAY_FIELDS[sourceId]
  if (!fieldConfigs) return []

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

/**
 * Check if a source has any displayable metadata fields.
 */
export function hasMetadataFields(sourceId: string): boolean {
  return sourceId in SOURCE_DISPLAY_FIELDS
}
