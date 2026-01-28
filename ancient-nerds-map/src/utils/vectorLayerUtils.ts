import * as THREE from 'three'
import { isArtificialAntarcticBoundary } from './geoUtils'

/**
 * Vector layer utilities for processing GeoJSON data into Three.js geometries
 */

/**
 * Type for coordinate conversion function
 */
export type CoordToPointFn = (lat: number, lng: number, radius: number) => THREE.Vector3

/**
 * Extract coordinate sets from a GeoJSON feature geometry
 */
export function extractCoordSets(geometry: { type: string; coordinates: any }): number[][][] {
  const { type, coordinates } = geometry

  if (type === 'LineString') {
    return [coordinates]
  } else if (type === 'MultiLineString') {
    return coordinates
  } else if (type === 'Polygon') {
    return coordinates
  } else if (type === 'MultiPolygon') {
    return coordinates.flat()
  }

  return []
}

/**
 * Process GeoJSON features into vertex positions array
 * Handles Antarctic boundary filtering and line breaks
 *
 * @param features - Array of GeoJSON features
 * @param radius - Sphere radius for 3D conversion
 * @param latLngTo3D - Function to convert lat/lng to 3D point
 * @returns Float32Array of vertex positions with NaN line breaks
 */
export function processGeoJSONFeatures(
  features: any[],
  radius: number,
  latLngTo3D: CoordToPointFn
): number[] {
  const allPositions: number[] = []

  for (const feature of features) {
    if (!feature.geometry) continue

    const coordSets = extractCoordSets(feature.geometry)

    for (const coords of coordSets) {
      if (coords.length <= 1) continue

      // Filter out artificial Antarctic boundaries while preserving line continuity
      let segmentStarted = false
      for (let i = 0; i < coords.length; i++) {
        const coord = coords[i]
        const nextCoord = coords[i + 1]

        // Check if this segment should be skipped
        if (nextCoord && isArtificialAntarcticBoundary(coord, nextCoord)) {
          // End current segment if one was started
          if (segmentStarted) {
            allPositions.push(NaN, NaN, NaN)
            segmentStarted = false
          }
          continue
        }

        // Add vertex
        const point = latLngTo3D(coord[1], coord[0], radius)
        allPositions.push(point.x, point.y, point.z)
        segmentStarted = true
      }
      // Add NaN to create line break (visual separation between features)
      if (segmentStarted) {
        allPositions.push(NaN, NaN, NaN)
      }
    }
  }

  // Remove trailing NaN values to avoid computeBoundingSphere errors
  while (allPositions.length >= 3 && isNaN(allPositions[allPositions.length - 1])) {
    allPositions.pop()
    allPositions.pop()
    allPositions.pop()
  }

  return allPositions
}

/**
 * Create a Three.js Line geometry from positions array
 */
export function createLineGeometry(positions: number[], boundingRadius: number): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  // Set bounding sphere manually to avoid NaN issues from line breaks
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), boundingRadius + 0.01)
  return geometry
}

/**
 * Process polygon rings (for empire/territory rendering)
 */
export function processPolygonRing(
  ring: number[][],
  radius: number,
  latLngTo3D: CoordToPointFn
): THREE.Vector3[] {
  return ring.map(coord => latLngTo3D(coord[1], coord[0], radius))
}
