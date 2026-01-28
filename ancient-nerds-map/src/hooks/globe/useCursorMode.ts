/**
 * useCursorMode - Hook for managing globe cursor styles
 *
 * Consolidates:
 * - Custom crosshair cursor SVG
 * - Proximity mode cursor handling
 * - Measure mode cursor handling
 * - Mapbox cursor sync
 */

import { useEffect } from 'react'
import type { GlobeRefs } from './types'

interface UseCursorModeOptions {
  refs: GlobeRefs
  proximityIsSettingOnGlobe?: boolean
  measureMode: boolean
}

export function useCursorMode({
  refs,
  proximityIsSettingOnGlobe,
  measureMode,
}: UseCursorModeOptions): void {
  // Handle proximity mode - set data attribute for click detection
  // Always use custom crosshair cursor on globe (4 lines with hole in center)
  useEffect(() => {
    if (!refs.container.current) return

    // Custom crosshair SVG: 4 lines with gap in center
    const size = 24
    const gap = 4
    const center = size / 2
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">
        <line x1="${center}" y1="0" x2="${center}" y2="${center - gap}" stroke="white" stroke-width="1.5"/>
        <line x1="${center}" y1="${center + gap}" x2="${center}" y2="${size}" stroke="white" stroke-width="1.5"/>
        <line x1="0" y1="${center}" x2="${center - gap}" y2="${center}" stroke="white" stroke-width="1.5"/>
        <line x1="${center + gap}" y1="${center}" x2="${size}" y2="${center}" stroke="white" stroke-width="1.5"/>
        <line x1="${center}" y1="0" x2="${center}" y2="${center - gap}" stroke="rgba(0,0,0,0.5)" stroke-width="3"/>
        <line x1="${center}" y1="${center + gap}" x2="${center}" y2="${size}" stroke="rgba(0,0,0,0.5)" stroke-width="3"/>
        <line x1="0" y1="${center}" x2="${center - gap}" y2="${center}" stroke="rgba(0,0,0,0.5)" stroke-width="3"/>
        <line x1="${center + gap}" y1="${center}" x2="${size}" y2="${center}" stroke="rgba(0,0,0,0.5)" stroke-width="3"/>
        <line x1="${center}" y1="0" x2="${center}" y2="${center - gap}" stroke="white" stroke-width="1"/>
        <line x1="${center}" y1="${center + gap}" x2="${center}" y2="${size}" stroke="white" stroke-width="1"/>
        <line x1="0" y1="${center}" x2="${center - gap}" y2="${center}" stroke="white" stroke-width="1"/>
        <line x1="${center + gap}" y1="${center}" x2="${size}" y2="${center}" stroke="white" stroke-width="1"/>
      </svg>
    `.replace(/\n\s*/g, '')
    const cursorUrl = `url("data:image/svg+xml,${encodeURIComponent(svg)}") ${center} ${center}, crosshair`
    refs.container.current.style.cursor = cursorUrl

    if (proximityIsSettingOnGlobe) {
      refs.container.current.dataset.proximityMode = 'true'
      // Also set Mapbox cursor when in primary mode
      if (refs.mapboxService.current?.getIsPrimaryMode()) {
        refs.mapboxService.current.setCursor('crosshair')
      }
    } else {
      refs.container.current.dataset.proximityMode = 'false'
      // Reset Mapbox cursor if not in measure mode either
      if (refs.mapboxService.current?.getIsPrimaryMode() && !refs.measureMode.current) {
        refs.mapboxService.current.setCursor('grab')
      }
    }
  }, [proximityIsSettingOnGlobe, refs.container, refs.mapboxService, refs.measureMode])

  // Handle measure mode cursor for Mapbox
  useEffect(() => {
    if (!refs.mapboxService.current?.getIsPrimaryMode()) return

    if (measureMode) {
      refs.mapboxService.current.setCursor('crosshair')
    } else if (!proximityIsSettingOnGlobe) {
      // Only reset to grab if not in proximity mode either
      refs.mapboxService.current.setCursor('grab')
    }
  }, [measureMode, proximityIsSettingOnGlobe, refs.mapboxService])
}
