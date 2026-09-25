/**
 * A chunk download that stalls never rejects on its own. Once the loader runs
 * as a background-queue task, a pending import would hold every task behind
 * it, so the import gets its own visible-time deadline: longer than the map's
 * (a slow 1.7 MB download must still finish), but finite.
 * Own file, because the module mock must hang for every import in it.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../MapboxGlobeService', () => new Promise(() => {}))

import {
  MAPBOX_IMPORT_DEADLINE_MS,
  MAPBOX_LOAD_DEADLINE_MS,
  type MapboxLoadState,
  runMapboxLoadTask,
} from '../mapboxLoader'
import type { MapboxGlobeService } from '../MapboxGlobeService'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('runMapboxLoadTask when the mapbox chunk download stalls', () => {
  it('waits past the map deadline, then reports failed after the import deadline', async () => {
    vi.useFakeTimers()
    const doc = { hidden: false }
    vi.stubGlobal('document', doc)
    const states: MapboxLoadState[] = []
    const serviceRef = { current: null as MapboxGlobeService | null }

    let outcome: unknown = 'pending'
    runMapboxLoadTask({
      containerRef: { current: {} as HTMLDivElement },
      serviceRef,
      satelliteRef: { current: false },
      dotSizeRef: { current: 6 },
      setState: s => { states.push(s) },
      isCancelled: () => false,
      signal: new AbortController().signal,
    }).then(() => { outcome = 'resolved' }, (e: unknown) => { outcome = e })

    expect(MAPBOX_IMPORT_DEADLINE_MS).toBe(60_000)
    expect(MAPBOX_IMPORT_DEADLINE_MS).toBeGreaterThan(MAPBOX_LOAD_DEADLINE_MS)

    // A slow download is not cut off at the map's 20 s, and hidden time does not count.
    await vi.advanceTimersByTimeAsync(MAPBOX_LOAD_DEADLINE_MS * 2)
    doc.hidden = true
    await vi.advanceTimersByTimeAsync(MAPBOX_IMPORT_DEADLINE_MS * 5)
    expect(outcome).toBe('pending')
    expect(states).toEqual(['loading'])

    doc.hidden = false
    await vi.advanceTimersByTimeAsync(MAPBOX_IMPORT_DEADLINE_MS - MAPBOX_LOAD_DEADLINE_MS * 2)
    expect(outcome).toBeInstanceOf(Error)
    expect((outcome as Error).message).toBe('The Mapbox chunk did not arrive within 60 s of visible time')
    expect(states).toEqual(['loading', 'failed'])
    expect(serviceRef.current).toBeNull()
  })
})
