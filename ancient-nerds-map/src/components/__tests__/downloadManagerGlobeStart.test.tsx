/**
 * @vitest-environment jsdom
 *
 * The Download Manager and the globe's offline start: every download also
 * stores the files the start cannot do without (GlobeStartCache), whatever
 * was ticked, and a basemap item counts as downloaded only when all of its
 * files are cached - a 'Satellite' download from before the basemap tiers is
 * offered again instead of showing as Cached. A download made before the start
 * files existed (every ticked item still complete) offers the start files on
 * their own, so an offline start works for it too.
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const calls: string[] = []

const NO_DOWNLOAD = { sources: {}, basemapQuality: 'none', empires: [], layers: [], basemapItems: [] }
// What OfflineStorage.clearAllSites writes: no layers, no basemapItems
const CLEARED = { sources: {}, basemapQuality: 'none', empires: [] }
// The old download: 'Satellite' marked, but its files are not all cached
const OLD_SATELLITE = { ...NO_DOWNLOAD, basemapItems: ['satellite'] }
// Only the default source, downloaded before the start files existed; complete
const SOURCE_ONLY = {
  ...NO_DOWNLOAD,
  sources: { ancient_nerds: { cached: true, downloadedAt: '2026-01-01', siteCount: 5004 } },
}
let downloadState: object = OLD_SATELLITE
let startCached = false

vi.mock('../../services/OfflineStorage', () => ({
  OfflineStorage: {
    getDownloadState: vi.fn(async () => downloadState),
    getStorageEstimate: vi.fn(async () => ({ used: 0, quota: 0 })),
    saveSites: vi.fn(),
  },
}))
vi.mock('../../services/BasemapCache', () => ({
  BasemapCache: {
    getBasemapItems: () => [
      { id: 'satellite', name: 'Satellite', files: [{ url: '/s.webp', size: 10 }], totalSize: 10 },
    ],
    getBasemapItemInfo: (id: string) => ({ id, name: id, files: [], totalSize: 10 }),
    // The old download: marked, but its files are not all cached
    getCachedItems: vi.fn(async () => []),
    estimateSize: (ids: string[]) => ids.length * 10,
    downloadBasemapItem: vi.fn(async (id: string) => { calls.push(`basemap:${id}`) }),
  },
}))
vi.mock('../../services/VectorLayerCache', () => ({
  VectorLayerCache: {
    getAvailableLayers: () => [{ id: 'coastlines', name: 'Coastlines', color: '#0ff', fileCount: 3, estimatedSize: 100 }],
    getLayerInfo: (id: string) => ({ id, name: id, color: '#0ff', fileCount: 3, estimatedSize: 100 }),
    getCachedLayers: vi.fn(async () => []),
    estimateSize: (ids: string[]) => ids.length * 100,
    downloadLayer: vi.fn(async (id: string) => { calls.push(`layer:${id}`) }),
  },
}))
vi.mock('../../services/EmpireCache', () => ({
  EmpireCache: {
    getEmpiresByRegion: () => ({}),
    getAvailableEmpires: () => [],
    getTotalSize: () => 0,
    estimateEmpireSize: () => 0,
  },
}))
// Missing start files: labels.json (600 B) and one gray tier (400 B)
const MISSING = [
  { url: '/data/labels.json', size: 600, cache: 'basemaps', viaOfflineFetch: true },
  { url: '/data/basemaps/gray_dark_low.webp', size: 400, cache: 'basemaps', viaOfflineFetch: false },
]
vi.mock('../../services/GlobeStartCache', () => ({
  startFilesSize: (files: Array<{ size: number }>) => files.reduce((sum, f) => sum + f.size, 0),
  missingGlobeStartFiles: vi.fn(async () => (startCached ? [] : MISSING)),
  downloadGlobeStart: vi.fn(async (files: Array<{ url: string }>) => {
    calls.push(`globe-start:${files.map(f => f.url).join(',')}`)
    startCached = true
  }),
}))
vi.mock('../../services/ImageCache', () => ({ ImageCache: {} }))
vi.mock('../../utils/cardApi', () => ({ reportAchievementEvent: vi.fn() }))

import DownloadManager from '../DownloadManager'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root | null = null
let container: HTMLDivElement

async function open(ensureOfflineWorker: (() => Promise<void>) | null = null) {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => {
    root!.render(<DownloadManager isOpen onClose={() => {}} sources={[]} isOffline={false} onToggleOffline={() => {}} ensureOfflineWorker={ensureOfflineWorker} />)
  })
  await act(async () => { await new Promise(r => setTimeout(r, 0)) })
}

function click(el: Element | null | undefined) {
  if (!el) throw new Error('element not found')
  return act(async () => { (el as HTMLElement).click() })
}

beforeEach(() => {
  calls.length = 0
  downloadState = OLD_SATELLITE
  startCached = false
})

afterEach(async () => {
  await act(async () => root?.unmount())
  root = null
  container.remove()
})

describe('DownloadManager and the globe start files', () => {
  it('stores the globe start files with any download, before the ticked items', async () => {
    await open()
    // Layers tab: tick Coastlines only
    await click(container.querySelector('.dm-item'))
    expect(container.querySelector('.ready-status')!.textContent).toBe('1 KB ready to download') // 100 B of layer + 1000 B of start files
    await click(container.querySelector('.dm-download-btn'))
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
    expect(calls).toEqual(['globe-start:/data/labels.json,/data/basemaps/gray_dark_low.webp', 'layer:coastlines'])
  })

  it('offers nothing to download while nothing is ticked and nothing was downloaded', async () => {
    downloadState = NO_DOWNLOAD
    await open()
    expect(container.querySelector('.empty-status')).not.toBeNull()
    expect(container.querySelector<HTMLButtonElement>('.dm-download-btn')!.disabled).toBe(true)
  })

  it('reads a state without layers and basemap items (after Clear All) as no download', async () => {
    downloadState = CLEARED
    await open()
    expect(container.querySelector('.empty-status')).not.toBeNull()
    expect(container.querySelector<HTMLButtonElement>('.dm-download-btn')!.disabled).toBe(true)
  })

  it('offers the missing start files to a complete download made before they existed', async () => {
    downloadState = SOURCE_ONLY
    await open()
    expect(container.querySelector('.ready-status')!.textContent).toBe('Globe start files missing: 1000 B ready to download')
    const download = container.querySelector<HTMLButtonElement>('.dm-download-btn')!
    expect(download.disabled).toBe(false)
    await click(download)
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
    expect(calls).toEqual(['globe-start:/data/labels.json,/data/basemaps/gray_dark_low.webp'])
    expect(container.querySelector('.empty-status')).not.toBeNull()
    expect(download.disabled).toBe(true)
  })

  it('offers nothing to such a download once its start files are cached', async () => {
    downloadState = SOURCE_ONLY
    startCached = true
    await open()
    expect(container.querySelector('.empty-status')).not.toBeNull()
    expect(container.querySelector<HTMLButtonElement>('.dm-download-btn')!.disabled).toBe(true)
  })

  it('does not fetch the start files again when they were cached since the dialog opened', async () => {
    await open()
    await click(container.querySelector('.dm-item'))
    startCached = true // stored in the meantime (another tab)
    await click(container.querySelector('.dm-download-btn'))
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
    expect(calls).toEqual(['layer:coastlines'])
  })

  it('has the service worker active before the first file (the sw task may not have run yet)', async () => {
    await open(async () => { calls.push('worker') })
    await click(container.querySelector('.dm-item'))
    await click(container.querySelector('.dm-download-btn'))
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
    expect(calls).toEqual(['worker', 'globe-start:/data/labels.json,/data/basemaps/gray_dark_low.webp', 'layer:coastlines'])
  })

  it('downloads nothing and says why when the service worker cannot be installed', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    await open(async () => { throw new Error('this browser has no service workers') })
    await click(container.querySelector('.dm-item'))
    await click(container.querySelector('.dm-download-btn'))
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
    expect(calls).toEqual([])
    expect(container.querySelector('[role="alert"]')!.textContent).toBe(
      'Offline use is not possible in this browser: this browser has no service workers',
    )
  })

  it('does not show an incomplete Satellite download as Cached, and lets it be ticked again', async () => {
    await open()
    const basemapTab = [...container.querySelectorAll('.dm-tab')].find(b => b.textContent === 'Basemap')
    await click(basemapTab)
    const satellite = [...container.querySelectorAll('.dm-item')].find(el => el.textContent!.includes('Satellite'))!
    expect(satellite.querySelector('.cached-badge')).toBeNull()
    expect(satellite.classList.contains('selected')).toBe(false)
    await click(satellite)
    expect(satellite.classList.contains('selected')).toBe(true)
    await click(container.querySelector('.dm-download-btn'))
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
    expect(calls).toEqual(['globe-start:/data/labels.json,/data/basemaps/gray_dark_low.webp', 'basemap:satellite'])
  })
})
