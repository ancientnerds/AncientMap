import { describe, expect, it } from 'vitest'

import { TITLE_H, boardLayout, claimAppear, rowFrame } from '../src/blocks/ClaimBoard'
import type { RowFrame } from '../src/blocks/ClaimBoard'
import { cardLayout } from '../src/blocks/EvidenceCard'
import { checkMeter, meterTop } from '../src/blocks/Meter'
import { checkQuoteCard } from '../src/blocks/QuoteCard'
import { checkSourceViewer, defaultScroll, pageInfo, scrollAt, windowRect } from '../src/blocks/SourceViewer'
import type { Capture, Evidence } from '../src/blocks/types'
import { findViolations } from '../src/layout/geometry'
import type { Box, Rect } from '../src/layout/geometry'
import { ZONES } from '../src/layout/zones'
import { stampSlam } from '../src/motion'
import { CLAIM_STATUSES } from '../src/theme/colors'
import type { ClaimStatus } from '../src/theme/colors'
import { heading, hud } from '../src/theme/type'

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
    expect(boardLayout(2, ZONES.stage)).toEqual({ rowH: 190, labelSize: 46, stampSize: 32, top: 335 })
    expect(boardLayout(6, ZONES.stage)).toEqual({ rowH: 98, labelSize: 30, stampSize: 22, top: 231 })
  })
})

/**
 * Stamp text widths in Chrome (Playwright Chromium with the brand woff2 files, 2026-09-27): each
 * status in heading()'s Orbitron 700, upper case with its 0.06em letter-spacing, in em of the font
 * size (SUPPORTED at 32 px: 249.2 px). Stamp.tsx draws the text with 18 px padding left and right,
 * 6 px above and below, inside a 4 px border.
 */
const STAMP_TEXT_EM: Record<ClaimStatus, number> = { pending: 5.5191, supported: 7.7882, weakened: 7.2564, refuted: 5.9214, open: 3.4571 }
const STAMP_FRAME = { w: 2 * 18 + 2 * 4, h: 2 * 6 + 2 * 4 }
/** hud(28) draws the unstamped status in JetBrains Mono 500, 0.6 em per character (measured the same day) plus its letter-spacing. */
const HUD_ADVANCE_EM = 0.6

/** The largest scale of the stamp slam and its tilt, read from motion's stampSlam over its whole spring. */
function slamWorst(): { scale: number; deg: number } {
  let worst = { scale: 0, deg: 0 }
  for (let frame = 0; frame <= 120; frame++) {
    const transform = String(stampSlam(frame, 0, 60).transform)
    const m = /^rotate\((-?[\d.]+)deg\) scale\(([\d.]+)\)$/.exec(transform)
    if (m === null) throw new Error(`unexpected stampSlam transform ${transform}`)
    if (Number(m[2]) > worst.scale) worst = { scale: Number(m[2]), deg: Number(m[1]) }
  }
  return worst
}

/** The box getBoundingClientRect reports (what LayoutBox measures) for a w x h box turned and scaled about its centre (cx, cy). */
function turnedBox(cx: number, cy: number, w: number, h: number, scale: number, deg: number): Rect {
  const rad = (deg * Math.PI) / 180
  const bw = scale * (w * Math.abs(Math.cos(rad)) + h * Math.abs(Math.sin(rad)))
  const bh = scale * (h * Math.abs(Math.cos(rad)) + w * Math.abs(Math.sin(rad)))
  return { x: cx - bw / 2, y: cy - bh / 2, w: bw, h: bh }
}

/**
 * The text boxes the lint measures on a ClaimBoard frame where every stamped row's stamp is at the
 * slam's largest scale at once: the title, each label and each row's stamp or status text (both
 * centred on the row panel's height at the status column).
 */
function boardBoxes(stage: Rect, count: number, stamped: (row: number) => boolean, status: ClaimStatus, frame?: RowFrame, stampSize?: number): Box[] {
  const layout = boardLayout(count, stage)
  const f = frame ?? rowFrame(stage.w, layout.rowH)
  const size = stampSize ?? layout.stampSize
  const slam = slamWorst()
  const boxes: Box[] = [{ id: 'title', kind: 'text', rect: { x: stage.x, y: stage.y, w: stage.w, h: TITLE_H }, allow: [] }]
  for (let i = 0; i < count; i++) {
    const x = stage.x
    const y = layout.top + i * layout.rowH
    const cy = y + f.h / 2
    boxes.push({ id: `claim:${i}`, kind: 'text', rect: { ...f.label, x: x + f.label.x, y: y + f.label.y }, allow: [] })
    if (stamped(i)) {
      const w = STAMP_TEXT_EM[status] * size + STAMP_FRAME.w
      const h = Number(heading(size).lineHeight) * size + STAMP_FRAME.h
      boxes.push({ id: `stamp:${i}`, kind: 'text', rect: turnedBox(x + f.statusX + w / 2, cy, w, h, slam.scale, slam.deg), allow: [] })
    } else {
      const style = hud(28)
      const w = status.length * 28 * (HUD_ADVANCE_EM + Number.parseFloat(String(style.letterSpacing)))
      const h = Number(style.lineHeight) * 28
      boxes.push({ id: `status:${i}`, kind: 'text', rect: { x: x + f.statusX, y: cy - h / 2, w, h }, allow: [] })
    }
  }
  return boxes
}

describe('ClaimBoard stamps', () => {
  it('slams from 1.35x at -6 deg (the worst case the checks below assume)', () => {
    expect(slamWorst()).toEqual({ scale: 1.35, deg: -6 })
  })
  it('keeps every stamp, slamming in at 1.35x, clear of its label, its neighbours, the title and the safe area', () => {
    for (const [name, stage] of Object.entries({ stage: ZONES.stage, stageHook: ZONES.stageHook })) {
      for (let count = 1; count <= 6; count++) {
        for (const status of CLAIM_STATUSES) {
          const where = `${name}, ${count} claims, ${status}`
          expect(findViolations(boardBoxes(stage, count, () => true, status)), where).toEqual([])
          expect(findViolations(boardBoxes(stage, count, (row) => row % 2 === 0, status)), `${where}, even rows stamped`).toEqual([])
          expect(findViolations(boardBoxes(stage, count, (row) => row % 2 === 1, status)), `${where}, odd rows stamped`).toEqual([])
        }
      }
    }
  })
  it('catches the plan layout: a label to 380 px from the right edge and a 32 px stamp 40 px after it', () => {
    const stage = ZONES.stage
    const { rowH } = boardLayout(6, stage)
    const plan = { h: rowH - 14, label: { x: 120, y: 6, w: stage.w - 120 - 380, h: rowH - 26 }, statusX: stage.w - 340 }
    const violations = findViolations(boardBoxes(stage, 6, () => true, 'supported', plan, 32))
    expect(violations).toContainEqual({ a: 'claim:0', b: 'stamp:0', reason: 'overlap' })
    expect(violations).toContainEqual({ a: 'stamp:0', b: null, reason: 'outside-safe' })
    expect(violations).toContainEqual({ a: 'stamp:0', b: 'stamp:1', reason: 'overlap' })
  })
})

describe('Meter', () => {
  it('needs a start split summing to 100 and centres its stack', () => {
    expect(checkMeter({ hypotheses: ['Roman engineers', 'A lost older civilization'], start: [50, 50] })).toEqual([])
    expect(checkMeter({ hypotheses: ['a', 'b'], start: [60, 30] })).toEqual(['meter start [60,30] must sum to 100'])
    expect(meterTop(140, 680, false)).toBeGreaterThan(meterTop(140, 680, true))
  })
})
