/**
 * Shared figure segmentation for Theo papers.
 *
 * Walks the paper markdown and pulls every research-image block out. A lone
 * image becomes a `figure` segment (floats into the next paragraph); two or
 * more images adjacent in the markdown — separated only by whitespace —
 * collapse into a single `mosaic` segment so they render as a grid of up to
 * three columns beneath the paragraph rather than floating side-by-side with
 * prose squeezed between them.
 *
 * Surrounding prose is returned verbatim as `text` segments so consumers can
 * hand it to ReactMarkdown unchanged. Used by both the live SSE overlay
 * (TheoReportOverlay) and the public research page (ResearchPaperPage) so the
 * rendering is identical.
 */

export interface ImageFigure {
  src: string
  title: string
  caption: string
  sourceUrl: string
  galleryId?: string
}

export type PaperSegment =
  | { kind: 'text'; content: string }
  | { kind: 'figure'; figure: ImageFigure }
  | { kind: 'mosaic'; figures: ImageFigure[] }
  | { kind: 'carousel'; galleryId: string; figures: ImageFigure[] }

// Matches any inline image under /data/research-images/, plus the optional
// italic caption line and optional [Source](url) trailer. Non-greedy on the
// caption so adjacent blocks don't bleed into one match.
const FIGURE_RE =
  /!\[(?<alt>[^\]]*)\]\((?<src>\/data\/research-images\/[^)]+)\)(?:\s*\n\n\*(?<caption>[^*\n][^*]*?)\*(?:\s*\n\[Source\]\((?<url>[^)]+)\))?)?/g

// Parses `gallery:ID|verified:yes|Title` (and legacy variants). Returns the
// extracted galleryId (null if absent) and the cleaned title.
function parseAlt(alt: string): { galleryId: string | null; title: string } {
  const m = alt.match(/^gallery:([^|]+)\|(?:verified:(?:yes|no)\|)?(.*)$/)
  if (m) {
    return { galleryId: m[1], title: (m[2] || '').trim() || 'Research image' }
  }
  return { galleryId: null, title: alt.trim() || 'Research image' }
}

export function splitIntoImageSegments(md: string): PaperSegment[] {
  const matches: Array<{ start: number; end: number; figure: ImageFigure }> = []
  const re = new RegExp(FIGURE_RE.source, FIGURE_RE.flags)
  let m: RegExpExecArray | null
  while ((m = re.exec(md)) !== null) {
    const g = m.groups || {}
    const parsed = parseAlt(g.alt || '')
    matches.push({
      start: m.index,
      end: m.index + m[0].length,
      figure: {
        src: g.src || '',
        title: parsed.title,
        caption: (g.caption || '').trim(),
        sourceUrl: g.url || '',
        galleryId: parsed.galleryId || undefined,
      },
    })
  }

  if (matches.length === 0) {
    return [{ kind: 'text', content: md }]
  }

  // Group matches whose gap contains only whitespace (blank lines between
  // image blocks). Anything with real prose in between breaks the group so
  // that image stays attached to the paragraph before it.
  type Group = { start: number; end: number; figures: ImageFigure[] }
  const groups: Group[] = []
  for (const match of matches) {
    const last = groups[groups.length - 1]
    if (last && md.slice(last.end, match.start).trim() === '') {
      last.end = match.end
      last.figures.push(match.figure)
    } else {
      groups.push({ start: match.start, end: match.end, figures: [match.figure] })
    }
  }

  const segments: PaperSegment[] = []
  let cursor = 0
  for (const group of groups) {
    if (group.start > cursor) {
      segments.push({ kind: 'text', content: md.slice(cursor, group.start) })
    }
    if (group.figures.length === 1) {
      segments.push({ kind: 'figure', figure: group.figures[0] })
    } else {
      // Always stack multi-image groups as a mosaic. We used to render
      // backend-flagged same-paragraph groups (shared gallery id) as a
      // carousel, but that hid most images behind ‹ N / M › chrome and
      // people consistently missed the supporting evidence. The existing
      // `.theo-figure-mosaic--cols-N` CSS caps at 3 columns, so a
      // 6-image group becomes two rows of three — all visible at once.
      segments.push({ kind: 'mosaic', figures: group.figures })
    }
    cursor = group.end
  }
  if (cursor < md.length) {
    segments.push({ kind: 'text', content: md.slice(cursor) })
  }
  return segments
}
