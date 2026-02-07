import { useState, useEffect, useRef } from 'react'
import { config } from '../../config'
import { categorizePeriod } from '../../data/sites'
import type { SiteData } from '../../data/sites'
import type { AlternateSource } from './types'

// Simple cache to avoid re-fetching on re-renders
const cache = new Map<string, AlternateSource[]>()

export function alternateToSiteData(alt: AlternateSource): SiteData {
  return {
    id: alt.id,
    title: alt.name,
    location: alt.country || '',
    category: alt.siteType || '',
    period: alt.periodName || categorizePeriod(alt.periodStart),
    periodStart: alt.periodStart,
    description: alt.description || '',
    image: alt.thumbnailUrl,
    sourceUrl: alt.sourceUrl,
    sourceId: alt.sourceId,
    coordinates: [alt.lon, alt.lat],
  }
}

export function useAlternateSources(site: SiteData | undefined): {
  alternates: AlternateSource[]
  isLoading: boolean
} {
  const [alternates, setAlternates] = useState<AlternateSource[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!site) {
      setAlternates([])
      return
    }

    const siteId = site.id

    // Return cached result if available
    if (cache.has(siteId)) {
      setAlternates(cache.get(siteId)!)
      return
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setIsLoading(true)
    fetch(`${config.api.baseUrl}/sites/${siteId}/alternates`, { signal: controller.signal })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (controller.signal.aborted) return
        const alts: AlternateSource[] = data?.alternates || []
        cache.set(siteId, alts)
        setAlternates(alts)
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.warn('Failed to fetch alternate sources:', err)
          setAlternates([])
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false)
      })

    return () => controller.abort()
  }, [site?.id])

  return { alternates, isLoading }
}
