/**
 * Pre-processes Lyra's markdown response to insert:
 * - Site name links: [SiteName](lyra-site:id:lon:lat)
 * - Country flags: ![flag](/flags-flat/xx.webp) CountryName
 * - Copyable coordinates: [coord:lat,lon](lyra-coord:lat,lon)
 *
 * These are then rendered by react-markdown custom components in LyraChatModal.
 */

import type { SiteHighlight } from '../types/ai'
import { COUNTRY_CODES, getCountryFlatFlagUrl } from './countryFlags'

// Build sorted country names list (longest first to avoid partial matches)
const COUNTRY_NAMES = Object.keys(COUNTRY_CODES).sort((a, b) => b.length - a.length)

// Escape special regex chars
function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Pre-process markdown content to embed interactive markers.
 *
 * Order matters: coordinates first (they contain brackets that could interfere),
 * then sites, then countries.
 */
export function enrichLyraContent(content: string, sites: SiteHighlight[]): string {
  let result = content

  // 1. Coordinates: [lat, lon] or [lat,lon] → custom link
  //    Match patterns like [37.0928, 39.3041] but NOT already-linked markdown
  result = result.replace(
    /(?<!\()\[(-?\d+\.?\d*),\s*(-?\d+\.?\d*)\](?!\()/g,
    (_match, lat, lon) => `[${lat}, ${lon}](lyra-coord:${lat},${lon})`
  )

  // 2. Site names → links (longest first to avoid partial matches)
  //    Only match if not already inside a markdown link [...](...) or **bold**
  const sortedSites = [...sites].sort((a, b) => b.name.length - a.name.length)
  const replacedSiteNames = new Set<string>()
  for (const site of sortedSites) {
    const nameLower = site.name.toLowerCase()
    if (replacedSiteNames.has(nameLower)) continue
    if (!site.id || site.name.length < 3) continue

    const escaped = escapeRegex(site.name)
    // Word-boundary match, case-insensitive. Avoid matching inside existing links.
    const regex = new RegExp(
      `(?<!\\[)(?<!\\]\\()\\b(${escaped})\\b(?!\\]|\\()`,
      'gi'
    )
    let replaced = false
    result = result.replace(regex, (match) => {
      if (replaced) return match // Only link first occurrence
      replaced = true
      return `[${match}](lyra-site:${site.id}:${site.lon}:${site.lat})`
    })
    if (replaced) replacedSiteNames.add(nameLower)
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
      `(?<!\\[)(?<!/)\\b(${escaped})\\b(?!\\]|\\()`,
      'gi'
    )
    let replaced = false
    result = result.replace(regex, (match) => {
      if (replaced) return match
      replaced = true
      return `![flag](${flagUrl})${match}`
    })
    if (replaced) replacedCountries.add(name.toLowerCase())
  }

  return result
}
