/**
 * Geometry utilities for screen coordinate sync between Three.js and Mapbox
 *
 * This module provides ray-sphere intersection and coordinate conversion
 * functions to determine what geographic area is visible on screen.
 */

import * as THREE from 'three'

/**
 * Calculate the great-circle distance between two points using the Haversine formula
 * @param lat1 Latitude of first point in degrees
 * @param lng1 Longitude of first point in degrees
 * @param lat2 Latitude of second point in degrees
 * @param lng2 Longitude of second point in degrees
 * @returns Distance in kilometers
 */
export function haversineDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371 // Earth radius in km
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLng = (lng2 - lng1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

/**
 * Ray-sphere intersection - returns hit points sorted by distance
 * Returns points where a ray intersects a sphere, sorted nearest first
 */
export function raySphereIntersect(
  rayOrigin: THREE.Vector3,
  rayDir: THREE.Vector3,
  sphereCenter: THREE.Vector3,
  radius: number
): THREE.Vector3[] {
  const oc = rayOrigin.clone().sub(sphereCenter)
  const a = rayDir.dot(rayDir)
  const b = 2 * oc.dot(rayDir)
  const c = oc.dot(oc) - radius * radius
  const discriminant = b * b - 4 * a * c

  if (discriminant < 0) return []

  const sqrtD = Math.sqrt(discriminant)
  const t1 = (-b - sqrtD) / (2 * a)
  const t2 = (-b + sqrtD) / (2 * a)

  const hits: THREE.Vector3[] = []
  if (t1 > 0) hits.push(rayOrigin.clone().add(rayDir.clone().multiplyScalar(t1)))
  if (t2 > 0 && t2 !== t1) hits.push(rayOrigin.clone().add(rayDir.clone().multiplyScalar(t2)))

  return hits
}

/** Convert 3D point on unit sphere to lat/lng */
export function cartesianToLatLng(point: THREE.Vector3): { lat: number; lng: number } {
  const normalized = point.clone().normalize()
  const lat = Math.asin(normalized.y) * (180 / Math.PI)
  // Adjust for Three.js coordinate system
  const lng = Math.atan2(normalized.z, -normalized.x) * (180 / Math.PI) - 180
  return { lat, lng: lng < -180 ? lng + 360 : lng > 180 ? lng - 360 : lng }
}

/** Convert lat/lng to 3D point on sphere */
export function latLngToCartesian(lat: number, lng: number, radius: number = 1): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180)
  const theta = (lng + 180) * (Math.PI / 180)
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta)
  )
}

/** Geographic bounds type: bounds [[west, south], [east, north]] */
export interface VisibleBounds {
  center: [number, number] // [lng, lat]
  bounds: [[number, number], [number, number]] | null // [[sw_lng, sw_lat], [ne_lng, ne_lat]] or null if zoomed way out
}

/** Get the visible geographic bounds from a Three.js camera looking at a globe */
export function getVisibleBounds(
  camera: THREE.PerspectiveCamera,
  globeRadius: number = 1.0
): VisibleBounds | null {
  const raycaster = new THREE.Raycaster()
  const sphereCenter = new THREE.Vector3(0, 0, 0)

  // Screen points in normalized device coordinates (-1 to 1)
  // Use 0.9 for corners to avoid edge artifacts
  const screenPoints = [
    { name: 'center', ndc: new THREE.Vector2(0, 0) },
    { name: 'topLeft', ndc: new THREE.Vector2(-0.9, 0.9) },
    { name: 'topRight', ndc: new THREE.Vector2(0.9, 0.9) },
    { name: 'bottomLeft', ndc: new THREE.Vector2(-0.9, -0.9) },
    { name: 'bottomRight', ndc: new THREE.Vector2(0.9, -0.9) },
  ]

  const hits: { name: string; lat: number; lng: number }[] = []

  for (const { name, ndc } of screenPoints) {
    raycaster.setFromCamera(ndc, camera)
    const intersects = raySphereIntersect(
      raycaster.ray.origin,
      raycaster.ray.direction,
      sphereCenter,
      globeRadius
    )
    if (intersects.length > 0) {
      const latLng = cartesianToLatLng(intersects[0])
      hits.push({ name, ...latLng })
    }
  }

  const center = hits.find(h => h.name === 'center')
  if (!center) return null

  const corners = hits.filter(h => h.name !== 'center')
  if (corners.length < 2) {
    // Corners missed globe (zoomed way out) - return center only
    return { center: [center.lng, center.lat], bounds: null }
  }

  const lats = corners.map(c => c.lat)
  const lngs = corners.map(c => c.lng)

  // Handle cross-dateline views by detecting large lng spread
  const lngMin = Math.min(...lngs)
  const lngMax = Math.max(...lngs)

  // Note: If lngMax - lngMin > 180, we're likely crossing the dateline
  // Mapbox fitBounds handles this case automatically

  return {
    center: [center.lng, center.lat],
    bounds: [
      [lngMin, Math.min(...lats)], // SW corner [lng, lat]
      [lngMax, Math.max(...lats)]  // NE corner [lng, lat]
    ]
  }
}

