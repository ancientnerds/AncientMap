import * as THREE from 'three'

/**
 * Geo utilities for globe calculations
 * Consolidates repeated patterns from Globe.tsx
 */

/**
 * Convert latitude/longitude to 3D position on a sphere
 * Uses the standard formula: phi from lat, theta from lng
 * @param lng Longitude in degrees (-180 to 180)
 * @param lat Latitude in degrees (-90 to 90)
 * @param radius Sphere radius (default 1.003 for globe surface)
 */
export function latLngToPosition(lng: number, lat: number, radius: number = 1.003): THREE.Vector3 {
  const phi = (90 - lat) * Math.PI / 180
  const theta = (lng + 180) * Math.PI / 180
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta)
  )
}

/**
 * Calculate the visible horizon threshold based on camera distance
 * Points with dot product below this value are on the back side of the globe
 */
export function getHorizonThreshold(cameraDistance: number): number {
  return 1.0 / cameraDistance
}

/**
 * Check if a point is on the front side of the globe (visible from camera)
 */
export function isPointFrontFacing(
  point: THREE.Vector3,
  cameraPosition: THREE.Vector3,
  cameraDistance: number
): boolean {
  const toCamera = cameraPosition.clone().normalize()
  const surfaceNormal = point.clone().normalize()
  const facing = surfaceNormal.dot(toCamera)
  const horizon = getHorizonThreshold(cameraDistance)
  return facing >= horizon
}

/**
 * Generate circle points on a sphere surface (for proximity circles, etc.)
 */
export function generateSphereCircle(
  centerLng: number,
  centerLat: number,
  radiusKm: number,
  segments: number = 64,
  sphereRadius: number = 1.003
): THREE.Vector3[] {
  const earthRadiusKm = 6371
  const angularRadius = radiusKm / earthRadiusKm
  const centerLatRad = centerLat * Math.PI / 180
  const centerLngRad = centerLng * Math.PI / 180

  const points: THREE.Vector3[] = []
  for (let i = 0; i <= segments; i++) {
    const bearing = (i / segments) * 2 * Math.PI
    const lat = Math.asin(
      Math.sin(centerLatRad) * Math.cos(angularRadius) +
      Math.cos(centerLatRad) * Math.sin(angularRadius) * Math.cos(bearing)
    )
    const lng = centerLngRad + Math.atan2(
      Math.sin(bearing) * Math.sin(angularRadius) * Math.cos(centerLatRad),
      Math.cos(angularRadius) - Math.sin(centerLatRad) * Math.sin(lat)
    )
    points.push(latLngToPosition(lng * 180 / Math.PI, lat * 180 / Math.PI, sphereRadius))
  }
  return points
}

/**
 * Convert hex color to RGB values (0-1 range)
 */
export function hexToRgb(hex: string): [number, number, number] {
  const r = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  return r ? [parseInt(r[1], 16) / 255, parseInt(r[2], 16) / 255, parseInt(r[3], 16) / 255] : [1, 1, 1]
}

/**
 * Check if a line segment is an artificial Antarctic boundary
 * (straight lines at 0°, ±90°, ±180° longitude dividing ice sheet sectors)
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

/**
 * Format year as BCE/CE string
 */
export function formatYear(year: number): string {
  if (year < 0) return `${Math.abs(year)} BC`
  return `${year} AD`
}

/**
 * Format year period as range string (e.g., "121 - 140 AD" or "50 BC - 27 BC")
 */
export function formatYearPeriod(fromYear: number, toYear: number | null): string {
  if (toYear === null) {
    return formatYear(fromYear)
  }
  const fromBC = fromYear < 0
  const toBC = toYear < 0
  if (fromBC && toBC) {
    return `${Math.abs(fromYear)} - ${Math.abs(toYear)} BC`
  } else if (!fromBC && !toBC) {
    return `${fromYear} - ${toYear} AD`
  } else {
    return `${formatYear(fromYear)} - ${formatYear(toYear)}`
  }
}
