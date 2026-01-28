/**
 * SourceLoader - Sequential source loading with idle-time processing
 *
 * Loads sources one at a time, yielding to browser between loads.
 * Uses requestIdleCallback for non-blocking UI updates.
 */

import { config } from '../config'
import type { Site } from '../types/data'
import { offlineFetch } from './OfflineFetch'

const API_BASE_URL = config.api.baseUrl

/** Compact site format from API */
interface CompactSite {
  id: string
  n: string   // name
  la: number  // latitude
  lo: number  // longitude
  s: string   // sourceId
  t?: string  // type
  p?: number  // periodStart
  i?: string  // image
  c?: string  // country
}

export type SourceLoadState = 'idle' | 'loading' | 'loaded' | 'error'

export interface SourceLoadStatus {
  sourceId: string
  state: SourceLoadState
  siteCount: number
  error?: string
}

export interface SourceLoaderCallbacks {
  onSourceLoaded?: (sourceId: string, sites: Site[]) => void
  onSourceError?: (sourceId: string, error: string) => void
  onProgress?: (loaded: number, total: number) => void
  onComplete?: () => void
}

/** Yield to browser - lets animations/interactions continue */
const yieldToBrowser = (): Promise<void> => {
  return new Promise(resolve => {
    if ('requestIdleCallback' in window) {
      requestIdleCallback(() => resolve(), { timeout: 100 })
    } else {
      setTimeout(resolve, 16) // ~1 frame
    }
  })
}

/**
 * Sequential source loader with browser-friendly scheduling.
 *
 * Loads one source at a time to avoid blocking the main thread.
 * Yields to browser between processing steps for smooth animations.
 */
class SourceLoaderClass {
  private queue: string[] = []
  private sourceStates = new Map<string, SourceLoadStatus>()
  private callbacks: SourceLoaderCallbacks = {}
  private totalSources = 0
  private loadedCount = 0
  private isRunning = false

  /**
   * Start loading sources sequentially (one at a time).
   * Yields to browser between loads for smooth globe animation.
   * Can be called while already running - new sources are queued.
   */
  async loadSources(sourceIds: string[], callbacks: SourceLoaderCallbacks = {}): Promise<void> {
    // Filter out sources already in queue or already loaded
    const newSources = sourceIds.filter(id =>
      !this.queue.includes(id) &&
      this.sourceStates.get(id)?.state !== 'loading' &&
      this.sourceStates.get(id)?.state !== 'loaded'
    )

    if (newSources.length === 0) return

    // Update callbacks (use latest)
    this.callbacks = callbacks

    // Add new sources to queue
    this.queue.push(...newSources)
    this.totalSources += newSources.length

    // Initialize new sources as idle
    for (const id of newSources) {
      this.sourceStates.set(id, { sourceId: id, state: 'idle', siteCount: 0 })
    }


    // If already running, the processQueue loop will pick up new items
    if (this.isRunning) return

    this.isRunning = true

    // Process queue one at a time
    await this.processQueue()

    this.isRunning = false
    this.callbacks.onComplete?.()
  }

  private async processQueue(): Promise<void> {
    while (this.queue.length > 0) {
      const sourceId = this.queue.shift()!

      // Yield before starting new load
      await yieldToBrowser()

      await this.doLoad(sourceId)

      // Yield after load completes to let React render
      await yieldToBrowser()
    }
  }

  private async doLoad(sourceId: string): Promise<void> {
    this.updateState(sourceId, 'loading')

    try {
      const response = await offlineFetch(
        `${API_BASE_URL}/sites/all?source=${sourceId}&limit=1000000`
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      // Yield before heavy JSON parsing
      await yieldToBrowser()

      const data = await response.json()

      // Yield before processing
      await yieldToBrowser()

      const sites = this.parseSites(data.sites || [])

      this.updateState(sourceId, 'loaded', sites.length)
      this.loadedCount++

      // Yield before callback (which triggers React update)
      await yieldToBrowser()

      this.callbacks.onSourceLoaded?.(sourceId, sites)
      this.callbacks.onProgress?.(this.loadedCount, this.totalSources)
    } catch (error) {
      const errorMsg = (error as Error).message
      this.updateState(sourceId, 'error', 0, errorMsg)
      this.callbacks.onSourceError?.(sourceId, errorMsg)
    }
  }

  private parseSites(sites: CompactSite[]): Site[] {
    return sites.map(s => ({
      id: s.id,
      name: s.n,
      lat: s.la,
      lon: s.lo,
      sourceId: s.s,
      type: s.t || undefined,
      periodStart: s.p ?? null,
      periodEnd: null,
      image: s.i || null,
      location: s.c || undefined,
    }))
  }

  private updateState(
    sourceId: string,
    state: SourceLoadState,
    siteCount = 0,
    error?: string
  ): void {
    this.sourceStates.set(sourceId, { sourceId, state, siteCount, error })
  }

  /**
   * Get current state of all sources.
   */
  getStates(): Map<string, SourceLoadStatus> {
    return new Map(this.sourceStates)
  }

  /**
   * Check if currently loading.
   */
  isLoading(): boolean {
    return this.isRunning
  }

  /**
   * Get loading progress.
   */
  getProgress(): { loaded: number; total: number } {
    return { loaded: this.loadedCount, total: this.totalSources }
  }
}

// Singleton export
export const SourceLoader = new SourceLoaderClass()
