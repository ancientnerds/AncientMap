import { describe, expect, it } from 'vitest'

import { boardLayout, claimAppear } from '../src/blocks/ClaimBoard'
import { cardLayout } from '../src/blocks/EvidenceCard'
import { checkMeter, meterTop } from '../src/blocks/Meter'
import { checkQuoteCard } from '../src/blocks/QuoteCard'
import { checkSourceViewer, defaultScroll, pageInfo, scrollAt, windowRect } from '../src/blocks/SourceViewer'
import type { Capture, Evidence } from '../src/blocks/types'
import { ZONES } from '../src/layout/zones'

const evidence: Evidence = {
  id: 'e1',
  claim_id: 'c1',
  kind: 'quantity',
  statement: 'The Stone of the Pregnant Woman weighs about 1,000 tonnes.',
  source: { url: 'https://www.dainst.org/baalbek-report', title: 'DAI report', tier: 1, license: '', quote: 'estimated to weigh 1,650 tonnes', locator: 'section 2' },
  paper_anchor: 'ev-01',
}
const page: Capture = {
  id: 'src1',
  kind: 'source',
  src: 'captures/src1.png',
  fps: null,
  duration_s: null,
  width: 2560,
  height: 3686,
  events: [
    { t: 0, name: 'page', url: 'https://en.wikipedia.org/wiki/Baalbek', title: 'Baalbek - Wikipedia' },
    { t: 0, name: 'highlight', box: [528, 1800, 1489, 86], target: 'quote' },
  ],
  credits: [],
}

describe('EvidenceCard', () => {
  it('shares the free height 45:55 between statement and quote', () => {
    const l = cardLayout(660)
    expect(l.statement.y).toBe(102)
    expect(l.quote.y).toBe(l.statement.y + l.statement.h + 18)
    expect(l.quote.y + l.quote.h + 18).toBe(l.source.y)
  })
})

describe('QuoteCard', () => {
  it('needs a verbatim quote', () => {
    expect(checkQuoteCard({ evidence })).toEqual([])
    expect(checkQuoteCard({ evidence: { ...evidence, source: { ...evidence.source, quote: ' ' } } })).toEqual(['evidence e1 has no verbatim quote to show'])
  })
})

describe('SourceViewer', () => {
  it('reads the url and the highlight box from the capture events; the page title stays a record', () => {
    expect(pageInfo(page)).toEqual({ url: 'https://en.wikipedia.org/wiki/Baalbek', box: [528, 1800, 1489, 86] })
    expect(checkSourceViewer({ page, evidence })).toEqual([])
    expect(checkSourceViewer({ page: { ...page, events: [] }, evidence })).toEqual(['capture src1 has no page event with a url', 'capture src1 has no highlight event with a box'])
  })
  it('brings the quote from low in the window to 35 % from the top', () => {
    const win = windowRect(ZONES.stage)
    const keys = defaultScroll(2560, 4000, 2000, win)
    const viewport = ((win.h - 52) * 2560) / win.w
    expect(keys[0].y).toBeCloseTo(2000 - viewport * 0.8)
    expect(scrollAt(keys, 1)).toBeCloseTo(2000 - viewport * 0.35)
  })
})

describe('ClaimBoard', () => {
  it('lets claims appear at their introduce cue, earlier ones at once, later ones not yet', () => {
    expect(claimAppear(undefined, 2, 0, 100)).toBe(28)
    expect(claimAppear(40, 0, 0, 100)).toBe(40)
    expect(claimAppear(10, 0, 200, 300)).toBe(0)
    expect(claimAppear(400, 0, 200, 300)).toBeNull()
  })
  it('makes the rows as tall as the stage allows and centres them', () => {
    expect(boardLayout(2, 230, 820)).toEqual({ rowH: 190, labelSize: 46, top: 335 })
    expect(boardLayout(6, 230, 820)).toEqual({ rowH: 98, labelSize: 30, top: 231 })
  })
})

describe('Meter', () => {
  it('needs a start split summing to 100 and centres its stack', () => {
    expect(checkMeter({ hypotheses: ['Roman engineers', 'A lost older civilization'], start: [50, 50] })).toEqual([])
    expect(checkMeter({ hypotheses: ['a', 'b'], start: [60, 30] })).toEqual(['meter start [60,30] must sum to 100'])
    expect(meterTop(140, 680, false)).toBeGreaterThan(meterTop(140, 680, true))
  })
})
