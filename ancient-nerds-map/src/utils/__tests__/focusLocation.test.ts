/**
 * The focus site's position (?focus= links) aims the intro, and the loading
 * overlay waits for this lookup. It gets a deadline like the IP lookup: when
 * the API does not answer in time (or answers without a position) the intro
 * aims where it would have anyway (the IP location or the default) - logged,
 * not swallowed.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FOCUS_LOOKUP_DEADLINE_MS, lookupFocusLocation } from '../focusLocation'

type Answer = { status?: number; body?: unknown } | 'hang'

/** fetch stub: 'hang' settles only through the abort signal (like a real fetch). */
function stubFetch(answer: Answer) {
  const fetchMock = vi.fn((_url: string, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
    const signal = init?.signal
    const onAbort = () => reject(new DOMException('The operation was aborted.', 'AbortError'))
    if (signal?.aborted) return onAbort()
    signal?.addEventListener('abort', onAbort)
    if (answer === 'hang') return
    resolve(new Response(JSON.stringify(answer.body ?? {}), { status: answer.status ?? 200 }))
  }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const STONEHENGE = { id: 'abc', name: 'Stonehenge', lat: 51.1789, lon: -1.8262, sourceId: 'ancient_nerds' }

describe('lookupFocusLocation', () => {
  let warn: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.useFakeTimers()
    warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('gives the API 8 s', () => {
    expect(FOCUS_LOOKUP_DEADLINE_MS).toBe(8000)
  })

  it('answers with the site position as [lng, lat]', async () => {
    const fetchMock = stubFetch({ body: STONEHENGE })
    await expect(lookupFocusLocation('abc', new AbortController().signal)).resolves.toEqual([-1.8262, 51.1789])
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith('/api/sites/abc', { signal: expect.any(AbortSignal) })
    expect(warn).not.toHaveBeenCalled()
  })

  it('gives up after the deadline: null, and the timeout is logged', async () => {
    stubFetch('hang')
    let result: [number, number] | null | undefined
    const lookup = lookupFocusLocation('abc', new AbortController().signal).then(r => { result = r })
    await vi.advanceTimersByTimeAsync(FOCUS_LOOKUP_DEADLINE_MS - 1)
    expect(result).toBeUndefined()
    await vi.advanceTimersByTimeAsync(1)
    await lookup
    expect(result).toBeNull()
    expect(warn).toHaveBeenCalledTimes(1)
    expect(String(warn.mock.calls[0])).toMatch(/focus site abc/)
    expect(String(warn.mock.calls[0][1])).toMatch(/no answer within 8000 ms/)
  })

  it('an HTTP error is null and logged', async () => {
    stubFetch({ status: 404, body: { detail: 'Site not found' } })
    await expect(lookupFocusLocation('abc', new AbortController().signal)).resolves.toBeNull()
    expect(warn).toHaveBeenCalledTimes(1)
    expect(String(warn.mock.calls[0][1])).toMatch(/HTTP 404/)
  })

  it('a site without a position is null and logged', async () => {
    stubFetch({ body: { ...STONEHENGE, lat: null } })
    await expect(lookupFocusLocation('abc', new AbortController().signal)).resolves.toBeNull()
    expect(warn).toHaveBeenCalledTimes(1)
    expect(String(warn.mock.calls[0])).toMatch(/has no position/)
  })

  it("the caller's abort rejects with its reason and logs nothing", async () => {
    stubFetch('hang')
    const outer = new AbortController()
    const lookup = lookupFocusLocation('abc', outer.signal)
    const reason = new Error('app unmounted')
    outer.abort(reason)
    await expect(lookup).rejects.toBe(reason)
    expect(warn).not.toHaveBeenCalled()
  })
})
