/**
 * The Discord auth token as THIS tab sees it: one place to read it, one to
 * store it, and one announcement for every reader.
 *
 * The token arrives in three ways — AuthProvider promotes the post-OAuth
 * handoff cookie (120 s, set by /api/auth/discord/callback) into localStorage,
 * a page stores one directly, or a logout or an expired token removes it. The
 * browser's own 'storage' event reaches the OTHER tabs only, so a component
 * that reads the token itself (LyraChatModal, HamburgerNav, SocialLinks) never
 * learned about a change made in its own tab.
 *
 * The order matters: AuthProvider writes from its mount effect, which React
 * runs AFTER the effects of the children it renders. A child that subscribed
 * by then still hears the promotion; a child that read the storage once while
 * mounting does not — that was the /lyra.html login bug, where the visitor
 * came back from Discord and the sign-in gate stayed shut.
 */

// The API sets the OAuth handoff cookie under this name (api/routes/auth.py)
// and the components that still read the storage directly use the same
// literal — the key is not ours to rename.
const KEY = 'an_auth_token'

type Listener = (token: string | null) => void

const listeners = new Set<Listener>()

/** localStorage, or null where it cannot be reached. The getter itself throws
 *  in Safari private mode and with blocked cookies. */
function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : (window.localStorage ?? null)
  } catch {
    return null
  }
}

/** The token stored for this tab; null when none is, or when the storage
 *  cannot be reached at all. */
export function getAuthToken(): string | null {
  const store = storage()
  if (!store) return null
  try {
    return store.getItem(KEY)
  } catch {
    return null
  }
}

/** Store the token for this tab and tell every reader. `null` drops it. */
export function storeAuthToken(token: string | null): void {
  const store = storage()
  if (store) {
    try {
      if (token) store.setItem(KEY, token)
      else store.removeItem(KEY)
    } catch {
      // A storage that refuses writes (quota, private mode): the readers below
      // still hear the value, and the page keeps working for this visit. A
      // reader that subscribes only later (a lazy component) hears nothing —
      // deliberately not patched by replaying a remembered value here: a
      // second copy of the token in memory would outlive a logout in another
      // tab, which is the cross-tab bug this module exists to avoid.
    }
  }
  for (const listener of [...listeners]) listener(token)
}

/** Hear about token changes in this tab; the browser fires 'storage' in the
 *  other tabs only. Returns the unsubscribe function. */
export function subscribeAuthToken(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Test hook: forget every subscriber. */
export function _resetAuthTokenForTests(): void {
  listeners.clear()
}
