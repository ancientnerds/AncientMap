/**
 * useLayersReady - Hook for coordinating layer readiness
 *
 * Consolidates:
 * - Ready state tracking for all essential visual elements
 * - onLayersReady callback coordination
 * - Polling for remaining elements after core textures load
 */

import { useEffect } from 'react'
import type { GlobeRefs } from './types'

interface UseLayersReadyOptions {
  refs: GlobeRefs
  labelsLoaded: boolean
  texturesReady: boolean
  layersLoaded: Record<string, boolean>
  onLayersReady?: () => void
}

export function useLayersReady({
  refs,
  labelsLoaded,
  texturesReady,
  layersLoaded,
  onLayersReady,
}: UseLayersReadyOptions): void {
  // Call onLayersReady when ALL essential assets are loaded AND basemap is visible
  // This triggers the splash screen to fade and warp animation to start
  // CRITICAL: Must wait for basemap, textures, labels, coastlines, AND borders to be visible
  useEffect(() => {
    if (refs.layersReadyCalled.current) return

    // Wait for ALL essential visual elements before starting warp
    const basemapVisible = refs.basemapMesh.current?.visible === true
    const coastlinesLoaded = layersLoaded['coastlines'] === true
    const bordersLoaded = layersLoaded['countryBorders'] === true
    const allReady = labelsLoaded && texturesReady && basemapVisible && coastlinesLoaded && bordersLoaded

    if (allReady) {
      console.log('[Loading] ALL ASSETS READY (textures, labels, coastlines, borders) - starting warp')
      refs.layersReadyCalled.current = true
      onLayersReady?.()
    } else if (labelsLoaded && texturesReady) {
      // Core textures ready, poll for remaining elements
      const missing: string[] = []
      if (!basemapVisible) missing.push('basemap')
      if (!coastlinesLoaded) missing.push('coastlines')
      if (!bordersLoaded) missing.push('borders')
      console.log(`[Loading] Textures/labels ready. Waiting for: ${missing.join(', ')}`)

      // Poll for remaining elements
      const checkInterval = setInterval(() => {
        const nowBasemapVisible = refs.basemapMesh.current?.visible === true
        const nowCoastlinesLoaded = layersLoaded['coastlines'] === true
        const nowBordersLoaded = layersLoaded['countryBorders'] === true
        if (nowBasemapVisible && nowCoastlinesLoaded && nowBordersLoaded) {
          clearInterval(checkInterval)
          if (!refs.layersReadyCalled.current) {
            console.log('[Loading] All visual elements ready - starting warp')
            refs.layersReadyCalled.current = true
            onLayersReady?.()
          }
        }
      }, 50)
      return () => clearInterval(checkInterval)
    }
  }, [labelsLoaded, texturesReady, layersLoaded, onLayersReady, refs.layersReadyCalled, refs.basemapMesh])
}
