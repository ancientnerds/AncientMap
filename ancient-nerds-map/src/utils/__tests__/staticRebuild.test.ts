/**
 * The audit page's upload starts the static rebuild as a background job (202) and follows
 * it through /rebuild-static/status. A 409 means another rebuild is running - one that may
 * have read the sites before this upload - so the helper waits for it and starts another.
 */

import { describe, expect, it } from 'vitest'

import { rebuildStaticData, startStaticRebuild, waitForStaticRebuild } from '../staticRebuild'

type Call = { url: string; method: string }

function fakeFetch(responses: Array<{ status: number; body?: unknown }>) {
  const calls: Call[] = []
  const impl = (async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? 'GET' })
    const next = responses.shift()
    if (!next) throw new Error(`unexpected request ${url}`)
    return {
      status: next.status,
      ok: next.status >= 200 && next.status < 300,
      json: async () => next.body,
    } as Response
  }) as typeof fetch
  return { impl, calls }
}

const noSleep = async () => {}

describe('startStaticRebuild', () => {
  it('reports a started job on 202', async () => {
    const { impl, calls } = fakeFetch([{ status: 202, body: { state: 'running' } }])
    await expect(startStaticRebuild('/api', 't', impl)).resolves.toBe('started')
    expect(calls).toEqual([{ url: '/api/sites/rebuild-static', method: 'POST' }])
  })

  it('reports busy on 409 and throws on anything else', async () => {
    const busy = fakeFetch([{ status: 409 }])
    await expect(startStaticRebuild('/api', 't', busy.impl)).resolves.toBe('busy')
    const broken = fakeFetch([{ status: 500 }])
    await expect(startStaticRebuild('/api', 't', broken.impl)).rejects.toThrow('HTTP 500')
  })
})

describe('waitForStaticRebuild', () => {
  it('polls until the job leaves running and returns its state', async () => {
    const { impl, calls } = fakeFetch([
      { status: 200, body: { state: 'running' } },
      { status: 200, body: { state: 'running' } },
      { status: 200, body: { state: 'ok' } },
    ])
    await expect(waitForStaticRebuild('/api', 't', impl, noSleep)).resolves.toBe('ok')
    expect(calls.map((c) => c.url)).toEqual(Array(3).fill('/api/sites/rebuild-static/status'))
  })

  it('returns a failed state instead of hiding it', async () => {
    const { impl } = fakeFetch([{ status: 200, body: { state: 'error' } }])
    await expect(waitForStaticRebuild('/api', 't', impl, noSleep)).resolves.toBe('error')
  })

  it('gives up on a job that never finishes', async () => {
    const { impl } = fakeFetch(Array(90).fill({ status: 200, body: { state: 'running' } }))
    await expect(waitForStaticRebuild('/api', 't', impl, noSleep)).rejects.toThrow('15 minutes')
  })
})

describe('rebuildStaticData', () => {
  it('starts one rebuild and follows it', async () => {
    const { impl, calls } = fakeFetch([
      { status: 202, body: { state: 'running' } },
      { status: 200, body: { state: 'ok' } },
    ])
    await expect(rebuildStaticData('/api', 't', impl, noSleep)).resolves.toBe('ok')
    expect(calls.map((c) => c.method)).toEqual(['POST', 'GET'])
  })

  it('after a 409 waits for the running rebuild and starts one that includes this upload', async () => {
    const { impl, calls } = fakeFetch([
      { status: 409 },
      { status: 200, body: { state: 'ok' } }, // the other upload's rebuild ends
      { status: 202, body: { state: 'running' } }, // ours starts
      { status: 200, body: { state: 'ok' } },
    ])
    await expect(rebuildStaticData('/api', 't', impl, noSleep)).resolves.toBe('ok')
    expect(calls.map((c) => c.method)).toEqual(['POST', 'GET', 'POST', 'GET'])
  })
})
