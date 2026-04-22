/**
 * Map a source URL's hostname to the `sourceType` keys that `ImageLightbox`
 * recognises (so it can render the branded "View on ..." link correctly).
 *
 * Mirrors the backend mapping in `pipeline/lyra/backfill_hero_image.py`
 * (`_HOST_TO_SOURCE`) — keep the two in sync when adding new connectors.
 */
export function inferSourceType(url: string | undefined | null): string | undefined {
  if (!url) return undefined
  let host = ''
  try {
    host = new URL(url).hostname.toLowerCase()
  } catch {
    return undefined
  }
  if (/(^|\.)(wikipedia|wikimedia)\.org$/.test(host)) return 'wikimedia'
  if (/(^|\.)metmuseum\.org$/.test(host)) return 'met-museum'
  if (/(^|\.)si\.edu$/.test(host)) return 'smithsonian'
  if (/(^|\.)davidrumsey\.com$/.test(host)) return 'david-rumsey'
  if (/(^|\.)europeana\.eu$/.test(host)) return 'europeana'
  if (/(^|\.)loc\.gov$/.test(host)) return 'loc'
  if (/(^|\.)britishmuseum\.org$/.test(host)) return 'british-museum'
  if (/(^|\.)sketchfab\.com$/.test(host)) return 'sketchfab'
  if (/(^|\.)getty\.edu$/.test(host)) return 'getty-museum'
  if (/(^|\.)louvre\.fr$/.test(host)) return 'louvre'
  if (/(^|\.)finds\.org\.uk$/.test(host)) return 'pas'
  return undefined
}
