/**
 * The limits of text a block composes from several fields. A field's own maxLength cannot bound
 * it: a BarChart's value box holds "1,000–1,650 tonnes" or does not by the digits and the unit
 * together, an evidence card's source line by host, tier, locator and anchor together. Every
 * one of these is one monospace line, so the box holds a number of characters, measured with
 * the real lint on the RTX 3080 (test/gpu/capacity.gpu.ts) with a margin of at least two.
 * The block checks (checkBarChart, checkEvidenceCard, checkQuoteCard) refuse a line above them,
 * so `episode check` refuses what the lint would refuse; pipeline/studio/blocks.py mirrors the
 * numbers (test/fixtures/composed-limits.json pins both).
 */
import { domainOf } from '../format'
import type { Evidence } from './types'

export const COMPOSED = {
  /** BarChart `valueText`: hud 34 px (a single value) and 30 px (a range) in a 360 px box, 0.14 em of tracking. */
  'BarChart.valueText': { single: 14, range: 16 },
  /** EvidenceCard: 18 px caps, 0.14 em of tracking, in the text column beside the 500 px image or the 360 px stamp column (measured: 74 and 88 fit). */
  'EvidenceCard.sourceLine': { image: 72, plain: 86 },
  /** QuoteCard meta line, 20 px caps (measured: 96 fits). */
  'QuoteCard.metaLine': 94,
  /** QuoteCard work line, 30 px mono: bounded by its fields (attribution 32, ", ", title 43), the box holds exactly that. */
  'QuoteCard.workLine': 77,
} as const

/** The EvidenceCard source line: "host  //  tier 1  //  locator  //  paper #anchor". */
export const sourceLine = (e: Evidence): string =>
  [domainOf(e.source.url), `tier ${e.source.tier}`, e.source.locator, e.paper_anchor ? `paper #${e.paper_anchor}` : ''].filter(Boolean).join('  //  ')

/** The QuoteCard meta line: "locator  //  host  //  tier 1". */
export const metaLine = (e: Evidence): string => [e.source.locator, domainOf(e.source.url), `tier ${e.source.tier}`].filter(Boolean).join('  //  ')

/** The error for a line of `text` over `limit` characters, or none: `<what> "<text>" is N characters; <holder> holds <limit> <layout>`. */
export function lineProblem(what: string, text: string, limit: number, holder: string, layout: string): string[] {
  return text.length > limit ? [`${what} "${text}" is ${text.length} characters; ${holder} holds ${limit} ${layout}`] : []
}
