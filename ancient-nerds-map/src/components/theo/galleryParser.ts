/**
 * Shared figure segmentation for Theo papers.
 *
 * Walks the paper markdown and pulls every research-image block out into a
 * single `figure` segment carrying the src, alt title, italic caption and
 * [Source] URL. Surrounding prose is returned verbatim as `text` segments so
 * consumers can hand it to ReactMarkdown unchanged.
 *
 * Used by both the live SSE overlay (TheoReportOverlay) and the public
 * research page (ResearchPaperPage) so the rendering is identical.
 */

export interface ImageFigure {
  src: string
  title: string
  caption: string
  sourceUrl: string
}

export type PaperSegment =
  | { kind: 'text'; content: string }
  | { kind: 'figure'; figure: ImageFigure }

// Matches any inline image under /data/research-images/, plus the optional
// italic caption line and optional [Source](url) trailer. Non-greedy on the
// caption so adjacent blocks don't bleed into one match.
const FIGURE_RE =
  /!\[(?<alt>[^\]]*)\]\((?<src>\/data\/research-images\/[^)]+)\)(?:\s*\n\n\*(?<caption>[^*\n][^*]*?)\*(?:\s*\n\[Source\]\((?<url>[^)]+)\))?)?/g

// Strips legacy `gallery:ID|verified:yes|` or `gallery:ID|` alt prefixes left
// over from the slideshow era — the title is whatever comes after the last |.
function cleanAlt(alt: string): string {
  const m = alt.match(/^gallery:[^|]+\|(?:verified:(?:yes|no)\|)?(.*)$/)
  return (m ? m[1] : alt).trim() || 'Research image'
}

export function splitIntoImageSegments(md: string): PaperSegment[] {
  const matches: Array<{ start: number; end: number; figure: ImageFigure }> = []
  const re = new RegExp(FIGURE_RE.source, FIGURE_RE.flags)
  let m: RegExpExecArray | null
  while ((m = re.exec(md)) !== null) {
    const g = m.groups || {}
    matches.push({
      start: m.index,
      end: m.index + m[0].length,
      figure: {
        src: g.src || '',
        title: cleanAlt(g.alt || ''),
        caption: (g.caption || '').trim(),
        sourceUrl: g.url || '',
      },
    })
  }

  if (matches.length === 0) {
    return [{ kind: 'text', content: md }]
  }

  const segments: PaperSegment[] = []
  let cursor = 0
  for (const match of matches) {
    if (match.start > cursor) {
      segments.push({ kind: 'text', content: md.slice(cursor, match.start) })
    }
    segments.push({ kind: 'figure', figure: match.figure })
    cursor = match.end
  }
  if (cursor < md.length) {
    segments.push({ kind: 'text', content: md.slice(cursor) })
  }
  return segments
}
