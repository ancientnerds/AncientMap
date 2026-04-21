/**
 * Geological layer configuration for the globe.
 *
 * Sources:
 *   - Unpath'd Waters (University of Bradford, CC BY 4.0) — North Sea palaeolandscape (9 static layers)
 *   - Sturt et al. 2013 (Archaeology Data Service, CC BY) — UK/Ireland palaeo-coastlines (22 time slices)
 *
 * Layer model:
 *   - Static layer → one GeoJSON file, `file` field resolves the URL.
 *   - Temporal layer → `timeSteps[]` array of slices; `getGeologicalLayerUrl(key, index)`
 *     picks the active slice. One GeologicalLayerKey per temporal GROUP (not per slice).
 */

// ============================================================================
// Source registry (citation / license / DOI)
// ============================================================================

export interface LayerSource {
  sourceId: string
  sourceName: string
  license: string
  citation: string
  doi?: string
}

export const LAYER_SOURCES: Record<string, LayerSource> = {
  unpathd_waters: {
    sourceId: 'unpathd_waters',
    sourceName: "Unpath'd Waters Palaeolandscapes Data Package",
    license: 'CC BY 4.0',
    citation:
      "University of Bradford (2025) Digital Data from the Land Beneath the Sea Palaeolandscapes Project (Unpath'd Waters), 2016-2024",
    doi: 'https://doi.org/10.5284/1126107',
  },
  sturt_2013: {
    sourceId: 'sturt_2013',
    sourceName: "Sturt et al. 2013 — 'Stepping Stones' sea-level reconstructions",
    license: 'CC BY 4.0',
    citation:
      'Sturt, F., Garrow, D., Bradley, S. (2013). New models of North West European Holocene palaeogeography and inundation. Journal of Archaeological Science.',
    doi: 'https://doi.org/10.5284/1021326',
  },
}

// ============================================================================
// Time-step descriptor (for temporal layers)
// ============================================================================

export interface TimeStep {
  /** Base filename without extension (e.g. 'sturt_2013_11000bp'). */
  file: string
  /** Years before present. */
  year: number
  /** UI label (e.g. '11,000 BP' or 'LGM (~20ka)'). */
  label: string
}

/** Sturt 2013 time slices: 11,000 → 500 BP at 500-year intervals (22 slices). */
const STURT_2013_TIME_STEPS: TimeStep[] = [
  11000, 10500, 10000, 9500, 9000, 8500, 8000, 7500, 7000, 6500, 6000, 5500,
  5000, 4500, 4000, 3500, 3000, 2500, 2000, 1500, 1000, 500,
].map((year) => ({
  file: `sturt_2013_${year}bp`,
  year,
  label: year >= 1000 ? `${(year / 1000).toLocaleString('en-US', { maximumFractionDigits: 1 })}ka` : `${year} BP`,
}))

// ============================================================================
// Layer config
// ============================================================================

export interface GeologicalLayerConfig {
  /** Source identifier (matches LAYER_SOURCES key). */
  sourceId: string
  /** Base GeoJSON filename (no extension). For temporal layers this is the default (slice 0) file. */
  file: string
  /** If present, this is a temporal layer — array drives the time-step selector UI. */
  timeSteps?: TimeStep[]
  label: string
  color: number
  group: GeologicalLayerGroup
  radius: number
}

export type GeologicalLayerGroup = 'Landscape' | 'Peat' | 'Research' | 'SeaLevel'

