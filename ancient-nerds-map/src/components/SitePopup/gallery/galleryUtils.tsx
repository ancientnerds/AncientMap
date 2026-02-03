import { useState } from 'react'
import type { GalleryTab, UnifiedGalleryItem } from '../types'
import type { GroupedGalleryItems } from '../../../services/connectors'

/**
 * Deduplicate photos: priority items first, then connector items (excluding matches).
 * Matches by title (case-insensitive) or full URL (case-insensitive).
 */
export function dedupePhotos(
  priorityItems: UnifiedGalleryItem[],
  connectorPhotos: UnifiedGalleryItem[]
): UnifiedGalleryItem[] {
  const titles = new Set(priorityItems.map(p => p.title?.toLowerCase()).filter(Boolean))
  const urls = new Set(priorityItems.map(p => p.full?.toLowerCase()).filter(Boolean))

  const deduped = connectorPhotos.filter(p => {
    if (p.title && titles.has(p.title.toLowerCase())) return false
    if (p.full && urls.has(p.full.toLowerCase())) return false
    return true
  })

  return [...priorityItems, ...deduped]
}

/**
 * Select the items array for a given gallery tab.
 */
export function selectCurrentItems(
  tab: GalleryTab,
  items: GroupedGalleryItems & { photos: UnifiedGalleryItem[] }
): UnifiedGalleryItem[] {
  switch (tab) {
    case 'photos': return items.photos
    case 'maps': return items.maps
    case '3dmodels': return items['3dmodels']
    case 'artifacts': return items.artifacts
    case 'artworks': return items.artworks
    case 'books': return items.books
    case 'papers': return items.papers
    case 'myths': return items.myths
    default: return []
  }
}

/**
 * Shared favicon component for gallery items.
 * Extracts domain from the item's source URL and renders Google favicon.
 */
export function SourceFavicon({ original, className }: {
  source?: string
  original: Record<string, unknown>
  className: string
}) {
  const [error, setError] = useState(false)

  const sourceUrl = (original?.sourceUrl as string)
    || (original?.url as string)
    || (original?.webUrl as string)
    || (original?.wikimediaUrl as string)
    || ''

  if (error || !sourceUrl) return null

  let domain: string
  try {
    domain = new URL(sourceUrl).hostname
  } catch {
    return null
  }

  const faviconUrl = `https://www.google.com/s2/favicons?domain=${domain}&sz=32`

  return (
    <img
      src={faviconUrl}
      alt=""
      className={className}
      title={domain}
      onError={() => setError(true)}
    />
  )
}
