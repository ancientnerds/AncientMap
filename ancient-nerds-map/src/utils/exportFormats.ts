/**
 * Export utilities for the Database Audit page.
 *
 * Converts the compact AuditSite[] format into downloadable
 * CSV, JSON, and GeoJSON files.
 */

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
    'Source URL', 'Thumbnail URL', 'Edited By', 'Last Edited',
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