// Colors follow geological mapping conventions, brightened for dark globe background:
// - Fluvial/alluvial: blues — palaeo-water (distinct from rivers #2196f3 and coastlines #00e0d0)
// - Elevated terrain: yellow (standard for topographic highs)
// - Drainage: greens (fluvial systems)
// - Peat/organic: warm amber/orange
// - Archaeological: coral red
// - Research points: amber / purple
// - Sea level / palaeo-coastlines: bright blue (time-series)
export const GEOLOGICAL_LAYER_CONFIG = {
  palaeochannels: {
    sourceId: 'unpathd_waters',
    file: 'palaeochannels',
    label: 'Palaeochannels & Lakes',
    color: 0x5BC0EB,
    group: 'Landscape' as const,
    radius: 1.002,
  },
  highGround: {
    sourceId: 'unpathd_waters',
    file: 'high_ground',
    label: 'High Ground Features',
    color: 0xFDE74C,
    group: 'Landscape' as const,
    radius: 1.002,
  },
  palaeovalleysLGM: {
    sourceId: 'unpathd_waters',
    file: 'palaeovalleys_lgm',
    label: 'Palaeovalleys (LGM)',
    color: 0x9BC53D,
    group: 'Landscape' as const,
    radius: 1.002,
  },
  drainage80k20k: {
    sourceId: 'unpathd_waters',
    file: 'drainage_80k_20k',
    label: 'Drainage (80k-20k)',
    color: 0x56E39F,
    group: 'Landscape' as const,
    radius: 1.002,
  },
  drainage11k: {
    sourceId: 'unpathd_waters',
    file: 'drainage_11k',
    label: 'Drainage (~11ka)',
    color: 0x59C3C3,
    group: 'Landscape' as const,
    radius: 1.002,
  },
  peatPolygons: {
    sourceId: 'unpathd_waters',
    file: 'peat_polygons',
    label: 'Peat Deposits',
    color: 0xE8985E,
    group: 'Peat' as const,
    radius: 1.002,
  },
  peatPoints: {
    sourceId: 'unpathd_waters',
    file: 'peat_points',
    label: 'Peat Core Points',
    color: 0xC45BAA,
    group: 'Peat' as const,
    radius: 1.002,
  },
  archaeologicalFinds: {
    sourceId: 'unpathd_waters',
    file: 'archaeological_finds',
    label: 'Archaeological Finds',
    color: 0xF45B69,
    group: 'Research' as const,
    radius: 1.002,
  },
  boreholes: {
    sourceId: 'unpathd_waters',
    file: 'boreholes',
    label: 'Boreholes',
    color: 0xF7B32B,
    group: 'Research' as const,
    radius: 1.002,
  },
  sturt2013: {
    sourceId: 'sturt_2013',
    file: STURT_2013_TIME_STEPS[0].file,
    timeSteps: STURT_2013_TIME_STEPS,
    label: 'UK Sea Level (Sturt 2013)',
    color: 0x3B82F6,
    group: 'SeaLevel' as const,
    radius: 1.002,
  },
} as const satisfies Record<string, GeologicalLayerConfig>

export type GeologicalLayerKey = keyof typeof GEOLOGICAL_LAYER_CONFIG

export type GeologicalLayerVisibility = Record<GeologicalLayerKey, boolean>

export const GEOLOGICAL_LAYER_KEYS = Object.keys(GEOLOGICAL_LAYER_CONFIG) as GeologicalLayerKey[]

export const GEOLOGICAL_GROUPS: { group: GeologicalLayerGroup; label: string; layers: GeologicalLayerKey[] }[] = [
  {
    group: 'SeaLevel',
    label: 'Sea Level',
    layers: ['sturt2013'],
  },
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

/**
 * Resolve the GeoJSON URL for a layer.
 *
 * - Static layer → `/data/geological/{file}.geojson`
 * - Temporal layer with `timeStepIndex` → `/data/geological/{timeSteps[index].file}.geojson`
 * - Temporal layer without index → `timeStepIndex = 0` (default / first slice)
 */
export function getGeologicalLayerUrl(key: GeologicalLayerKey, timeStepIndex?: number): string {
  const cfg = GEOLOGICAL_LAYER_CONFIG[key] as GeologicalLayerConfig
  if (cfg.timeSteps && cfg.timeSteps.length > 0) {
    const idx = Math.max(0, Math.min(cfg.timeSteps.length - 1, timeStepIndex ?? 0))
    return `/data/geological/${cfg.timeSteps[idx].file}.geojson`
  }
  return `/data/geological/${cfg.file}.geojson`
}

/** Whether a given layer is temporal (has time-step slices). */
export function isTemporalLayer(key: GeologicalLayerKey): boolean {
  return !!(GEOLOGICAL_LAYER_CONFIG[key] as GeologicalLayerConfig).timeSteps?.length
}
