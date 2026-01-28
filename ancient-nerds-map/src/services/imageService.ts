/**
 * Unified image service for fetching site images from multiple sources.
 *
 * This module provides:
 * - Shared types (ImageResult) used across all image sources
 * - Unified fetch function for Wikipedia images
 */

import { offlineFetch } from './OfflineFetch'

// =============================================================================
// Shared Types
// =============================================================================

export interface ImageResult {
  id: string
  thumb: string
  full: string
  title?: string
  author?: string
  authorUrl?: string
  sourceUrl?: string  // Link to original page (Wikimedia Commons, Europeana)
  license?: string
  source: 'wikipedia' | 'europeana' | 'local'
}

// =============================================================================
// Unified Image Fetching
// =============================================================================

export interface FetchSiteImagesOptions {
  wikipediaUrl?: string
  europeanaApiKey?: string
  location?: string
  limit?: number
}

export interface FetchSiteImagesResult {
  wikipedia: ImageResult[]
  europeana: ImageResult[]
}

/**
 * Fetch images for a site from all available sources.
 *
 * @param siteName - Name of the archaeological site
 * @param options - Fetch options including API keys and source URLs
 * @returns Object with arrays of images from each source
 */
export async function fetchSiteImages(
  siteName: string,
  options: FetchSiteImagesOptions = {}
): Promise<FetchSiteImagesResult> {
  const { wikipediaUrl } = options

  // Fetch from Wikipedia
  const wikipediaImages = wikipediaUrl
    ? await fetchWikipediaImagesInternal(wikipediaUrl)
    : await searchWikipediaByName(siteName)

  return {
    wikipedia: wikipediaImages,
    europeana: [],
  }
}

/**
 * Search Wikipedia by site name and fetch images from the best matching article
 */
async function searchWikipediaByName(siteName: string): Promise<ImageResult[]> {
  try {
    // Search Wikipedia for the site name
    const searchUrl = `https://en.wikipedia.org/w/api.php?${new URLSearchParams({
      action: 'opensearch',
      search: siteName,
      limit: '1',
      namespace: '0',
      format: 'json',
      origin: '*'
    })}`

    const response = await offlineFetch(searchUrl)
    if (!response.ok) return []

    const data = await response.json()
    // OpenSearch returns: [query, [titles], [descriptions], [urls]]
    const urls = data[3] as string[]
    if (!urls || urls.length === 0) return []

    // Fetch images from the first matching Wikipedia article
    return fetchWikipediaImagesInternal(urls[0])
  } catch (error) {
    console.warn('Failed to search Wikipedia by name:', error)
    return []
  }
}

// =============================================================================
// Wikipedia Implementation
// =============================================================================

interface WikipediaImageInfo {
  title: string
  url: string
  thumbUrl: string
  descriptionUrl: string
  author?: string
  license?: string
  width: number
  height: number
}

const EXCLUDED_PATTERNS = /icon|logo|symbol|diagram|map|chart|graph|flag|wikimedia|commons-logo|edit-|question-mark|disambig|stub|padlock|pp-|protection|wikidata|wiktionary|wikinews|wikiquote|wikisource|wikiversity|wikivoyage|wikispecies|wikibooks|mediawiki|signature|coat.of.arms|escudo|blason|coa_|seal_of|emblem/i
const EXCLUDED_EXTENSIONS = /\.svg$/i
const MIN_WIDTH = 500
const MIN_HEIGHT = 500

function extractPageTitle(sourceUrl: string): { title: string; lang: string } | null {
  if (!sourceUrl) return null

  try {
    const url = new URL(sourceUrl)
    const match = url.hostname.match(/^(\w+)\.wikipedia\.org$/)
    if (!match) return null

    const lang = match[1]
    const wikiMatch = url.pathname.match(/^\/wiki\/(.+)$/)
    if (wikiMatch) {
      return { title: decodeURIComponent(wikiMatch[1]), lang }
    }

    const titleParam = url.searchParams.get('title')
    if (titleParam) {
      return { title: decodeURIComponent(titleParam), lang }
    }

    return null
  } catch {
    return null
  }
}

function shouldExcludeFile(filename: string): boolean {
  return EXCLUDED_PATTERNS.test(filename) || EXCLUDED_EXTENSIONS.test(filename)
}

