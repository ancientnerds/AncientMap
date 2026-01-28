import * as THREE from 'three'
import { haversineDistance } from './geoMath'

/** Convert latitude/longitude to 3D position on a sphere */
export function latLngToPoint(lng: number, lat: number, radius: number = 1.003): THREE.Vector3 {
  const phi = (90 - lat) * Math.PI / 180
  const theta = (lng + 180) * Math.PI / 180
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta)
  )
}

/**
 * Create a great circle arc between two points
 */
export function createGreatCircleArc(lng1: number, lat1: number, lng2: number, lat2: number, segments: number = 64): THREE.Vector3[] {
  const arcPoints: THREE.Vector3[] = []

  const lat1Rad = lat1 * Math.PI / 180
  const lng1Rad = lng1 * Math.PI / 180
  const lat2Rad = lat2 * Math.PI / 180
  const lng2Rad = lng2 * Math.PI / 180

  // Angular distance between points
  const d = 2 * Math.asin(Math.sqrt(
    Math.pow(Math.sin((lat2Rad - lat1Rad) / 2), 2) +
    Math.cos(lat1Rad) * Math.cos(lat2Rad) * Math.pow(Math.sin((lng2Rad - lng1Rad) / 2), 2)
  ))

  // If points are very close, just return a straight line
  if (d < 0.0001) {
    arcPoints.push(latLngToPoint(lng1, lat1))
    arcPoints.push(latLngToPoint(lng2, lat2))
    return arcPoints
  }

  // Spherical linear interpolation
  for (let i = 0; i <= segments; i++) {
    const f = i / segments
    const A = Math.sin((1 - f) * d) / Math.sin(d)
    const B = Math.sin(f * d) / Math.sin(d)
    const x = A * Math.cos(lat1Rad) * Math.cos(lng1Rad) + B * Math.cos(lat2Rad) * Math.cos(lng2Rad)
    const y = A * Math.cos(lat1Rad) * Math.sin(lng1Rad) + B * Math.cos(lat2Rad) * Math.sin(lng2Rad)
    const z = A * Math.sin(lat1Rad) + B * Math.sin(lat2Rad)

    const lat = Math.atan2(z, Math.sqrt(x * x + y * y)) * 180 / Math.PI
    const lng = Math.atan2(y, x) * 180 / Math.PI

    arcPoints.push(latLngToPoint(lng, lat))
  }
  return arcPoints
}

/**
 * Get the midpoint of a great circle arc
 */
export function getArcMidpoint(lng1: number, lat1: number, lng2: number, lat2: number, radius: number = 1.02): THREE.Vector3 {
  const lat1Rad = lat1 * Math.PI / 180
  const lng1Rad = lng1 * Math.PI / 180
  const lat2Rad = lat2 * Math.PI / 180
  const lng2Rad = lng2 * Math.PI / 180

  // Great circle angular distance
  const d = 2 * Math.asin(Math.sqrt(
    Math.pow(Math.sin((lat2Rad - lat1Rad) / 2), 2) +
    Math.cos(lat1Rad) * Math.cos(lat2Rad) * Math.pow(Math.sin((lng2Rad - lng1Rad) / 2), 2)
  ))

  // If points are very close, use simple average
  if (d < 0.0001) {
    return latLngToPoint((lng1 + lng2) / 2, (lat1 + lat2) / 2, radius)
  }

  // Spherical linear interpolation at f=0.5 (midpoint)
  const f = 0.5
  const A = Math.sin((1 - f) * d) / Math.sin(d)
  const B = Math.sin(f * d) / Math.sin(d)
  const x = A * Math.cos(lat1Rad) * Math.cos(lng1Rad) + B * Math.cos(lat2Rad) * Math.cos(lng2Rad)
  const y = A * Math.cos(lat1Rad) * Math.sin(lng1Rad) + B * Math.cos(lat2Rad) * Math.sin(lng2Rad)
  const z = A * Math.sin(lat1Rad) + B * Math.sin(lat2Rad)

  const midLat = Math.atan2(z, Math.sqrt(x * x + y * y)) * 180 / Math.PI
  const midLng = Math.atan2(y, x) * 180 / Math.PI

  return latLngToPoint(midLng, midLat, radius)
}

/**
 * Create a square marker using Points (constant screen size)
 */
export function createMarkerPoints(positions: THREE.Vector3[], color: number): THREE.Points {
  const geometry = new THREE.BufferGeometry()
  const posArray = new Float32Array(positions.length * 3)
  positions.forEach((pos, i) => {
    posArray[i * 3] = pos.x
    posArray[i * 3 + 1] = pos.y
    posArray[i * 3 + 2] = pos.z
  })
  geometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3))

  const material = new THREE.PointsMaterial({
    color: color,
    size: 8,
    sizeAttenuation: false, // Constant screen size
    transparent: true,
  })
  const points = new THREE.Points(geometry, material)
  points.renderOrder = 15
  return points
}

/**
 * Create a ring marker sprite for snapped points
 */
