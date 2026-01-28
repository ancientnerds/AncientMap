/**
 * ImageCache - Browser Cache API for hero images
 *
 * Caches hero images locally so they load instantly on repeat views.
 * Uses the Cache API which is designed for HTTP response caching.
 */

import { offlineFetch } from './OfflineFetch'

const CACHE_NAME = 'ancient-nerds-hero-images-v1'
const MAX_CACHE_SIZE = 500 // Max number of cached images (increased from 100 for field users)

class ImageCacheClass {
  private cachePromise: Promise<Cache> | null = null
  private isSupported = 'caches' in window

  /**
   * Get the cache instance (lazy initialization).
   */
  private async getCache(): Promise<Cache | null> {
    if (!this.isSupported) return null

    if (!this.cachePromise) {
      this.cachePromise = caches.open(CACHE_NAME)
    }
    return this.cachePromise
  }

  /**
   * Check if an image URL is cached.
   */
  async has(url: string): Promise<boolean> {
    const cache = await this.getCache()
    if (!cache) return false

    const response = await cache.match(url)
    return !!response
  }

  /**
   * Get a cached image as a blob URL.
   * Returns null if not cached.
   */
  async get(url: string): Promise<string | null> {
    const cache = await this.getCache()
    if (!cache) return null

    const response = await cache.match(url)
    if (!response) return null

    try {
      const blob = await response.blob()
      return URL.createObjectURL(blob)
    } catch {
      return null
    }
  }

  /**
   * Cache an image from a URL.
   * Fetches the image and stores it in the cache.
   */
  async cacheFromUrl(url: string): Promise<string | null> {
    const cache = await this.getCache()
    if (!cache) return null

    try {
      // Fetch the image (uses offline-aware fetch)
      const response = await offlineFetch(url, { mode: 'cors' })
      if (!response.ok) return null

      // Clone the response (one for cache, one for blob URL)
      const responseForCache = response.clone()

      // Store in cache
      await cache.put(url, responseForCache)

      // Return blob URL for immediate use
      const blob = await response.blob()
      return URL.createObjectURL(blob)
    } catch (error) {
      console.warn('[ImageCache] Failed to cache image:', url, error)
      return null
    }
  }

  /**
   * Get or fetch an image, caching it for future use.
   * Returns a blob URL for the image.
   */
  async getOrFetch(url: string): Promise<string> {
    // Try cache first
    const cached = await this.get(url)
    if (cached) {
      console.log('[ImageCache] Cache hit:', url.substring(0, 50))
      return cached
    }

    // Fetch and cache
    console.log('[ImageCache] Cache miss, fetching:', url.substring(0, 50))
    const blobUrl = await this.cacheFromUrl(url)

    // Cleanup old entries periodically
    this.cleanupIfNeeded()

    return blobUrl || url // Fallback to original URL if caching fails
  }

  /**
   * Preload and cache an image, returning when ready.
   * This ensures the image is both cached AND loaded into browser memory.
   */
  async preloadAndCache(url: string): Promise<string> {
    const blobUrl = await this.getOrFetch(url)

    // Also preload into browser's image cache
    return new Promise((resolve) => {
      const img = new Image()
      img.onload = () => resolve(blobUrl)
      img.onerror = () => resolve(blobUrl) // Still return URL on error
      img.src = blobUrl
      // Timeout after 2 seconds for faster initial load
      setTimeout(() => resolve(blobUrl), 2000)
    })
  }

  /**
   * Cleanup old cache entries if over limit.
   */
  private async cleanupIfNeeded(): Promise<void> {
    const cache = await this.getCache()
    if (!cache) return

    try {
      const keys = await cache.keys()
      if (keys.length > MAX_CACHE_SIZE) {
        // Delete oldest entries (first in list)
        const toDelete = keys.slice(0, keys.length - MAX_CACHE_SIZE)
        await Promise.all(toDelete.map(request => cache.delete(request)))
        console.log(`[ImageCache] Cleaned up ${toDelete.length} old entries`)
      }
    } catch (error) {
      console.warn('[ImageCache] Cleanup failed:', error)
    }
  }

  /**
   * Clear all cached images.
   */
  async clear(): Promise<void> {
    if (!this.isSupported) return
    await caches.delete(CACHE_NAME)
    this.cachePromise = null
    console.log('[ImageCache] Cache cleared')
  }

  /**
   * Get cache statistics.
   */
  async getStats(): Promise<{ count: number; supported: boolean }> {
    const cache = await this.getCache()
    if (!cache) return { count: 0, supported: this.isSupported }

    const keys = await cache.keys()
    return { count: keys.length, supported: true }
  }

  /**
   * Bulk cache multiple images for offline use.
   * Used for pre-downloading images for a source before going offline.
   * @param urls Array of image URLs to cache
   * @param onProgress Optional progress callback (completed, total)
   * @returns Number of successfully cached images
   */
  async bulkCache(
    urls: string[],
    onProgress?: (completed: number, total: number) => void
  ): Promise<number> {
    let completed = 0
    let successful = 0

    for (const url of urls) {
      try {
        // Skip if already cached
        if (!(await this.has(url))) {
          const result = await this.cacheFromUrl(url)
          if (result) successful++
        } else {
          successful++ // Already cached counts as success
        }
      } catch (e) {
        console.warn('[ImageCache] Failed to cache:', url, e)
        // Continue with next image even on error
      }
      completed++
      onProgress?.(completed, urls.length)
    }

    return successful
  }
}

// Singleton export
export const ImageCache = new ImageCacheClass()
