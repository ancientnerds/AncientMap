/**
 * Pre-processes Lyra's markdown response to insert:
 * - Copyable coordinates: [coord:lat,lon](lyra-coord:lat,lon)
 * - Country flags: ![flag](/flags-flat/xx.webp) CountryName
 * - YouTube video embeds: [▶ Channel](lyra-video:INDEX)
 *
 * Site links are emitted directly by the LLM as [Site Name](site:UUID)
 * and handled by the markdown renderer in LyraChatModal.
 */

import type { NewsHighlight } from '../types/ai'
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
 * Pre-process markdown content to embed interactive markers.
 *
 * Order matters: coordinates first (they contain brackets that could interfere),
 * then countries, then YouTube references.
 */
export function enrichLyraContent(content: string, news?: NewsHighlight[]): string {
  let result = content

  // 1. Coordinates: [lat, lon] or [lat,lon] → custom link
  //    Match patterns like [37.0928, 39.3041] but NOT already-linked markdown
  result = result.replace(
    /(?<!\()\[(-?\d+\.?\d*),\s*(-?\d+\.?\d*)\](?!\()/g,
    (_match, lat, lon) => `[${lat}, ${lon}](lyra-coord:${lat},${lon})`
  )

  // 2. Country names → flag image + name (longest first)
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

  // 3. YouTube video references → lyra-video:INDEX links
  if (news && news.length > 0) {
    // 3a. Direct [youtube: VIDEO_ID] markers (if LLM echoes them from context)
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

    // 3b. Channel names → link first occurrence to matching news item
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
