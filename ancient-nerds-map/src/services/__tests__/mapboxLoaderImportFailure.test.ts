/**
 * A failed chunk import (deploy swapped the chunk, network gone) is a Mapbox
 * failure like any other: `failed`, nothing left in the ref, error rethrown.
 * Own file, because the module mock must throw for every import in it.
 */

import { describe, expect, it, vi } from 'vitest'

vi.mock('../MapboxGlobeService', () => {
  throw new Error('Failed to fetch dynamically imported module')
})

import { type MapboxLoadState, runMapboxLoadTask } from '../mapboxLoader'
import type { MapboxGlobeService } from '../MapboxGlobeService'

describe('runMapboxLoadTask when the mapbox chunk cannot be imported', () => {
  it('reports failed and rethrows', async () => {
    vi.stubGlobal('document', { hidden: false })
    const states: MapboxLoadState[] = []
    const serviceRef = { current: null as MapboxGlobeService | null }

    const run = runMapboxLoadTask({
      containerRef: { current: {} as HTMLDivElement },
      serviceRef,
      satelliteRef: { current: false },
      dotSizeRef: { current: 6 },
      setState: s => { states.push(s) },
      isCancelled: () => false,
      signal: new AbortController().signal,
    })

    const err = await run.then(() => null, (e: unknown) => e)
    expect(err).toBeInstanceOf(Error)
    expect(String((err as Error).cause ?? err)).toContain('Failed to fetch dynamically imported module')
    expect(states).toEqual(['loading', 'failed'])
    expect(serviceRef.current).toBeNull()
    vi.unstubAllGlobals()
  })
})
