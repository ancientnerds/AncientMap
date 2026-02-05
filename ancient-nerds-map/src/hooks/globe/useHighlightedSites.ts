/**
 * useHighlightedSites - Hook for managing highlighted sites state and rendering
 *
 * Consolidates:
 * - listHighlightedSites state
 * - listHighlightedPositions state
 * - Highlighted sites rendering effect (Three.JS and Mapbox modes)
 * - Cleanup of highlight glows
 */

import { useEffect, useState, useCallback } from 'react'
import type { GlobeRefs } from './types'
import type { SiteData } from '../../data/sites'
import {
  cleanupHighlightGlows,
  renderHighlightedSitesMapbox,
  renderHighlightedSitesThreeJS,
  type HighlightedSitesContext,
  type HighlightedSitesOptions,
} from '../../components/Globe/rendering/highlightedSitesRenderer'

interface UseHighlightedSitesOptions {
  refs: GlobeRefs
  highlightedSiteId?: string | null
  listFrozenSiteIds: string[]
  showMapbox: boolean
  sites: SiteData[]
}

interface UseHighlightedSitesReturn {
  listHighlightedSites: SiteData[]
  setListHighlightedSites: (sites: SiteData[]) => void
  listHighlightedPositions: Map<string, { x: number; y: number }>
  setListHighlightedPositions: (positions: Map<string, { x: number; y: number }>) => void
}

export function useHighlightedSites({
  refs,
  highlightedSiteId,
  listFrozenSiteIds,
  showMapbox,
  sites,
}: UseHighlightedSitesOptions): UseHighlightedSitesReturn {
  const [listHighlightedSites, setListHighlightedSitesState] = useState<SiteData[]>([])
  const [listHighlightedPositions, setListHighlightedPositionsState] = useState<Map<string, { x: number; y: number }>>(new Map())

  // Sync state to refs
  const setListHighlightedSites = useCallback((sites: SiteData[]) => {
    setListHighlightedSitesState(sites)
    refs.listHighlightedSites.current = sites
  }, [refs.listHighlightedSites])

  const setListHighlightedPositions = useCallback((positions: Map<string, { x: number; y: number }>) => {
    setListHighlightedPositionsState(positions)
    refs.listHighlightedPositions.current = positions
  }, [refs.listHighlightedPositions])

  // Handle highlighted sites from search/proximity list hover (or frozen from click)
  useEffect(() => {
    // Clean up existing glows (Three.js only)
    cleanupHighlightGlows(refs.scene.current?.globe, refs.highlightGlows)

    // Build options for renderer
    const options: HighlightedSitesOptions = {
      highlightedSiteId,
      listFrozenSiteIds,
      showMapbox,
      mapboxService: refs.mapboxService.current,
    }

    // Check if we have any active sites
    const activeSiteIds = listFrozenSiteIds.length > 0
      ? (highlightedSiteId && !listFrozenSiteIds.includes(highlightedSiteId)
          ? [...listFrozenSiteIds, highlightedSiteId]
          : listFrozenSiteIds)
      : (highlightedSiteId ? [highlightedSiteId] : [])

    if (activeSiteIds.length === 0) {
      setListHighlightedSites([])
      setListHighlightedPositions(new Map())
      return
    }

    let result: { visibleSites: SiteData[]; positions: Map<string, { x: number; y: number }> }

    // MAPBOX MODE: Use Mapbox projection for screen positions
    if (showMapbox && refs.mapboxService.current?.getIsInitialized()) {
      result = renderHighlightedSitesMapbox(
        options,
        refs.validSites.current,
        listFrozenSiteIds,
        refs.listHighlightedPositions.current
      )
    } else if (refs.scene.current) {
      // THREE.JS MODE: Use Three.js projection and add ring sprites
      const ctx: HighlightedSitesContext = {
        globe: refs.scene.current.globe,
        camera: refs.scene.current.camera,
        highlightGlowsRef: refs.highlightGlows,
        validSitesRef: refs.validSites,
        listHighlightedPositionsRef: refs.listHighlightedPositions,
      }
      result = renderHighlightedSitesThreeJS(ctx, options, sites)
    } else {
      setListHighlightedSites([])
      return
    }

    setListHighlightedSites(result.visibleSites)
    setListHighlightedPositions(result.positions)
  }, [highlightedSiteId, listFrozenSiteIds, showMapbox, sites, refs.scene, refs.highlightGlows, refs.mapboxService, refs.validSites, refs.listHighlightedPositions, setListHighlightedSites, setListHighlightedPositions])

  return {
    listHighlightedSites,
    setListHighlightedSites,
    listHighlightedPositions,
    setListHighlightedPositions,
  }
}
