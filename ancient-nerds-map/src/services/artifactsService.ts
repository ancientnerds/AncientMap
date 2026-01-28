/**
 * Artifacts Service
 *
 * Searches the Metropolitan Museum of Art Collection API for artifacts
 * https://metmuseum.github.io/
 */

export interface Artifact {
  id: number
  title: string
  date: string | null
  thumbnail: string
  fullImage: string
  sourceUrl: string
  department: string | null
  culture: string | null
  objectType: string | null
}

interface SearchResponse {
  total: number
  objectIDs: number[] | null
}

interface ObjectResponse {
  objectID: number
  title: string
  primaryImage: string
  primaryImageSmall: string
  objectDate: string
  objectURL: string
  department: string
  culture: string
  objectName: string
  medium: string
}

const MET_API_BASE = 'https://collectionapi.metmuseum.org/public/collection/v1'

/**
 * Search Met Museum for artifacts
 */
export async function findArtifactsForSite(
  siteName: string,
  _location: string = '',
  limit: number = 20
): Promise<Artifact[]> {
  if (!siteName.trim()) {
    return []
  }

  try {
    // Search for the site name
    const searchUrl = `${MET_API_BASE}/search?q=${encodeURIComponent(siteName)}`
    const searchResponse = await fetch(searchUrl)

    if (!searchResponse.ok) {
      console.error('Met Museum search error:', searchResponse.status)
      return []
    }

    const searchData: SearchResponse = await searchResponse.json()

    if (!searchData.objectIDs || searchData.objectIDs.length === 0) {
      console.log(`Met Museum: No artifacts found for "${siteName}"`)
      return []
    }

    console.log(`Met Museum: Found ${searchData.total} artifacts for "${siteName}"`)

    // Fetch more than needed to filter for those with images
    const fetchCount = Math.min(searchData.objectIDs.length, limit * 3)
    const idsToFetch = searchData.objectIDs.slice(0, fetchCount)

    // Fetch object details in parallel
    const objectPromises = idsToFetch.map(async (id) => {
      try {
        const response = await fetch(`${MET_API_BASE}/objects/${id}`)
        if (!response.ok) return null
        return response.json() as Promise<ObjectResponse>
      } catch {
        return null
      }
    })

    const objects = await Promise.all(objectPromises)

    // Filter to valid objects with images
    const artifacts: Artifact[] = []

    for (const obj of objects) {
      if (!obj || !obj.primaryImageSmall) continue

      artifacts.push({
        id: obj.objectID,
        title: obj.title || 'Untitled',
        date: obj.objectDate || null,
        thumbnail: obj.primaryImageSmall,
        fullImage: obj.primaryImage || obj.primaryImageSmall,
        sourceUrl: obj.objectURL,
        department: obj.department || null,
        culture: obj.culture || null,
        objectType: obj.objectName || obj.medium || null
      })

      if (artifacts.length >= limit) break
    }

    console.log(`Returning ${artifacts.length} artifacts with images`)
    return artifacts

  } catch (error) {
    console.error('Error searching Met Museum:', error)
    return []
  }
}
