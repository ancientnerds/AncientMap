/**
 * The three panels that show Google's and the crawlers' side: Search Console,
 * CrUX field vitals and nginx's crawler log, with the shapes the API answered
 * on 2026-10-09, and the Attention lines they add.
 */
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { attentionLines } from '../Attention'
import { botItem, Crawlers, statusHint } from '../Crawlers'
import { FieldVitals, fmtVital, latest, rating } from '../FieldVitals'
import { changeLine, positionLine, SearchGoogle } from '../SearchGoogle'
import type { CrawlerBot, CrawlersData, FieldVitalsData, SearchData } from '../types'

const ok = <T,>(data: T) => ({ data, error: null })
/** renderToString separates adjacent text with empty comments; read without them. */
const text = (html: string) => html.replace(/<!-- -->/g, '')

const SEARCH: SearchData = {
  days: [
    { day: '2026-10-05', clicks: 40, impressions: 3000, position: 9.1 },
    { day: '2026-10-06', clicks: 57, impressions: 3389, position: 8.6 },
  ],
  current: { start: '2026-09-09', end: '2026-10-06', clicks: 1056, impressions: 76977, ctr: 0.0137, position: 8.93 },
  previous: { start: '2026-08-12', end: '2026-09-08', clicks: 569, impressions: 38371, ctr: 0.0148, position: 21.46 },
  queries: [{ query: 'louis de cordier', clicks: 16, impressions: 504, position: 9.17 }],
  pages: [{ path: '/', clicks: 56, impressions: 900, position: 3 }],
  pages_shown: { current: 4640, previous: 4096 },
}

const VITALS: FieldVitalsData = {
  phone: { weeks: ['2026-09-27', '2026-10-03'], lcp: [2797, 2765], inp: [436, null], cls: [0.04, 0.03] },
  desktop: { weeks: ['2026-09-27', '2026-10-03'], lcp: [1727, 1727], inp: [103, null], cls: [0.07, 0.05] },
}

const GOOGLEBOT: CrawlerBot = {
  bot: 'Googlebot',
  operator: 'google',
  kind: 'search',
  verified: true,
  requests: 1204,
  pages: 980,
  statuses: { '4xx': 31, '2xx': 1173 },
}

describe('search panel helpers', () => {
  it('words a count change against the window before', () => {
    expect(changeLine(1056, 569)).toEqual({ text: '+86 % on the 28 days before', cls: 'dash-delta--up' })
    expect(changeLine(80, 100)).toEqual({ text: '−20 % on the 28 days before', cls: 'dash-delta--down' })
    expect(changeLine(5, 0).cls).toBe('')
  })

  it('reads a smaller position as the better one', () => {
    expect(positionLine(8.93, 21.46)).toEqual({ text: 'was 21.5', cls: 'dash-delta--up' })
    expect(positionLine(12, 9).cls).toBe('dash-delta--down')
  })
})

describe('field vitals helpers', () => {
  it("rates with Google's bands", () => {
    expect(rating('lcp', 2500)).toBe('good')
    expect(rating('lcp', 2765)).toBe('ni')
    expect(rating('inp', 501)).toBe('poor')
    expect(rating('cls', 0.03)).toBe('good')
  })

  it('formats each metric in its own unit', () => {
    expect(fmtVital('lcp', 2765)).toBe('2.8 s')
    expect(fmtVital('inp', 436)).toBe('436 ms')
    expect(fmtVital('cls', 0.03)).toBe('0.03')
  })

  it('takes the newest week that has a number', () => {
    expect(latest([436, null])).toEqual({ value: 436, index: 0 })
    expect(latest([null, null])).toBeNull()
  })
})

describe('crawler panel helpers', () => {
  it('lists pages first, then the status classes in order', () => {
    expect(statusHint(GOOGLEBOT)).toBe('980 pages · 2xx 1,173 · 4xx 31')
  })

  it('marks a bot whose operator publishes no addresses', () => {
    expect(botItem({ ...GOOGLEBOT, bot: 'ClaudeBot', verified: null }).label).toBe('ClaudeBot (unverified)')
    expect(botItem(GOOGLEBOT).label).toBe('Googlebot')
  })
})

describe('the panels with data', () => {
  it('shows the four Search Console tiles and the two rankings', () => {
    const html = text(renderToString(<SearchGoogle state={ok(SEARCH)} />))
    expect(html).toContain('How does Google see us?')
    expect(html).toContain('1,056')
    expect(html).toContain('+86 % on the 28 days before')
    expect(html).toContain('8.9')
    expect(html).toContain('was 21.5')
    expect(html).toContain('louis de cordier')
    expect(html).toContain('href="https://ancientnerds.com/"')
  })

  it('says so when Search Console has nothing', () => {
    const empty: SearchData = { days: [], current: null, previous: null, queries: [], pages: [], pages_shown: null }
    expect(text(renderToString(<SearchGoogle state={ok(empty)} />))).toContain('Search Console has no data')
  })

  it('colours each vital by its band and names the week', () => {
    const html = text(renderToString(<FieldVitals state={ok(VITALS)} />))
    expect(html).toContain('dash-vital--ni">2.8 s')
    expect(html).toContain('dash-vital--good">1.7 s')
    expect(html).toContain('Phone · 28 days to 03 Oct')
  })

  it('counts the crawlers by kind and lists the pages AI read for someone', () => {
    const data: CrawlersData = {
      report: {
        covered_from: '2026-10-09T21:40:00+02:00',
        bots: [GOOGLEBOT, { ...GOOGLEBOT, bot: 'ChatGPT-User', operator: 'openai', kind: 'ai_user', requests: 4, pages: 3 }],
        days: [],
        ai_user_pages: [{ path: '/sites/egypt/giza-1', bot: 'ChatGPT-User', requests: 2 }],
        impostors: [{ bot: 'Googlebot', requests: 7 }],
      },
      log_reason: null,
    }
    const html = text(renderToString(<Crawlers state={ok(data)} />))
    expect(html).toContain('1,204')
    expect(html).toContain('/sites/egypt/giza-1')
    expect(html).toContain('7 claiming to be Googlebot')
    expect(html).toContain('The crawler log starts 09 Oct 19:40 UTC.')
  })

  it('names the missing log instead of drawing empty tiles', () => {
    const html = renderToString(<Crawlers state={ok({ report: null, log_reason: 'no crawlers.log here' })} />)
    expect(html).toContain('no crawlers.log here')
    expect(html).not.toContain('dash-tiles')
  })
})

describe('attentionLines with Google', () => {
  it("leads with Google's clicks and adds every vital below good", () => {
    const lines = attentionLines(null, null, null, SEARCH, VITALS)
    expect(lines[0]).toEqual({
      key: 'google',
      text: 'Google: 1,056 clicks in 28 days, +86 % on the 28 days before, average position 8.9.',
      tone: 'ok',
    })
    expect(lines.map(l => l.key)).toEqual(['google', 'vital:Phone:lcp', 'vital:Phone:inp'])
    expect(lines[2].text).toBe(
      'Phone · Reaction to input 436 ms — Google rates it needs improvement, good is up to 200 ms.'
    )
  })

  it('turns amber when the clicks fell', () => {
    const fell = { ...SEARCH, previous: { ...SEARCH.previous!, clicks: 2000 } }
    expect(attentionLines(null, null, null, fell, null)[0].tone).toBe('warn')
  })
})
