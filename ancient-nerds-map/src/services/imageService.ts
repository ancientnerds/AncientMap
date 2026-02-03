/**
 * Fast Wikipedia image fetching via REST API.
 *
 * Uses /api/rest_v1/page/media-list/{title} - returns ALL article images
 * in a single fast API call (~200-500ms), replacing three slow Action API calls.
 */

// =============================================================================
// Types
// =============================================================================

export interface ImageResult {
  id: string
  thumb: string
  full: string
  title?: string
  author?: string
  authorUrl?: string
  sourceUrl?: string
  license?: string
  source: 'wikipedia' | 'europeana' | 'local'
  isLeadImage?: boolean
}

export interface FetchSiteImagesResult {
  wikipedia: ImageResult[]
  europeana: ImageResult[]
}

// =============================================================================
// Excluded patterns (icons, logos, UI elements)
// =============================================================================

const EXCLUDED = /icon|logo|symbol|diagram|chart|graph|flag|wikimedia|commons-logo|edit-|question-mark|disambig|stub|padlock|pp-|protection|wikidata|wiktionary|wikinews|wikiquote|wikisource|wikiversity|wikivoyage|wikispecies|wikibooks|mediawiki|signature|coat.of.arms|escudo|blason|coa_|seal_of|emblem/i
const EXCLUDED_EXT = /\.svg$/i

// =============================================================================
// Public API
// =============================================================================

/**
 * Fetch images from a Wikipedia article about this site/empire.
 * If a Wikipedia URL is provided, uses that article directly.
 * Otherwise searches Wikipedia by name first.
 *
 * Total time: ~200-700ms (1-2 API calls via REST API).
 */
export async function fetchSiteImages(
  name: string,
  options: { wikipediaUrl?: string; location?: string; limit?: number } = {}
): Promise<FetchSiteImagesResult> {
  try {
    let images: ImageResult[]

    if (options.wikipediaUrl) {
      const title = extractTitleFromUrl(options.wikipediaUrl)
      images = title ? await fetchArticleImages(title) : []
    } else {
      images = await searchAndFetchImages(name)
    }

    // Lead image first, then the rest
    images.sort((a, b) => (b.isLeadImage ? 1 : 0) - (a.isLeadImage ? 1 : 0))

    return { wikipedia: images, europeana: [] }
  } catch (err) {
    console.warn('[imageService] Failed:', err)
    return { wikipedia: [], europeana: [] }
  }
}

/** Alias for callers that imported the progressive version */
export const fetchSiteImagesProgressive = fetchSiteImages

/**
 * Fetch metadata (author, license) for a specific image on demand.
 * Uses extmetadata which is slow - only call when user opens lightbox.
 */
export async function fetchWikipediaImageMetadata(
  imageTitle: string
): Promise<{ author?: string; license?: string }> {
  const normalized = imageTitle.startsWith('File:') ? imageTitle : `File:${imageTitle}`

  try {
    const response = await fetch(
      `https://en.wikipedia.org/w/api.php?${new URLSearchParams({
        action: 'query',
        titles: normalized,
        prop: 'imageinfo',
        iiprop: 'extmetadata',
        format: 'json',
        origin: '*'
      })}`
    )
    if (!response.ok) return {}

    const data = await response.json()
    const page = Object.values(data.query?.pages || {})[0] as {
      imageinfo?: Array<{ extmetadata?: Record<string, { value: string }> }>
    }
    const ext = page?.imageinfo?.[0]?.extmetadata

    let author = ext?.Artist?.value || ext?.Author?.value || ext?.Credit?.value
    if (author) {
      author = author.replace(/<[^>]*>/g, '').trim()
      if (author.length > 100) author = author.substring(0, 100) + '...'
    }

    return {
      author,
      license: ext?.LicenseShortName?.value || ext?.License?.value
    }
  } catch {
    return {}
  }
}

export function isWikipediaUrl(url: string): boolean {
  if (!url) return false
  try {
    return /\.wikipedia\.org$/i.test(new URL(url).hostname)
  } catch {
    return false
  }
}

