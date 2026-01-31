/**
 * Smithsonian Open Access Service
 *
 * Searches the Smithsonian Open Access API for museum artifacts and texts
 * related to empires/civilizations.
 */

import { SMITHSONIAN } from '../config/smithsonianConstants'
import { OfflineFetch } from './OfflineFetch'

export interface SmithsonianArtifact {
  id: string
  title: string
  thumbnail: string
  fullImage: string
  creator?: string
  sourceUrl: string
  date?: string
  license: string
  museum: string
  culture?: string
  objectType?: string
}

export interface SmithsonianText {
  id: string
  title: string
  author?: string
  date?: string
  sourceUrl: string
  description?: string
  museum: string
  coverUrl?: string
}

interface SmithsonianMedia {
  type: string
  content: string
  thumbnail?: string
  usage?: {
    access?: string
  }
}

interface SmithsonianItem {
  id: string
  unitCode: string
  title?: string
  content?: {
    descriptiveNonRepeating?: {
      title?: { content?: string }
      online_media?: {
        media?: SmithsonianMedia[]
      }
      record_link?: string
    }
    freetext?: {
      date?: Array<{ content?: string }>
      name?: Array<{ content?: string; label?: string }>
      culture?: Array<{ content?: string }>
      objectType?: Array<{ content?: string }>
      notes?: Array<{ content?: string; label?: string }>
    }
    indexedStructured?: {
      culture?: string[]
      object_type?: string[]
    }
  }
}

interface SmithsonianApiResponse {
  response?: {
    rows?: SmithsonianItem[]
    rowCount?: number
  }
}

// Cache
const cache = new Map<string, { artifacts: SmithsonianArtifact[]; texts: SmithsonianText[]; timestamp: number }>()

// Open Library cover cache
const coverCache = new Map<string, string | null>()

/**
 * Get book cover from Open Library by title search
 * Returns cover URL or null if not found
 */
async function getBookCover(title: string): Promise<string | null> {
  // Check cache
  const cacheKey = title.toLowerCase().slice(0, 50)
  if (coverCache.has(cacheKey)) {
    return coverCache.get(cacheKey) || null
  }

  try {
    // Search Open Library by title (just first few words for better match)
    const searchTitle = title.split(/[:/]/)[0].trim().slice(0, 100)
    const response = await fetch(
      `https://openlibrary.org/search.json?title=${encodeURIComponent(searchTitle)}&limit=1&fields=cover_i`,
      { signal: AbortSignal.timeout(3000) }
    )

    if (!response.ok) {
      coverCache.set(cacheKey, null)
      return null
    }

    const data = await response.json()
    const coverId = data.docs?.[0]?.cover_i

    if (coverId) {
      const coverUrl = `https://covers.openlibrary.org/b/id/${coverId}-M.jpg`
      coverCache.set(cacheKey, coverUrl)
      return coverUrl
    }

    coverCache.set(cacheKey, null)
    return null
  } catch {
    coverCache.set(cacheKey, null)
    return null
  }
}

// Museum names
const MUSEUM_NAMES: Record<string, string> = {
  'FSG': 'Freer Gallery of Art',
  'SAAM': 'Smithsonian American Art Museum',
  'NMNH': 'National Museum of Natural History',
  'NMAI': 'National Museum of the American Indian',
  'CHNDM': 'Cooper Hewitt Design Museum',
  'SIL': 'Smithsonian Libraries',
  'NMAH': 'National Museum of American History',
  'SIA': 'Smithsonian Archives',
}

/**
 * Check if item has CC0 images
 */
function hasCC0Images(item: SmithsonianItem): boolean {
  const media = item.content?.descriptiveNonRepeating?.online_media?.media || []
  return media.some(m => m.type === 'Images' && m.usage?.access === 'CC0')
}

/**
 * Extract image URLs from item
 */
function extractImageUrl(item: SmithsonianItem): { thumbnail: string; full: string } | null {
  const media = item.content?.descriptiveNonRepeating?.online_media?.media || []
  const imageMedia = media.find(m => m.type === 'Images' && m.usage?.access === 'CC0')
  if (!imageMedia?.content) return null

  return {
    thumbnail: imageMedia.thumbnail || imageMedia.content,
    full: imageMedia.content
  }
}

/**
 * Search Smithsonian for an empire/civilization
 * Returns both artifacts (with images) and texts (books)
 */
