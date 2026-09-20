import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { LiveNow, fmtSpan, pageUrl, secondsSince } from '../LiveNow'
import type { LiveData, LiveVisitor } from '../types'
import type { Loaded } from '../useStats'

describe('LiveNow fmtSpan', () => {
  it('never claims a whole minute it does not have', () => {
    expect(fmtSpan(0)).toBe('< 1 min')
    expect(fmtSpan(30)).toBe('< 1 min')
    expect(fmtSpan(59)).toBe('< 1 min')
  })

  it('reads minutes below the hour', () => {
    expect(fmtSpan(60)).toBe('1 min')
    expect(fmtSpan(360)).toBe('6 min')
  })

  it('splits hours from minutes and keeps the zero minute', () => {
    expect(fmtSpan(7860)).toBe('2 h 11 min')
    // A round hour must still say "min", or the row reads as a different unit
    // from the one above it.
    expect(fmtSpan(3600)).toBe('1 h 0 min')
  })
})

describe('LiveNow secondsSince', () => {
  it('measures whole seconds against the clock it is given', () => {
    expect(secondsSince('2026-09-19T07:30:00Z', Date.parse('2026-09-19T08:07:00Z'))).toBe(2220)
  })

  it('clamps a stamp from the future to zero', () => {
    // last_seen comes from the database's clock, not the browser's, so a
    // reader whose machine is a few seconds slow must not see "-4 s ago".
    expect(secondsSince('2026-09-19T08:07:00Z', Date.parse('2026-09-19T07:30:00Z'))).toBe(0)
  })
})

describe('LiveNow pageUrl', () => {
  it('lands on the main host, never on the host the dashboard is served from', () => {
    expect(pageUrl('/sites/x')).toBe('https://ancientnerds.com/sites/x')
  })

  it('repairs a path that arrived without its leading slash', () => {
    // Without the repair this reads "ancientnerds.comsites/x" - a different host.
    expect(pageUrl('sites/x')).toBe('https://ancientnerds.com/sites/x')
  })

  it('falls back to the home page when the row carries no path', () => {
    expect(pageUrl('')).toBe('https://ancientnerds.com/')
  })
})

const visitor = (over: Partial<LiveVisitor> = {}): LiveVisitor => ({
  session: 'abc12345',
  country: 'SE',
  device: 'mobile',
  browser: 'chrome',
  page: 'site',
  title: 'Temple of Diana',
  path: '/sites/temple-of-diana',
  here: 30,
  last_seen: '2026-09-20T09:00:00Z',
  ...over,
})

const live = (over: Partial<LiveData> = {}): Loaded<LiveData> => ({
  data: {
    window_minutes: 30,
    lookback_hours: 24,
    total: 1,
    shown: 1,
    visitors: [visitor()],
    last: null,
    ...over,
  },
  error: null,
})

describe('LiveNow row', () => {
  it('links the page title to what the visitor has open, in a new tab', () => {
    const html = renderToString(<LiveNow state={live()} />)
    expect(html).toContain('href="https://ancientnerds.com/sites/temple-of-diana"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it('prints the title inside the link, not beside it', () => {
    const html = renderToString(<LiveNow state={live()} />)
    expect(html).toMatch(/<a [^>]*>Temple of Diana<\/a>/)
  })

  it('keeps the title readable when no path came along', () => {
    const html = renderToString(<LiveNow state={live({ visitors: [visitor({ path: '' })] })} />)
    expect(html).toContain('href="https://ancientnerds.com/"')
    expect(html).toContain('Temple of Diana')
  })
})
