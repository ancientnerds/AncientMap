/**
 * Umami custom events — one helper, one event taxonomy for the whole site.
 *
 * The tracker (/pulse.js, injected by vite.config.ts `analyticsTag` when the
 * deploy names a website id) exposes `window.umami.track`. This module is the
 * only place that talks to it: every interaction calls `track(name, props)`
 * with a name from `EventName`, so the dashboard vocabulary stays fixed and
 * a typo is a compile error, not a silent new event.
 *
 * Cookieless by design (privacy.html §2a): props carry what the interaction
 * is about — a site id, a country, a result count — never who did it. Values
 * are clipped to 100 characters. Without the tracker (dev, blockers, DNT)
 * `track` is a no-op; events raised before the deferred script has loaded
 * wait in a small queue for up to ten seconds, then are dropped.
 */

export type EventName =
  | 'site_open' // site popup / detail shown — site, country, context
  | 'search' // query executed — chars, results, context
  | 'search_empty' // query with zero results — chars, context
  | 'filter_toggle' // data-source or facet toggled — filter, on
  | 'hub_click' // country hub / chip — country (static landing uses data-umami-event)
  | 'story_open' // story opened from a list — story, context
  | 'paper_open' // research paper opened — paper, context
  | 'media_play' // webcam, video, 3D model, street view, gallery — kind, site
  | 'lyra_chat' // first message of a Lyra chat — page
  | 'lyra_login_click' // Discord button of the Lyra sign-in gate — page, context
  | 'lyra_login_success' // Lyra login came back with a token the server confirmed — src
  | 'lyra_login_aborted' // Lyra login failed in the OAuth callback instead — src, reason
  | 'share' // share button — method, site
  | 'discord_click' // Discord CTA — src (server counts it too via /goto)
  | 'globe_ready' // globe interactive — ms since navigation start
  | 'globe_idle' // globe ready, no site/search/filter within 30 s — ms
  | 'webgl_lost' // globe's WebGL context died — reason, phase
  | 'globe_focus' // #focus= deep link resolved — site
  | 'vital' // Core Web Vital sample — name, value, rating, page
  | 'js_error' // uncaught error / rejection — message, source, page
  | 'scroll_depth' // 25/50/75/100 % of a content page — depth, page
  | 'outbound_click' // link to another host — host, page
  | 'feedback' // micro-feedback at a dead end — prompt, answer, text (≤ 100 chars), page
  | 'not_found' // a 404 page was shown — path, referrer host (raised by the server-rendered page, pipeline/article_html_renderer.py)

export type EventProps = Record<string, string | number | boolean | null | undefined>

interface Umami {
  track: (name: string, data?: Record<string, string | number | boolean>) => unknown
}

declare global {
  interface Window {
    umami?: Umami
  }
}

/** Every event value is clipped to this — exported so nothing clips twice to
 *  a different length (boot.ts used to promise 120 characters of an error
 *  message and hand over 100, cutting the reason off a ServiceWorker error). */
export const MAX_VALUE_CHARS = 100
const QUEUE_LIMIT = 50
const QUEUE_TTL_MS = 10_000
const POLL_MS = 500

const queue: Array<[EventName, EventProps | undefined]> = []
let pollHandle: ReturnType<typeof setTimeout> | null = null
let queuedSince = 0

function tracker(): Umami | undefined {
  if (typeof window === 'undefined') return undefined
  const u = window.umami
  return u && typeof u.track === 'function' ? u : undefined
}

/** Drop undefined/null, clip strings, keep numbers finite. */
export function cleanProps(props?: EventProps): Record<string, string | number | boolean> | undefined {
  if (!props) return undefined
  const out: Record<string, string | number | boolean> = {}
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null) continue
    if (typeof value === 'number') {
      if (Number.isFinite(value)) out[key] = value
      continue
    }
    if (typeof value === 'boolean') {
      out[key] = value
      continue
    }
    const text = String(value)
    out[key] = text.length > MAX_VALUE_CHARS ? text.slice(0, MAX_VALUE_CHARS) : text
  }
  return out
}

function send(u: Umami, name: EventName, props?: EventProps): void {
  try {
    u.track(name, cleanProps(props))
  } catch {
    // The tracker is third-party code; an exception there must never reach the UI.
  }
}

function flush(): void {
  const u = tracker()
  if (!u) return
  while (queue.length) {
    const [name, props] = queue.shift()!
    send(u, name, props)
  }
}

function poll(): void {
  pollHandle = null
  if (tracker()) {
    flush()
    return
  }
  if (Date.now() - queuedSince > QUEUE_TTL_MS) {
    queue.length = 0 // blocked or absent tracker: nothing to wait for
    return
  }
  pollHandle = setTimeout(poll, POLL_MS)
}

/** Record one interaction. Safe to call anywhere, including before the tracker loaded. */
export function track(name: EventName, props?: EventProps): void {
  const u = tracker()
  if (u) {
    send(u, name, props)
    return
  }
  if (typeof window === 'undefined') return
  if (queue.length >= QUEUE_LIMIT) return
  if (queue.length === 0) queuedSince = Date.now()
  queue.push([name, props])
  if (!pollHandle) pollHandle = setTimeout(poll, POLL_MS)
}

/** A search term as the `search` event carries it: lower-case, whitespace
 * collapsed, 60 characters, with e-mail addresses and digit runs of six or
 * more (phone numbers, ids) removed — years like "1200 bc" stay. What people
 * look for, never who they are (privacy §2a, owner's decision 2026-09-17). */
export function searchTerm(query: string): string {
  return query
    .toLowerCase()
    .replace(/[\w.+-]+@[\w-]+\.[\w.-]+/g, ' ')
    .replace(/\d{6,}/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 60)
}

/** Page type from the path — the `page`/`context` value events carry. */
export function pageType(pathname: string): string {
  if (pathname === '/' || pathname === '/index.html') return 'home'
  const m = /^\/([a-z0-9-]+)\.html$/.exec(pathname)
  if (m) return m[1]
  if (pathname === '/sites' || pathname === '/sites/') return 'sites'
  if (pathname.startsWith('/sites/')) return pathname.split('/').filter(Boolean).length >= 3 ? 'site' : 'country'
  if (pathname.startsWith('/news-archive/')) return pathname === '/news-archive/' ? 'stories' : 'story'
  if (pathname.startsWith('/research/')) return pathname === '/research/' ? 'papers' : 'paper'
  if (pathname.startsWith('/articles/')) return pathname === '/articles/' ? 'journals' : 'journal'
  return 'other'
}

/** Test hook: forget queued events and stop polling. */
export function _resetForTests(): void {
  queue.length = 0
  if (pollHandle) clearTimeout(pollHandle)
  pollHandle = null
  queuedSince = 0
}

/** Test hook: how many events are waiting for the tracker. */
export function _queuedForTests(): number {
  return queue.length
}
