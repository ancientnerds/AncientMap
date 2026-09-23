// =============================================================================
// MAPBOX LOADER - loads mapbox-gl on demand and drives the Mapbox load state
// =============================================================================
//
// mapbox-gl (463 kB gzip, a second WebGL context, style, fonts, tiles) is not
// needed for the first frame: Mapbox only takes over at the switch distance.
// This module is the one runtime entry to it, through a dynamic import, so the
// library stays out of the globe's static graph (guard:
// services/__tests__/mapboxImportGraph.test.ts). Import MapboxGlobeService
// here as a type only.

import type { MapboxGlobeService } from './MapboxGlobeService'

/** idle → loading → ready | failed; ready and failed are terminal until unmount. */
export type MapboxLoadState = 'idle' | 'loading' | 'ready' | 'failed'

/**
 * Visible time the map gets to fire 'load' once constructed. Without it a
 * style request that never answers leaves the task pending forever. mapbox-gl
 * fires 'load' from requestAnimationFrame, which does not run in a hidden
 * tab, so only visible time counts.
 */
export const MAPBOX_LOAD_DEADLINE_MS = 20_000
/**
 * Visible time the mapbox chunk (463 kB gzip) gets to arrive. A failed fetch
 * rejects on its own, a stalled one never does and would hold every
 * background task queued behind this one. Longer than the map's deadline:
 * on the local dev server the download alone took more than 20 s, and a slow
 * connection must still get Mapbox.
 */
export const MAPBOX_IMPORT_DEADLINE_MS = 60_000
const DEADLINE_TICK_MS = 250

export interface MapboxLoadTaskDeps {
  containerRef: React.RefObject<HTMLDivElement | null>
  serviceRef: React.MutableRefObject<MapboxGlobeService | null>
  /** refs.satelliteMode (written by useSatelliteMode), not useMapboxSync's satelliteModeRef. */
  satelliteRef: React.MutableRefObject<boolean>
  dotSizeRef: React.MutableRefObject<number>
  setState: (state: MapboxLoadState) => void
  isCancelled: () => boolean
  signal: AbortSignal
}

/**
 * Settles with `work`, or rejects with the abort reason when the owner
 * aborts (a removed map never settles on its own), or rejects with
 * `${what} within N s of visible time` once that much visible time has passed.
 */
function settle<T>(work: Promise<T>, signal: AbortSignal, visibleDeadlineMs: number, what: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let visibleMs = 0
    const timer = setInterval(() => {
      if (document.hidden) return
      visibleMs += DEADLINE_TICK_MS
      if (visibleMs < visibleDeadlineMs) return
      done()
      reject(new Error(`${what} within ${visibleDeadlineMs / 1000} s of visible time`))
    }, DEADLINE_TICK_MS)
    const onAbort = () => {
      done()
      reject(signal.reason)
    }
    function done() {
      clearInterval(timer)
      signal.removeEventListener('abort', onAbort)
    }
    if (signal.aborted) {
      onAbort()
      return
    }
    signal.addEventListener('abort', onAbort)
    work.then(
      value => { done(); resolve(value) },
      (err: unknown) => { done(); reject(err) },
    )
  })
}

/**
 * Imports and initialises Mapbox for the globe. Sets `ready` only after
 * `initialize` resolved, so state and service agree. Every failure (chunk
 * import or its deadline, missing container, constructor throw, fatal map
 * error before 'load', load deadline) disposes the service, sets `failed` and is rethrown for
 * the caller to report. Once cancelled it touches neither state nor refs:
 * the owner's cleanup disposes whatever sits in `serviceRef`.
 */
export async function runMapboxLoadTask(d: MapboxLoadTaskDeps): Promise<void> {
  const cancelled = () => d.isCancelled() || d.signal.aborted
  d.setState('loading')
  let service: MapboxGlobeService | null = null
  try {
    const { MapboxGlobeService } = await settle(
      import('./MapboxGlobeService'), d.signal, MAPBOX_IMPORT_DEADLINE_MS, 'The Mapbox chunk did not arrive')
    if (cancelled()) return
    const container = d.containerRef.current
    if (!container) throw new Error('Mapbox container not mounted')
    service = new MapboxGlobeService()
    d.serviceRef.current = service
    // A dot-size change before the service existed would be lost otherwise.
    service.setDotSize(d.dotSizeRef.current)
    const style = d.satelliteRef.current ? 'satellite' : 'dark'
    await settle(service.initialize(container, style), d.signal, MAPBOX_LOAD_DEADLINE_MS, 'Mapbox did not load')
  } catch (err) {
    if (!cancelled()) {
      service?.dispose()
      d.serviceRef.current = null
      d.setState('failed')
    }
    throw err
  }
  if (!cancelled()) d.setState('ready')
}