// =============================================================================
// Internal: REST API media-list fetch
// =============================================================================

interface MediaListItem {
  title: string
  type: string
  leadImage?: boolean
  showInGallery?: boolean
  srcset?: Array<{ src: string; scale: string }>
}

/**
 * Fetch all images from a Wikipedia article via REST API.
 * Single API call, ~200-500ms.
 */
async function fetchArticleImages(articleTitle: string, lang = 'en'): Promise<ImageResult[]> {
  const encoded = encodeURIComponent(articleTitle.replace(/ /g, '_'))

  const response = await fetch(
    `https://${lang}.wikipedia.org/api/rest_v1/page/media-list/${encoded}`,
    { headers: { 'Accept': 'application/json', 'User-Agent': 'AncientNerdsMap/1.0' } }
  )

  if (!response.ok) return []

  const data = await response.json()
  if (!data.items) return []

  const images: ImageResult[] = []

  for (const item of data.items as MediaListItem[]) {
    if (item.type !== 'image') continue
    if (item.showInGallery === false) continue
    if (!item.srcset?.length) continue
    if (EXCLUDED.test(item.title) || EXCLUDED_EXT.test(item.title)) continue

    // Get largest thumbnail from srcset (2x > 1.5x > 1x)
    const sorted = [...item.srcset].sort((a, b) =>
      (parseFloat(b.scale) || 1) - (parseFloat(a.scale) || 1)
    )

    const thumbSrc = sorted[0].src
    const thumbUrl = thumbSrc.startsWith('//') ? 'https:' + thumbSrc : thumbSrc
    const fullUrl = thumbToOriginal(thumbUrl)

    const title = item.title
      .replace(/^File:/, '')
      .replace(/\.[^.]+$/, '')

    images.push({
      id: `wiki-${images.length}`,
      thumb: thumbUrl,
      full: fullUrl,
      title,
      sourceUrl: `https://commons.wikimedia.org/wiki/${encodeURIComponent(item.title)}`,
      source: 'wikipedia',
      isLeadImage: item.leadImage === true
    })
  }

  return images
}

/**
 * Search Wikipedia by name, then fetch images from the matching article.
 * OpenSearch (~200ms) + media-list (~200ms) = ~400ms total.
 */
async function searchAndFetchImages(name: string): Promise<ImageResult[]> {
  const response = await fetch(
    `https://en.wikipedia.org/w/api.php?${new URLSearchParams({
      action: 'opensearch',
      search: name,
      limit: '1',
      namespace: '0',
      format: 'json',
      origin: '*'
    })}`
  )

  if (!response.ok) return []
  const data = await response.json()

  // OpenSearch returns: [query, [titles], [descriptions], [urls]]
  const titles = data[1] as string[]
  if (!titles?.length) return []

  return fetchArticleImages(titles[0])
}

// =============================================================================
// URL helpers
// =============================================================================

/**
 * Convert a Wikimedia thumbnail URL to the original full-resolution URL.
 *
 * Input:  //upload.wikimedia.org/wikipedia/commons/thumb/d/d4/File.jpg/500px-File.jpg
 * Output: https://upload.wikimedia.org/wikipedia/commons/d/d4/File.jpg
 */
function thumbToOriginal(thumbUrl: string): string {
  let url = thumbUrl
  if (url.startsWith('//')) url = 'https:' + url

  if (url.includes('/thumb/')) {
    url = url.replace('/thumb/', '/')
    const lastSlash = url.lastIndexOf('/')
    if (lastSlash > 0) url = url.substring(0, lastSlash)
  }

  return url
}

function extractTitleFromUrl(wikipediaUrl: string): string | null {
  try {
    const url = new URL(wikipediaUrl)
    if (!/\.wikipedia\.org$/i.test(url.hostname)) return null

    const wikiMatch = url.pathname.match(/^\/wiki\/(.+)$/)
    if (wikiMatch) return decodeURIComponent(wikiMatch[1])

    const titleParam = url.searchParams.get('title')
    if (titleParam) return decodeURIComponent(titleParam)

    return null
  } catch {
    return null
  }
}