/** Calculate camera distance needed to show geographic bounds */
export function boundsToDistance(
  bounds: [[number, number], [number, number]],
  minDistance: number = 1.02,
  maxDistance: number = 2.44
): number {
  const [[w, s], [e, n]] = bounds
  const latSpan = Math.abs(n - s)
  const lngSpan = Math.abs(e - w)
  const maxSpan = Math.max(latSpan, lngSpan)

  // Map geographic span to camera distance
  // Full globe (~120°) = max distance, small area (~5°) = min distance
  const t = Math.min(1, maxSpan / 120)
  return minDistance + t * (maxDistance - minDistance)
}

/** Universal globe view state that both renderers understand */
export interface GlobeView {
  lat: number      // Center latitude
  lng: number      // Center longitude
  distance: number // Normalized 0-1 (0 = closest, 1 = farthest)
}

/** Camera distance constants */
export const GLOBE_DISTANCE = {
  MIN: 1.02,  // Closest zoom (Three.js)
  MAX: 2.44,  // Farthest zoom (Three.js)
  MAPBOX_ZOOM_MIN: 0.7,   // Mapbox zoom at farthest
  MAPBOX_ZOOM_MAX: 8.25,  // Mapbox zoom at closest (lowered to zoom out more at 66%)
}

/** Get current view from Three.js camera */
export function getThreeJsView(camera: THREE.PerspectiveCamera): GlobeView {
  const raycaster = new THREE.Raycaster()
  raycaster.setFromCamera(new THREE.Vector2(0, 0), camera)

  const hits = raySphereIntersect(
    raycaster.ray.origin,
    raycaster.ray.direction,
    new THREE.Vector3(0, 0, 0),
    1.0
  )

  const cameraDist = camera.position.length()
  const distance = (cameraDist - GLOBE_DISTANCE.MIN) / (GLOBE_DISTANCE.MAX - GLOBE_DISTANCE.MIN)

  if (hits.length > 0) {
    const latLng = cartesianToLatLng(hits[0])
    return { lat: latLng.lat, lng: latLng.lng, distance: Math.max(0, Math.min(1, distance)) }
  }

  // Fallback if ray misses globe
  const dir = camera.position.clone().normalize().negate()
  const latLng = cartesianToLatLng(dir)
  return { lat: latLng.lat, lng: latLng.lng, distance: Math.max(0, Math.min(1, distance)) }
}

/** Apply view to Three.js camera */
export function setThreeJsView(
  camera: THREE.PerspectiveCamera,
  controls: { target: THREE.Vector3; update: () => void },
  view: GlobeView
): void {
  const cameraDist = GLOBE_DISTANCE.MIN + view.distance * (GLOBE_DISTANCE.MAX - GLOBE_DISTANCE.MIN)
  const centerPoint = latLngToCartesian(view.lat, view.lng, 1.0)
  const cameraDir = centerPoint.clone().normalize()

  camera.position.copy(cameraDir.multiplyScalar(cameraDist))
  camera.lookAt(0, 0, 0)
  controls.update()
}

/** Convert GlobeView to Mapbox camera settings */
export function viewToMapbox(view: GlobeView): { lat: number; lng: number; zoom: number } {
  // distance 0 = closest = max zoom, distance 1 = farthest = min zoom
  const zoom = GLOBE_DISTANCE.MAPBOX_ZOOM_MAX - view.distance * (GLOBE_DISTANCE.MAPBOX_ZOOM_MAX - GLOBE_DISTANCE.MAPBOX_ZOOM_MIN)
  return { lat: view.lat, lng: view.lng, zoom }
}

/** Convert Mapbox camera to GlobeView */
export function mapboxToView(lat: number, lng: number, zoom: number): GlobeView {
  // zoom high = close = distance 0, zoom low = far = distance 1
  const distance = (GLOBE_DISTANCE.MAPBOX_ZOOM_MAX - zoom) / (GLOBE_DISTANCE.MAPBOX_ZOOM_MAX - GLOBE_DISTANCE.MAPBOX_ZOOM_MIN)
  return { lat, lng, distance: Math.max(0, Math.min(1, distance)) }
}

