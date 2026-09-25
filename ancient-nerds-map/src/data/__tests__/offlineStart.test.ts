/**
 * The offline start and what an offline download stores. DataStore reads the
 * sites from IndexedDB only when a source is stored there (isOfflineEnabled);
 * otherwise it asks /api/sources, which no offline cache holds, and the globe
 * ends on the error screen. So every download stores the default source
 * (DownloadManager, downloadManagerGlobeStart.test.tsx): a download of layers
 * only starts offline on it.
 *
 * Node 20 (CI) has no global `navigator`: stubbed per test.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DataStore, DEFAULT_SOURCE } from '../DataStore'
import { OfflineStorage, type DownloadState } from '../../services/OfflineStorage'

// What a Coastlines-only download stores now: the layer and the default source
const LAYERS_DOWNLOAD: DownloadState = {
  sources: { [DEFAULT_SOURCE]: { cached: true, downloadedAt: '2026-09-24T10:00:00.000Z', siteCount: 1 } },
  basemapQualities: [],
  basemapQuality: 'none',
  empires: [],
  layers: ['coastlines'],
  basemapItems: [],
  lastUpdated: '2026-09-24T10:00:00.000Z',
}

beforeEach(() => {
  vi.stubGlobal('navigator', { onLine: false })
  vi.spyOn(OfflineStorage, 'getDownloadState').mockResolvedValue(LAYERS_DOWNLOAD)
  vi.spyOn(OfflineStorage, 'getAllSites').mockResolvedValue([{ id: 'a', n: 'Alpha', la: 10, lo: 20, s: DEFAULT_SOURCE }])
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => { throw new Error(`offline: fetch ${String(input)}`) })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('offline start', () => {
  it('starts from IndexedDB on the default source a layers download stored, without the network', async () => {
    await DataStore.initialize('globe')

    expect(DataStore.getStats().dataSource).toBe('offline')
    expect(DataStore.getSites().map(s => s.id)).toEqual(['a'])
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })
})
