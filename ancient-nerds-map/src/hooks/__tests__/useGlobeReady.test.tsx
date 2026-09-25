/**
 * @vitest-environment jsdom
 *
 * globe_ready marks the moment the visitor sees the globe: the loading overlay
 * fades (App's loadingComplete - the sites, the critical layers and the focus
 * lookup are in). The layers alone are not that moment: they are in at about
 * 1.5 s on desktop, often before the sites. Until the globe shows, the load's
 * ending latch stays open, so a sites failure or an abandon while the overlay
 * waits is still this load's ending.
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../analytics', () => ({ track: vi.fn() }))

import { track } from '../../analytics'
import { createGlobeEndingLatch, installGlobeAbandon, type GlobeEndingLatch } from '../../analytics/globeAbandon'
import { useGlobeReady } from '../useGlobeReady'
import { useGlobeScreenEnding, type ScreenEnding } from '../useGlobeScreenEnding'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const trackMock = vi.mocked(track)

interface Props {
  latch: GlobeEndingLatch
  readyRef: { current: boolean }
  shown: boolean
  ending: ScreenEnding | null
  onReady: () => void
}

/** App's two hooks side by side: the ready moment and a start failure's screen ending. */
function Harness({ latch, readyRef, shown, ending, onReady }: Props) {
  useGlobeReady(shown, latch, readyRef, onReady)
  useGlobeScreenEnding(latch, ending, false)
  return null
}

let root: Root | null = null
async function render(props: Props) {
  if (!root) root = createRoot(document.createElement('div'))
  await act(async () => root!.render(<Harness {...props} />))
}

const SITES_FAILED: ScreenEnding = { name: 'globe_error', props: { phase: 'sites', message: '/api/sites/all: HTTP 504' } }

beforeEach(() => trackMock.mockClear())

afterEach(async () => {
  await act(async () => root?.unmount())
  root = null
})

describe('useGlobeReady', () => {
  it('layers in, then the sites fail: one globe_error{sites} and no globe_ready', async () => {
    const latch = createGlobeEndingLatch()
    const readyRef = { current: false }
    const onReady = vi.fn()
    // The layers are ready, the overlay still waits for the sites
    await render({ latch, readyRef, shown: false, ending: null, onReady })
    expect(trackMock).not.toHaveBeenCalled()
    expect(latch.open).toBe(true)
    expect(readyRef.current).toBe(false)
    // The sites reject: the error screen shows
    await render({ latch, readyRef, shown: false, ending: SITES_FAILED, onReady })
    expect(trackMock.mock.calls).toEqual([['globe_error', SITES_FAILED.props]])
    expect(onReady).not.toHaveBeenCalled()
  })

  it('leaving while the overlay waits for the sites sends globe_abandon', async () => {
    const latch = createGlobeEndingLatch()
    const uninstall = installGlobeAbandon({ latch, getPhase: () => 'sites', now: () => 20000 })
    await render({ latch, readyRef: { current: false }, shown: false, ending: null, onReady: vi.fn() })
    window.dispatchEvent(new Event('pagehide'))
    uninstall()
    expect(trackMock.mock.calls).toEqual([['globe_abandon', { ms: 20000, phase: 'sites' }]])
  })

  it('once the globe shows: the latch closes before globe_ready, which is sent once', async () => {
    const latch = createGlobeEndingLatch()
    const readyRef = { current: false }
    let latchOpenAtTrack: boolean | null = null
    trackMock.mockImplementation(() => { latchOpenAtTrack = latch.open })
    const onReady = vi.fn()
    await render({ latch, readyRef, shown: false, ending: null, onReady })
    await render({ latch, readyRef, shown: true, ending: null, onReady })
    expect(trackMock).toHaveBeenCalledTimes(1)
    expect(trackMock.mock.calls[0][0]).toBe('globe_ready')
    expect(trackMock.mock.calls[0][1]).toEqual({ ms: expect.any(Number) })
    expect(latchOpenAtTrack).toBe(false)
    expect(readyRef.current).toBe(true)
    expect(onReady).toHaveBeenCalledTimes(1)
    // Shown again later (a context restore): still one globe_ready
    await render({ latch, readyRef, shown: false, ending: null, onReady })
    await render({ latch, readyRef, shown: true, ending: null, onReady })
    expect(trackMock).toHaveBeenCalledTimes(1)
    expect(onReady).toHaveBeenCalledTimes(1)
    trackMock.mockReset()
  })
})
