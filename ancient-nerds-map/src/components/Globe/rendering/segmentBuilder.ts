/**
 * Pure geometry for the globe's vector layers, shared by the layer worker and the tests.
 *
 * No three.js and no DOM here: the worker imports this module, and it must stay a small,
 * self-contained chunk. The main thread only turns the returned Float32Arrays into geometries.
 */

export interface LayerGeometry {
  type: string
  coordinates: unknown
}

export interface LayerFeature {
  properties?: Record<string, unknown> | null
  geometry: LayerGeometry
}

/** A name for a river or lake at the centroid of its coordinates (the old label code's rule). */
export interface LineLabel {
  name: string
  lat: number
  lng: number
  rank: number
}

export interface LayerWorkerRequest {
  id: number
  buffer: ArrayBuffer
  radii: readonly number[]
  withLabels: boolean
}

export type LayerWorkerResponse =
  | { id: number; positions: Float32Array[]; labels?: LineLabel[] }
  | { id: number; error: string }

/**
 * Lat/lng to a point on the sphere of radius r: the formula of the basemap sphere and of every
 * vector layer (sceneInit.ts). Keep the evaluation order: the first frame must stay pixel-identical.
 */
export function latLngTo3DArray(lat: number, lng: number, r: number): [number, number, number] {
  const phi = (90 - lat) * Math.PI / 180
  const theta = (lng + 180) * Math.PI / 180
  return [
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  ]
}

/**
 * Check if a line segment is an artificial Antarctic boundary
 * (straight lines at 0°, ±90°, ±180° longitude dividing ice sheet sectors).
 * scripts/build_globe_layers.py ports this rule to drop the segments before it simplifies.
 */
export function isArtificialAntarcticBoundary(coord1: number[], coord2: number[]): boolean {
  const [lon1, lat1] = coord1
  const [lon2, lat2] = coord2
  // Only check Antarctica (lat < -60)
  if (lat1 > -60 && lat2 > -60) return false
  // Check if segment is at a round longitude (tolerance 0.5°)
  for (const roundLon of [0, 90, -90, 180, -180]) {
    if (Math.abs(lon1 - roundLon) < 0.5 && Math.abs(lon2 - roundLon) < 0.5) {
      // Check if it's a significant vertical segment (spans > 2° latitude)
      if (Math.abs(lat1 - lat2) > 2) return true
    }
  }
  // Also check horizontal lines at -90° latitude (South Pole connections)
  if (Math.abs(lat1 - (-90)) < 0.5 && Math.abs(lat2 - (-90)) < 0.5) {
    if (Math.abs(lon1 - lon2) > 10) return true
  }
  return false
}

/** The lines of one feature: LineString → [coords]; MultiLineString, Polygon → coords; MultiPolygon → rings. */
function featureLines(geometry: LayerGeometry): number[][][] {
  switch (geometry.type) {
    case 'LineString': return [geometry.coordinates as number[][]]
    case 'MultiLineString':
    case 'Polygon': return geometry.coordinates as number[][][]
    case 'MultiPolygon': return (geometry.coordinates as number[][][][]).flat()
    default: return []
  }
}

/**
 * Explicit segment pairs (LineSegments, no NaN separators: NaN vertices corrupt geometry on
 * ANGLE/Metal), artificial Antarctic segments skipped. Two passes: count, then fill one
 * pre-sized Float32Array per radius.
 */
export function buildSegmentPositions(features: readonly LayerFeature[], radii: readonly number[]): Float32Array[] {
  let segments = 0
  for (const feature of features) {
    for (const coords of featureLines(feature.geometry)) {
      for (let i = 0; i < coords.length - 1; i++) {
        if (!isArtificialAntarcticBoundary(coords[i], coords[i + 1])) segments++
      }
    }
  }

  const out = radii.map(() => new Float32Array(segments * 6))
  let offset = 0
  const write = (p: number[]) => {
    const phi = (90 - p[1]) * Math.PI / 180
    const theta = (p[0] + 180) * Math.PI / 180
    const sinPhi = Math.sin(phi)
    const cosPhi = Math.cos(phi)
    const sinTheta = Math.sin(theta)
    const cosTheta = Math.cos(theta)
    for (let k = 0; k < radii.length; k++) {
      const r = radii[k]
      const target = out[k]
      // Same operand order as latLngTo3DArray: (-r * sinφ) * cosθ, r * cosφ, (r * sinφ) * sinθ
      target[offset] = -r * sinPhi * cosTheta
      target[offset + 1] = r * cosPhi
      target[offset + 2] = r * sinPhi * sinTheta
    }
    offset += 3
  }
  for (const feature of features) {
    for (const coords of featureLines(feature.geometry)) {
      for (let i = 0; i < coords.length - 1; i++) {
        const a = coords[i]
        const b = coords[i + 1]
        if (isArtificialAntarcticBoundary(a, b)) continue
        write(a)
        write(b)
      }
    }
  }
  return out
}

/** The coordinates the old label code averaged: Polygon outer ring only, everything else flat. */
function labelCoordinates(geometry: LayerGeometry): number[][] {
  switch (geometry.type) {
    case 'LineString': return geometry.coordinates as number[][]
    case 'MultiLineString': return (geometry.coordinates as number[][][]).flat()
    case 'Polygon': return (geometry.coordinates as number[][][])[0]
    case 'MultiPolygon': return (geometry.coordinates as number[][][][]).flat(2)
    default: return []
  }
}

/** Name candidates for river and lake labels, in file order (the main thread de-duplicates). */
export function extractLineLabels(features: readonly LayerFeature[]): LineLabel[] {
  const labels: LineLabel[] = []
  for (const feature of features) {
    const props = feature.properties ?? {}
    const name = (props.name || props.NAME) as string | undefined
    if (!name) continue
    const coords = labelCoordinates(feature.geometry)
    if (coords.length === 0) continue
    let sumLng = 0
    let sumLat = 0
    for (const c of coords) {
      sumLng += c[0]
      sumLat += c[1]
    }
    const rank = (props.scalerank ?? props.SCALERANK ?? 99) as number
    labels.push({ name, lat: sumLat / coords.length, lng: sumLng / coords.length, rank })
  }
  return labels
}

/**
 * The worker's whole job, as a pure function: decode, parse once, build every radius. A parse
 * failure is answered as `{id, error}` so the main thread rejects the load that asked for it.
 */
export function processLayerRequest(req: LayerWorkerRequest): { response: LayerWorkerResponse; transfer: ArrayBuffer[] } {
  try {
    const data = JSON.parse(new TextDecoder().decode(req.buffer)) as { type?: string; features?: LayerFeature[] }
    if (data.type !== 'FeatureCollection' || !Array.isArray(data.features)) {
      throw new Error(`expected a GeoJSON FeatureCollection, got type ${String(data.type)}`)
    }
    const positions = buildSegmentPositions(data.features, req.radii)
    const response: LayerWorkerResponse = req.withLabels
      ? { id: req.id, positions, labels: extractLineLabels(data.features) }
      : { id: req.id, positions }
    return { response, transfer: positions.map(p => p.buffer as ArrayBuffer) }
  } catch (err) {
    return { response: { id: req.id, error: err instanceof Error ? err.message : String(err) }, transfer: [] }
  }
}
