/**
 * Export and import utilities for the Database Audit page.
 *
 * Exports: Converts the compact AuditSite[] format into downloadable CSV, JSON, and GeoJSON files.
 * Imports: Parses CSV, JSON, and GeoJSON files into ParsedSite[] for upload preview.
 */

export interface ParsedSite {
  name: string
  lat: number
  lon: number
  site_type?: string
  period_name?: string
  period_start?: number
  country?: string
  description?: string
  source_url?: string
  thumbnail_url?: string
  card_description?: string
  _status?: 'insert' | 'update' | 'error'
  _error?: string
  _matchedId?: string  // ID of existing site if this is an update
  _currentData?: Record<string, string | number | null | undefined>  // Current DB values for diff display
  _changedFields?: string[]  // Fields that differ from current DB values
}

interface AuditSite {
  id: string
  n: string        // name
  la: number       // lat
  lo: number       // lon
  s: string        // source_id
  t?: string       // site_type
  p?: number       // period_start
  pn?: string      // period_name
  d?: string       // description
  c?: string       // country
  u?: string       // source_url
  i?: string       // thumbnail_url
  cd?: string      // card_description
  eb?: string      // edited_by
  ea?: string      // edited_at
}

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function dateSuffix(): string {
  return new Date().toISOString().slice(0, 10) // YYYY-MM-DD
}

function csvEscape(value: string | number | undefined | null): string {
  if (value == null) return ''
  const str = String(value)
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return '"' + str.replace(/"/g, '""') + '"'
  }
  return str
}

export function exportCSV(sites: AuditSite[]) {
  const headers = [
    'Name', 'Latitude', 'Longitude', 'Source', 'Type',
    'Period Start', 'Period Name', 'Country', 'Description',
    'Source URL', 'Thumbnail URL', 'Card Description', 'Edited By', 'Last Edited',
  ]

  const rows = sites.map(s => [
    csvEscape(s.n),
    csvEscape(s.la),
    csvEscape(s.lo),
    csvEscape(s.s),
    csvEscape(s.t),
    csvEscape(s.p),
    csvEscape(s.pn),
    csvEscape(s.c),
    csvEscape(s.d),
    csvEscape(s.u),
    csvEscape(s.i),
    csvEscape(s.cd),
    csvEscape(s.eb),
    csvEscape(s.ea),
  ].join(','))

  const csv = '\uFEFF' + headers.join(',') + '\n' + rows.join('\n')
  downloadBlob(csv, `ancient-nerds-csv-${dateSuffix()}.csv`, 'text/csv;charset=utf-8')
}

export function exportJSON(sites: AuditSite[]) {
  const expanded = sites.map(s => ({
    id: s.id,
    name: s.n,
    latitude: s.la,
    longitude: s.lo,
    source_id: s.s,
    site_type: s.t ?? null,
    period_start: s.p ?? null,
    period_name: s.pn ?? null,
    country: s.c ?? null,
    description: s.d ?? null,
    source_url: s.u ?? null,
    thumbnail_url: s.i ?? null,
    card_description: s.cd ?? null,
    edited_by: s.eb ?? null,
    edited_at: s.ea ?? null,
  }))

  const output = {
    exported_at: new Date().toISOString(),
    count: expanded.length,
    sites: expanded,
  }

  const json = JSON.stringify(output, null, 2)
  downloadBlob(json, `ancient-nerds-json-${dateSuffix()}.json`, 'application/json')
}

export function exportGeoJSON(sites: AuditSite[]) {
  const features = sites
    .filter(s => !(s.la === 0 && s.lo === 0))
    .map(s => ({
      type: 'Feature' as const,
      geometry: {
        type: 'Point' as const,
        coordinates: [s.lo, s.la],
      },
      properties: {
        id: s.id,
        name: s.n,
        source_id: s.s,
        site_type: s.t ?? null,
        period_start: s.p ?? null,
        period_name: s.pn ?? null,
        country: s.c ?? null,
        description: s.d ?? null,
        source_url: s.u ?? null,
        thumbnail_url: s.i ?? null,
        card_description: s.cd ?? null,
        edited_by: s.eb ?? null,
        edited_at: s.ea ?? null,
      },
    }))

  const geojson = {
    type: 'FeatureCollection' as const,
    metadata: {
      exported_at: new Date().toISOString(),
      count: features.length,
    },
    features,
  }

  const json = JSON.stringify(geojson, null, 2)
  downloadBlob(json, `ancient-nerds-geojson-${dateSuffix()}.geojson`, 'application/geo+json')
}


