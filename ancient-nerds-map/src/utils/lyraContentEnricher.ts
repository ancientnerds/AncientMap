/**
 * Pre-processes Lyra's markdown response for frontend display.
 *
 * Most enrichment (coordinates, country flags, video links) is now handled by
 * the backend structured output pipeline (expand_markers). This enricher only
 * handles edge-case fixups that the backend can't cover:
 *
 * - En-dash normalization in site UUIDs (Mercury diffusion artifact)
 * - Bare [site:UUID] link wrapping
 * - Double-enrichment guard for lyra-video: links during streaming
 * - Warning log for stray guillemet markers (backend cleanup failure)
 */

/**
 * Pre-process markdown content — lightweight fixups only.
 * Coordinates, flags, and video links are resolved server-side by expand_markers().
 */
export function enrichLyraContent(content: string): string {
  let result = content

  // 0a. Normalize en-dashes (U+2011, U+2013) in site UUIDs to regular hyphens
  //     Mercury's diffusion model sometimes outputs non-breaking or en-dash hyphens
  result = result.replace(
    /(site:[0-9a-f]{8})[‑–]([0-9a-f]{4})[‑–]([0-9a-f]{4})[‑–]([0-9a-f]{4})[‑–]([0-9a-f]{12})/gi,
    (_m, a, b, c, d, e) => `${a}-${b}-${c}-${d}-${e}`
  )

  // 0b. Fix bare [site:UUID] links → wrap as [View Site](site:UUID)
  result = result.replace(
    /(?<!\()\[site:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\](?!\()/gi,
    (_match, uuid) => `[View Site](site:${uuid})`
  )

  // Warn if guillemet markers leaked through (backend should have stripped these)
  if (result.includes('\u00ab')) {
    console.warn('[enrichLyraContent] Guillemet markers found in content — backend cleanup may have failed')
  }

  return result
}
