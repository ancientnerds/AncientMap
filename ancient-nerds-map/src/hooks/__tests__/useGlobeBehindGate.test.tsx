/**
 * @vitest-environment jsdom
 *
 * The phone gate can appear mid-load (a resize or a rotation below 768 px): App
 * renders it instead of the loading overlay and the Globe, which unmount. The
 * load's ready moment belongs to the Globe on screen, so nothing may complete
 * behind the gate: no globe_ready, no fade of an overlay that is not in the page
 * (its transitionend would never come and the invisible overlay, z-index 1000,
 * would take every click over the remounted globe).
 *
 * The harness is App's load state reduced to what the gate touches, with App's
 * formulas (pinned against App.tsx in globeReadyWiring.test.ts).
 */

import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../analytics', () => ({ track: vi.fn() }))

import { track } from '../../analytics'
import {
  START_ITEMS,
  createGlobeEndingLatch,
  dropGlobeStartItems,
  loadPhase,
  type AbandonPhase,
  type StartItem,
} from '../../analytics/globeAbandon'
import { useGlobeBehindGate } from '../useGlobeBehindGate'
import { useGlobeReady } from '../useGlobeReady'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const trackMock = vi.mocked(track)

interface Controls {
  setGate: (on: boolean) => void
  setSitesIn: () => void
  setLayersIn: () => void
  /** The Globe's WebGL context died (App's onWebglLost). */
  loseContext: () => void
  markItem: (item: StartItem) => void
  phase: () => AbandonPhase
}

function Harness({ controls }: { controls: Controls }) {
  const [gateShowing, setGateShowing] = React.useState(false)
  const [isLoading, setIsLoading] = React.useState(true)
  const [layersReady, setLayersReady] = React.useState(false)
  const [overlayFading, setOverlayFading] = React.useState(false)
  const [overlayRendered, setOverlayRendered] = React.useState(true)
  const [webglLost, setWebglLost] = React.useState(false)
  const [latch] = React.useState(createGlobeEndingLatch)
  const readyRef = React.useRef(false)
  const startItemsRef = React.useRef(new Set<StartItem>())
  controls.setGate = setGateShowing
  controls.markItem = item => startItemsRef.current.add(item)
  controls.phase = () => loadPhase(gateShowing, startItemsRef.current)
  controls.setSitesIn = () => setIsLoading(false)
  controls.setLayersIn = () => setLayersReady(true)
  controls.loseContext = () => setWebglLost(true)

  const loadingComplete = !gateShowing && !isLoading && layersReady
  React.useEffect(() => {
    if (loadingComplete && overlayRendered && !overlayFading) setOverlayFading(true)
  }, [loadingComplete, overlayRendered, overlayFading])
  useGlobeReady(loadingComplete && !webglLost, latch, readyRef, () => {})
  useGlobeBehindGate(gateShowing, overlayFading, {
    resetLayers: () => {
      setLayersReady(false)
      dropGlobeStartItems(startItemsRef.current)
    },
    removeOverlay: () => setOverlayRendered(false),
    dropLostContext: () => setWebglLost(false),
  })

  if (gateShowing) return <div id="gate" />
  return (
    <>
      {overlayRendered && (
        <div
          id="overlay"
          className={`loading-overlay${overlayFading ? ' fading' : ''}`}
          onTransitionEnd={() => overlayFading && setOverlayRendered(false)}
        />
      )}
      {webglLost && <div id="webgl-lost" />}
      <div id="globe" />
    </>
  )
}

let container: HTMLDivElement
let root: Root
let controls: Controls

beforeEach(() => {
  trackMock.mockClear()
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  controls = {
    setGate: () => {},
    setSitesIn: () => {},
    setLayersIn: () => {},
    loseContext: () => {},
    markItem: () => {},
    phase: () => 'gate',
  }
  act(() => root.render(<Harness controls={controls} />))
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

const overlay = () => container.querySelector('#overlay')
const readyEvents = () => trackMock.mock.calls.filter(([name]) => name === 'globe_ready')

describe('useGlobeBehindGate', () => {
  it('a gate that appears after the layers and before the sites: nothing completes behind it', () => {
    act(() => controls.setLayersIn())
    act(() => controls.setGate(true))
    act(() => controls.setSitesIn()) // the sites arrive while the gate is on screen
    expect(readyEvents()).toHaveLength(0)
    act(() => controls.setGate(false)) // '3D Globe' or a rotation back: a fresh Globe mounts
    // The overlay is back, not fading: it waits for the fresh Globe's own layers
    expect(overlay()?.className).toBe('loading-overlay')
    expect(readyEvents()).toHaveLength(0)
    act(() => controls.setLayersIn())
    expect(overlay()?.className).toBe('loading-overlay fading')
    expect(readyEvents()).toHaveLength(1)
  })

  it('a gate that appears during the fade: the overlay does not come back over the remounted globe', () => {
    act(() => controls.setLayersIn())
    act(() => controls.setSitesIn())
    expect(overlay()?.className).toBe('loading-overlay fading')
    expect(readyEvents()).toHaveLength(1)
    act(() => controls.setGate(true)) // mid-fade: the transitionend never comes
    act(() => controls.setGate(false))
    expect(overlay()).toBeNull()
    expect(container.querySelector('#globe')).not.toBeNull()
    expect(readyEvents()).toHaveLength(1)
  })

  // The gate unmounts the Globe whose context died; the fresh Globe has a context
  // of its own and never reports a restore, so the loss goes with the old one.
  it('a context lost during the load does not outlive the Globe the gate unmounts', () => {
    act(() => controls.setSitesIn())
    act(() => controls.loseContext()) // Safari drops the context under memory pressure, never restores it
    act(() => controls.setLayersIn())
    expect(readyEvents()).toHaveLength(0)
    act(() => controls.setGate(true)) // rotated to portrait
    act(() => controls.setGate(false)) // 'globe': a fresh Globe with a fresh context
    expect(container.querySelector('#webgl-lost')).toBeNull()
    act(() => controls.setLayersIn())
    expect(readyEvents()).toHaveLength(1)
  })

  it('a context lost after the load goes with the Globe the gate unmounts too', () => {
    act(() => controls.setLayersIn())
    act(() => controls.setSitesIn())
    expect(readyEvents()).toHaveLength(1)
    act(() => controls.loseContext())
    act(() => controls.setGate(true))
    act(() => controls.setGate(false))
    expect(container.querySelector('#webgl-lost')).toBeNull()
  })

  it("a gate before completion: globe_abandon's phase follows the fresh Globe, not the unmounted one", () => {
    // The old Globe had every critical item in; the sites had not arrived yet
    for (const item of START_ITEMS) if (item !== 'sites') act(() => controls.markItem(item))
    act(() => controls.setLayersIn())
    act(() => controls.setGate(true))
    expect(controls.phase()).toBe('gate')
    act(() => controls.markItem('sites'))
    act(() => controls.setSitesIn())
    act(() => controls.setGate(false)) // a fresh Globe mounts and starts from its scene
    expect(controls.phase()).toBe('scene')
    act(() => controls.markItem('scene'))
    expect(controls.phase()).toBe('basemap')
  })
})
