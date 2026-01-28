/**
 * Data types for ANCIENT NERDS Map - Three.js Globe
 *
 * Matches the static export format from pipeline/static_exporter.py
 * Compact keys for smaller file sizes, expanded for internal use.
 */

// =============================================================================
// Source Metadata (sources.json)
// =============================================================================

/** Compact source format from JSON export */
export interface SourceMetaCompact {
  n: string       // name
  d: string       // description
  c: string       // color (hex)
  i?: string      // icon
  cat: string     // category
  cnt: number     // record count
  lic?: string    // license
  att?: string    // attribution
  on: boolean     // enabled
  url?: string    // source homepage URL
  primary?: boolean       // is primary source (Ancient Nerds original)
  enabledByDefault?: boolean  // enabled by default
}

/** Expanded source metadata for internal use */
export interface SourceMeta {
  id: string
  name: string
  description: string
  color: string
  icon?: string
  category: string
  recordCount: number
  license?: string
  attribution?: string
  enabled: boolean
  url?: string    // source homepage URL
  isPrimary?: boolean        // Whether this is the primary source (Ancient Nerds original)
  enabledByDefault?: boolean // Whether this source is enabled by default
  priority?: number          // Display priority (lower = higher priority)
}

/** sources.json file format */
export interface SourcesFile {
  sources: Record<string, SourceMetaCompact>
  total: number
  exported_at: string
}

// =============================================================================
// Site Data (sites/index.json)
// =============================================================================

/** Compact site format from JSON export (for markers) */
export interface SiteCompact {
  i: string       // id
  n: string       // name
  la: number      // latitude
  lo: number      // longitude
  s: string       // source_id
  t?: string      // type (optional)
  d?: string      // description (optional)
  l?: string      // location/country (optional)
  p?: string      // period name (optional)
  u?: string      // source URL (optional)
  im?: string     // image URL (optional)
}

/** Expanded site for internal use */
export interface Site {
  id: string
  name: string
  lat: number
  lon: number
  sourceId: string
  type?: string
  description?: string
  location?: string
  period?: string
  sourceUrl?: string
  imageUrl?: string
  periodStart?: number | null
  periodEnd?: number | null
  image?: string | null  // thumbnail URL from API
}

/** sites/index.json file format */
export interface SiteIndexFile {
  sites: SiteCompact[]
  count: number
  by_source: Record<string, number>
  exported_at: string
}

// =============================================================================
// Site Details (sites/details/*.json)
// =============================================================================

/** Full site details from region files */
export interface SiteDetail {
  id: string
  source: string
  source_record_id?: string
  name: string
  lat: number
  lon: number
  type?: string
  period?: {
    start?: number | null
    end?: number | null
    name?: string
  }
  country?: string
  description?: string
  thumbnail?: string
  url?: string
}

/** sites/details/{region}.json file format */
export interface SiteDetailsFile {
  region: string
  bounds: {
    min_lat: number
    max_lat: number
    min_lon: number
    max_lon: number
  }
  sites: Record<string, SiteDetail>
  count: number
}

// =============================================================================
// Content Links (links.json)
// =============================================================================

/** Content link: [source, id, relevance_score] */
export type ContentLink = [string, string, number]

/** links.json file format */
export interface ContentLinksFile {
  links: Record<string, Record<string, ContentLink[]>>  // site_id -> content_type -> links
  count: number
  exported_at: string
}

// =============================================================================
// Content Items (content/*.json)
// =============================================================================

/** Content item from export */
export interface ContentItem {
  src: string     // source
  id: string      // id
  t: string       // title
  thumb?: string  // thumbnail url
  url?: string    // content url
  meta?: Record<string, unknown>
}

/** content/{type}s.json file format */
export interface ContentFile {
  type: string
  items: Record<string, ContentItem>
  count: number
}

// =============================================================================
// Helper Functions
// =============================================================================

/** Expand compact source to full format */
export function expandSource(id: string, compact: SourceMetaCompact): SourceMeta {
  return {
    id,
    name: compact.n,
    description: compact.d,
    color: compact.c,
    icon: compact.i,
    category: compact.cat,
    recordCount: compact.cnt,
    license: compact.lic,
    attribution: compact.att,
    enabled: compact.on,
    url: compact.url,
    isPrimary: compact.primary,
    enabledByDefault: compact.enabledByDefault,
  }
}

/** Expand compact site to full format */
export function expandSite(compact: SiteCompact): Site {
  return {
    id: compact.i,
    name: compact.n,
    lat: compact.la,
    lon: compact.lo,
    sourceId: compact.s,
    type: compact.t,
    description: compact.d,
    location: compact.l,
    period: compact.p,
    sourceUrl: compact.u,
    imageUrl: compact.im,
  }
}

// =============================================================================
// Source Colors (fallback when no sources.json available)
// =============================================================================

/** Default source colors for visualization - NO GREENS (coastlines are teal) */
export const DEFAULT_SOURCE_COLORS: Record<string, string> = {
  // PRIMARY SOURCE - Ancient Nerds Original (manually curated)
  ancient_nerds: '#FFD700',    // Gold - primary source (manually curated)

  // Core ancient world
  pleiades: '#e74c3c',         // Red - ancient places
  dare: '#6c5ce7',             // Violet-blue - Roman Empire
  topostext: '#00bcd4',        // Cyan - ancient texts

  // Global databases
  unesco: '#ffd700',           // Gold/Yellow - UNESCO
  wikidata: '#9966ff',         // Purple - Wikidata
  osm_historic: '#ff9800',     // Orange - OpenStreetMap

  // Europe
  historic_england: '#c0392b', // Dark red - England
  ireland_nms: '#ff6699',      // Pink - Ireland
  arachne: '#8e44ad',          // Dark purple - Arachne
  megalithic_portal: '#9966cc', // Amethyst - megaliths

  // Specialized
  sacred_sites: '#ff69b4',     // Hot Pink - sacred sites
  rock_art: '#e67e22',         // Orange - rock art
  inscriptions_edh: '#5dade2', // Light blue - inscriptions
  coins_nomisma: '#d4af37',    // Gold - coins
  shipwrecks_oxrep: '#0066ff', // Ocean Blue - shipwrecks
  volcanic_holvol: '#ff0000',  // Bright Red - volcanoes

  // Americas & MENA
  dinaa: '#cd853f',            // Peru brown - Americas
  eamena: '#d35400',           // Dark orange - MENA
  open_context: '#2980b9',     // Strong blue - Open Context

  // Fallback
  default: '#ff00ff',          // Magenta - visible fallback
}

/** Get color for a source ID */
export function getSourceColor(sourceId: string, sources?: Record<string, SourceMeta>): string {
  if (sources?.[sourceId]) {
    return sources[sourceId].color
  }
  return DEFAULT_SOURCE_COLORS[sourceId] || DEFAULT_SOURCE_COLORS.default
}
