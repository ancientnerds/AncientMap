/**
 * Ancient Maps Service
 *
 * Searches the David Rumsey Map Collection API by site name
 */

import { OfflineFetch } from './OfflineFetch'

export interface AncientMap {
  id: string
  title: string
  date: string | null
  thumbnail: string
  fullImage: string
  webUrl: string
}

interface ApiFieldValue {
  fieldName: string
  value: string
}

interface ApiResult {
  id: string
  displayName: string
  urlSize2?: string
  urlSize4?: string
  fieldValues?: ApiFieldValue[]
  iiifManifest?: string
}

interface ApiResponse {
  results?: ApiResult[]
  totalResults?: number
}

/**
 * Search for maps by site name using David Rumsey API
 */
export async function findMapsForLocation(
  _lat: number,
  _lon: number,
  siteName: string,
  _location: string = '',
  limit: number = 50
): Promise<AncientMap[]> {
  // Early return if offline - David Rumsey API requires internet
  if (OfflineFetch.isOffline) {
    return []
  }

  if (!siteName.trim()) {
    return []
  }

  const searchQuery = encodeURIComponent(siteName)
  const apiUrl = `https://www.davidrumsey.com/luna/servlet/as/search?q=${searchQuery}&os=0&bs=${limit}`

  try {
    const response = await fetch(apiUrl)
    if (!response.ok) {
      console.error('David Rumsey API error:', response.status)
      return []
    }

    const data: ApiResponse = await response.json()

    if (!data.results || data.results.length === 0) {
      return []
    }

    console.log(`Found ${data.results.length} maps for "${siteName}"`)

    return data.results.map(result => {
      // Extract date from fieldValues
      const dateField = result.fieldValues?.find(f => f.fieldName === 'Date')
      const date = dateField?.value || null

      // Build web URL from id
      const webUrl = `https://www.davidrumsey.com/luna/servlet/detail/${result.id}`

      return {
        id: result.id,
        title: result.displayName || 'Untitled',
        date,
        thumbnail: result.urlSize2 || '',
        fullImage: result.urlSize4 || result.urlSize2 || '',
        webUrl
      }
    }).filter(map => map.thumbnail) // Only include maps with thumbnails
  } catch (error) {
    console.error('Error searching David Rumsey:', error)
    return []
  }
}

/**
 * Preload is no longer needed with API search
 */
export function preloadMaps(): void {
  // No-op - we search on demand now
}
