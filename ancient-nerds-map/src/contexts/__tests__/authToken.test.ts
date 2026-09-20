/**
 * The token every reader in this tab shares. The case that matters is the
 * return leg of the OAuth redirect: AuthProvider promotes the post-OAuth
 * cookie from its mount effect, and React runs that after the effects of the
 * children it renders — so a gate that subscribed while mounting must still
 * hear about it (/lyra.html used to send the visitor back to the gate).
 *
 * vitest runs in node: no DOM, so the tests install a minimal fake `window`
 * with the localStorage the token is written into.
 */

import { afterEach, describe, expect, it } from 'vitest'

import { _resetAuthTokenForTests, getAuthToken, storeAuthToken, subscribeAuthToken } from '../authToken'

const g = globalThis as unknown as { window?: unknown }

function fakeLocalStorage(): Storage {
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
function blockedLocalStorage(): Storage {
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

function install(store: Storage = fakeLocalStorage()): Storage {
  g.window = { localStorage: store }
  return store
}

afterEach(() => {
  _resetAuthTokenForTests()
  delete g.window
})

describe('authToken', () => {
  it('reaches a subscriber that was already listening when the cookie is promoted', () => {
    install()
    const heard: (string | null)[] = []
    subscribeAuthToken(token => heard.push(token)) // the gate, subscribed while mounting

    storeAuthToken('jwt-from-oauth-cookie') // AuthProvider's mount effect, later

    expect(heard).toEqual(['jwt-from-oauth-cookie'])
    expect(getAuthToken()).toBe('jwt-from-oauth-cookie')
  })

  it('writes under the key of the OAuth cookie and of the other readers', () => {
    const store = install()

    storeAuthToken('jwt')

    // api/routes/auth.py sets the handoff cookie under this name; components
    // that read the storage directly use the same literal.
    expect(store.getItem('an_auth_token')).toBe('jwt')
  })

  it('drops the token and announces null on logout', () => {
    const store = install()
    storeAuthToken('jwt')
    const heard: (string | null)[] = []
    subscribeAuthToken(token => heard.push(token))

    storeAuthToken(null)

    expect(store.getItem('an_auth_token')).toBeNull()
    expect(getAuthToken()).toBeNull()
    expect(heard).toEqual([null])
  })

  it('stops calling a subscriber after unsubscribe, and keeps the order', () => {
    install()
    const order: string[] = []
    const unsubscribe = subscribeAuthToken(() => order.push('first'))
    subscribeAuthToken(() => order.push('second'))

    storeAuthToken('jwt')
    unsubscribe()
    storeAuthToken('jwt2')

    expect(order).toEqual(['first', 'second', 'second'])
  })

  it('announces a token even when the storage refuses the write', () => {
    install(blockedLocalStorage())
    const heard: (string | null)[] = []
    subscribeAuthToken(token => heard.push(token))

    expect(() => storeAuthToken('jwt-for-this-visit')).not.toThrow()

    // The token is valid, only its persistence failed: the mounted readers
    // still get it, and the page works for this visit.
    expect(heard).toEqual(['jwt-for-this-visit'])
    expect(getAuthToken()).toBeNull()
  })

  it('throws nowhere and reads null with an unreachable storage (no window)', () => {
    // Not a guard test: with no window there is no storage to write to, and the
    // outcome is the same as with a storage that throws — no throw, read null.
    delete g.window

    expect(() => storeAuthToken('jwt')).not.toThrow()
    expect(getAuthToken()).toBeNull()
  })
})
