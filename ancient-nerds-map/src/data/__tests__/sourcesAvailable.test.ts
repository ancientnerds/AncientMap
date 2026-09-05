/**
 * DataStore.sourcesAvailable() is the gate SitePage uses before swapping the
 * static record for SitePopup. It must answer false — and never throw — when
 * the registry cannot be fetched (Google's renderer: /api/sources/ is
 * robots-disallowed, the fetch rejects) or comes back unusable, and true only
 * once sources are actually in hand.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { DataStore } from '../DataStore'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('DataStore.sourcesAvailable', () => {
  it('false when the registry fetch rejects (robots-blocked renderer)', async () => {
    vi.spyOn(DataStore, 'loadSources').mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(DataStore.sourcesAvailable()).resolves.toBe(false)
  })

  it('false when the fetch settles but no source was loaded (non-2xx response)', async () => {
    vi.spyOn(DataStore, 'loadSources').mockResolvedValue()
    await expect(DataStore.sourcesAvailable()).resolves.toBe(false)
  })

  it('true once the registry is loaded', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        sources: [{ id: 'ancient_nerds', name: 'Ancient Nerds', color: '#fff', count: 1, isPrimary: true }],
      }),
    } as unknown as Response)
    await expect(DataStore.sourcesAvailable()).resolves.toBe(true)
    expect(DataStore.getSource('ancient_nerds')?.name).toBe('Ancient Nerds')
  })
})
