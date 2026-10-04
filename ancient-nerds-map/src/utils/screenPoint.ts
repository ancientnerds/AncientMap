/**
 * Viewport pixel of a place in the current view, for the studio captures
 * (window.__DEMO.screenPoint, pipeline/studio/capture): the globe take marks
 * places where the page itself draws them, the platform take clicks measure
 * points exactly. Pure; the camera or Mapbox's project() is passed in.
 */
import type * as THREE from 'three'

import { latLngToPosition } from './geoUtils'

export type ScreenPoint = { x: number; y: number }

/** The point when it lies inside the width x height viewport, else null. */
export function viewportPoint(p: ScreenPoint, width: number, height: number): ScreenPoint | null {
  return p.x >= 0 && p.x <= width && p.y >= 0 && p.y <= height ? { x: p.x, y: p.y } : null
}

/**
 * Pixel of a surface point for the Three.js globe camera (unit globe at the
 * origin); null behind the horizon or outside the viewport. A point p of the
 * unit sphere faces a camera at C (|C| > 1) exactly when p . C > 1.
 */
export function globeScreenPoint(camera: THREE.Camera, lat: number, lng: number, width: number, height: number): ScreenPoint | null {
  const p = latLngToPosition(lng, lat, 1)
  if (p.dot(camera.position) <= 1) return null
  const v = p.clone().project(camera)
  return viewportPoint({ x: ((v.x + 1) / 2) * width, y: ((1 - v.y) / 2) * height }, width, height)
}
