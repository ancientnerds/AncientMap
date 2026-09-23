/**
 * The IP lookup that centres the globe's intro on the visitor. It runs in
 * parallel with the start and never holds it: each provider gets a deadline,
 * the second is asked only when the first gave nothing, and a double failure
 * means the default target (as a failed lookup always did) - logged, not
 * swallowed.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { IP_LOOKUP_DEADLINE_MS, lookupIpLocation } from '../ipLocation'

const IPWHO = 'https://ipwho.is/'
const GEOJS = 'https://get.geojs.io/v1/ip/geo.json'

type Answer = { status?: number; body?: unknown } | 'hang' | 'network'

/** fetch stub: per URL an answer; 'hang' settles only through the abort signal (like a real fetch). */
function stubFetch(answers: Record<string, Answer>) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const answer = answers[url]
    if (answer === undefined) throw new Error(`unexpected fetch ${url}`)
    return new Promise<Response>((resolve, reject) => {
      const signal = init?.signal
      const onAbort = () => reject(new DOMException('The operation was aborted.', 'AbortError'))
      if (signal?.aborted) return onAbort()
      signal?.addEventListener('abort', onAbort)
      if (answer === 'hang') return
      if (answer === 'network') return reject(new TypeError('Failed to fetch'))
      resolve(new Response(JSON.stringify(answer.body ?? {}), { status: answer.status ?? 200 }))
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('lookupIpLocation', () => {
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

  it('answers from the first provider and never asks the second', async () => {
    const fetchMock = stubFetch({ [IPWHO]: { body: { success: true, latitude: 48.1, longitude: 11.6 } } })
    await expect(lookupIpLocation(new AbortController().signal)).resolves.toEqual([11.6, 48.1])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(warn).not.toHaveBeenCalled()
  })

  it('asks the second provider only after the first failed, and logs the failure', async () => {
    const fetchMock = stubFetch({
      [IPWHO]: { status: 503 },
      [GEOJS]: { body: { latitude: '40.4', longitude: '-3.7' } },
    })
    await expect(lookupIpLocation(new AbortController().signal)).resolves.toEqual([-3.7, 40.4])
    expect(fetchMock.mock.calls.map(c => c[0])).toEqual([IPWHO, GEOJS])
    expect(warn).toHaveBeenCalledTimes(1)
    expect(String(warn.mock.calls[0].join(' '))).toContain('ipwho.is')
  })

  it('treats an answer without coordinates as a failure', async () => {
    stubFetch({
      [IPWHO]: { body: { success: false, message: 'reserved range' } },
      [GEOJS]: { body: { latitude: 'nil' } },
    })
    await expect(lookupIpLocation(new AbortController().signal)).resolves.toBeNull()
    expect(warn).toHaveBeenCalledTimes(2)
  })

  it('gives each provider its deadline, then returns null when both fail', async () => {
    const fetchMock = stubFetch({ [IPWHO]: 'hang', [GEOJS]: 'network' })
    const result = lookupIpLocation(new AbortController().signal)
    await vi.advanceTimersByTimeAsync(IP_LOOKUP_DEADLINE_MS - 1)
    expect(fetchMock).toHaveBeenCalledTimes(1) // the first provider still has time
    await vi.advanceTimersByTimeAsync(1)
    await expect(result).resolves.toBeNull()
    expect(fetchMock.mock.calls.map(c => c[0])).toEqual([IPWHO, GEOJS])
    expect(warn).toHaveBeenCalledTimes(2)
  })

  it('the deadline is 2 s per provider', () => {
    expect(IP_LOOKUP_DEADLINE_MS).toBe(2000)
  })

  it('stops at once when the caller aborts, without asking the second provider', async () => {
    const fetchMock = stubFetch({ [IPWHO]: 'hang', [GEOJS]: { body: { latitude: '1', longitude: '2' } } })
    const caller = new AbortController()
    const result = lookupIpLocation(caller.signal)
    const reason = new Error('unmounted')
    caller.abort(reason)
    await expect(result).rejects.toBe(reason)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(warn).not.toHaveBeenCalled()
  })
})
