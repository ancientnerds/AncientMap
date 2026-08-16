/**
 * Text-Helfer der SEO-Seiten — Portierung von blurb() und den beiden
 * String-Idiomen aus pipeline/seo_pages.py.
 *
 * Alle Längen zählen Codepoints (Array.from), nicht UTF-16-Einheiten:
 * Python-Slicing arbeitet auf Codepoints, und die Vitest-Vergleiche gegen
 * die Python-Referenz-Heads müssen byte-genau aufgehen — auch wenn eine
 * Headline ein Emoji trägt.
 *
 * Bekanntes Whitespace-Delta für künftige Parity-Diagnose: JS \s matcht
 * U+FEFF (Python str.split() nicht), Python splittet zusätzlich an
 * U+0085 und U+001C–001F. In realen Headlines/Descriptions kommt beides
 * nicht vor.
 */

/** Python `" ".join(s.split())`: Whitespace-Läufe kollabieren, trimmen. */
export function collapse(text: string): string {
  return text.split(/\s+/).filter(Boolean).join(' ')
}

/** Python `s[:limit]`: harter Schnitt nach Codepoints. */
export function cut(text: string, limit: number): string {
  const points = Array.from(text)
  return points.length <= limit ? text : points.slice(0, limit).join('')
}

/**
 * Whitespace kollabieren und an der Wortgrenze mit Ellipse kappen —
 * seo_pages.blurb(), eine Definition für Listing-Karten und Descriptions.
 */
export function blurb(text: string | null | undefined, limit = 180): string {
  if (!text) return ''
  const collapsed = collapse(text)
  if (Array.from(collapsed).length <= limit) return collapsed
  const sliced = cut(collapsed, limit)
  const space = sliced.lastIndexOf(' ')
  return (space === -1 ? sliced : sliced.slice(0, space)) + '…'
}
