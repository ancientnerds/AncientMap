import { afterEach, describe, expect, it, vi } from 'vitest'

import { errorProps, newDepthSteps, outboundHost } from '../boot'
import { _queuedForTests, _resetForTests, cleanProps, pageType, searchTerm, track } from '../index'

// vitest runs in node: no DOM, so the tests install a minimal fake `window`.
const g = globalThis as unknown as { window?: unknown }

afterEach(() => {
  _resetForTests()
  delete g.window
  vi.useRealTimers()
})

describe('track', () => {
  it('sends straight to the tracker when it is present', () => {
    const spy = vi.fn()
    g.window = { umami: { track: spy } }
    track('site_open', { site: 'abc', country: 'Peru', context: 'globe' })
    expect(spy).toHaveBeenCalledWith('site_open', { site: 'abc', country: 'Peru', context: 'globe' })
  })

  it('queues until the deferred tracker appears, then flushes in order', () => {
    vi.useFakeTimers()
    g.window = {}
    track('search', { chars: 5, results: 12 })
    track('search_empty', { chars: 9 })
    expect(_queuedForTests()).toBe(2)
    const spy = vi.fn()
    ;(g.window as { umami?: unknown }).umami = { track: spy }
    vi.advanceTimersByTime(600)
    expect(spy.mock.calls.map(c => c[0])).toEqual(['search', 'search_empty'])
    expect(_queuedForTests()).toBe(0)
  })

  it('drops the queue when no tracker shows up (blocked or dev)', () => {
    vi.useFakeTimers()
    g.window = {}
    track('share', { method: 'clipboard' })
    vi.advanceTimersByTime(11_000)
    expect(_queuedForTests()).toBe(0)
  })

  it('is a no-op without a window (SSR)', () => {
    track('js_error', { message: 'x' })
    expect(_queuedForTests()).toBe(0)
  })

  it('never lets a tracker exception escape', () => {
    g.window = {
      umami: {
        track: () => {
          throw new Error('boom')
        },
      },
    }
    expect(() => track('discord_click', { src: 'app' })).not.toThrow()
  })
})

describe('cleanProps', () => {
  it('drops empty values, clips long strings, keeps finite numbers and booleans', () => {
    const cleaned = cleanProps({ a: undefined, b: null, c: 'x'.repeat(150), d: 3.5, e: NaN, f: true })
    expect(cleaned).toEqual({ c: 'x'.repeat(100), d: 3.5, f: true })
    expect(cleanProps(undefined)).toBeUndefined()
  })
})

describe('pageType', () => {
  it.each([
    ['/', 'home'],
    ['/globe.html', 'globe'],
    ['/search.html', 'search'],
    ['/sites/', 'sites'],
    ['/sites/peru', 'country'],
    ['/sites/peru/machu-picchu-1234abcd', 'site'],
    ['/news-archive/', 'stories'],
    ['/news-archive/some-story-8054', 'story'],
    ['/research/', 'papers'],
    ['/research/the-egyptian-hard-stone-precision-debate', 'paper'],
    ['/articles/', 'journals'],
    ['/articles/week-of-september-7', 'journal'],
    ['/whatever', 'other'],
  ])('%s -> %s', (path, expected) => {
    expect(pageType(path)).toBe(expected)
  })
})

describe('boot helpers', () => {
  it('scroll steps fire once each and only when reached', () => {
    const fired = new Set<number>()
    expect(newDepthSteps(0, 800, 4000, fired)).toEqual([]) // 20 % visible
    expect(newDepthSteps(1200, 800, 4000, fired)).toEqual([25, 50]) // 50 %
    expect(newDepthSteps(1200, 800, 4000, fired)).toEqual([]) // no repeat
    expect(newDepthSteps(3200, 800, 4000, fired)).toEqual([75, 100])
    expect(newDepthSteps(0, 800, 600, new Set())).toEqual([25, 50, 75, 100]) // short page
    expect(newDepthSteps(0, 800, 0, new Set())).toEqual([])
  })

  it('error props are short and carry only the file name', () => {
    const props = errorProps('  Uncaught   TypeError: x is not a function ' + 'y'.repeat(200), 'https://ancientnerds.com/assets/App-abc123.js?token=secret')
    expect(props.message.length).toBe(120)
    expect(props.message.startsWith('Uncaught TypeError: x is not a function')).toBe(true)
    expect(props.source).toBe('App-abc123.js')
    expect(errorProps(undefined, undefined)).toEqual({ message: 'error', source: '' })
  })

  it('outbound host ignores own domain, subdomains, relative and non-http links', () => {
    expect(outboundHost('https://en.wikipedia.org/wiki/Giza', 'ancientnerds.com')).toBe('en.wikipedia.org')
    expect(outboundHost('https://www.youtube.com/watch?v=1', 'ancientnerds.com')).toBe('youtube.com')
    expect(outboundHost('https://ancientnerds.com/sites/', 'ancientnerds.com')).toBeNull()
    expect(outboundHost('https://www.ancientnerds.com/', 'ancientnerds.com')).toBeNull()
    expect(outboundHost('/sites/peru', 'ancientnerds.com')).toBeNull()
    expect(outboundHost('mailto:x@y.z', 'ancientnerds.com')).toBeNull()
    expect(outboundHost('javascript:void(0)', 'ancientnerds.com')).toBeNull()
  })
})

describe('searchTerm', () => {
  it('keeps what people look for and drops what identifies them', () => {
    expect(searchTerm('  Göbekli   TEPE ')).toBe('göbekli tepe')
    expect(searchTerm('mail me at max@example.com about giza')).toBe('mail me at about giza')
    expect(searchTerm('phone 015112345678 pyramid 1200 bc')).toBe('phone pyramid 1200 bc')
    expect(searchTerm('x'.repeat(100)).length).toBe(60)
  })
})