async function fetchImageList(pageTitle: string, lang: string): Promise<string[]> {
  const apiUrl = `https://${lang}.wikipedia.org/w/api.php`
  const params = new URLSearchParams({
    action: 'query',
    titles: pageTitle,
    prop: 'images',
    imlimit: '50',
    format: 'json',
    origin: '*'
  })

  try {
    const response = await offlineFetch(`${apiUrl}?${params}`)
    if (!response.ok) return []

    const data = await response.json()
    const pages = data.query?.pages
    if (!pages) return []

    const page = Object.values(pages)[0] as { images?: { title: string }[] }
    if (!page.images) return []

    return page.images
      .map(img => img.title)
      .filter(title => !shouldExcludeFile(title))
  } catch (error) {
    console.warn('Failed to fetch Wikipedia image list:', error)
    return []
  }
}

function parseWikipediaLicense(extmetadata: Record<string, { value: string }> | undefined): string {
  if (!extmetadata) return 'Unknown'
  return extmetadata.LicenseShortName?.value ||
         extmetadata.License?.value ||
         'Unknown'
}

function parseWikipediaAuthor(extmetadata: Record<string, { value: string }> | undefined): string {
  if (!extmetadata) return 'Unknown'

  let author = extmetadata.Artist?.value ||
               extmetadata.Author?.value ||
               extmetadata.Credit?.value ||
               'Unknown'

  author = author.replace(/<[^>]*>/g, '').trim()

  if (author.length > 100) {
    author = author.substring(0, 100) + '...'
  }

  return author
}

async function fetchImageInfo(titles: string[], lang: string): Promise<WikipediaImageInfo[]> {
  if (titles.length === 0) return []

  const apiUrl = `https://${lang}.wikipedia.org/w/api.php`
  const params = new URLSearchParams({
    action: 'query',
    titles: titles.join('|'),
    prop: 'imageinfo',
    iiprop: 'url|size|extmetadata',
    iiurlwidth: '400',
    format: 'json',
    origin: '*'
  })

  try {
    const response = await offlineFetch(`${apiUrl}?${params}`)
    if (!response.ok) return []

    const data = await response.json()
    const pages = data.query?.pages
    if (!pages) return []

    const images: WikipediaImageInfo[] = []

    for (const page of Object.values(pages) as Array<{
      title: string
      imageinfo?: Array<{
        url: string
        thumburl: string
        descriptionurl: string
        width: number
        height: number
        extmetadata?: Record<string, { value: string }>
      }>
    }>) {
      if (!page.imageinfo?.[0]) continue

      const info = page.imageinfo[0]

      if (info.width < MIN_WIDTH || info.height < MIN_HEIGHT) continue

      images.push({
        title: page.title,
        url: info.url,
        thumbUrl: info.thumburl || info.url,
        descriptionUrl: info.descriptionurl,
        author: parseWikipediaAuthor(info.extmetadata),
        license: parseWikipediaLicense(info.extmetadata),
        width: info.width,
        height: info.height
      })
    }

    return images
  } catch (error) {
    console.warn('Failed to fetch Wikipedia image info:', error)
    return []
  }
}

async function fetchWikipediaImagesInternal(sourceUrl: string): Promise<ImageResult[]> {
  const parsed = extractPageTitle(sourceUrl)
  if (!parsed) return []

  const { title, lang } = parsed

  const imageTitles = await fetchImageList(title, lang)
  if (imageTitles.length === 0) return []

  const batchSize = 50
  const allImages: WikipediaImageInfo[] = []

  for (let i = 0; i < imageTitles.length; i += batchSize) {
    const batch = imageTitles.slice(i, i + batchSize)
    const images = await fetchImageInfo(batch, lang)
    allImages.push(...images)

    if (i + batchSize < imageTitles.length) {
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }

  allImages.sort((a, b) => (b.width * b.height) - (a.width * a.height))

  return allImages.slice(0, 20).map((img, index) => ({
    id: `wiki-${index}`,
    thumb: img.thumbUrl,
    full: img.url,
    title: img.title.replace(/^File:/, '').replace(/\.[^.]+$/, ''),
    author: img.author,
    sourceUrl: img.descriptionUrl,
    license: img.license,
    source: 'wikipedia' as const,
  }))
}

// =============================================================================
// Utility Exports
// =============================================================================

/**
 * Check if a URL is a Wikipedia URL
 */
export function isWikipediaUrl(url: string): boolean {
  if (!url) return false
  try {
    const parsed = new URL(url)
    return /\.wikipedia\.org$/i.test(parsed.hostname)
  } catch {
    return false
  }
}
