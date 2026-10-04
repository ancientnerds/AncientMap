import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { checkBlocks } from '../src/blocks'
import { type BarChartProps, checkBarChart } from '../src/blocks/BarChart'
import { COMPOSED, metaLine, sourceLine } from '../src/blocks/composed'
import { checkEvidenceCard } from '../src/blocks/EvidenceCard'
import { checkQuoteCard } from '../src/blocks/QuoteCard'
import { REGISTRY_BLOCKS } from '../src/blocks/schemas'
import type { Evidence } from '../src/blocks/types'
import { parseTimeline } from '../src/timeline'
import { capacityTimeline, metaLineEdits, quotesOfLength, sceneVariants, sourceLineEdits } from './capacity'
import { schemaAt } from './registryHelpers'

const pinned = JSON.parse(readFileSync(fileURLToPath(new URL('./fixtures/composed-limits.json', import.meta.url)), 'utf-8')) as Record<string, unknown>

/**
 * Text that is built from several fields has no per-field limit that bounds it: the box holds a number of
 * characters of the whole line (every one of these is a monospace line, so characters are exact), and
 * `episode check` has to refuse what the render lint refuses (render-R2). The numbers are measured by
 * test/gpu/capacity.gpu.ts on the RTX 3080 and mirrored by pipeline/studio/blocks.py.
 */
describe('the limits of text composed of several fields (blocks/composed.ts)', () => {
  it('are the numbers pinned in test/fixtures/composed-limits.json, which tests/pipeline/studio/test_blocks.py reads too', () => {
    expect(COMPOSED).toEqual(pinned)
  })
})

const bars = (unit: string, ...values: BarChartProps['bars'][number]['value'][]): BarChartProps => ({
  title: 'Weights',
  unit,
  basis: 'two sources',
  bars: values.map((value, i) => ({ id: `b${i}`, label: `Bar ${i}`, value })),
})
const barErrors = (p: BarChartProps) => checkBarChart(p, { fps: 60, durationInFrames: 600 })

describe('BarChart value text (digits plus unit)', () => {
  it('refuses a range that the 16-character value box cannot hold: "1,000–1,650 tonnes" is 18 characters', () => {
    expect(barErrors(bars('tonnes', [1000, 1650]))).toEqual(['bar b0: "1,000–1,650 tonnes" is 18 characters; the value box holds 16 for a range'])
  })
  it('refuses a single value that the 14-character value box cannot hold', () => {
    expect(barErrors(bars('tonnes', 125000))).toEqual([])
    expect(barErrors(bars('tonnes', 1250000))).toEqual(['bar b0: "1,250,000 tonnes" is 16 characters; the value box holds 14 for a single value'])
  })
  it('accepts what fits: a 4-digit range of a short unit, a 3-digit range of the longest unit, a 4-digit value of it', () => {
    expect(barErrors(bars('t', [1000, 1650]))).toEqual([])
    expect(barErrors(bars('tons', [1000, 1650]))).toEqual([])
    expect(barErrors(bars('tonnes', [100, 165], 1250))).toEqual([])
  })
  it('counts the exact decimals the bar prints', () => {
    expect(barErrors(bars('metres', [19.6, 20.5]))).toEqual([])
    expect(barErrors(bars('metres', [119.65, 120.55]))).toEqual(['bar b0: "119.65–120.55 metres" is 20 characters; the value box holds 16 for a range'])
  })
})

const evidence = (host: string, locator: string, over: Partial<Evidence['source']> = {}, anchor: string | null = 'ev-01'): Evidence => ({
  id: 'ev-01',
  claim_id: 'c1',
  kind: 'fact',
  statement: 'A statement.',
  source: { url: `https://${host}/paper`, title: 'A paper', tier: 1, license: '', quote: 'A quote.', locator, ...over },
  paper_anchor: anchor,
})
const IMAGE = { src: 'media/x.jpg', width: 960, height: 540, alt: 'x', markers: [] } as never

describe('EvidenceCard source line (host // tier // locator // paper #anchor)', () => {
  it('refuses a long host with a long locator beside an image: the line holds 72 characters, not a host of 16 plus a locator of 24', () => {
    expect(checkEvidenceCard({ evidence: evidence('onlinelibrary.wiley.com', 'Results, paragraph 2'), image: IMAGE })).toEqual([
      'evidence ev-01: the source line "onlinelibrary.wiley.com  //  tier 1  //  Results, paragraph 2  //  paper #ev-01" is 79 characters; the card holds 72 beside an image',
    ])
    expect(checkEvidenceCard({ evidence: evidence('pubmed.ncbi.nlm.nih.gov', 'Table 2, third column'), image: IMAGE })).toHaveLength(1)
  })
  it('holds 86 characters when there is no image', () => {
    expect(checkEvidenceCard({ evidence: evidence('onlinelibrary.wiley.com', 'Results, paragraph 2') })).toEqual([])
    expect(checkEvidenceCard({ evidence: evidence('onlinelibrary.wiley.com', 'x'.repeat(24), {}, 'ev-zzzzzzzzzz') })).toEqual([
      expect.stringContaining('is 91 characters; the card holds 86 with no image'),
    ])
  })
  it('accepts the sources that fit: the usual hosts with the longest locator, a 16-character host with a locator of 20 (72 characters)', () => {
    expect(checkEvidenceCard({ evidence: evidence('jstor.org', 'x'.repeat(24)), image: IMAGE })).toEqual([])
    expect(checkEvidenceCard({ evidence: evidence('researchgate.net', 'x'.repeat(20)), image: IMAGE })).toEqual([])
    expect(checkEvidenceCard({ evidence: evidence('researchgate.net', 'x'.repeat(21)), image: IMAGE })).toHaveLength(1)
  })
  it('counts the hostname as the lint draws it: without www., an unbounded paper anchor included', () => {
    expect(checkEvidenceCard({ evidence: evidence('www.jstor.org', 'x'.repeat(24)), image: IMAGE })).toEqual([])
    expect(checkEvidenceCard({ evidence: evidence('jstor.org', '', {}, 'ev-' + 'z'.repeat(60)), image: IMAGE })).toHaveLength(1)
  })
})

