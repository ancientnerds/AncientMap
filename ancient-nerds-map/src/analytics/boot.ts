/**
 * Page-level signals that need no component: Core Web Vitals, uncaught
 * errors, scroll depth on content pages, outbound clicks. Imported once by
 * every entry (`*Main.tsx`); idempotent, and a no-op during SSR.
 *
 * These are the "why did they leave" proxies the interaction events cannot
 * give: a slow LCP or an exception on the page is measurable, a change of
 * mind is not.
 */

import { onCLS, onINP, onLCP, onTTFB, type Metric } from 'web-vitals'

import { pageType, track } from './index'

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

/** Message + file for a js_error event: short, no query strings, no tokens. */
export function errorProps(message: unknown, source?: string): { message: string; source: string } {
  const text = String(message ?? 'error').replace(/\s+/g, ' ').trim()
  const file = (source ?? '').split('?')[0].split('/').pop() ?? ''
  return { message: text.slice(0, 120), source: file.slice(0, 60) }
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

function reportVital(metric: Metric): void {
  const value = metric.name === 'CLS' ? Math.round(metric.value * 1000) / 1000 : Math.round(metric.value)
  track('vital', { name: metric.name, value, rating: metric.rating, page: pageType(location.pathname) })
}

function installErrorCapture(page: string): void {
  let sent = 0
  window.addEventListener('error', event => {
    if (sent++ >= MAX_ERRORS_PER_PAGE) return
    track('js_error', { ...errorProps(event.message, event.filename), page })
  })
  window.addEventListener('unhandledrejection', event => {
    if (sent++ >= MAX_ERRORS_PER_PAGE) return
    const reason = event.reason
    const message = reason instanceof Error ? reason.message : reason
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
  window.addEventListener(
    'scroll',
    () => {
      if (ticking) return
      ticking = true
      requestAnimationFrame(measure)
    },
    { passive: true }
  )
  // A short page can already be fully visible: count that too.
  measure()
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

declare global {
  interface Window {
    __anAnalyticsBooted?: boolean
  }
}

export function bootAnalytics(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return
  if (window.__anAnalyticsBooted) return
  window.__anAnalyticsBooted = true
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
