/**
 * The Lyra login funnel — the three events around the Discord OAuth handoff.
 *
 * The click leaves the page for Discord and comes back through
 * /api/auth/discord/callback, so nothing held in memory survives the trip:
 * the click writes a marker into sessionStorage (which does survive the
 * redirect in the same tab) and the two return legs consume it. Success is
 * the return leg where the token just came out of the handoff cookie and the
 * server confirmed it (AuthContext), aborted is the callback's own redirect
 * to /account.html?error=<reason> — every refusal on the way (access_denied,
 * invalid_state, not_in_guild, …) ends there, never back on the page that
 * started the login.
 *
 * The marker is single-use — take/clear so a reload or StrictMode's second
 * mount cannot count the same login twice — and older than 15 minutes it is
 * dropped: a login that comes back that late is another visit.
 */

import { pageType, track } from './index'

const KEY = 'an_login_pending'
const MAX_AGE_MS = 15 * 60 * 1000
/** A timestamp from the future is a broken clock, not a fresh marker. The
 *  tolerance absorbs the milliseconds between two machines' clocks. */
const CLOCK_SKEW_MS = 60 * 1000

/** Every reason the OAuth callback redirects with (api/routes/auth.py). The
 *  event vocabulary is fixed like the event names: a crafted link or a reason
 *  added later is folded to 'unknown' instead of inventing a new value. */
const ABORT_REASONS = new Set([
  'rate_limited',
  'access_denied',
  'missing_params',
  'invalid_state',
  'not_configured',
  'token_exchange_failed',
  'no_access_token',
  'user_fetch_failed',
  'not_in_guild',
  'server_error',
])

interface LoginPending {
  src: string
}

/** sessionStorage, or null where it cannot be reached. The getter itself
 *  throws in Safari private mode and with blocked cookies, which is a
 *  property of the browser, not an error of ours: the funnel goes silent. */
function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : (window.sessionStorage ?? null)
  } catch {
    return null
  }
}

/** The stored marker, or null when it is absent, unreadable or expired. An
 *  entry that no longer counts is removed while we are looking at it. */
function readMarker(): LoginPending | null {
  const store = storage()
  if (!store) return null
  try {
    const raw = store.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { src?: unknown; at?: unknown }
    const age = typeof parsed.at === 'number' ? Date.now() - parsed.at : Number.NaN
    if (typeof parsed.src !== 'string' || Number.isNaN(age) || age > MAX_AGE_MS || age < -CLOCK_SKEW_MS) {
      store.removeItem(KEY)
      return null
    }
    return { src: parsed.src }
  } catch {
    return null
  }
}

/** Remember that a login left this tab, and from where. */
export function setLoginPending(src: string): void {
  const store = storage()
  if (!store) return
  try {
    store.setItem(KEY, JSON.stringify({ src, at: Date.now() }))
  } catch {
    // Quota or a storage that refuses writes: this one login stays uncounted.
  }
}

/** Read the marker without consuming it — for a caller that only clears it
 *  once its event has gone out. */
export function peekLoginPending(): LoginPending | null {
  return readMarker()
}

/** Read and consume the marker: the second caller gets null. */
export function takeLoginPending(): LoginPending | null {
  const pending = readMarker()
  clearLoginPending()
  return pending
}

export function clearLoginPending(): void {
  const store = storage()
  if (!store) return
  try {
    store.removeItem(KEY)
  } catch {
    // See setLoginPending — nothing to do about a storage that forbids this.
  }
}

/** The Lyra gate's "Continue with Discord": the click event and the marker
 *  that arms the two return legs. Runs before the redirect (sessionStorage
 *  survives it, component state would not). */
export function lyraLoginClick(pathname: string, context: string): void {
  track('lyra_login_click', { page: pageType(pathname), context })
  setLoginPending('lyra')
}

/** Called with the outcome of the post-redirect token check, and only when
 *  the token was just promoted from the handoff cookie — a token that was
 *  already stored is an ordinary page load, not a return leg. Only a token
 *  the server confirmed counts — a dead or expired one leaves the marker to
 *  its expiry instead of reporting a login that did not happen. Taking the
 *  marker is also what keeps this to one event per login. */
export function reportLyraLoginSuccess(validated: boolean): void {
  if (!validated) return
  const pending = takeLoginPending()
  if (pending?.src === 'lyra') {
    track('lyra_login_success', { src: 'lyra' })
  }
}

/** The callback refused and sent the visitor to /account.html?error=<reason>:
 *  the funnel's dead end, with the reason as the URL spells it. Only the
 *  reasons the callback itself redirects with are reported; anything else is
 *  'unknown'. */
export function reportLyraLoginAborted(reason: string): void {
  const pending = peekLoginPending()
  if (pending?.src !== 'lyra') return
  track('lyra_login_aborted', { src: 'lyra', reason: ABORT_REASONS.has(reason) ? reason : 'unknown' })
  clearLoginPending()
}
