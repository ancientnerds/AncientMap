/**
 * The Lyra login funnel: click, success and abort of a login that leaves for
 * Discord and comes back through /api/auth/discord/callback.
 *
 * vitest runs in node: no DOM, so the tests install a minimal fake `window`
 * with the sessionStorage the marker is written into.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { _resetForTests } from '../index'
import {
  clearLoginPending,
  lyraLoginClick,
  peekLoginPending,
  reportLyraLoginAborted,
  reportLyraLoginSuccess,
  setLoginPending,
  takeLoginPending,
} from '../loginFunnel'

const g = globalThis as unknown as { window?: unknown }

function fakeSessionStorage(): Storage {
  const entries = new Map<string, string>()
  return {
    get length() {
      return entries.size
    },
    clear: () => entries.clear(),
    getItem: key => entries.get(key) ?? null,
    key: index => [...entries.keys()][index] ?? null,
    removeItem: key => {
      entries.delete(key)
    },
    setItem: (key, value) => {
      entries.set(key, value)
    },
  }
}

/** A storage that refuses everything the way Safari private mode does. */
function blockedSessionStorage(): Storage {
  const blocked = (): never => {
    throw new Error('SecurityError: the operation is insecure')
  }
  return {
    get length() {
      return blocked()
    },
    clear: blocked,
    getItem: blocked,
    key: blocked,
    removeItem: blocked,
    setItem: blocked,
  }
}

type Tracker = (name: string, data?: Record<string, string | number | boolean>) => unknown

function install(spy: Tracker, store: Storage | null = fakeSessionStorage()): Storage | null {
  g.window = { umami: { track: spy }, sessionStorage: store }
  return store
}

afterEach(() => {
  _resetForTests()
  delete g.window
  vi.useRealTimers()
})

describe('lyra_login_click', () => {
  it('carries page and context, and arms the marker for the return leg', () => {
    const spy = vi.fn()
    install(spy)

    lyraLoginClick('/lyra.html', 'global')

    expect(spy).toHaveBeenCalledWith('lyra_login_click', { page: 'lyra', context: 'global' })
    expect(peekLoginPending()).toEqual({ src: 'lyra' })
  })

  it('names the site page it was clicked on', () => {
    const spy = vi.fn()
    install(spy)

    lyraLoginClick('/sites/peru/machu-picchu-1234abcd', 'site')

    expect(spy).toHaveBeenCalledWith('lyra_login_click', { page: 'site', context: 'site' })
  })

  it('still sends the click event when the marker cannot be written', () => {
    const spy = vi.fn()
    install(spy, blockedSessionStorage())

    expect(() => lyraLoginClick('/lyra.html', 'global')).not.toThrow()

    expect(spy).toHaveBeenCalledWith('lyra_login_click', { page: 'lyra', context: 'global' })
    expect(peekLoginPending()).toBeNull()
  })
})

