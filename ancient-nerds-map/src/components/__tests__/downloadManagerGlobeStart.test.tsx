/**
 * @vitest-environment jsdom
 *
 * The Download Manager and the globe's offline start: every download also
 * stores the files the start cannot do without (GlobeStartCache), whatever
 * was ticked, and a basemap item counts as downloaded only when all of its
 * files are cached - a 'Satellite' download from before the basemap tiers is
 * offered again instead of showing as Cached.
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const calls: string[] = []

vi.mock('../../services/OfflineStorage', () => ({
  OfflineStorage: {
    getDownloadState: vi.fn(async () => ({ sources: {}, empires: [], layers: [], basemapItems: ['satellite'] })),
    getStorageEstimate: vi.fn(async () => ({ used: 0, quota: 0 })),
    saveSites: vi.fn(),
  },
}))
vi.mock('../../services/BasemapCache', () => ({
  BasemapCache: {
    getBasemapItems: () => [
      { id: 'satellite', name: 'Satellite', files: [{ url: '/s.webp', size: 10 }], totalSize: 10 },
      { id: 'labels', name: 'Labels', files: [{ url: '/data/labels.json', size: 5 }], totalSize: 5 },
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
vi.mock('../../services/GlobeStartCache', () => ({
  globeStartSize: () => 1000,
  isGlobeStartCached: vi.fn(async () => false),
  downloadGlobeStart: vi.fn(async () => { calls.push('globe-start') }),
}))
vi.mock('../../services/ImageCache', () => ({ ImageCache: {} }))
vi.mock('../../utils/cardApi', () => ({ reportAchievementEvent: vi.fn() }))

import DownloadManager from '../DownloadManager'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root | null = null
let container: HTMLDivElement

async function open() {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => {
    root!.render(<DownloadManager isOpen onClose={() => {}} sources={[]} isOffline={false} onToggleOffline={() => {}} />)
  })
  await act(async () => { await new Promise(r => setTimeout(r, 0)) })
}

function click(el: Element | null | undefined) {
  if (!el) throw new Error('element not found')
  return act(async () => { (el as HTMLElement).click() })
}

beforeEach(() => { calls.length = 0 })

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
    expect(calls).toEqual(['globe-start', 'layer:coastlines'])
  })

  it('offers nothing to download while nothing is ticked', async () => {
    await open()
    expect(container.querySelector('.empty-status')).not.toBeNull()
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
    expect(calls).toEqual(['globe-start', 'basemap:satellite'])
  })
})
