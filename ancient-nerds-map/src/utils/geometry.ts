/**
 * Geometry utilities for spatial filtering
 */

/**
 * Empire polygon data structure for filtering
 */
export interface EmpirePolygonData {
  empireId: string
  year: number
  bbox: [number, number, number, number] // [minLng, minLat, maxLng, maxLat]
  features: Array<{
    geometry: { type: string; coordinates: any }
  }>
}

/**
 * Compute bounding box from GeoJSON features
 */
export function computeBoundingBox(features: Array<{ geometry: { type: string; coordinates: any } }>): [number, number, number, number] {
  let minLng = Infinity, minLat = Infinity
  let maxLng = -Infinity, maxLat = -Infinity

  function processCoord(coord: [number, number]) {
    const [lng, lat] = coord
    if (lng < minLng) minLng = lng
    if (lng > maxLng) maxLng = lng
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
  }

  function processRing(ring: number[][]) {
    for (const coord of ring) {
      processCoord(coord as [number, number])
    }
  }

  for (const feature of features) {
    const { type, coordinates } = feature.geometry
    if (type === 'Polygon') {
      for (const ring of coordinates) {
        processRing(ring)
      }
    } else if (type === 'MultiPolygon') {
      for (const polygon of coordinates) {
        for (const ring of polygon) {
          processRing(ring)
        }
      }
    }
  }

  return [minLng, minLat, maxLng, maxLat]
}

/**
 * Quick bounding box check before expensive polygon test
 */
export function pointInBoundingBox(
  point: [number, number],
  bbox: [number, number, number, number]
): boolean {
  const [lng, lat] = point
  const [minLng, minLat, maxLng, maxLat] = bbox
  return lng >= minLng && lng <= maxLng && lat >= minLat && lat <= maxLat
}

/**
 * Ray-casting point-in-polygon algorithm
 * Works for simple polygons
 */
export function pointInPolygon(point: [number, number], polygon: number[][]): boolean {
  const [x, y] = point // [lng, lat]
  let inside = false

  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i][0], yi = polygon[i][1]
    const xj = polygon[j][0], yj = polygon[j][1]

    const intersect = ((yi > y) !== (yj > y)) &&
      (x < (xj - xi) * (y - yi) / (yj - yi) + xi)

    if (intersect) inside = !inside
  }

  return inside
}

/**
 * Check if point is inside a GeoJSON geometry (Polygon or MultiPolygon)
 * Handles holes correctly
 */
export function pointInGeoJSONGeometry(
  point: [number, number],
  geometry: { type: string; coordinates: any }
): boolean {
  if (geometry.type === 'Polygon') {
    // First ring is outer boundary, rest are holes
    const outerRing = geometry.coordinates[0]
    if (!pointInPolygon(point, outerRing)) return false
    // Check holes - if inside any hole, point is outside polygon
    for (let h = 1; h < geometry.coordinates.length; h++) {
      if (pointInPolygon(point, geometry.coordinates[h])) return false
    }
    return true
  } else if (geometry.type === 'MultiPolygon') {
    // Check each polygon - point must be in at least one
    for (const polygon of geometry.coordinates) {
      const outerRing = polygon[0]
      if (pointInPolygon(point, outerRing)) {
        // Check holes
        let inHole = false
        for (let h = 1; h < polygon.length; h++) {
          if (pointInPolygon(point, polygon[h])) {
            inHole = true
            break
          }
        }
        if (!inHole) return true
      }
    }
    return false
  }
  return false
}

/**
 * Check if a site is within any of the provided empire polygons
 */
export function isSiteInEmpirePolygons(
  siteCoords: [number, number],
  empirePolygons: EmpirePolygonData[]
): boolean {
  for (const empire of empirePolygons) {
    // Quick bounding box rejection
    if (!pointInBoundingBox(siteCoords, empire.bbox)) continue

    // Detailed polygon check
    for (const feature of empire.features) {
      if (feature.geometry && pointInGeoJSONGeometry(siteCoords, feature.geometry)) {
        return true
      }
    }
  }
  return false
}
