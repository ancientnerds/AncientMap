import { useState, useEffect, useMemo, useRef } from 'react'
import {
  groupByTab,
  type GroupedGalleryItems,
  type ContentItem,
  CONTENT_TIERS,
  type ContentTier,
  type ContentSearchResponse,
} from '../../../services/connectors'

export interface TieredFetchResult {
  grouped: GroupedGalleryItems
  tier1Loading: boolean
  tier2Loading: boolean
  tier3Loading: boolean
  tier4Loading: boolean
  isLoading: boolean
  sourcesSearched: string[]
  sourcesFailed: string[]
  itemsBySource: Record<string, number>
  searchTimeMs: number
}

export function useTieredFetch(
  fetchFn: (tier: ContentTier) => Promise<ContentSearchResponse>,
  key: string,
  enabled: boolean
): TieredFetchResult {
  const [tier1Items, setTier1Items] = useState<ContentItem[]>([])
  const [tier2Items, setTier2Items] = useState<ContentItem[]>([])
  const [tier3Items, setTier3Items] = useState<ContentItem[]>([])
  const [tier4Items, setTier4Items] = useState<ContentItem[]>([])

  const [tier1Loading, setTier1Loading] = useState(false)
  const [tier2Loading, setTier2Loading] = useState(false)
  const [tier3Loading, setTier3Loading] = useState(false)
  const [tier4Loading, setTier4Loading] = useState(false)

  const [sourcesSearched, setSourcesSearched] = useState<string[]>([])
  const [sourcesFailed, setSourcesFailed] = useState<string[]>([])
  const [itemsBySource, setItemsBySource] = useState<Record<string, number>>({})
  const [searchTimeMs, setSearchTimeMs] = useState(0)

  const fetchedRef = useRef<string | null>(null)

  useEffect(() => {
    if (fetchedRef.current === key || !enabled) return

    // Reset state
    setTier1Items([]); setTier2Items([]); setTier3Items([]); setTier4Items([])
    setSourcesSearched([]); setSourcesFailed([]); setItemsBySource({}); setSearchTimeMs(0)

    const doFetch = async (
      tier: ContentTier,
      setItems: React.Dispatch<React.SetStateAction<ContentItem[]>>,
      setLoading: React.Dispatch<React.SetStateAction<boolean>>
    ) => {
      setLoading(true)
      try {
        const result = await fetchFn(tier)
        console.log(`[useTieredFetch] ${CONTENT_TIERS[tier].label}:`, result.items.length, 'items from', result.sources_searched)
        setItems(result.items)

        // Aggregate metadata additively
        setSourcesSearched(prev => [...new Set([...prev, ...result.sources_searched])])
        setSourcesFailed(prev => [...new Set([...prev, ...result.sources_failed])])
        setItemsBySource(prev => {
          const merged = { ...prev }
          for (const [source, count] of Object.entries(result.items_by_source || {})) {
            merged[source] = (merged[source] || 0) + count
          }
          return merged
        })
        setSearchTimeMs(prev => Math.max(prev, result.search_time_ms))
      } catch (err) {
        console.warn(`Failed to load ${CONTENT_TIERS[tier].label}:`, err)
        setItems([])
      } finally {
        setLoading(false)
      }
    }

    fetchedRef.current = key

    // ALL tiers start immediately in parallel
    doFetch('tier1', setTier1Items, setTier1Loading)
    doFetch('tier2', setTier2Items, setTier2Loading)
    doFetch('tier3', setTier3Items, setTier3Loading)
    doFetch('tier4', setTier4Items, setTier4Loading)
  }, [key, enabled, fetchFn])

  const contentItems = useMemo(
    () => [...tier1Items, ...tier2Items, ...tier3Items, ...tier4Items],
    [tier1Items, tier2Items, tier3Items, tier4Items]
  )

  const grouped = useMemo(() => groupByTab(contentItems), [contentItems])

  const isLoading = tier1Loading || tier2Loading || tier3Loading || tier4Loading

  return {
    grouped,
    tier1Loading,
    tier2Loading,
    tier3Loading,
    tier4Loading,
    isLoading,
    sourcesSearched,
    sourcesFailed,
    itemsBySource,
    searchTimeMs,
  }
}
