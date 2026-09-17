import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  FEEDBACK_RATE_LIMIT_MS,
  markRated,
  ratedRecently,
} from '../feedback'

const g = globalThis as unknown as { window?: unknown }

/** The smallest localStorage that behaves like one. */
function fakeWindow(store: Record<string, string> = {}, broken = false) {
  return {
    localStorage: {
      getItem: (k: string) => (k in store ? store[k] : null),
      setItem: (k: string, v: string) => {
        if (broken) throw new Error('quota')
        store[k] = v
      },
    },
  }
}

afterEach(() => {
  delete g.window
  vi.useRealTimers()
})

describe('feedback throttle', () => {
  beforeEach(() => {
    g.window = fakeWindow()
  })

  it('lets the first rating through and blocks the same thing for a day', () => {
    const now = 1_000_000_000_000
    expect(ratedRecently('site_page', 'abc', now)).toBe(false)
    markRated('site_page', 'abc', now)
    expect(ratedRecently('site_page', 'abc', now + 60_000)).toBe(true)
    expect(ratedRecently('site_page', 'abc', now + FEEDBACK_RATE_LIMIT_MS - 1)).toBe(true)
    expect(ratedRecently('site_page', 'abc', now + FEEDBACK_RATE_LIMIT_MS)).toBe(false)
  })

  it('throttles per thing and per prompt, not globally', () => {
    const now = 1_000_000_000_000
    markRated('site_page', 'abc', now)
    expect(ratedRecently('site_page', 'other-site', now)).toBe(false)
    expect(ratedRecently('story_end', 'abc', now)).toBe(false)
  })

  it('prunes entries older than a day when it writes', () => {
    const store: Record<string, string> = {}
    g.window = fakeWindow(store)
    const now = 1_000_000_000_000
    markRated('site_page', 'old', now)
    markRated('site_page', 'new', now + FEEDBACK_RATE_LIMIT_MS + 1)
    const kept = JSON.parse(store.an_feedback_seen) as Record<string, number>
    expect(Object.keys(kept)).toEqual(['site_page:new'])
  })

  it('survives unreadable, broken and absent storage', () => {
    g.window = fakeWindow({ an_feedback_seen: 'not json' })
    expect(ratedRecently('site_page', 'abc', 1)).toBe(false)
    g.window = fakeWindow({ an_feedback_seen: '"a string"' })
    expect(ratedRecently('site_page', 'abc', 1)).toBe(false)
    g.window = fakeWindow({}, true)
    expect(() => markRated('site_page', 'abc', 1)).not.toThrow()
    delete g.window // server render
    expect(ratedRecently('site_page', 'abc', 1)).toBe(false)
    expect(() => markRated('site_page', 'abc', 1)).not.toThrow()
  })
})
