/**
 * Shared gallery segmentation for Theo papers.
 *
 * Groups consecutive `![gallery:ID|verified:..|...]()` image blocks into
 * `TheoGallery` slideshows and leaves everything else as plain markdown.
 * Used by both the live SSE overlay (TheoReportOverlay) and the public
 * research page (ResearchPaperPage) so the rendering is identical.
 */

import type { TheoGalleryImage } from './TheoGallery'

export type PaperSegment =
  | { kind: 'text'; content: string }
  | { kind: 'gallery'; groupId: string; images: TheoGalleryImage[] }

// Matches one inserted image block: image line + blank line + italic caption
// + optional [Source](url) on the next line. Non-greedy on the caption to
// avoid swallowing adjacent blocks.
const IMG_BLOCK_RE =
  /!\[gallery:([^|\]]+)\|verified:(yes|no)\|([^\]]*)\]\(([^)]+)\)\s*\n\n\*([^*\n][^*]*?)\*(?:\s*\n\[Source\]\(([^)]+)\))?/g

export function splitIntoGallerySegments(md: string): PaperSegment[] {
  const matches: Array<{ start: number; end: number; groupId: string; image: TheoGalleryImage }> = []
  const re = new RegExp(IMG_BLOCK_RE.source, IMG_BLOCK_RE.flags)
  let m: RegExpExecArray | null
  while ((m = re.exec(md)) !== null) {
    matches.push({
      start: m.index,
      end: m.index + m[0].length,
      groupId: m[1],
      image: {
        src: m[4],
        title: m[3] || 'Research image',
        caption: (m[5] || '').trim(),
        sourceUrl: m[6] || '',
        verified: m[2] === 'yes',
      },
    })
  }
  if (matches.length === 0) {
    return [{ kind: 'text', content: md }]
  }
  const segments: PaperSegment[] = []
  let cursor = 0
  let i = 0
  while (i < matches.length) {
    if (matches[i].start > cursor) {
      segments.push({ kind: 'text', content: md.slice(cursor, matches[i].start) })
    }
    const groupId = matches[i].groupId
    const images: TheoGalleryImage[] = [matches[i].image]
    let j = i + 1
    while (j < matches.length && matches[j].groupId === groupId) {
      const between = md.slice(matches[j - 1].end, matches[j].start)
      if (between.trim()) break
      images.push(matches[j].image)
      j++
    }
    segments.push({ kind: 'gallery', groupId, images })
    cursor = matches[j - 1].end
    i = j
  }
  if (cursor < md.length) {
    segments.push({ kind: 'text', content: md.slice(cursor) })
  }
  return segments
}
