/**
 * Wikipedia REST API service for fetching empire descriptions
 */

export interface WikipediaSummary {
  extract: string
  thumbnail?: string
  url: string
}

/**
 * Fetch a summary of a Wikipedia article
 * Uses the Wikipedia REST API summary endpoint
 */
export async function getWikipediaSummary(title: string): Promise<WikipediaSummary | null> {
  try {
    // Normalize title for Wikipedia API (replace spaces with underscores)
    const normalizedTitle = title.replace(/ /g, '_')

    // Use Wikipedia REST API summary endpoint
    const response = await fetch(
      `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(normalizedTitle)}`,
      {
        headers: {
          'Accept': 'application/json',
        }
      }
    )

    if (!response.ok) {
      console.warn(`Wikipedia API returned ${response.status} for "${title}"`)
      return null
    }

    const data = await response.json()

    // Check if we got a valid response
    if (data.type === 'disambiguation') {
      // Disambiguation page - try to get the first link
      console.warn(`Wikipedia returned disambiguation page for "${title}"`)
      return null
    }

    if (!data.extract) {
      return null
    }

    return {
      extract: data.extract,
      thumbnail: data.thumbnail?.source,
      url: data.content_urls?.desktop?.page || `https://en.wikipedia.org/wiki/${normalizedTitle}`
    }
  } catch (error) {
    console.error('Failed to fetch Wikipedia summary:', error)
    return null
  }
}

/**
 * Search Wikipedia for articles matching a query
 * Returns the best matching article title
 */
export async function searchWikipedia(query: string): Promise<string | null> {
  try {
    const response = await fetch(
      `https://en.wikipedia.org/w/api.php?action=opensearch&search=${encodeURIComponent(query)}&limit=1&format=json&origin=*`
    )

    if (!response.ok) {
      return null
    }

    const data = await response.json()

    // OpenSearch returns [query, [titles], [descriptions], [urls]]
    if (data[1] && data[1].length > 0) {
      return data[1][0]
    }

    return null
  } catch (error) {
    console.error('Failed to search Wikipedia:', error)
    return null
  }
}

/**
 * Get Wikipedia summary for an empire, trying multiple search strategies
 */
export async function getEmpireWikipediaSummary(empireName: string): Promise<WikipediaSummary | null> {
  // Try exact name first
  let summary = await getWikipediaSummary(empireName)
  if (summary) return summary

  // Try with "Empire" suffix if not already present
  if (!empireName.toLowerCase().includes('empire')) {
    summary = await getWikipediaSummary(`${empireName} Empire`)
    if (summary) return summary
  }

  // Try searching Wikipedia
  const searchResult = await searchWikipedia(empireName)
  if (searchResult) {
    summary = await getWikipediaSummary(searchResult)
    if (summary) return summary
  }

  return null
}

// =============================================================================
// Wikidata Image Fetching for Empires
// =============================================================================

export interface WikidataImage {
  id: string
  thumb: string
  full: string
  title: string
  photographer?: string
  photographerUrl?: string
  wikimediaUrl?: string
  license?: string
}

/**
 * Get images from Wikipedia article in DOCUMENT ORDER (as they appear on the page)
 * Uses the REST API media-list endpoint which preserves order
 */
async function getWikipediaArticleImages(title: string): Promise<WikidataImage[]> {
  try {
    const normalizedTitle = title.replace(/ /g, '_')

    // Use REST API media-list - returns images in document order!
    const response = await fetch(
      `https://en.wikipedia.org/api/rest_v1/page/media-list/${encodeURIComponent(normalizedTitle)}`,
      { headers: { 'Accept': 'application/json' } }
    )

    if (!response.ok) {
      console.warn(`Wikipedia media-list failed for "${title}": ${response.status}`)
      return []
    }

    const data = await response.json()
    const items = data.items || []

    if (items.length === 0) {
      console.warn(`Wikipedia media-list returned no items for "${title}"`)
    }

    const images: WikidataImage[] = []

    for (const item of items) {
      // Only process images (not audio/video)
      if (item.type !== 'image') continue

      // Get source URL from srcset or original
      const srcset = item.srcset || []
      let src = ''
      let thumbSrc = ''

      // srcset has format: [{ src: "//url", scale: "1x" }, { src: "//url", scale: "1.5x" }, ...]
      for (const s of srcset) {
        if (s.src) {
          if (!thumbSrc) thumbSrc = s.src
          // Get the highest resolution available
          src = s.src
        }
      }

      // Fallback to original_image if srcset is empty
      if (!src && item.original?.source) {
        src = item.original.source
        thumbSrc = item.original.source
      }

      if (!src) continue

      const filename = (item.title || '').toLowerCase()

      // Basic exclusions only - SVGs, GIFs, icons, logos
      if (/\.(svg|gif)$/i.test(filename)) continue
      if (/icon|logo|symbol|wikimedia|commons-logo|flag_of|coat_of_arms|emblem/i.test(filename)) continue

      // Ensure HTTPS
      if (src.startsWith('//')) src = 'https:' + src
      if (thumbSrc.startsWith('//')) thumbSrc = 'https:' + thumbSrc

      images.push({
        id: `wiki-${images.length}`,
        thumb: thumbSrc,
        full: src,
        title: (item.title || '').replace(/^File:/, '').replace(/\.[^.]+$/, ''),
        photographer: item.artist?.text || 'Unknown',
        wikimediaUrl: `https://commons.wikimedia.org/wiki/${encodeURIComponent(item.title || '')}`,
        license: item.license?.type || 'Unknown'
      })

      // Limit to 20 images per article
      if (images.length >= 20) break
    }

    return images
  } catch (error) {
    console.warn('Failed to get Wikipedia article images:', error)
    return []
  }
}

// =============================================================================
// Empire Image Fetching
// =============================================================================

/**
 * Check if a Wikipedia article exists and return its canonical title
 * Returns null if article doesn't exist
 */
async function findWikipediaArticle(title: string): Promise<string | null> {
  try {
    const normalizedTitle = title.replace(/ /g, '_')
    const response = await fetch(
      `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(normalizedTitle)}`,
      { headers: { 'Accept': 'application/json' } }
    )
    if (!response.ok) return null
    const data = await response.json()
    // Return the canonical title from Wikipedia
    return data.title || title
  } catch {
    return null
  }
}

/**
 * Fetch images for an empire/period from Wikipedia
 *
 * @param periodName - The period-specific name (e.g., "Roman Principate")
 * @param empireName - The fallback empire name (e.g., "Roman Empire")
 * @returns Images in document order from the found article
 */
export async function getEmpireImages(periodName: string, empireName?: string): Promise<WikidataImage[]> {
  // Step 1: Try to find article for period name
  let articleTitle = await findWikipediaArticle(periodName)

  // Step 2: If not found and we have a fallback, try the empire name
  if (!articleTitle && empireName && empireName !== periodName) {
    articleTitle = await findWikipediaArticle(empireName)
  }

  // Step 3: If still not found, try Wikipedia search
  if (!articleTitle) {
    const searchResult = await searchWikipedia(periodName)
    if (searchResult) {
      articleTitle = searchResult
    } else if (empireName) {
      const fallbackSearch = await searchWikipedia(empireName)
      if (fallbackSearch) {
        articleTitle = fallbackSearch
      }
    }
  }

  if (!articleTitle) {
    return []
  }

  // Get ALL images from the found article (in document order)
  const images = await getWikipediaArticleImages(articleTitle)
  return images
}
