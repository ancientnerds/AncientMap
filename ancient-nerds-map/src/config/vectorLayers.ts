/**
 * Vector layer configuration for the globe
 * Maps layer keys to their data sources, colors, and rendering properties
 */

import { DETAIL_SCALE, type DetailLevel } from './globeConstants'

export const LAYER_CONFIG = {
  coastlines: {
    file: 'coast_hires',  // High-res World Base Map data
    category: 'physical',
    color: 0x00e0d0, // Teal
    radius: 1.002,
    label: 'Coastlines',
    custom: true
  },
  countryBorders: {
    file: 'admin_0_boundary_lines_land',
    category: 'cultural',
    color: 0x00e0d0, // Teal (same as coastlines)
    radius: 1.002, // Same as all other layers - no parallax
    label: 'Country Borders',
    custom: false
  },
  rivers: {
    file: 'rivers',  // Base name - LOD adds ne_XXm_ prefix or _hires suffix
    category: 'physical',
    color: 0x2196f3,
    radius: 1.002, // Same as coastlines
    label: 'Rivers',
    custom: true,
    hasLOD: true  // Enable 4-level LOD switching
  },
  lakes: {
    file: 'lakes',  // Base name - LOD adds ne_XXm_ prefix or _hires suffix
    category: 'physical',
    color: 0x1976d2,
    radius: 1.002, // Same as coastlines
    label: 'Lakes',
    custom: true,
    hasLOD: true  // Enable 4-level LOD switching
  },
  coralReefs: {
    file: 'coral_reefs',
    category: 'physical',
    color: 0xff6b9d, // Coral pink
    radius: 1.002,
    label: 'Coral Reefs',
    custom: true,
    hasLOD: true  // Enable 4-level LOD switching (ne_10m_, ne_50m_, ne_110m_)
  },
  glaciers: {
    file: 'glaciers',
    category: 'physical',
    color: 0x88ddff, // Ice blue
    radius: 1.002,
    label: 'Glaciers',
    custom: true,
    hasLOD: true  // Enable 4-level LOD switching (ne_10m_, ne_50m_, ne_110m_)
  },
  plateBoundaries: {
    file: 'plate_boundaries_hires',
    category: 'geological',
    color: 0xFF6B6B,  // Coral red
    radius: 1.002,
    label: 'Tectonic Plates',
    custom: true,
    hasLOD: false
  }
} as const

export type VectorLayerKey = keyof typeof LAYER_CONFIG

export interface VectorLayerVisibility {
  coastlines: boolean
  countryBorders: boolean
  rivers: boolean
  lakes: boolean
  coralReefs: boolean
  glaciers: boolean
  plateBoundaries: boolean
}

/**
 * Generate URL for a vector layer based on detail level
 */
export function getLayerUrl(layerKey: VectorLayerKey, detail: DetailLevel): string {
  const config = LAYER_CONFIG[layerKey]

  // Handle LOD-enabled layers (rivers, lakes, glaciers)
  if ('hasLOD' in config && config.hasLOD) {
    // Cap rivers and lakes at 'medium' detail - hires files are too large (59MB rivers, 14MB lakes)
    // This prevents browser crashes from JSON.parse() blocking main thread
    const cappedDetail = (layerKey === 'rivers' || layerKey === 'lakes') && detail === 'high'
      ? 'medium'
      : detail

    if (cappedDetail === 'high') {
      return `/data/layers/${config.file}_hires.geojson`
    }
    const cappedScale = DETAIL_SCALE[cappedDetail]
    return `/data/layers/ne_${cappedScale}_${config.file}.geojson`
  }

  const scale = DETAIL_SCALE[detail]

  if (config.custom) {
    // High-res files don't have scale prefix, NE-derived files do
    if (config.file.endsWith('_hires')) {
      return `/data/layers/${config.file}.geojson`
    }
    return `/data/layers/ne_${scale}_${config.file}.geojson`
  }
  // Natural Earth layers from GitHub - 'hires' maps to '10m' for NE
  const neScale = detail === 'high' ? '10m' : scale
  return `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_${neScale}_${config.file}.geojson`
}
