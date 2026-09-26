/**
 * Page-level signals that need no component: Core Web Vitals, uncaught
 * errors, scroll depth on content pages, outbound clicks. Imported once by
 * every entry (`*Main.tsx`); idempotent, and a no-op during SSR.
 *
 * These are the "why did they leave" proxies the interaction events cannot
 * give: a slow LCP or an exception on the page is measurable, a change of
 * mind is not.
 *
 * One thing here is not a signal: boot is the module every entry runs before
 * React mounts, so it also keeps page translation from blanking the page
 * (utils/translatedDom.ts) - the cause of every removeChild js_error so far.
 */

import { onCLS, onINP, onLCP, onTTFB, type MetricWithAttribution } from 'web-vitals/attribution'

import { tolerateDetachedNodes } from '../utils/translatedDom'
import { MAX_VALUE_CHARS, pageType, track } from './index'

const SCROLL_STEPS = [25, 50, 75, 100] as const
const CONTENT_PAGES = new Set(['story', 'site', 'paper', 'journal', 'country'])
const MAX_ERRORS_PER_PAGE = 3

/** Depth steps newly reached for a scroll position; pure for tests. */
export function newDepthSteps(
  scrollTop: number,
  viewport: number,
  docHeight: number,
  fired: Set<number>
): number[] {
  if (docHeight <= 0) return []
  const seen = Math.min(100, Math.round(((scrollTop + viewport) / docHeight) * 100))
  const reached: number[] = []
  for (const step of SCROLL_STEPS) {
    if (seen >= step && !fired.has(step)) {
      fired.add(step)
      reached.push(step)
    }
  }
  return reached
}

/** Message + file for a js_error event: short, no query strings, no tokens.
 *
 *  The "Uncaught " prefix goes: Chrome puts it in front of every window error,
 *  WebKit does not, so one React hydration bug filled two rows of the problems
 *  panel — "Uncaught Error: Minified React error #418" from a laptop and
 *  "Error: Minified React error #418" from an iPhone (2026-09-17/18). */
export function errorProps(message: unknown, source?: string): { message: string; source: string } {
  const text = String(message ?? 'error').replace(/\s+/g, ' ').trim().replace(/^Uncaught /, '')
  const file = (source ?? '').split('?')[0].split('/').pop() ?? ''
  return { message: text.slice(0, MAX_VALUE_CHARS), source: file.slice(0, 60) }
}

