/**
 * @vitest-environment jsdom
 *
 * A screen that ends a load of /globe.html (GlobeUnsupported, GlobeErrorScreen
 * for a start failure) sends its ending event when it actually shows. Behind
 * the phone gate it does not show yet: the sites can fail while the gate is up,
 * and a gate link used then is the load's ending (globe_gate), not the failure
 * nobody saw. One ending per load (the latch).
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../analytics', () => ({ track: vi.fn() }))

import { track } from '../../analytics'
import { createGlobeEndingLatch, installGlobeAbandon, reportGateChoice, type GlobeEndingLatch } from '../../analytics/globeAbandon'
import { useGlobeScreenEnding, type ScreenEnding } from '../useGlobeScreenEnding'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const trackMock = vi.mocked(track)

function Harness({ latch, ending, gateShowing }: { latch: GlobeEndingLatch; ending: ScreenEnding | null; gateShowing: boolean }) {
  useGlobeScreenEnding(latch, ending, gateShowing)
  return null
}

let root: Root | null = null
async function render(latch: GlobeEndingLatch, ending: ScreenEnding | null, gateShowing: boolean) {
  if (!root) root = createRoot(document.createElement('div'))
  await act(async () => root!.render(<Harness latch={latch} ending={ending} gateShowing={gateShowing} />))
}

const SITES_FAILED: ScreenEnding = { name: 'globe_error', props: { phase: 'sites', message: '/api/sites/all: HTTP 502' } }
const NO_WEBGL2: ScreenEnding = { name: 'globe_unsupported', props: { reason: 'no_webgl2', detail: '' } }

beforeEach(() => trackMock.mockClear())

afterEach(async () => {
  await act(async () => root?.unmount())
  root = null
})

describe('useGlobeScreenEnding', () => {
  it('sends the ending as soon as its screen shows (no gate)', async () => {
    const latch = createGlobeEndingLatch()
    await render(latch, SITES_FAILED, false)
    expect(trackMock.mock.calls).toEqual([['globe_error', SITES_FAILED.props]])
  })

  it('holds a start failure behind the phone gate and sends it once the gate is passed', async () => {
    const latch = createGlobeEndingLatch()
    await render(latch, null, true)
    await render(latch, SITES_FAILED, true) // the sites fail while the gate shows
    expect(trackMock).not.toHaveBeenCalled()
    expect(latch.open).toBe(true)
    reportGateChoice('globe', latch) // "3D Globe": not an ending
    await render(latch, SITES_FAILED, false) // the error screen shows
    expect(trackMock.mock.calls).toEqual([
      ['globe_gate', { choice: 'globe' }],
      ['globe_error', SITES_FAILED.props],
    ])
    await render(latch, SITES_FAILED, false)
    expect(trackMock).toHaveBeenCalledTimes(2)
  })

  it('a gate link used while the failure waits is the ending; the failure is no second one', async () => {
    const latch = createGlobeEndingLatch()
    await render(latch, SITES_FAILED, true)
    reportGateChoice('radar', latch)
    expect(trackMock.mock.calls).toEqual([['globe_gate', { choice: 'radar' }]])
    await render(latch, SITES_FAILED, false) // (a back/forward restore of this page)
    expect(trackMock.mock.calls).toEqual([
      ['globe_gate', { choice: 'radar' }],
      ['globe_error', { ...SITES_FAILED.props, ending: 'no' }],
    ])
  })

  it('a start failure after a tab switch closed the latch keeps its phase and message, marked as no ending', async () => {
    const latch = createGlobeEndingLatch()
    const uninstall = installGlobeAbandon({ latch, getPhase: () => 'basemap', now: () => 10_000 })
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    document.dispatchEvent(new Event('visibilitychange')) // the visitor flips to another app...
    visibility.mockReturnValue('visible') // ...and comes back
    const BASEMAP_FAILED: ScreenEnding = { name: 'globe_error', props: { phase: 'basemap', message: 'decode failed' } }
    await render(latch, BASEMAP_FAILED, false)
    uninstall()
    // One ending per load (the abandon); the failure still reaches Umami for diagnosis
    expect(trackMock.mock.calls).toEqual([
      ['globe_abandon', { ms: 10_000, phase: 'basemap' }],
      ['globe_error', { phase: 'basemap', message: 'decode failed', ending: 'no' }],
    ])
  })

  it('sends a failure once however often the window passes through the phone gate', async () => {
    const latch = createGlobeEndingLatch()
    await render(latch, SITES_FAILED, false) // the error screen shows on a desktop
    await render(latch, SITES_FAILED, true) // the window snaps narrower than the phone gate...
    await render(latch, SITES_FAILED, false) // ...and wide again
    await render(latch, SITES_FAILED, true)
    await render(latch, SITES_FAILED, false)
    expect(trackMock.mock.calls).toEqual([['globe_error', SITES_FAILED.props]])
  })

  it('sends the marked copy once too when the failure passes through the gate again', async () => {
    const latch = createGlobeEndingLatch()
    await render(latch, SITES_FAILED, true)
    reportGateChoice('radar', latch)
    await render(latch, SITES_FAILED, false)
    await render(latch, SITES_FAILED, true)
    await render(latch, SITES_FAILED, false)
    expect(trackMock.mock.calls).toEqual([
      ['globe_gate', { choice: 'radar' }],
      ['globe_error', { ...SITES_FAILED.props, ending: 'no' }],
    ])
  })

  it('leaving while the gate shows is an abandon at the gate, not the hidden failure', async () => {
    const latch = createGlobeEndingLatch()
    const uninstall = installGlobeAbandon({ latch, getPhase: () => 'gate', now: () => 4321 })
    await render(latch, SITES_FAILED, true)
    window.dispatchEvent(new Event('pagehide'))
    uninstall()
    expect(trackMock.mock.calls).toEqual([['globe_abandon', { ms: 4321, phase: 'gate' }]])
  })

  it('the unsupported screen waits for the gate the same way', async () => {
    const latch = createGlobeEndingLatch()
    await render(latch, NO_WEBGL2, true)
    expect(trackMock).not.toHaveBeenCalled()
    await render(latch, NO_WEBGL2, false)
    expect(trackMock.mock.calls).toEqual([['globe_unsupported', NO_WEBGL2.props]])
  })

  it('sends nothing without an ending screen', async () => {
    const latch = createGlobeEndingLatch()
    await render(latch, null, false)
    await render(latch, null, true)
    expect(trackMock).not.toHaveBeenCalled()
    expect(latch.open).toBe(true)
  })
})
