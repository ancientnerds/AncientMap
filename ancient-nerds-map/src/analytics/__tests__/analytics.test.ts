import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  applyTrackingChoice,
  errorProps,
  isForeignError,
  linkClick,
  newDepthSteps,
  outboundHost,
  pageScrollBox,
  TRACKING_OFF_KEY,
  vitalProps,
  youtubeVideoId,
} from '../boot'
import { _queuedForTests, _resetForTests, cleanProps, MAX_VALUE_CHARS, pageType, searchTerm, track } from '../index'

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
    // Clipped to the tracker's own limit, not to a longer one it then cuts again.
    expect(props.message.length).toBe(MAX_VALUE_CHARS)
    expect(props.message.startsWith('TypeError: x is not a function')).toBe(true)
    expect(props.source).toBe('App-abc123.js')
    expect(errorProps(undefined, undefined)).toEqual({ message: 'error', source: '' })
  })

  it('drops the Uncaught prefix so one defect is one row', () => {
    // Chrome writes it, WebKit does not — the same React hydration error filled
    // two rows of the problems panel on 2026-09-17/18.
    const chrome = errorProps('Uncaught Error: Minified React error #418; visit https://x', 'client.js')
    const webkit = errorProps('Error: Minified React error #418; visit https://x', 'client.js')
    expect(chrome.message).toBe(webkit.message)
    expect(chrome.message.startsWith('Error: Minified React error #418')).toBe(true)
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

describe('pageScrollBox', () => {
  it('measures the container a story or site page scrolls, not only the document', () => {
    // .story-page: 100vh tall, 3,681 px scrolled - the window never moved
    const page = { scrollTop: 3681, clientHeight: 844, scrollHeight: 4525 }
    expect(pageScrollBox(page, 844)).toBe(page)
    expect(newDepthSteps(page.scrollTop, page.clientHeight, page.scrollHeight, new Set())).toEqual([25, 50, 75, 100])
  })
  it('ignores a strip inside the page and a missing target', () => {
    expect(pageScrollBox({ scrollTop: 300, clientHeight: 120, scrollHeight: 900 }, 844)).toBeNull()
    expect(pageScrollBox(null, 844)).toBeNull()
  })
})

describe('linkClick', () => {
  it('reports nothing for a link whose handler took the click over', () => {
    // the video poster of a story: a youtube.com link that plays in place
    expect(linkClick('https://www.youtube.com/watch?v=1', true, 'ancientnerds.com')).toBeNull()
    expect(linkClick('/goto/discord?src=story', true, 'ancientnerds.com')).toBeNull()
  })
  it('reports outbound and Discord clicks that navigate', () => {
    expect(linkClick('https://www.youtube.com/watch?v=1', false, 'ancientnerds.com')).toEqual({
      name: 'outbound_click',
      host: 'youtube.com',
    })
    expect(linkClick('/goto/discord?src=landing', false, 'ancientnerds.com')).toEqual({
      name: 'discord_click',
      src: 'landing',
    })
    expect(linkClick('/goto/discord', false, 'ancientnerds.com')).toEqual({ name: 'discord_click', src: 'unknown' })
    expect(linkClick('/sites/peru', false, 'ancientnerds.com')).toBeNull()
  })
  it("names the YouTube video a click goes to, so the creator's channel gets the credit", () => {
    expect(linkClick('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42', false, 'ancientnerds.com')).toEqual({
      name: 'outbound_click',
      host: 'youtube.com',
      media: 'dQw4w9WgXcQ',
    })
    expect(linkClick('https://en.wikipedia.org/wiki/Giza', false, 'ancientnerds.com')).toEqual({
      name: 'outbound_click',
      host: 'en.wikipedia.org',
    })
  })
})

describe('youtubeVideoId', () => {
  it('reads the id from every link form YouTube uses', () => {
    expect(youtubeVideoId('https://www.youtube.com/watch?v=dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ')
    expect(youtubeVideoId('https://m.youtube.com/watch?v=dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ')
    expect(youtubeVideoId('https://youtu.be/dQw4w9WgXcQ?t=10')).toBe('dQw4w9WgXcQ')
    expect(youtubeVideoId('https://www.youtube.com/shorts/dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ')
    expect(youtubeVideoId('https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ')
  })

  it('answers null for a channel page, another host or no URL at all', () => {
    expect(youtubeVideoId('https://www.youtube.com/@AncientArchitects')).toBeNull()
    expect(youtubeVideoId('https://vimeo.com/123')).toBeNull()
    expect(youtubeVideoId('/sites/peru')).toBeNull()
    expect(youtubeVideoId('https://www.youtube.com/watch?v=short')).toBeNull()
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


describe('isForeignError', () => {
  it('drops what an extension injected, by its file or by its stack', () => {
    expect(isForeignError('x is undefined', 'chrome-extension://abc/inpage.js')).toBe(true)
    expect(isForeignError('Failed to connect to MetaMask', undefined, 'Error: Failed\n    at chrome-extension://nkbi/inpage.js:1:1')).toBe(true)
    expect(isForeignError('boom', 'moz-extension://id/content.js')).toBe(true)
  })

  it('drops the ResizeObserver loop notice in both spellings', () => {
    expect(isForeignError('ResizeObserver loop completed with undelivered notifications.')).toBe(true)
    expect(isForeignError('Uncaught ResizeObserver loop limit exceeded')).toBe(true)
  })

  it('keeps our own errors', () => {
    expect(isForeignError("NotFoundError: Failed to execute 'removeChild' on 'Node'", 'https://ancientnerds.com/assets/index-x.js')).toBe(false)
    expect(isForeignError('Load failed', undefined, 'TypeError: Load failed\n    at https://ancientnerds.com/assets/a.js:1:1')).toBe(false)
  })
})

describe('applyTrackingChoice', () => {
  const storage = () => {
    const items = new Map<string, string>()
    return { items, setItem: (k: string, v: string) => void items.set(k, v), removeItem: (k: string) => void items.delete(k) }
  }

  it('keeps this browser out of Umami with ?notrack=1 and drops the parameter', () => {
    const s = storage()
    const out = applyTrackingChoice(new URL('https://ancientnerds.com/news.html?notrack=1&x=2'), s)
    expect(out.choice).toBe('off')
    expect(s.items.get(TRACKING_OFF_KEY)).toBe('1')
    expect(out.url.toString()).toBe('https://ancientnerds.com/news.html?x=2')
  })

  it('counts it again with ?notrack=0', () => {
    const s = storage()
    s.setItem(TRACKING_OFF_KEY, '1')
    expect(applyTrackingChoice(new URL('https://ancientnerds.com/news.html?notrack=0'), s).choice).toBe('on')
    expect(s.items.has(TRACKING_OFF_KEY)).toBe(false)
  })

  it('does nothing without the parameter or with another value', () => {
    const s = storage()
    expect(applyTrackingChoice(new URL('https://ancientnerds.com/news.html'), s).choice).toBeNull()
    expect(applyTrackingChoice(new URL('https://ancientnerds.com/news.html?notrack=yes'), s).choice).toBeNull()
    expect(s.items.size).toBe(0)
  })
})

describe('vitalProps', () => {
  type Metric = Parameters<typeof vitalProps>[0]
  const inp = (value: number, rating: string, attribution: object) =>
    ({ name: 'INP', value, rating, attribution }) as unknown as Metric

  it('keeps a good vital to its four fields', () => {
    const good = inp(80, 'good', { inputDelay: 5, processingDuration: 40, presentationDelay: 35, loadState: 'complete' })
    expect(vitalProps(good, 'globe')).toEqual({ name: 'INP', value: 80, rating: 'good', page: 'globe' })
  })

  it('says where a slow interaction went: its element, its longest phase, the input', () => {
    const slow = inp(1908.4, 'poor', {
      inputDelay: 40,
      processingDuration: 120,
      presentationDelay: 1748,
      interactionTarget: 'canvas',
      interactionType: 'pointer',
      loadState: 'complete',
    })
    expect(vitalProps(slow, 'globe')).toEqual({
      name: 'INP', value: 1908, rating: 'poor', page: 'globe',
      phase: 'presentation', target: 'canvas', input: 'pointer', load: 'complete',
    })
  })

  it('names the slow part of a slow LCP', () => {
    const lcp = {
      name: 'LCP', value: 5620, rating: 'poor',
      attribution: { timeToFirstByte: 300, resourceLoadDelay: 2900, resourceLoadDuration: 900, elementRenderDelay: 1520, target: 'img.lyra-discovery-image' },
    } as unknown as Metric
    expect(vitalProps(lcp, 'radar')).toMatchObject({ phase: 'load_delay', target: 'img.lyra-discovery-image' })
  })

  it('rounds CLS to three places and adds nothing to it', () => {
    const cls = { name: 'CLS', value: 0.28149, rating: 'poor', attribution: {} } as unknown as Metric
    expect(vitalProps(cls, 'radar')).toEqual({ name: 'CLS', value: 0.281, rating: 'poor', page: 'radar' })
  })
})