export async function searchSmithsonian(
  empireName: string,
  limit: number = 20
): Promise<{ artifacts: SmithsonianArtifact[]; texts: SmithsonianText[] }> {
  if (OfflineFetch.isOffline || !SMITHSONIAN.API_KEY || !empireName.trim()) {
    return { artifacts: [], texts: [] }
  }

  // Check cache
  const cacheKey = empireName.toLowerCase().trim()
  const cached = cache.get(cacheKey)
  if (cached && Date.now() - cached.timestamp < SMITHSONIAN.CACHE_TTL_MS) {
    return { artifacts: cached.artifacts, texts: cached.texts }
  }

  // Simple search - just use the empire name
  const query = encodeURIComponent(`${empireName} ancient`)
  const apiUrl = `${SMITHSONIAN.BASE_URL}/search?api_key=${SMITHSONIAN.API_KEY}&q=${query}&rows=${limit * 2}`

  try {
    const response = await fetch(apiUrl, {
      headers: { 'Accept': 'application/json' }
    })

    if (!response.ok) {
      console.warn('[Smithsonian] API error:', response.status)
      return cached ? { artifacts: cached.artifacts, texts: cached.texts } : { artifacts: [], texts: [] }
    }

    const data: SmithsonianApiResponse = await response.json()
    const rows = data.response?.rows || []

    const artifacts: SmithsonianArtifact[] = []
    const texts: SmithsonianText[] = []

    for (const item of rows) {
      const museum = MUSEUM_NAMES[item.unitCode] || item.unitCode
      const title = item.content?.descriptiveNonRepeating?.title?.content || item.title || 'Untitled'
      const sourceUrl = item.content?.descriptiveNonRepeating?.record_link || `https://www.si.edu/object/${item.id}`
      const dates = item.content?.freetext?.date || []
      const date = dates[0]?.content
      const names = item.content?.freetext?.name || []
      const cultures = item.content?.indexedStructured?.culture || []

      // Books go to texts
      if (item.unitCode === 'SIL') {
        if (texts.length < limit) {
          // Dedupe by normalized title (first 50 chars, lowercase)
          const normalizedTitle = title.toLowerCase().slice(0, 50)
          const isDuplicate = texts.some(t =>
            t.title.toLowerCase().slice(0, 50) === normalizedTitle
          )
          if (!isDuplicate) {
            const authorEntry = names.find(n => n.label?.toLowerCase().includes('author')) || names[0]
            texts.push({
              id: item.id,
              title,
              author: authorEntry?.content,
              date,
              sourceUrl,
              description: item.content?.freetext?.notes?.[0]?.content,
              museum
            })
          }
        }
        continue
      }

      // Items with CC0 images go to artifacts
      if (hasCC0Images(item) && artifacts.length < limit) {
        const imageUrls = extractImageUrl(item)
        if (imageUrls) {
          const artistEntry = names.find(n =>
            n.label?.toLowerCase().includes('artist') || n.label?.toLowerCase().includes('maker')
          ) || names[0]

          artifacts.push({
            id: item.id,
            title,
            thumbnail: imageUrls.thumbnail,
            fullImage: imageUrls.full,
            creator: artistEntry?.content,
            sourceUrl,
            date,
            license: 'CC0',
            museum,
            culture: cultures[0],
            objectType: item.content?.indexedStructured?.object_type?.[0]
          })
        }
      }
    }

    // Fetch book covers in parallel
    if (texts.length > 0) {
      await Promise.all(
        texts.map(async (text) => {
          const coverUrl = await getBookCover(text.title)
          if (coverUrl) {
            text.coverUrl = coverUrl
          }
        })
      ).catch(err => console.warn('[Smithsonian] Cover fetch error:', err))
    }

    console.log(`[Smithsonian] Found ${artifacts.length} artifacts, ${texts.length} texts for "${empireName}"`)

    // Cache results
    cache.set(cacheKey, { artifacts, texts, timestamp: Date.now() })

    return { artifacts, texts }
  } catch (error) {
    console.error('[Smithsonian] Error:', error)
    return cached ? { artifacts: cached.artifacts, texts: cached.texts } : { artifacts: [], texts: [] }
  }
}

// Legacy function for backwards compatibility with site popups
export async function findSmithsonianArtifacts(
  siteName: string,
  culture?: string,
  limit: number = 15
): Promise<SmithsonianArtifact[]> {
  const searchTerm = culture || siteName
  const result = await searchSmithsonian(searchTerm, limit)
  return result.artifacts
}

export function clearSmithsonianCache(): void {
  cache.clear()
}
