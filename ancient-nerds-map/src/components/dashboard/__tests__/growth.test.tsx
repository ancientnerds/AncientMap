import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { Growth, linePoints, weekChange } from '../Growth'
import type { DailyData, DailyPoint } from '../types'

/** `n` days from 18 Sep, visitors from `visitors(i)`, humans half of them. */
function days(n: number, visitors: (i: number) => number): DailyPoint[] {
  return Array.from({ length: n }, (_, i) => {
    const v = visitors(i)
    const d = new Date(Date.UTC(2026, 8, 18 + i))
    return { day: d.toISOString().slice(0, 10), visitors: v, human: Math.floor(v / 2), ai: 0 }
  })
}

/** The chart's viewBox height. LINE_HEIGHT is module-private, so the tests
 *  pass it explicitly and pin the default with the same number. */
const H = 100

/** renderToString separates adjacent text with empty comments; read without them. */
const text = (html: string) => html.replace(/<!-- -->/g, '')

describe('Growth linePoints', () => {
  it('puts day i at x = i and the peak at the top', () => {
    expect(linePoints([0, 50, 100], 100, H)).toBe('0,100 1,50 2,0')
  })

  it('uses the same height when none is given', () => {
    expect(linePoints([3, 7], 7)).toBe(linePoints([3, 7], 7, H))
  })

  it('draws an empty history on the baseline instead of dividing by zero', () => {
    expect(linePoints([0, 0], 0, H)).toBe('0,100 1,100')
  })
})

describe('Growth weekChange', () => {
  it('waits for two weeks that do not overlap', () => {
    expect(weekChange(days(13, () => 10), 'visitors')).toBeNull()
    expect(weekChange(days(14, () => 10), 'visitors')).not.toBeNull()
  })

  it('compares the first full week with the last finished one', () => {
    // 100 a day in the first week, 150 a day in the third: the middle week is in neither.
    const c = weekChange(days(21, i => (i < 7 ? 100 : i < 14 ? 1000 : 150)), 'visitors')
    expect(c).toEqual({ first: 100, last: 150, change: 0.5 })
  })

  it('reads the humans from their own field', () => {
    const c = weekChange(days(14, i => (i < 7 ? 20 : 40)), 'human')
    expect(c).toEqual({ first: 10, last: 20, change: 1 })
  })

  it('has no ratio for a first week without anybody', () => {
    expect(weekChange(days(14, i => (i < 7 ? 0 : 5)), 'visitors')?.change).toBeNull()
  })
})

describe('Growth', () => {
  const ok = (data: DailyData) => ({ data, error: null })
  const today = { day: '2026-10-09', visitors: 192, human: 80, ai: 2 }

  it('draws both lines and says how the last week compares with the first', () => {
    const html = text(renderToString(<Growth state={ok({ days: days(21, i => (i < 7 ? 100 : 150)), today })} />))
    expect(html).toContain('dash-line-all')
    expect(html).toContain('dash-line-human')
    expect(html).toContain('+50 %')
    expect(html).toContain('First week (18 Sep–24 Sep): 100 a day, 50 human')
    expect(html).toContain('Last week (02 Oct–08 Oct): <b>150</b> visitors a day')
    expect(html).toContain('192 visitors, 80 human')
  })

  it('says a falling week is falling', () => {
    const html = text(renderToString(<Growth state={ok({ days: days(14, i => (i < 7 ? 100 : 80)), today })} />))
    expect(html).toContain('dash-delta--down')
    expect(html).toContain('−20 %')
  })

  it('draws the line and counts the days it still needs before comparing', () => {
    const html = text(renderToString(<Growth state={ok({ days: days(5, () => 10), today })} />))
    expect(html).toContain('dash-line-human')
    expect(html).toContain('there are 5')
  })
})
