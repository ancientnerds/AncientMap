/**
 * DataStore.interactiveAllowed() is the gate SitePage uses before swapping the
 * static record for SitePopup. It must answer false — and never throw — when
 * the probe cannot be fetched (Google's renderer: /api/app/interactive is
 * robots-disallowed, the fetch rejects), when it answers non-2xx, or when the
 * registry that follows comes back unusable; true only once both are in hand.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { DataStore } from '../DataStore'

afterEach(() => {
  vi.restoreAllMocks()
})

const ok = (body: unknown = null) =>
  ({ ok: true, status: body === null ? 204 : 200, json: async () => body }) as unknown as Response

describe('DataStore.interactiveAllowed', () => {
  it('false when the probe fetch rejects (robots-blocked renderer)', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(DataStore.interactiveAllowed()).resolves.toBe(false)
  })

  it('false when the probe answers non-2xx', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: false, status: 499 } as unknown as Response)
    await expect(DataStore.interactiveAllowed()).resolves.toBe(false)
  })

  it('false when the probe passes but no source was loaded', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok())
    vi.spyOn(DataStore, 'loadSources').mockResolvedValue()
    await expect(DataStore.interactiveAllowed()).resolves.toBe(false)
  })

  it('true once the probe passes and the registry is loaded', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    fetchMock.mockResolvedValueOnce(ok())
    fetchMock.mockResolvedValueOnce(
      ok({ sources: [{ id: 'ancient_nerds', name: 'Ancient Nerds', color: '#fff', count: 1, isPrimary: true }] }),
    )
    await expect(DataStore.interactiveAllowed()).resolves.toBe(true)
    expect(DataStore.getSource('ancient_nerds')?.name).toBe('Ancient Nerds')
    expect(String(fetchMock.mock.calls[0][0])).toContain('/app/interactive')
  })
})