describe('login marker', () => {
  it('is read once and gone on the second read', () => {
    install(vi.fn())
    setLoginPending('lyra')

    expect(takeLoginPending()).toEqual({ src: 'lyra' })
    expect(takeLoginPending()).toBeNull()
  })

  it('peeks without consuming, clear drops it', () => {
    install(vi.fn())
    setLoginPending('lyra')

    expect(peekLoginPending()).toEqual({ src: 'lyra' })
    expect(peekLoginPending()).toEqual({ src: 'lyra' })
    clearLoginPending()
    expect(takeLoginPending()).toBeNull()
  })

  it('keeps a marker from a minute ago and drops one older than 15 minutes', () => {
    vi.useFakeTimers()
    const store = install(vi.fn())
    setLoginPending('lyra')
    vi.advanceTimersByTime(14 * 60 * 1000)
    expect(takeLoginPending()).toEqual({ src: 'lyra' })

    setLoginPending('lyra')
    vi.advanceTimersByTime(16 * 60 * 1000)
    expect(peekLoginPending()).toBeNull()
    // Expired means removed, not hidden: the raw storage must be empty too, so
    // no later read can resurrect it.
    expect(store!.getItem('an_login_pending')).toBeNull()
    expect(takeLoginPending()).toBeNull()
  })

  it('drops a marker whose timestamp lies in the future', () => {
    vi.useFakeTimers()
    const store = install(vi.fn())
    // A clock that was set back leaves a timestamp ahead of now; its age stays
    // negative and would never reach the 15-minute limit.
    store!.setItem('an_login_pending', JSON.stringify({ src: 'lyra', at: Date.now() + 5 * 60 * 1000 }))

    expect(peekLoginPending()).toBeNull()
    expect(store!.getItem('an_login_pending')).toBeNull()
  })

  it('stays silent with a sessionStorage that throws (Safari private mode)', () => {
    install(vi.fn(), blockedSessionStorage())

    expect(() => setLoginPending('lyra')).not.toThrow()
    expect(peekLoginPending()).toBeNull()
    expect(takeLoginPending()).toBeNull()
    expect(() => clearLoginPending()).not.toThrow()
  })

  it('throws nowhere and reads null with an unreachable storage (no window)', () => {
    // Not a guard test: a storage that cannot be reached and no window at all
    // end in the same branch, and both only promise "no throw, read null".
    install(vi.fn(), null)
    expect(peekLoginPending()).toBeNull()

    delete g.window
    expect(() => setLoginPending('lyra')).not.toThrow()
    expect(takeLoginPending()).toBeNull()
  })
})

describe('lyra_login_success', () => {
  it('fires once, and only for a token the server confirmed', () => {
    const spy = vi.fn()
    install(spy)
    setLoginPending('lyra')

    reportLyraLoginSuccess(false) // /auth/me refused it — no login happened
    expect(spy).not.toHaveBeenCalled()
    expect(peekLoginPending()).toEqual({ src: 'lyra' }) // the dead token leaves the marker alone

    reportLyraLoginSuccess(true)
    expect(spy).toHaveBeenCalledWith('lyra_login_success', { src: 'lyra' })

    reportLyraLoginSuccess(true) // React StrictMode mounts the provider twice
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('does not count a login that started somewhere else', () => {
    const spy = vi.fn()
    install(spy)
    setLoginPending('account')

    reportLyraLoginSuccess(true)

    expect(spy).not.toHaveBeenCalled()
  })

  it('does not count without a marker', () => {
    const spy = vi.fn()
    install(spy)

    reportLyraLoginSuccess(true)

    expect(spy).not.toHaveBeenCalled()
  })
})

describe('lyra_login_aborted', () => {
  it('sends the reason from the URL and consumes the marker', () => {
    const spy = vi.fn()
    install(spy)
    setLoginPending('lyra')

    reportLyraLoginAborted('not_in_guild')

    expect(spy).toHaveBeenCalledWith('lyra_login_aborted', { src: 'lyra', reason: 'not_in_guild' })
    expect(peekLoginPending()).toBeNull()

    reportLyraLoginAborted('not_in_guild') // StrictMode mounts AccountPage twice
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('stays quiet on an ordinary visit to /account.html?error=', () => {
    const spy = vi.fn()
    install(spy)

    reportLyraLoginAborted('invalid_state')

    expect(spy).not.toHaveBeenCalled()
  })

  it('does not count an abort for a login that started somewhere else', () => {
    const spy = vi.fn()
    install(spy)
    setLoginPending('account')

    reportLyraLoginAborted('not_in_guild')

    expect(spy).not.toHaveBeenCalled()
    expect(peekLoginPending()).toEqual({ src: 'account' }) // the marker is not ours to drop
  })

  it('folds a reason the callback never sends into "unknown"', () => {
    const spy = vi.fn()
    install(spy)
    setLoginPending('lyra')

    reportLyraLoginAborted('<script>alert(1)</script>')

    expect(spy).toHaveBeenCalledWith('lyra_login_aborted', { src: 'lyra', reason: 'unknown' })
  })
})
