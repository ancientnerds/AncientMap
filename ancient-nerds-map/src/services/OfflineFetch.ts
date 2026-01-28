/**
 * OfflineFetch - Unified offline-aware fetch service
 *
 * Central service managing all network requests with offline mode support.
 * When offline mode is enabled, only cached data is returned.
 * All fetch() calls in the app should use this service.
 */

// Cache names used by the app
const CACHE_NAMES = [
  'vector-layers',      // Coastlines, rivers, lakes, borders, paleoshorelines
  'historical-data',    // Empire boundaries, metadata
  'basemaps',          // Satellite imagery
]

/**
 * Error thrown when data is not cached and offline mode is enabled
 */
export class OfflineNotCachedError extends Error {
  constructor(public url: string) {
    super(`Offline mode: ${url} not cached`)
    this.name = 'OfflineNotCachedError'
  }
}

type OfflineModeListener = (isOffline: boolean) => void

/**
 * Singleton service for offline-aware fetching
 */
class OfflineFetchService {
  private _isOffline = false
  private listeners = new Set<OfflineModeListener>()

  constructor() {
    // Initialize from browser's online status
    this._isOffline = !navigator.onLine

    // Listen for browser online/offline events
    window.addEventListener('online', () => {
      if (this._isOffline) {
        console.log('[OfflineFetch] Browser went online')
        // Don't auto-switch - let user control it
      }
    })

    window.addEventListener('offline', () => {
      if (!this._isOffline) {
        console.log('[OfflineFetch] Browser went offline - switching to offline mode')
        this.setOfflineMode(true)
      }
    })
  }

  /**
   * Get current offline mode state
   */
  get isOffline(): boolean {
    return this._isOffline
  }

  /**
   * Set offline mode (called when user toggles)
   */
  setOfflineMode(offline: boolean): void {
    if (this._isOffline === offline) return

    this._isOffline = offline
    console.log(`[OfflineFetch] Mode changed to: ${offline ? 'OFFLINE' : 'ONLINE'}`)

    // Notify all listeners
    this.listeners.forEach(listener => listener(offline))
  }

  /**
   * Subscribe to offline mode changes
   * Returns unsubscribe function
   */
  onOfflineModeChange(callback: OfflineModeListener): () => void {
    this.listeners.add(callback)
    return () => this.listeners.delete(callback)
  }

  /**
   * Check if a URL is cached (in any cache)
   */
  async isCached(url: string): Promise<boolean> {
    const cached = await this.getCached(url)
    return cached !== null
  }

  /**
   * Get cached response for a URL
   * Checks all app caches
   */
  async getCached(url: string): Promise<Response | null> {
    for (const cacheName of CACHE_NAMES) {
      try {
        const cache = await caches.open(cacheName)
        const cached = await cache.match(url)
        if (cached) {
          return cached
        }
      } catch (e) {
        // Cache API not available or error - continue
      }
    }
    return null
  }

  /**
   * Fetch with offline mode awareness
   *
   * When offline:
   * - Returns cached data if available
   * - Throws OfflineNotCachedError if not cached
   *
   * When online:
   * - Returns cached data if available (for speed)
   * - Fetches from network only if not cached
   */
  async fetch(url: string, options?: RequestInit): Promise<Response> {
    // Always check cache first for maximum speed
    const cached = await this.getCached(url)
    if (cached) {
      return cached
    }

    // Offline mode - nothing cached, throw error
    if (this._isOffline) {
      throw new OfflineNotCachedError(url)
    }

    // Online mode - fetch from network
    return fetch(url, options)
  }
}

// Singleton instance
export const OfflineFetch = new OfflineFetchService()

// Convenience function - drop-in replacement for fetch()
export const offlineFetch = OfflineFetch.fetch.bind(OfflineFetch)
