/**
 * Pre-processes Lyra's markdown response to insert:
 * - Site name links: [SiteName](lyra-site:id:lon:lat)
 * - Country flags: ![flag](/flags-flat/xx.webp) CountryName
 * - Copyable coordinates: [coord:lat,lon](lyra-coord:lat,lon)
 *
 * These are then rendered by react-markdown custom components in LyraChatModal.
 */

import type { SiteHighlight, NewsHighlight } from '../types/ai'
import { COUNTRY_CODES, getCountryFlatFlagUrl } from './countryFlags'

// Build sorted country names list (longest first to avoid partial matches)
const COUNTRY_NAMES = Object.keys(COUNTRY_CODES).sort((a, b) => b.length - a.length)

// Escape special regex chars
function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// Format seconds → "m:ss" label
function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/**
 * Generate prefix variants of a site name for flexible matching.
 * "Gunung Padang Megalithic Site" → ["Gunung Padang Megalithic Site", "Gunung Padang Megalithic", "Gunung Padang"]
 * "Ġgantija Temples" → ["Ġgantija Temples", "Ġgantija"]
 * "Newgrange" → ["Newgrange"]
 */
function getNameVariants(name: string): string[] {
  const words = name.split(/\s+/)
  const variants: string[] = [name]
  for (let i = words.length - 1; i >= 1; i--) {
    const variant = words.slice(0, i).join(' ')
    if (variant === name) continue
    // Keep 2+ word prefixes, or single words of 8+ chars
    if (i >= 2 || variant.length >= 8) {
      variants.push(variant)
    }
  }
  return variants
}

/**
 * Check if a site name (or a shorter variant) appears in content.
 * Used by the done-handler to decide which sites to keep.
 */
export function siteNameInContent(siteName: string, lowerContent: string): boolean {
  if (lowerContent.includes(siteName.toLowerCase())) return true
  const variants = getNameVariants(siteName)
  for (let i = 1; i < variants.length; i++) {
    if (lowerContent.includes(variants[i].toLowerCase())) return true
  }
  return false
}

/**
 * Extract site names from a completed Lyra response that aren't already in sidebarSites.
 * Looks at bold text and table first-column cells — strong signals for site names.
 * Returns candidate names to search via the API.
 */
export function extractUnlinkedSiteNames(content: string, existingSites: SiteHighlight[]): string[] {
  // Build set of names we already know about (including prefix variants)
  const known = new Set<string>()
  for (const s of existingSites) {
    known.add(s.name.toLowerCase())
    for (const v of getNameVariants(s.name)) {
      known.add(v.toLowerCase())
    }
  }

  const candidates = new Set<string>()
  const SKIP = new Set([
    'site', 'sites', 'date', 'country', 'notes', 'location', 'significance',
    'type', 'period', 'quick notes', 'description', 'details', 'summary',
    'features', 'key facts', 'coordinates', 'overview', 'history',
  ])

  function addCandidate(raw: string) {
    let name = raw.trim()
    // Strip leading emoji
    name = name.replace(/^[\p{Emoji_Presentation}\p{Extended_Pictographic}]+\s*/u, '')
    // Strip trailing colon
    if (name.endsWith(':')) name = name.slice(0, -1).trim()
    // Strip parenthetical suffix like "(Malta)"
    name = name.replace(/\s*\([^)]*\)\s*$/, '').trim()

    if (name.length < 3) return
    if (name.split(/\s+/).length > 5) return
    if (SKIP.has(name.toLowerCase())) return
    if (known.has(name.toLowerCase())) return
    // Must start with uppercase (site names are proper nouns)
    if (!/^[A-ZÀ-ÖØ-Ý\u0100-\u024F]/.test(name)) return

    candidates.add(name)
  }

  // 1. Bold text: **SomeName**
  for (const m of content.matchAll(/\*\*([^*]+)\*\*/g)) {
    addCandidate(m[1])
  }

  // 2. Table data rows (after separator row like |---|---|)
  const lines = content.split('\n')
  let inTable = false
  for (const line of lines) {
    if (/^\|.*\|/.test(line)) {
      if (/^\|[\s\-:|]+\|/.test(line)) {
        inTable = true
        continue
      }
      if (inTable) {
        const cells = line.split('|').filter(c => c.trim())
        if (cells.length > 0) addCandidate(cells[0])
      }
    } else {
      inTable = false
    }
  }

  return [...candidates]
}

/**
 * Pre-process markdown content to embed interactive markers.
 *
 * Order matters: coordinates first (they contain brackets that could interfere),
 * then sites (hijack existing links, then plain text), then countries.
 */