// =============================================================================
// Parse functions — import CSV, JSON, GeoJSON into ParsedSite[]
// =============================================================================

// Column name mapping: various header names → ParsedSite field
const HEADER_MAP: Record<string, keyof ParsedSite> = {
  name: 'name', title: 'name', site_name: 'name', n: 'name',
  latitude: 'lat', lat: 'lat', la: 'lat',
  longitude: 'lon', lng: 'lon', lon: 'lon', lo: 'lon',
  type: 'site_type', site_type: 'site_type', category: 'site_type', t: 'site_type',
  period_name: 'period_name', period: 'period_name', pn: 'period_name',
  period_start: 'period_start', p: 'period_start',
  country: 'country', c: 'country', location: 'country',
  description: 'description', desc: 'description', d: 'description',
  source_url: 'source_url', url: 'source_url', u: 'source_url',
  thumbnail_url: 'thumbnail_url', image: 'thumbnail_url', i: 'thumbnail_url',
  card_description: 'card_description', cd: 'card_description',
}

function mapRow(raw: Record<string, string | number | null | undefined>): ParsedSite | null {
  const site: Partial<ParsedSite> = {}
  for (const [key, value] of Object.entries(raw)) {
    if (value == null || value === '') continue
    const field = HEADER_MAP[key.toLowerCase().trim()]
    if (!field) continue
    if (field === 'lat' || field === 'lon') {
      const n = typeof value === 'number' ? value : parseFloat(String(value))
      if (!isNaN(n)) (site as Record<string, unknown>)[field] = n
    } else if (field === 'period_start') {
      const n = typeof value === 'number' ? value : parseInt(String(value), 10)
      if (!isNaN(n)) site.period_start = n
    } else {
      (site as Record<string, unknown>)[field] = String(value).trim()
    }
  }
  if (!site.name) return null
  if (site.lat == null || site.lon == null) {
    return { name: site.name!, lat: 0, lon: 0, ...site, _status: 'error', _error: 'Missing coordinates' }
  }
  return site as ParsedSite
}

export function parseCSV(text: string): ParsedSite[] {
  const lines = text.split(/\r?\n/).filter(l => l.trim())
  if (lines.length < 2) return []

  // Parse header
  const headers = lines[0].split(',').map(h => h.replace(/^["']|["']$/g, '').trim())

  const results: ParsedSite[] = []
  for (let i = 1; i < lines.length; i++) {
    // Simple CSV parser — handles quoted fields
    const values: string[] = []
    let current = ''
    let inQuote = false
    for (const ch of lines[i]) {
      if (ch === '"') { inQuote = !inQuote; continue }
      if (ch === ',' && !inQuote) { values.push(current); current = ''; continue }
      current += ch
    }
    values.push(current)

    const raw: Record<string, string> = {}
    for (let j = 0; j < headers.length && j < values.length; j++) {
      raw[headers[j]] = values[j].trim()
    }
    const site = mapRow(raw)
    if (site) results.push(site)
  }
  return results
}

export function parseJSON(text: string): ParsedSite[] {
  const data = JSON.parse(text)
  const arr = Array.isArray(data) ? data : (data.sites || data.features || [])
  return arr.map((item: Record<string, unknown>) => mapRow(item as Record<string, string>)).filter(Boolean) as ParsedSite[]
}

export function parseGeoJSON(text: string): ParsedSite[] {
  const data = JSON.parse(text)
  if (data.type !== 'FeatureCollection' || !Array.isArray(data.features)) return []

  return data.features.map((f: { geometry?: { coordinates?: number[] }; properties?: Record<string, unknown> }) => {
    const props = f.properties || {}
    const coords = f.geometry?.coordinates
    const raw: Record<string, unknown> = { ...props }
    if (coords && coords.length >= 2) {
      raw.lon = coords[0]
      raw.lat = coords[1]
    }
    return mapRow(raw as Record<string, string>)
  }).filter(Boolean) as ParsedSite[]
}
