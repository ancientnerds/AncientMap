/**
 * Vector layer configuration for the globe
 * Maps layer keys to their data sources, colors, and rendering properties
 */

import { DETAIL_SCALE, type DetailLevel } from './globeConstants'
import globeLayerManifest from '../data/globeLayers.generated.json'

export const LAYER_CONFIG = {
  coastlines: {
    file: 'coast_hires',  // High-res World Base Map data: the 'hires' tier; start/detail come from the manifest
    category: 'physical',
    color: 0x00e0d0, // Teal
    radius: 1.002,
    label: 'Coastlines',
    custom: true
  },
  countryBorders: {
    file: 'admin_0_boundary_lines_land',  // Natural Earth 10 m, self-hosted in tiers (scripts/build_globe_layers.py)
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
    hasLOD: true,  // Enable 4-level LOD switching (ne_10m_, ne_50m_, ne_110m_)
    labelsFile: '/data/layers/coral_reef_labels.geojson',
  },
  glaciers: {
    file: 'glaciers',
    category: 'physical',
    color: 0x88ddff, // Ice blue
    radius: 1.002,
    label: 'Glaciers',
    custom: true,
    hasLOD: true,  // Enable 4-level LOD switching (ne_10m_, ne_50m_, ne_110m_)
    labelsFile: '/data/layers/glacier_labels.geojson',
  },
  plateBoundaries: {
    file: 'plate_boundaries_hires',
    category: 'geological',
    color: 0xFF6B6B,  // Coral red
    radius: 1.002,
    label: 'Tectonic Plates',
    custom: true,
    hasLOD: false,
    labelsFile: '/data/layers/tectonic_plate_labels.geojson',
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
 * Coastlines and borders come in tiers (plan U6, contract C1). The globe starts on `start`
 * (0.5 device px at the start view), the background queue swaps in `detail` (0.5 device px at
 * the Mapbox switch), and `hires` (today's coast_hires, coastlines only) loads when Mapbox
 * failed and the camera goes closer than the switch. The file names carry a content hash, so
 * the URLs need no cache-busting query.
 */
export type GlobeLayerKey = 'coastlines' | 'countryBorders'
export type LayerTier = 'start' | 'detail' | 'hires'
/** The tiers that replace the start tier in place. */
export type UpgradeTier = Exclude<LayerTier, 'start'>
/**
 * A coastline/border layer's tiers. In-flight and failed upgrades are kept per tier, so a
 * hi-res load that is on its way or failed never stands in for the detail tier.
 */
export interface GlobeLayerTierState {
  /** The tier on the globe; null until the start tier landed. */
  committed: LayerTier | null
  /** Upgrades on their way; a second request for the same tier joins the load. */
  inFlight: Partial<Record<UpgradeTier, Promise<void>>>
  /** Upgrades that failed, with their error: never fetched again. */
  failed: Partial<Record<UpgradeTier, unknown>>
}
export const GLOBE_LAYER_KEYS: readonly GlobeLayerKey[] = ['coastlines', 'countryBorders']

/** Nothing on the globe, nothing asked for. */
export function createGlobeLayerTiers(): Record<GlobeLayerKey, GlobeLayerTierState> {
  return {
    coastlines: { committed: null, inFlight: {}, failed: {} },
    countryBorders: { committed: null, inFlight: {}, failed: {} },
  }
}

const COAST_HIRES_URL = `/data/layers/${LAYER_CONFIG.coastlines.file}.geojson`
const TIER_RANK: Record<LayerTier, number> = { start: 0, detail: 1, hires: 2 }

export function isGlobeLayerKey(key: VectorLayerKey): key is GlobeLayerKey {
  return key === 'coastlines' || key === 'countryBorders'
}

/** Order of the tiers; `null` (nothing loaded yet) ranks below every tier. */
export function tierRank(tier: LayerTier | null): number {
  return tier === null ? -1 : TIER_RANK[tier]
}

export function getGlobeLayerUrl(key: GlobeLayerKey, tier: LayerTier): string {
  if (tier !== 'hires') return globeLayerManifest[key][tier]
  if (key !== 'coastlines') throw new Error(`${key} has no hires tier: its detail tier is the unsimplified source`)
  return COAST_HIRES_URL
}

/**
 * URL of a layer at a zoom detail level. Coastlines and borders always start at their start
 * tier; the higher tiers go through getGlobeLayerUrl.
 */
export function getLayerUrl(layerKey: VectorLayerKey, detail: DetailLevel): string {
  if (isGlobeLayerKey(layerKey)) return getGlobeLayerUrl(layerKey, 'start')
  const config = LAYER_CONFIG[layerKey]

  if ('hasLOD' in config && config.hasLOD) {
    // No LOD layer goes above the 10 m files: rivers_hires (59 MB) and lakes_hires (14 MB) would
    // block the browser, and coral reefs and glaciers have no _hires file at all.
    const cappedDetail = detail === 'high' ? 'medium' : detail
    return `/data/layers/ne_${DETAIL_SCALE[cappedDetail]}_${config.file}.geojson`
  }
  return `/data/layers/${config.file}.geojson`
}

/**
 * Every file the globe can fetch for a layer, each once: what the offline download must store
 * (OfflineFetch matches the Cache API by exact URL).
 */
export function getLayerFiles(layerKey: VectorLayerKey): string[] {
  const files = isGlobeLayerKey(layerKey)
    ? [getGlobeLayerUrl(layerKey, 'start'), getGlobeLayerUrl(layerKey, 'detail'), ...(layerKey === 'coastlines' ? [COAST_HIRES_URL] : [])]
    : (Object.keys(DETAIL_SCALE) as DetailLevel[]).map(detail => getLayerUrl(layerKey, detail))
  const config = LAYER_CONFIG[layerKey]
  if ('labelsFile' in config) files.push(config.labelsFile)
  return [...new Set(files)]
}
