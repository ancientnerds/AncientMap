/**
 * OfflineContext - React Context for offline mode state
 *
 * Provides offline state to all React components via useOffline() hook.
 * Syncs with the OfflineFetch singleton service.
 * Tracks what data is cached for offline availability indicators.
 */

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import { OfflineFetch } from '../services/OfflineFetch'
import { OfflineStorage } from '../services/OfflineStorage'

interface OfflineContextValue {
  isOffline: boolean
  setOfflineMode: (offline: boolean) => void
  pendingContributions: number
  // Cache state for offline availability indicators
  cachedSourceIds: Set<string>
  cachedEmpireIds: Set<string>
  cachedLayerIds: Set<string>
  cachedBasemapQualities: Set<string>
  cachedBasemapItems: Set<string>  // New: 'satellite' | 'labels'
  hasMapboxTilesCached: boolean    // Derived: whether satellite basemap is downloaded
  refreshCacheState: () => Promise<void>
}

const OfflineContext = createContext<OfflineContextValue | null>(null)

interface OfflineProviderProps {
  children: ReactNode
}

// Empty sets for initial state
const EMPTY_SET = new Set<string>()

/**
 * Provider component that wraps the app
 * Syncs React state with OfflineFetch service
 */
export function OfflineProvider({ children }: OfflineProviderProps) {
  const [isOffline, setIsOffline] = useState(OfflineFetch.isOffline)
  const [pendingContributions, setPendingContributions] = useState(0)

  // Cache state - what's been downloaded
  const [cachedSourceIds, setCachedSourceIds] = useState<Set<string>>(EMPTY_SET)
  const [cachedEmpireIds, setCachedEmpireIds] = useState<Set<string>>(EMPTY_SET)
  const [cachedLayerIds, setCachedLayerIds] = useState<Set<string>>(EMPTY_SET)
  const [cachedBasemapQualities, setCachedBasemapQualities] = useState<Set<string>>(EMPTY_SET)
  const [cachedBasemapItems, setCachedBasemapItems] = useState<Set<string>>(EMPTY_SET)

  // Derived: whether Mapbox tiles (satellite basemap) are cached for offline use
  const hasMapboxTilesCached = cachedBasemapItems.has('satellite')

  // Function to refresh cache state from OfflineStorage
  const refreshCacheState = useCallback(async () => {
    try {
      const state = await OfflineStorage.getDownloadState()

      // Extract cached source IDs
      const sourceIds = new Set<string>(
        Object.entries(state.sources)
          .filter(([_, info]) => info.cached)
          .map(([id]) => id)
      )
      setCachedSourceIds(sourceIds)

      // Extract cached empire IDs
      setCachedEmpireIds(new Set(state.empires || []))

      // Extract cached layer IDs
      setCachedLayerIds(new Set(state.layers || []))

      // Extract cached basemap qualities
      setCachedBasemapQualities(new Set(state.basemapQualities || []))

      // Extract cached basemap items (satellite, labels)
      setCachedBasemapItems(new Set(state.basemapItems || []))
    } catch (e) {
      // OfflineStorage not available - leave empty sets
    }
  }, [])

  // Sync with OfflineFetch service
  useEffect(() => {
    const unsubscribe = OfflineFetch.onOfflineModeChange((offline) => {
      setIsOffline(offline)
    })
    return unsubscribe
  }, [])

  // Load cache state on mount and refresh periodically
  useEffect(() => {
    // Initial load
    refreshCacheState()

    // Refresh every 5 seconds to catch newly downloaded data
    const interval = setInterval(refreshCacheState, 5000)
    return () => clearInterval(interval)
  }, [refreshCacheState])

  // Also refresh cache state when offline mode changes
  useEffect(() => {
    refreshCacheState()
  }, [isOffline, refreshCacheState])

  // Load pending contributions count
  useEffect(() => {
    const loadPending = async () => {
      try {
        const pending = await OfflineStorage.getPendingContributions()
        setPendingContributions(pending.length)
      } catch (e) {
        // OfflineStorage not available
      }
    }
    loadPending()

    // Refresh count periodically
    const interval = setInterval(loadPending, 5000)
    return () => clearInterval(interval)
  }, [])

  // Handler that updates both service and React state
  const handleSetOfflineMode = (offline: boolean) => {
    OfflineFetch.setOfflineMode(offline)
    setIsOffline(offline)
  }

  return (
    <OfflineContext.Provider
      value={{
        isOffline,
        setOfflineMode: handleSetOfflineMode,
        pendingContributions,
        cachedSourceIds,
        cachedEmpireIds,
        cachedLayerIds,
        cachedBasemapQualities,
        cachedBasemapItems,
        hasMapboxTilesCached,
        refreshCacheState,
      }}
    >
      {children}
    </OfflineContext.Provider>
  )
}

/**
 * Hook to access offline state from any component
 */
export function useOffline(): OfflineContextValue {
  const context = useContext(OfflineContext)
  if (!context) {
    throw new Error('useOffline must be used within an OfflineProvider')
  }
  return context
}
