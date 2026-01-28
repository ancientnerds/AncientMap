/**
 * Measurement Renderer Module
 *
 * Handles rendering of measurement lines, markers, and distance labels on the globe.
 * Supports both completed measurements and in-progress drawing.
 *
 * Extracted from Globe.tsx to reduce file size and improve maintainability.
 */

import * as THREE from 'three'
import {
  latLngToPoint,
  createGreatCircleArc,
  createMarkerPoints,
  createRingMarker,
  createMeasurementLine,
  createDistanceLabel,
} from '../../../utils/measurementHelpers'

// ============================================================================
// Types
// ============================================================================

export interface Measurement {
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

export interface MeasurementRendererContext {
  globe: THREE.Mesh
  measurementObjectsRef: React.MutableRefObject<THREE.Object3D[]>
  measurementLabelsRef: React.MutableRefObject<MeasurementLabelEntry[]>
  measurementLinesRef: React.MutableRefObject<MeasurementLineEntry[]>
  measurementMarkersRef: React.MutableRefObject<MeasurementMarkerEntry[]>
}

export interface MeasurementRendererOptions {
  measurements: Measurement[]
  currentMeasurePoints: MeasurePoint[]
  selectedMeasurementId: string | null | undefined
  measureUnit: 'km' | 'miles'
  currentMeasurementColor: string
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Clean up measurement objects from the scene
 */
function cleanupMeasurementObjects(
  globe: THREE.Mesh,
  measurementObjectsRef: React.MutableRefObject<THREE.Object3D[]>,
  measurementLabelsRef: React.MutableRefObject<MeasurementLabelEntry[]>,
  measurementLinesRef: React.MutableRefObject<MeasurementLineEntry[]>,
  measurementMarkersRef: React.MutableRefObject<MeasurementMarkerEntry[]>
): void {
  for (const obj of measurementObjectsRef.current) {
    globe.remove(obj)
    if ((obj as any).geometry) (obj as any).geometry.dispose()
    if ((obj as any).material) {
      const mat = (obj as any).material
      if (mat.map) mat.map.dispose()
      mat.dispose()
    }
  }
  measurementObjectsRef.current = []
  measurementLabelsRef.current = []
  measurementLinesRef.current = []
  measurementMarkersRef.current = []
}

/**
 * Add a marker (ring for snapped, square for non-snapped)
 */
function addMarker(
  globe: THREE.Mesh,
  position: THREE.Vector3,
  color: number,
  snapped: boolean,
  measurementObjectsRef: React.MutableRefObject<THREE.Object3D[]>,
  measurementMarkersRef: React.MutableRefObject<MeasurementMarkerEntry[]>
): void {
  if (snapped) {
    const ring = createRingMarker(position, color)
    globe.add(ring)
    measurementObjectsRef.current.push(ring)
    measurementMarkersRef.current.push({ marker: ring, position: position.clone() })
  } else {
    const marker = createMarkerPoints([position], color)
    globe.add(marker)
    measurementObjectsRef.current.push(marker)
    measurementMarkersRef.current.push({ marker, position: position.clone() })
  }
}

// ============================================================================
// Main Renderer Function
// ============================================================================

/**
 * Render all measurements on the globe
 */
export function renderMeasurements(
  ctx: MeasurementRendererContext,
  options: MeasurementRendererOptions
): void {
  const { globe, measurementObjectsRef, measurementLabelsRef, measurementLinesRef, measurementMarkersRef } = ctx
  const { measurements, currentMeasurePoints, selectedMeasurementId, measureUnit, currentMeasurementColor } = options

  // Clean up previous measurement objects
  cleanupMeasurementObjects(globe, measurementObjectsRef, measurementLabelsRef, measurementLinesRef, measurementMarkersRef)

  // Render all completed measurements
  measurements.forEach((measurement) => {
    const isSelected = selectedMeasurementId === measurement.id
    const baseColor = measurement.color || '#32CD32'
    const colorNum = parseInt(baseColor.replace('#', ''), 16)
    const colorStr = baseColor
    const [start, end] = measurement.points
    const [startSnapped, endSnapped] = measurement.snapped || [false, false]

    // Add line
    const line = createMeasurementLine(start, end, colorNum, isSelected ? 1.0 : 0.7)
    globe.add(line)
    measurementObjectsRef.current.push(line)

    // Track line with its arc points for back-side fading
    const linePoints = createGreatCircleArc(start[0], start[1], end[0], end[1])
    measurementLinesRef.current.push({ line, points: linePoints })

    // Add markers - ring for snapped points, square for non-snapped
    const startPos = latLngToPoint(start[0], start[1])
    const endPos = latLngToPoint(end[0], end[1])

    addMarker(globe, startPos, colorNum, startSnapped, measurementObjectsRef, measurementMarkersRef)
    addMarker(globe, endPos, colorNum, endSnapped, measurementObjectsRef, measurementMarkersRef)

    // Add distance label
    const label = createDistanceLabel(start, end, colorStr, measureUnit)
    globe.add(label)
    measurementObjectsRef.current.push(label)
    measurementLabelsRef.current.push({
      label,
      midpoint: label.position.clone(),
      targetWidth: (label as any).targetWidth || 60,
      targetHeight: (label as any).targetHeight || 20
    })
  })

  // Render current measurement being drawn (if any)
  if (currentMeasurePoints.length > 0) {
    const colorStr = currentMeasurementColor
    const color = parseInt(colorStr.replace('#', ''), 16)
    const firstPoint = currentMeasurePoints[0]

    // Add marker for first point
    const pos1 = latLngToPoint(firstPoint.coords[0], firstPoint.coords[1])
    addMarker(globe, pos1, color, firstPoint.snapped, measurementObjectsRef, measurementMarkersRef)

    // If we have second point, add line, second marker and label
    if (currentMeasurePoints.length === 2) {
      const secondPoint = currentMeasurePoints[1]
      const pos2 = latLngToPoint(secondPoint.coords[0], secondPoint.coords[1])

      addMarker(globe, pos2, color, secondPoint.snapped, measurementObjectsRef, measurementMarkersRef)

      // Add line
      const line = createMeasurementLine(firstPoint.coords, secondPoint.coords, color)
      globe.add(line)
      measurementObjectsRef.current.push(line)
      const linePoints = createGreatCircleArc(firstPoint.coords[0], firstPoint.coords[1], secondPoint.coords[0], secondPoint.coords[1])
      measurementLinesRef.current.push({ line, points: linePoints })

      // Add distance label
      const label = createDistanceLabel(firstPoint.coords, secondPoint.coords, colorStr, measureUnit)
      globe.add(label)
      measurementObjectsRef.current.push(label)
      measurementLabelsRef.current.push({
        label,
        midpoint: label.position.clone(),
        targetWidth: (label as any).targetWidth || 60,
        targetHeight: (label as any).targetHeight || 20
      })
    }
  }
}
