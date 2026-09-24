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
    expect(app).toContain('const loadingComplete = !gateShowing && !isLoading && layersReady && focusResolved')
    expect(app).toContain('useGlobeReady(loadingComplete && !globeFailure && !webglLost, endingLatch, globeReadyRef, armGlobeIdle)')
  })

  it('completes nothing behind the phone gate, which unmounts the overlay and the Globe (useGlobeBehindGate.test.tsx)', () => {
    // gateShowing is known before loadingComplete reads it
    expect(app.indexOf('const gateShowing = isMobile && !mobileWarningDismissed'))
      .toBeLessThan(app.indexOf('const loadingComplete ='))
    expect(app).toContain('if (loadingComplete && overlayRendered && !overlayFading) setOverlayFading(true)')
    expect(app).toMatch(/useGlobeBehindGate\(gateShowing, overlayFading, \{\s*resetLayers: \(\) => setLayersReady\(false\),\s*removeOverlay: \(\) => setOverlayRendered\(false\),\s*\}\)/)
  })

  it('does not treat the layers alone as ready', () => {
    const layersReady = callbackBody(app, 'handleLayersReady')
    expect(layersReady).toContain('setLayersReady(true)')
    expect(layersReady).not.toMatch(/globe_ready|endingLatch|globeReadyRef/)
  })

  it("the overlay says READY at the same moment, not when the layers alone are in", () => {
    // The layers often land before the sites (the Globe mounts in parallel with the sites
    // fetch): the bar, stamp and text must keep showing the step still pending
    const layersReady = callbackBody(app, 'handleLayersReady')
    expect(layersReady).not.toContain('setLoadingProgress(100)')
    expect(layersReady).not.toContain('updateLoadingStatus(')
    expect(app).toContain("{webglLost ? 'GPU LOST' : loadingComplete ? 'READY' : 'LOADING'}")
    expect(app).toContain("{webglLost ? 'GRAPHICS CONTEXT LOST' : loadingComplete ? 'ALL SYSTEMS NOMINAL' : loadingStatus.toUpperCase()}")
    expect(app).toContain('if (loadingComplete) setLoadingProgress(100)')
    expect(app).not.toMatch(/layersReady \? '(READY|ALL SYSTEMS NOMINAL)'/)
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

  it("hands what the boundary caught to failGlobe through boundaryFailure (a remounted Globe's step stays in a live message)", () => {
    expect(read('App.tsx')).toMatch(/const \{ phase, error \} = boundaryFailure\(err, globeReadyRef\.current\)\s*failGlobe\(phase, error\)/)
  })
})
