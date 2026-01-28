/**
 * useSiteTooltips - Hook for managing site tooltip state
 *
 * Consolidates:
 * - hoveredSite/frozenSite state
 * - Tooltip position tracking
 * - isFrozen state
 * - Sync highlightedSiteId to frozenSite
 * - Update frozenSite when sites data changes
 */

import { useEffect, useState, useCallback } from 'react'
import type { GlobeRefs } from './types'
import type { SiteData } from '../../data/sites'
import { calculateSiteTooltipPosition } from '../../components/Globe/rendering/highlightedSitesRenderer'

interface UseSiteTooltipsOptions {
  refs: GlobeRefs
  highlightedSiteId?: string | null
  listFrozenSiteIds: string[]
  sites: SiteData[]
}

interface UseSiteTooltipsReturn {
  hoveredSite: SiteData | null
  setHoveredSite: (site: SiteData | null) => void
  frozenSite: SiteData | null
  setFrozenSite: (site: SiteData | null) => void
  tooltipPos: { x: number; y: number }
  setTooltipPos: (pos: { x: number; y: number }) => void
  isFrozen: boolean
  setIsFrozen: (frozen: boolean) => void
  tooltipSiteOnFront: boolean
  setTooltipSiteOnFront: (onFront: boolean) => void
}

export function useSiteTooltips({
  refs,
  highlightedSiteId,
  listFrozenSiteIds,
  sites,
}: UseSiteTooltipsOptions): UseSiteTooltipsReturn {
  // Tooltip state
  const [hoveredSite, setHoveredSiteState] = useState<SiteData | null>(null)
  const [frozenSite, setFrozenSiteState] = useState<SiteData | null>(null)
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 })
  const [tooltipSiteOnFront, setTooltipSiteOnFront] = useState(true)
  const [isFrozen, setIsFrozenState] = useState(false)

  // Sync state to refs
  const setHoveredSite = useCallback((site: SiteData | null) => {
    setHoveredSiteState(site)
    refs.hoveredSite.current = site
  }, [refs.hoveredSite])

  const setFrozenSite = useCallback((site: SiteData | null) => {
    setFrozenSiteState(site)
    refs.frozenSite.current = site
  }, [refs.frozenSite])

  const setIsFrozen = useCallback((frozen: boolean) => {
    setIsFrozenState(frozen)
    refs.isFrozen.current = frozen
  }, [refs.isFrozen])

  // Sync highlightedSiteId to frozenSite - for hover tooltip only (not for selected sites)
  useEffect(() => {
    if (highlightedSiteId) {
      // Don't use frozenSite system if site is already selected (it uses listHighlightedSites tooltips)
      if (listFrozenSiteIds.includes(highlightedSiteId)) {
        // Clear frozenSite if it was set - let listHighlightedSites handle it
        if (frozenSite?.id === highlightedSiteId) {
          setFrozenSite(null)
          refs.highlightFrozen.current = false
          setIsFrozen(false)
        }
        return
      }

      const site = refs.validSites.current.find(s => s.id === highlightedSiteId)
      if (site && refs.scene.current) {
        setFrozenSite(site)
        refs.highlightFrozen.current = true // Mark as highlight-triggered (skip cursor distance check)
        setIsFrozen(true)

        // Calculate tooltip position from site's 3D position on globe
        const pos = calculateSiteTooltipPosition(site, refs.scene.current.camera)
        setTooltipPos(pos)
        refs.frozenTooltipPos.current = pos
      }
    } else {
      // Clear frozenSite when highlightedSiteId is cleared
      if (refs.highlightFrozen.current) {
        setFrozenSite(null)
        refs.highlightFrozen.current = false
        setIsFrozen(false)
      }
    }
  }, [highlightedSiteId, listFrozenSiteIds, frozenSite, refs.validSites, refs.scene, refs.highlightFrozen, refs.frozenTooltipPos, setFrozenSite, setIsFrozen])

  // Update frozenSite when sites data changes (e.g., after admin edit)
  useEffect(() => {
    if (frozenSite) {
      const updatedSite = sites.find(s => s.id === frozenSite.id)
      if (updatedSite && (
        updatedSite.title !== frozenSite.title ||
        updatedSite.description !== frozenSite.description ||
        updatedSite.category !== frozenSite.category ||
        updatedSite.period !== frozenSite.period
      )) {
        setFrozenSite(updatedSite)
      }
    }
  }, [sites, frozenSite, setFrozenSite])

  return {
    hoveredSite,
    setHoveredSite,
    frozenSite,
    setFrozenSite,
    tooltipPos,
    setTooltipPos,
    isFrozen,
    setIsFrozen,
    tooltipSiteOnFront,
    setTooltipSiteOnFront,
  }
}