export function enrichLyraContent(content: string, sites: SiteHighlight[], news?: NewsHighlight[]): string {
  let result = content

  // 1. Coordinates: [lat, lon] or [lat,lon] → custom link
  //    Match patterns like [37.0928, 39.3041] but NOT already-linked markdown
  result = result.replace(
    /(?<!\()\[(-?\d+\.?\d*),\s*(-?\d+\.?\d*)\](?!\()/g,
    (_match, lat, lon) => `[${lat}, ${lon}](lyra-coord:${lat},${lon})`
  )

  // 2. Site names → links (longest first to avoid partial matches)
  const sortedSites = [...sites].sort((a, b) => b.name.length - a.name.length)

  // 2a. Hijack existing markdown links [SiteName](external-url) → [SiteName](lyra-site:...)
  //     Lyra often generates its own wiki/external links — we want those to open popups.
  for (const site of sortedSites) {
    if (!site.id || site.name.length < 3) continue
    for (const variant of getNameVariants(site.name)) {
      const escaped = escapeRegex(variant)
      // Match [variant text](any-url-that-isnt-already-lyra-site)
      const linkRegex = new RegExp(
        `\\[(${escaped})\\]\\((?!lyra-site:|lyra-coord:)[^)]+\\)`,
        'giu'
      )
      result = result.replace(linkRegex, (_, name) =>
        `[${name}](lyra-site:${site.id}:${site.lon}:${site.lat})`
      )
    }
  }

  // 2b. Replace plain-text site names (not already inside links)
  const replacedNames = new Set<string>()
  for (const site of sortedSites) {
    if (!site.id || site.name.length < 3) continue
    for (const variant of getNameVariants(site.name)) {
      const varLower = variant.toLowerCase()
      if (replacedNames.has(varLower)) continue

      const escaped = escapeRegex(variant)
      // Unicode-aware word boundary (\b fails for Ġ, Ħ, etc.)
      const regex = new RegExp(
        `(?<!\\[)(?<!\\]\\()(?<![\\p{L}\\d])(${escaped})(?![\\p{L}\\d])(?!\\]|\\()`,
        'giu'
      )
      const before = result
      result = result.replace(regex, (match) =>
        `[${match}](lyra-site:${site.id}:${site.lon}:${site.lat})`
      )
      if (result !== before) {
        replacedNames.add(varLower)
        break // Longest matching variant wins, stop trying shorter ones
      }
    }
  }

  // 3. Country names → flag image + name (longest first)
  //    Only first occurrence of each country, avoid re-replacing inside links
  const replacedCountries = new Set<string>()
  for (const name of COUNTRY_NAMES) {
    if (replacedCountries.has(name.toLowerCase())) continue
    const flagUrl = getCountryFlatFlagUrl(name)
    if (!flagUrl) continue

    const escaped = escapeRegex(name)
    const regex = new RegExp(
      `(?<!\\[)(?<!/)(?<![\\p{L}\\d])(${escaped})(?![\\p{L}\\d])(?!\\]|\\()`,
      'giu'
    )
    result = result.replace(regex, (match) => {
      return `![flag](${flagUrl})${match}`
    })
    replacedCountries.add(name.toLowerCase())
  }

  // 4. YouTube video references → lyra-video:INDEX links
  if (news && news.length > 0) {
    // 4a. Direct [youtube: VIDEO_ID] markers (if LLM echoes them from context)
    result = result.replace(
      /\[youtube:\s*([a-zA-Z0-9_-]{11})\]/g,
      (_match, videoId) => {
        const idx = news.findIndex(n => n.video_id === videoId)
        if (idx === -1) return _match
        const n = news[idx]
        const ts = n.timestamp_seconds
        const tsLabel = ts != null ? ` ${formatTimestamp(ts)}` : ''
        return `[▶ ${n.channel || 'Video'}${tsLabel}](lyra-video:${idx})`
      }
    )

    // 4b. Channel names → link first occurrence to matching news item
    const linkedChannels = new Set<string>()
    for (let i = 0; i < news.length; i++) {
      const ch = news[i].channel
      if (!ch || ch.length < 4 || linkedChannels.has(ch.toLowerCase())) continue
      const escaped = escapeRegex(ch)
      const regex = new RegExp(
        `(?<!\\[)(?<!\\]\\()(?<![\\p{L}\\d])(${escaped})(?![\\p{L}\\d])(?!\\]|\\()`,
        'giu'
      )
      let replaced = false
      const before = result
      result = result.replace(regex, (match) => {
        if (replaced) return match
        replaced = true
        const ts = news[i].timestamp_seconds
        const tsLabel = ts != null ? ` ${formatTimestamp(ts)}` : ''
        return `[▶ ${match}${tsLabel}](lyra-video:${i})`
      })
      if (result !== before) linkedChannels.add(ch.toLowerCase())
    }
  }

  return result
}
