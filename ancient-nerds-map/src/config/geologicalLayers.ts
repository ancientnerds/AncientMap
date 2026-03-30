/**
 * Geological layer configuration for the globe
 * North Sea overlay data from the Unpath'd Waters project (University of Bradford, CC BY 4.0)
 */

export interface GeologicalLayerConfig {
  file: string
  label: string
  color: number
  group: GeologicalLayerGroup
  radius: number
}

export type GeologicalLayerGroup = 'Landscape' | 'Peat' | 'Research'

// Colors follow geological mapping conventions, brightened for dark globe background:
// - Fluvial/alluvial: blues (distinct from existing rivers #2196f3 and coastlines #00e0d0)
// - Elevated terrain: yellow (standard for topographic highs)
// - Drainage: greens (fluvial systems)
// - Peat/organic: warm amber/orange (organic sediment convention)
// - Archaeological: coral red (standard in arch. mapping)
// - Research points: distinct markers (amber, purple)
export const GEOLOGICAL_LAYER_CONFIG = {
  palaeochannels: {
    file: 'palaeochannels',
    label: 'Palaeochannels & Lakes',
    color: 0x5BC0EB,    // Bright sky blue — fluvial deposits
    group: 'Landscape' as const,
    radius: 1.002,
  },
  highGround: {
    file: 'high_ground',
    label: 'High Ground Features',
    color: 0xFDE74C,    // Bright yellow — elevated terrain
    group: 'Landscape' as const,
    radius: 1.002,
  },
  palaeovalleysLGM: {
    file: 'palaeovalleys_lgm',
    label: 'Palaeovalleys (LGM)',
    color: 0x9BC53D,    // Yellow-green — ancient drainage
    group: 'Landscape' as const,
    radius: 1.002,
  },
  drainage80k20k: {
    file: 'drainage_80k_20k',
    label: 'Drainage (80k-20k)',
    color: 0x56E39F,    // Seafoam green — older drainage
    group: 'Landscape' as const,
    radius: 1.002,
  },
  drainage11k: {
    file: 'drainage_11k',
    label: 'Drainage (~11ka)',
    color: 0x59C3C3,    // Teal-cyan — recent drainage
    group: 'Landscape' as const,
    radius: 1.002,
  },
  peatPolygons: {
    file: 'peat_polygons',
    label: 'Peat Deposits',
    color: 0xE8985E,    // Warm amber — organic deposits
    group: 'Peat' as const,
    radius: 1.002,
  },
  peatPoints: {
    file: 'peat_points',
    label: 'Peat Core Points',
    color: 0xC45BAA,    // Orchid purple — sample/core locations
    group: 'Peat' as const,
    radius: 1.002,
  },
  archaeologicalFinds: {
    file: 'archaeological_finds',
    label: 'Archaeological Finds',
    color: 0xF45B69,    // Coral red — archaeological convention
    group: 'Research' as const,
    radius: 1.002,
  },
  boreholes: {
    file: 'boreholes',
    label: 'Boreholes',
    color: 0xF7B32B,    // Amber — survey/research points
    group: 'Research' as const,
    radius: 1.002,
  },
} as const

export type GeologicalLayerKey = keyof typeof GEOLOGICAL_LAYER_CONFIG

export type GeologicalLayerVisibility = Record<GeologicalLayerKey, boolean>

export const GEOLOGICAL_LAYER_KEYS = Object.keys(GEOLOGICAL_LAYER_CONFIG) as GeologicalLayerKey[]

export const GEOLOGICAL_GROUPS: { group: GeologicalLayerGroup; label: string; layers: GeologicalLayerKey[] }[] = [
  {
    group: 'Landscape',
    label: 'Landscape',
    layers: ['palaeochannels', 'highGround', 'palaeovalleysLGM', 'drainage80k20k', 'drainage11k'],
  },
  {
    group: 'Peat',
    label: 'Peat',
    layers: ['peatPolygons', 'peatPoints'],
  },
  {
    group: 'Research',
    label: 'Research',
    layers: ['archaeologicalFinds', 'boreholes'],
  },
]

export function getGeologicalLayerUrl(key: GeologicalLayerKey): string {
  return `/data/geological/${GEOLOGICAL_LAYER_CONFIG[key].file}.geojson`
}
