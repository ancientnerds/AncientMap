import * as THREE from 'three'

/**
 * Proximity circle and marker helpers for Globe component
 */

/**
 * Convert lat/lng to 3D position on sphere
 */
function latLngToPoint(lat: number, lng: number, radius: number): THREE.Vector3 {
  const phi = (90 - lat) * Math.PI / 180
  const theta = (lng + 180) * Math.PI / 180
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta)
  )
}

/**
 * Create a proximity circle with filled area on the globe
 * @returns Object containing the circle group and center point
 */
export function createProximityCircle(
  centerLng: number,
  centerLat: number,
  radiusKm: number,
  opacity: number = 0.8
): { circle: THREE.Group; centerPoint: THREE.Vector3 } {
  const earthRadiusKm = 6371
  const angularRadius = radiusKm / earthRadiusKm
  const segments = 64

  const centerLatRad = centerLat * Math.PI / 180
  const centerLngRad = centerLng * Math.PI / 180

  // Generate circle edge points
  const circlePoints: THREE.Vector3[] = []
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
    circlePoints.push(latLngToPoint(lat * 180 / Math.PI, lng * 180 / Math.PI, 1.003))
  }

  // Create the circle outline - bright red
  const lineGeometry = new THREE.BufferGeometry().setFromPoints(circlePoints)
  const lineMaterial = new THREE.LineBasicMaterial({
    color: 0xff4444,
    linewidth: 2,
    transparent: true,
    opacity
  })
  const circle = new THREE.Line(lineGeometry, lineMaterial)
  circle.renderOrder = 15

  // Create filled area - triangles from center to edge
  const centerPoint3D = latLngToPoint(centerLat, centerLng, 1.0025)
  const fillVertices: number[] = []
  for (let i = 0; i < segments; i++) {
    fillVertices.push(centerPoint3D.x, centerPoint3D.y, centerPoint3D.z)
    fillVertices.push(circlePoints[i].x, circlePoints[i].y, circlePoints[i].z)
    fillVertices.push(circlePoints[i + 1].x, circlePoints[i + 1].y, circlePoints[i + 1].z)
  }

  const fillGeometry = new THREE.BufferGeometry()
  fillGeometry.setAttribute('position', new THREE.Float32BufferAttribute(fillVertices, 3))
  const fillMaterial = new THREE.MeshBasicMaterial({
    color: 0xff4444,
    transparent: true,
    opacity: opacity * 0.06,
    side: THREE.DoubleSide,
    depthWrite: false
  })
  const fill = new THREE.Mesh(fillGeometry, fillMaterial)
  fill.renderOrder = 14

  // Group circle and fill together
  const group = new THREE.Group()
  group.add(fill)
  group.add(circle)

  return { circle: group, centerPoint: latLngToPoint(centerLat, centerLng, 1.003) }
}

/**
 * Create a center marker sprite (crosshair)
 */
export function createCenterMarker(
  position: THREE.Vector3,
  opacity: number = 1
): THREE.Sprite & { targetPixels: number } {
  const canvas = document.createElement('canvas')
  canvas.width = 24
  canvas.height = 24
  const ctx = canvas.getContext('2d')!

  // Draw crosshair - 4 lines with gap in center
  ctx.strokeStyle = `rgba(120, 120, 120, ${opacity})`
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(2, 12)
  ctx.lineTo(8, 12)
  ctx.moveTo(16, 12)
  ctx.lineTo(22, 12)
  ctx.moveTo(12, 2)
  ctx.lineTo(12, 8)
  ctx.moveTo(12, 16)
  ctx.lineTo(12, 22)
  ctx.stroke()

  const texture = new THREE.CanvasTexture(canvas)
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
  })

  const sprite = new THREE.Sprite(material) as THREE.Sprite & { targetPixels: number }
  sprite.position.copy(position)
  sprite.scale.set(0.025, 0.025, 1)
  sprite.renderOrder = 17
  sprite.targetPixels = 24
  return sprite
}

/**
 * Dispose a THREE.Group and all its children
 */
export function disposeGroup(group: THREE.Group): void {
  group.traverse((child) => {
    if (child instanceof THREE.Mesh || child instanceof THREE.Line) {
      child.geometry?.dispose()
      if (child.material instanceof THREE.Material) {
        child.material.dispose()
      }
    }
  })
}

/**
 * Dispose a THREE.Sprite and its material/texture
 */
export function disposeSprite(sprite: THREE.Sprite): void {
  if (sprite.material instanceof THREE.SpriteMaterial && sprite.material.map) {
    sprite.material.map.dispose()
  }
  sprite.material?.dispose()
}

/**
 * Convert 3D point to lat/lng
 */
export function pointToLatLng(point: THREE.Vector3): { lat: number; lng: number } {
  const normalized = point.clone().normalize()
  const lat = 90 - Math.acos(normalized.y) * 180 / Math.PI
  const lng = Math.atan2(normalized.z, -normalized.x) * 180 / Math.PI - 180
  return { lat, lng }
}