export function createRingMarker(position: THREE.Vector3, color: number): THREE.Sprite {
  const dpr = 2
  const baseSize = 24
  const canvasSize = baseSize * dpr * 2
  const ringRadius = (baseSize - 2) * dpr
  const lineWidth = 3 * dpr

  const canvas = document.createElement('canvas')
  canvas.width = canvasSize
  canvas.height = canvasSize
  const ctx = canvas.getContext('2d')!

  ctx.clearRect(0, 0, canvasSize, canvasSize)

  const colorStr = '#' + color.toString(16).padStart(6, '0')

  ctx.strokeStyle = colorStr
  ctx.lineWidth = lineWidth
  ctx.beginPath()
  ctx.arc(canvasSize / 2, canvasSize / 2, ringRadius, 0, Math.PI * 2)
  ctx.stroke()

  const texture = new THREE.CanvasTexture(canvas)
  texture.needsUpdate = true

  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
    sizeAttenuation: true,
  })
  const sprite = new THREE.Sprite(material)

  sprite.position.copy(position)
  ;(sprite as any).isRingMarker = true
  ;(sprite as any).targetPixels = baseSize
  sprite.scale.set(0.01, 0.01, 1)
  sprite.renderOrder = 10

  return sprite
}

/**
 * Create a measurement line (great circle arc)
 */
export function createMeasurementLine(
  start: [number, number],
  end: [number, number],
  color: number,
  opacity: number = 0.8
): THREE.Line {
  const arcPoints = createGreatCircleArc(start[0], start[1], end[0], end[1])
  const lineGeometry = new THREE.BufferGeometry().setFromPoints(arcPoints)
  const lineMaterial = new THREE.LineBasicMaterial({
    color: color,
    linewidth: 2,
    transparent: true,
    opacity: opacity,
  })
  const line = new THREE.Line(lineGeometry, lineMaterial)
  line.renderOrder = 15
  return line
}

/**
 * Create a distance label sprite
 */
export function createDistanceLabel(
  start: [number, number],
  end: [number, number],
  color: string,
  measureUnit: 'km' | 'miles'
): THREE.Sprite {
  const distanceKm = haversineDistance(start[1], start[0], end[1], end[0])
  const distanceMiles = distanceKm * 0.621371
  const distanceText = measureUnit === 'km'
    ? `${distanceKm.toFixed(1)} km`
    : `${distanceMiles.toFixed(1)} mi`

  // High-DPI canvas for crisp text
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!

  const fontSize = 28 * dpr
  const fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
  ctx.font = `bold ${fontSize}px ${fontFamily}`
  const textWidth = ctx.measureText(distanceText).width
  const haloWidth = 3 * dpr
  const padding = haloWidth + 4 * dpr

  canvas.width = Math.ceil(textWidth + padding * 2)
  canvas.height = Math.ceil(fontSize + padding * 2)

  // Redraw font after canvas resize
  ctx.font = `bold ${fontSize}px ${fontFamily}`
  ctx.textBaseline = 'middle'
  ctx.textAlign = 'center'

  const centerX = canvas.width / 2
  const centerY = canvas.height / 2

  // Draw colored halo
  ctx.strokeStyle = color
  ctx.lineWidth = haloWidth
  ctx.lineJoin = 'round'
  ctx.miterLimit = 2
  ctx.strokeText(distanceText, centerX, centerY)

  // Draw black text fill
  ctx.fillStyle = '#000000'
  ctx.fillText(distanceText, centerX, centerY)

  const texture = new THREE.CanvasTexture(canvas)
  texture.minFilter = THREE.LinearFilter
  texture.magFilter = THREE.LinearFilter
  texture.needsUpdate = true

  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    sizeAttenuation: true,
    depthTest: false,
    depthWrite: false,
  })
  const sprite = new THREE.Sprite(material)

  // Store target pixel dimensions for dynamic scaling
  const targetPixelWidth = canvas.width / dpr * 0.5
  const targetPixelHeight = canvas.height / dpr * 0.5
  ;(sprite as any).targetWidth = targetPixelWidth
  ;(sprite as any).targetHeight = targetPixelHeight

  // Position at midpoint
  const midPos = getArcMidpoint(start[0], start[1], end[0], end[1], 1.02)
  sprite.position.copy(midPos)

  sprite.scale.set(0.05, 0.02, 1)
  sprite.renderOrder = 30

  return sprite
}

export interface MeasurementData {
  id: string
  points: [[number, number], [number, number]]
  snapped: [boolean, boolean]
  color: string
}

export interface MeasurePoint {
  coords: [number, number]
  snapped: boolean
}

export interface MeasurementLabelEntry {
  label: THREE.Sprite
  midpoint: THREE.Vector3
  targetWidth: number
  targetHeight: number
}

export interface MeasurementLineEntry {
  line: THREE.Line
  points: THREE.Vector3[]
}

export interface MeasurementMarkerEntry {
  marker: THREE.Object3D
  position: THREE.Vector3
}