/** Host of an outbound link, or null when the link stays on this site. */
export function outboundHost(href: string, ownHost: string): string | null {
  let url: URL
  try {
    url = new URL(href, `https://${ownHost}`)
  } catch {
    return null
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
  const host = url.hostname.replace(/^www\./, '')
  const own = ownHost.replace(/^www\./, '')
  return host === own || host.endsWith(`.${own}`) ? null : host
}

/** The part of a time span that took longest, by name. */
function longest(parts: Record<string, number>): string {
  return Object.entries(parts).reduce((a, b) => (b[1] > a[1] ? b : a))[0]
}

/** A vital as event props. An INP or LCP that is not good also says where it
 *  went: the element (`target`, a CSS selector) and the phase that took
 *  longest, so the dashboard can tell a slow handler from a slow frame. On
 *  2026-09-26 the globe's INP p75 on computers was 1.9 s and nothing could
 *  say which interaction; 5 of 19 samples, all of them with the background
 *  queue at work, could only be matched by time. */
export function vitalProps(metric: MetricWithAttribution, page: string): Record<string, string | number> {
  const value = metric.name === 'CLS' ? Math.round(metric.value * 1000) / 1000 : Math.round(metric.value)
  const props: Record<string, string | number> = { name: metric.name, value, rating: metric.rating, page }
  if (metric.rating === 'good') return props
  if (metric.name === 'INP') {
    const a = metric.attribution
    props.phase = longest({ input: a.inputDelay, processing: a.processingDuration, presentation: a.presentationDelay })
    if (a.interactionTarget) props.target = a.interactionTarget
    if (a.interactionType) props.input = a.interactionType
    props.load = a.loadState
  } else if (metric.name === 'LCP') {
    const a = metric.attribution
    props.phase = longest({
      ttfb: a.timeToFirstByte,
      load_delay: a.resourceLoadDelay,
      load: a.resourceLoadDuration,
      render: a.elementRenderDelay,
    })
    if (a.target) props.target = a.target
  }
  return props
}

function reportVital(metric: MetricWithAttribution): void {
  track('vital', vitalProps(metric, pageType(location.pathname)))
}

const EXTENSION_URL = /(chrome|moz|safari|safari-web|ms-browser)-extension:\/\//

/** An error that is not ours to fix, so no js_error: code a browser extension
 *  injected into the page (its file or its stack is an extension URL - live
 *  2026-09-25: "Failed to connect to MetaMask" on two pages of one session),
 *  and the ResizeObserver loop notice, which browsers raise when an observer's
 *  callback changes layout and which by the spec only delays the notification
 *  (six sessions on site pages, 2026-09-18..25, nothing broken). */
export function isForeignError(message: unknown, filename?: string, stack?: string): boolean {
  if (EXTENSION_URL.test(filename ?? '') || EXTENSION_URL.test(stack ?? '')) return true
  return /^(Uncaught )?ResizeObserver loop/.test(String(message ?? ''))
}

function installErrorCapture(page: string): void {
  let sent = 0
  window.addEventListener('error', event => {
    const stack = event.error instanceof Error ? event.error.stack : undefined
    if (isForeignError(event.message, event.filename, stack)) return
    if (sent++ >= MAX_ERRORS_PER_PAGE) return
    track('js_error', { ...errorProps(event.message, event.filename), page })
  })
  window.addEventListener('unhandledrejection', event => {
    const reason = event.reason
    const message = reason instanceof Error ? reason.message : reason
    if (isForeignError(message, undefined, reason instanceof Error ? reason.stack : undefined)) return
    if (sent++ >= MAX_ERRORS_PER_PAGE) return
    track('js_error', { ...errorProps(message, 'promise'), page })
  })
}

function installScrollDepth(page: string): void {
  if (!CONTENT_PAGES.has(page)) return
  const fired = new Set<number>()
  let ticking = false
  const measure = () => {
    ticking = false
    const doc = document.documentElement
    const reached = newDepthSteps(window.scrollY, window.innerHeight, doc.scrollHeight, fired)
    for (const depth of reached) track('scroll_depth', { depth, page })
  }
  // Only on a real scroll. Measuring at load counted a short page as "read
  // to the end" and gave every headless fetch four depth events at once
  // (SG/VN scraper bursts, 2026-09-17); a scroll is the visitor's own act.
  window.addEventListener(
    'scroll',
    () => {
      if (ticking) return
      ticking = true
      requestAnimationFrame(measure)
    },
    { passive: true }
  )
}

function installOutboundClicks(page: string): void {
  document.addEventListener('click', event => {
    const anchor = (event.target as Element | null)?.closest?.('a[href]')
    if (!anchor) return
    const href = anchor.getAttribute('href') ?? ''
    if (href.startsWith('/goto/discord')) {
      // The funnel redirect logs the click server-side as well; this one
      // puts it into the visitor's journey.
      track('discord_click', { src: new URLSearchParams(href.split('?')[1] ?? '').get('src') ?? 'unknown', page })
      return
    }
    const host = outboundHost(href, location.hostname)
    if (host) track('outbound_click', { host, page })
  })
}

/** The key the Umami tracker reads before every send (/pulse.js): set, and
 *  this browser sends nothing, page views and events alike. */
export const TRACKING_OFF_KEY = 'umami.disabled'

/** `?notrack=1` keeps this browser out of the numbers from now on,
 *  `?notrack=0` counts it again; the founders dashboard links both. On
 *  2026-09-25 the most opened site of the week, 24 opens, was six sessions of
 *  one German laptop - us looking at our own pages. Returns what it did, and
 *  the URL without the parameter. */
export function applyTrackingChoice(url: URL, storage: Pick<Storage, 'setItem' | 'removeItem'>): {
  choice: 'off' | 'on' | null
  url: URL
} {
  const value = url.searchParams.get('notrack')
  if (value !== '1' && value !== '0') return { choice: null, url }
  if (value === '1') storage.setItem(TRACKING_OFF_KEY, '1')
  else storage.removeItem(TRACKING_OFF_KEY)
  const clean = new URL(url)
  clean.searchParams.delete('notrack')
  return { choice: value === '1' ? 'off' : 'on', url: clean }
}

declare global {
  interface Window {
    __anAnalyticsBooted?: boolean
  }
}

export function bootAnalytics(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return
  if (window.__anAnalyticsBooted) return
  window.__anAnalyticsBooted = true
  tolerateDetachedNodes(Node.prototype)
  // Before the tracker's first send: module scripts run ahead of the deferred
  // /pulse.js, which the build appends at the end of <head>. localStorage is
  // touched only when the parameter is there - where storage is blocked, the
  // getter itself throws, and boot has to run for every other visitor.
  if (location.search.includes('notrack=')) {
    const { choice, url } = applyTrackingChoice(new URL(location.href), localStorage)
    if (choice) history.replaceState(history.state, '', url)
  }
  const page = pageType(location.pathname)
  onLCP(reportVital)
  onCLS(reportVital)
  onINP(reportVital)
  onTTFB(reportVital)
  installErrorCapture(page)
  installScrollDepth(page)
  installOutboundClicks(page)
}

bootAnalytics()
