/**
 * @vitest-environment jsdom
 *
 * OfflineProvider re-reads what is downloaded every 5 s for the whole session,
 * and App and Globe are among its consumers. One tick is one read of the
 * download state and one commit: setters behind separate awaits of IndexedDB
 * and Cache Storage (each resolving in a task of its own) commit one by one, and
 * each commit renders the whole page again.
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** IndexedDB and Cache Storage answer in a later task, not a microtask. */
const later = <T,>(value: T) => new Promise<T>(resolve => setTimeout(() => resolve(value), 0))

const STATE = { sources: { ancient_nerds: { cached: true } }, empires: [], basemapQualities: [], basemapItems: ['satellite'], layers: ['coastlines'] }

vi.mock('../../services/OfflineStorage', () => ({
  OfflineStorage: {
    getDownloadState: vi.fn(() => later(STATE)),
    getPendingContributions: vi.fn(() => later([])),
  },
}))
vi.mock('../../services/BasemapCache', () => ({
  BasemapCache: { getCachedItems: vi.fn(() => later(['satellite'])) },
}))
vi.mock('../../services/VectorLayerCache', () => ({
  VectorLayerCache: { getCachedLayers: vi.fn(() => later(['coastlines'])) },
}))

import { BasemapCache } from '../../services/BasemapCache'
import { OfflineStorage } from '../../services/OfflineStorage'
import { VectorLayerCache } from '../../services/VectorLayerCache'
import { OfflineProvider, useOffline } from '../OfflineContext'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let renders = 0
let seen: { basemaps: string[]; layers: string[] } = { basemaps: [], layers: [] }

function Consumer() {
  const { cachedBasemapItems, cachedLayerIds } = useOffline()
  renders++
  seen = { basemaps: [...cachedBasemapItems], layers: [...cachedLayerIds] }
  return null
}

let container: HTMLDivElement
let root: Root

beforeEach(async () => {
  vi.useFakeTimers()
  renders = 0
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => root.render(<OfflineProvider><Consumer /></OfflineProvider>))
  // The mount's refreshes and the pending count settle
  await act(async () => { await vi.advanceTimersByTimeAsync(10) })
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('OfflineProvider cache poll', () => {
  it('reads the download state once per tick and commits once', async () => {
    expect(seen).toEqual({ basemaps: ['satellite'], layers: ['coastlines'] })
    vi.mocked(OfflineStorage.getDownloadState).mockClear()
    const before = renders
    // The next cache tick, outside act (act would batch every update of its scope into one
    // commit): React commits as it would in the browser. The pending-contributions poll
    // shares the 5 s beat; its count is unchanged, so it renders nothing.
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false
    try {
      await vi.advanceTimersByTimeAsync(5000)
      await vi.advanceTimersByTimeAsync(10)
    } finally {
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    }
    expect(renders - before).toBe(1)
    expect(OfflineStorage.getDownloadState).toHaveBeenCalledTimes(1)
    expect(BasemapCache.getCachedItems).toHaveBeenLastCalledWith(STATE)
    expect(VectorLayerCache.getCachedLayers).toHaveBeenLastCalledWith(STATE)
  })
})
