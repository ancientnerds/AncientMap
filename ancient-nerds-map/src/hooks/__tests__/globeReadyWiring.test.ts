/**
 * One moment of "ready" for the whole load, wired in App and Globe.
 *
 * useGlobeReady.test.tsx proves the hook; this pins how App and Globe use it,
 * which no render test reaches (App and Globe need WebGL, the data and the
 * whole page): globe_ready fires when the overlay fades - the sites, the
 * critical layers and the focus lookup are in, no error screen, a live context -
 * and not when the layers alone are in. Globe's loader bridge asks the same
 * question: a loader failure before the overlay fades, or before a remounted
 * Globe's own layers are up, is a start failure (the error screen, one
 * globe_error{phase}), after it a 'live' one.
 */

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const read = (path: string) => readFileSync(resolve(SRC, path), 'utf-8')

/** The body of `const <name> = useCallback(` up to its dependency list. */
function callbackBody(source: string, name: string): string {
  const start = source.indexOf(`const ${name} = useCallback(`)
  expect(start, name).toBeGreaterThan(-1)
  return source.slice(start, source.indexOf(', [', start))
}

describe('App: globe_ready when the overlay fades', () => {
  const app = read('App.tsx')

  it('fires on loadingComplete (sites, layers, focus) with no error screen and a live context', () => {
    expect(app).toContain('const loadingComplete = !isLoading && layersReady && focusResolved')
    expect(app).toContain('useGlobeReady(loadingComplete && !globeFailure && !webglLost, endingLatch, globeReadyRef, armGlobeIdle)')
  })

  it('does not treat the layers alone as ready', () => {
    const layersReady = callbackBody(app, 'handleLayersReady')
    expect(layersReady).toContain('setLayersReady(true)')
    expect(layersReady).not.toMatch(/globe_ready|endingLatch|globeReadyRef/)
  })

  it('sends globe_ready from useGlobeReady only', () => {
    expect(app).not.toContain("track('globe_ready'")
    expect(read('components/Globe.tsx')).not.toContain("track('globe_ready'")
    expect(read('hooks/useGlobeReady.ts')).toContain("track('globe_ready'")
  })
})

describe("Globe's loader bridge uses App's ready moment", () => {
  it("passes App.globeReadyRef and this instance's layers flag to the bridge", () => {
    const app = read('App.tsx')
    const globe = read('components/Globe.tsx')
    expect(callbackBody(app, 'isGlobeReady')).toContain('globeReadyRef.current')
    expect(app).toContain('isGlobeReady={isGlobeReady}')
    expect(globe).toContain('isGlobeReady: () => boolean')
    // App's moment alone stays true across a Globe remount (the phone-gate resize)
    expect(globe).toContain('const reportStartError = useStartErrorBridge(isGlobeReady, refs.layersReadyCalled)')
  })
})
