import { useState, useRef, useCallback } from 'react'
import { SiteCard } from '../SiteCard'
import { config } from '../../config'
import { apiDetailToSiteData } from '../../utils/siteApi'
import type { SiteData } from '../../data/sites'

interface SiteChipProps {
  siteId: string
  children: React.ReactNode
  onOpenPopup: (site: SiteData) => void
  onFlyTo?: (coords: [number, number]) => void
  onHighlight?: (ids: string[]) => void
}

const siteCache = new Map<string, SiteData>()

export default function SiteChip({ siteId, children, onOpenPopup, onFlyTo, onHighlight }: SiteChipProps) {
  const [preview, setPreview] = useState<SiteData | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const chipRef = useRef<HTMLSpanElement>(null)

  const fetchSite = useCallback(async (): Promise<SiteData | null> => {
    const cached = siteCache.get(siteId)
    if (cached) return cached
    try {
      const res = await fetch(`${config.api.baseUrl}/sites/${siteId}`)
      if (!res.ok) return null
      const detail = await res.json()
      const site = apiDetailToSiteData(detail)
      siteCache.set(siteId, site)
      return site
    } catch {
      return null
    }
  }, [siteId])

  const handleMouseEnter = useCallback(() => {
    if (leaveTimer.current) { clearTimeout(leaveTimer.current); leaveTimer.current = null }
    hoverTimer.current = setTimeout(async () => {
      const site = await fetchSite()
      if (site) { setPreview(site); setShowPreview(true) }
    }, 300)
  }, [fetchSite])

  const handleMouseLeave = useCallback(() => {
    if (hoverTimer.current) { clearTimeout(hoverTimer.current); hoverTimer.current = null }
    leaveTimer.current = setTimeout(() => setShowPreview(false), 200)
  }, [])

  const handlePreviewEnter = useCallback(() => {
    if (leaveTimer.current) { clearTimeout(leaveTimer.current); leaveTimer.current = null }
  }, [])

  const handlePreviewLeave = useCallback(() => {
    leaveTimer.current = setTimeout(() => setShowPreview(false), 200)
  }, [])

  const handleClick = useCallback(async () => {
    const site = await fetchSite()
    if (!site) return
    onOpenPopup(site)
    if (onFlyTo && site.coordinates) {
      onHighlight?.([siteId])
      onFlyTo(site.coordinates)
    }
  }, [fetchSite, onOpenPopup, onFlyTo, onHighlight, siteId])

  return (
    <span className="lyra-site-chip-wrap" ref={chipRef}>
      <button
        className="lyra-site-chip"
        onClick={handleClick}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <span className="lyra-site-chip-dot" />
        {children}
      </button>
      {showPreview && preview && (
        <div
          className="lyra-site-preview"
          onMouseEnter={handlePreviewEnter}
          onMouseLeave={handlePreviewLeave}
        >
          <SiteCard
            site={preview}
            onClick={handleClick}
          />
        </div>
      )}
    </span>
  )
}