describe('QuoteCard lines', () => {
  const card = (host: string, locator: string, attribution?: string) => ({ evidence: evidence(host, locator), attribution })
  it('refuses a meta line (locator // host // tier) above 94 characters', () => {
    const errors = checkQuoteCard(card('a'.repeat(60) + '.org', 'x'.repeat(24)))
    expect(errors).toEqual([expect.stringContaining('the meta line')])
    expect(checkQuoteCard(card('onlinelibrary.wiley.com', 'x'.repeat(24)))).toEqual([])
  })
  it('has a work line that the per-field limits bound: attribution 32 + ", " + title 43 is the 77 characters the box holds', () => {
    const limit = (path: string) => schemaAt(REGISTRY_BLOCKS.QuoteCard.props, path)?.maxLength as number
    expect(limit('attribution') + 2 + limit('evidence.source.title')).toBe(COMPOSED['QuoteCard.workLine'])
  })
})

describe('the composed limits in the capacity episode', () => {
  it('leave the capacity episode (every field at its maxLength, a 16-character host) valid', () => {
    expect(() => checkBlocks(parseTimeline(capacityTimeline().timeline))).not.toThrow()
  })
})

/** The real-text variants the GPU tests lint (test/gpu/capacity.gpu.ts): valid timelines, every text exactly at its limit. */
describe('the real-text variants of the capacity episode', () => {
  const hookQuote = REGISTRY_BLOCKS.EvidenceCard.props.properties?.evidence.properties?.source.properties?.quote.hookMaxLength as number

  it('offer quotes of exactly the hook limit, in real words, that pass episode check on a hook card with and without an image', () => {
    const quotes = quotesOfLength(hookQuote, 12)
    expect(new Set(quotes).size).toBe(12)
    for (const q of quotes) {
      expect(q).toHaveLength(hookQuote)
      expect(q.endsWith(' ')).toBe(false)
    }
    for (const scene of ['EvidenceCard.withimage.hook', 'EvidenceCard.noimage.hook']) {
      const { timeline } = sceneVariants(scene, quotes.map((q, i) => ({ id: `q${i}`, edit: (p) => ((p.evidence as Evidence).source.quote = q) })))
      expect(() => checkBlocks(parseTimeline(timeline))).not.toThrow()
      // a quote of one character more is refused on the hook stage
      const over = sceneVariants(scene, [{ id: 'over', edit: (p) => ((p.evidence as Evidence).source.quote = quotesOfLength(hookQuote + 1, 1)[0]) }])
      expect(() => checkBlocks(parseTimeline(over.timeline))).toThrow(new RegExp(`quote: longer than ${hookQuote} on a hook beat`))
    }
  })
  it('captions the variants of a hook scene, so the lint draws them on the hook stage', () => {
    const { timeline } = sceneVariants('EvidenceCard.noimage.hook', [{ id: 'a', edit: () => undefined }, { id: 'b', edit: () => undefined }])
    expect(parseTimeline(timeline).captions).toHaveLength(2)
    expect(parseTimeline(sceneVariants('EvidenceCard.noimage.full', [{ id: 'a', edit: () => undefined }]).timeline).captions).toHaveLength(0)
  })
  it('offer source lines of exactly the limit that the block check accepts: real hosts, with an image (72) and without (86)', () => {
    for (const [scene, limit] of [['EvidenceCard.withimage.full', COMPOSED['EvidenceCard.sourceLine'].image], ['EvidenceCard.noimage.full', COMPOSED['EvidenceCard.sourceLine'].plain]] as const) {
      for (const hostOnly of [false, true]) {
        const edits = sourceLineEdits(limit, hostOnly)
        const { timeline } = sceneVariants(scene, edits.map((e) => ({ id: e.id, edit: (p) => {
          const ev = p.evidence as Evidence
          Object.assign(ev.source, { url: e.url, locator: e.locator })
          ev.paper_anchor = e.anchor
        } })))
        const parsed = parseTimeline(timeline)
        expect(() => checkBlocks(parsed)).not.toThrow()
        for (const s of parsed.scenes) expect(sourceLine(s.props.evidence as Evidence), `${scene} ${s.id}`).toHaveLength(limit)
      }
    }
  })
  it('offer QuoteCard meta lines of exactly the limit that the block check accepts', () => {
    const limit = COMPOSED['QuoteCard.metaLine']
    const { timeline } = sceneVariants('QuoteCard.full', metaLineEdits(limit).map((e) => ({ id: e.id, edit: (p) => Object.assign((p.evidence as Evidence).source, { url: e.url, locator: e.locator }) })))
    const parsed = parseTimeline(timeline)
    expect(() => checkBlocks(parsed)).not.toThrow()
    for (const s of parsed.scenes) expect(metaLine(s.props.evidence as Evidence)).toHaveLength(limit)
  })
})
