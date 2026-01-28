/**
 * useMeasurementTool - Measurement state and logic
 * Manages measurement points, completed measurements, and snap settings
 */

import { useState, useCallback, useRef } from 'react'
import type * as THREE from 'three'

export interface MeasurePoint {
  coords: [number, number]  // [lat, lng]
  snapped: boolean
}

export interface Measurement {
  id: string
  points: [[number, number], [number, number]]  // [start, end] as [lat, lng]
  snapped?: [boolean, boolean]
  color?: string
  distance?: number
}

export type MeasureUnit = 'km' | 'mi'

interface MeasurementToolOptions {
  initialUnit?: MeasureUnit
  initialSnapEnabled?: boolean
}

// Color palette for measurements
const MEASUREMENT_COLORS = [
  '#32CD32', // Lime green
  '#FF6B6B', // Coral
  '#4ECDC4', // Teal
  '#FFE66D', // Yellow
  '#95E1D3', // Mint
  '#F38181', // Salmon
  '#AA96DA', // Lavender
  '#FCBAD3', // Pink
]

export function useMeasurementTool(options: MeasurementToolOptions = {}) {
  const {
    initialUnit = 'km',
    initialSnapEnabled = true
  } = options

  // Current measurement points (0, 1, or 2 points)
  const [currentMeasurePoints, setCurrentMeasurePoints] = useState<MeasurePoint[]>([])

  // Completed measurements
  const [measurements, setMeasurements] = useState<Measurement[]>([])

  // Selected measurement for editing/deletion
  const [selectedMeasurementId, setSelectedMeasurementId] = useState<string | null>(null)

  // Unit (km or mi)
  const [measureUnit, setMeasureUnit] = useState<MeasureUnit>(initialUnit)

  // Snap to sites enabled
  const [measureSnapEnabled, setMeasureSnapEnabled] = useState(initialSnapEnabled)

  // Current measurement color
  const [currentMeasurementColor, setCurrentMeasurementColor] = useState(MEASUREMENT_COLORS[0])

  // Refs for 3D objects
  const measurementObjectsRef = useRef<THREE.Object3D[]>([])
  const measurementLabelsRef = useRef<Array<{
    label: THREE.Sprite
    midpoint: THREE.Vector3
    targetWidth: number
    targetHeight: number
  }>>([])
  const measurementLinesRef = useRef<Array<{
    line: THREE.Line
    points: THREE.Vector3[]
  }>>([])
  const measurementMarkersRef = useRef<Array<{
    marker: THREE.Object3D
    position: THREE.Vector3
  }>>([])

  // Add a point to current measurement
  const addMeasurePoint = useCallback((coords: [number, number], snapped: boolean) => {
    setCurrentMeasurePoints(prev => {
      if (prev.length >= 2) return prev  // Max 2 points
      return [...prev, { coords, snapped }]
    })
  }, [])

  // Complete current measurement (when 2 points are set)
  const completeMeasurement = useCallback(() => {
    if (currentMeasurePoints.length !== 2) return

    const [start, end] = currentMeasurePoints
    const newMeasurement: Measurement = {
      id: `m-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      points: [start.coords, end.coords],
      snapped: [start.snapped, end.snapped],
      color: currentMeasurementColor
    }

    setMeasurements(prev => [...prev, newMeasurement])
    setCurrentMeasurePoints([])

    // Cycle to next color
    const currentIndex = MEASUREMENT_COLORS.indexOf(currentMeasurementColor)
    const nextIndex = (currentIndex + 1) % MEASUREMENT_COLORS.length
    setCurrentMeasurementColor(MEASUREMENT_COLORS[nextIndex])
  }, [currentMeasurePoints, currentMeasurementColor])

  // Clear current measurement (cancel in-progress)
  const clearCurrentMeasurement = useCallback(() => {
    setCurrentMeasurePoints([])
  }, [])

  // Delete a specific measurement
  const deleteMeasurement = useCallback((id: string) => {
    setMeasurements(prev => prev.filter(m => m.id !== id))
    if (selectedMeasurementId === id) {
      setSelectedMeasurementId(null)
    }
  }, [selectedMeasurementId])

  // Delete all measurements
  const clearAllMeasurements = useCallback(() => {
    setMeasurements([])
    setCurrentMeasurePoints([])
    setSelectedMeasurementId(null)
  }, [])

  // Toggle snap to sites
  const toggleMeasureSnap = useCallback(() => {
    setMeasureSnapEnabled(prev => !prev)
  }, [])

  // Toggle unit
  const toggleMeasureUnit = useCallback(() => {
    setMeasureUnit(prev => prev === 'km' ? 'mi' : 'km')
  }, [])

  // Select a measurement
  const selectMeasurement = useCallback((id: string | null) => {
    setSelectedMeasurementId(id)
  }, [])

  return {
    // Current measurement
    currentMeasurePoints,
    setCurrentMeasurePoints,
    addMeasurePoint,
    completeMeasurement,
    clearCurrentMeasurement,

    // Completed measurements
    measurements,
    setMeasurements,
    deleteMeasurement,
    clearAllMeasurements,

    // Selection
    selectedMeasurementId,
    selectMeasurement,

    // Settings
    measureUnit,
    setMeasureUnit,
    toggleMeasureUnit,
    measureSnapEnabled,
    setMeasureSnapEnabled,
    toggleMeasureSnap,

    // Color
    currentMeasurementColor,
    setCurrentMeasurementColor,

    // 3D object refs
    measurementObjectsRef,
    measurementLabelsRef,
    measurementLinesRef,
    measurementMarkersRef,

    // Constants
    MEASUREMENT_COLORS
  }
}
