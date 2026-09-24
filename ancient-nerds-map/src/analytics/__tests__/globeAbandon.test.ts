/**
 * @vitest-environment jsdom
 *
 * How a load of /globe.html that never reaches the globe ends, as the
 * dashboard reads it (pipeline/umami_db.py SQL_GLOBE): at most ONE ending per
 * load - a gate choice other than the globe, globe_unsupported, a start
 * globe_error, or globe_abandon - and none once the globe is ready. The latch
 * is shared by all four senders.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../index', () => ({ track: vi.fn() }))

import { track } from '../index'
import {
  START_ITEMS,
  createGlobeEndingLatch,
  createLoadClock,
  dropGlobeStartItems,
  installGlobeAbandon,
  loadPhase,
  reportGateChoice,
  reportWebglLost,
  type StartItem,
} from '../globeAbandon'

const trackMock = vi.mocked(track)

function setVisibility(state: 'hidden' | 'visible') {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('the ending latch', () => {
  beforeEach(() => trackMock.mockClear())

  it('sends the first ending and refuses every later one', () => {
    const latch = createGlobeEndingLatch()
    expect(latch.end('globe_unsupported', { reason: 'no_webgl2' })).toBe(true)
    expect(latch.end('globe_error', { phase: 'sites', message: 'x' })).toBe(false)
    expect(latch.end('globe_abandon', { ms: 1, phase: 'sites' })).toBe(false)
    expect(trackMock.mock.calls).toEqual([['globe_unsupported', { reason: 'no_webgl2' }]])
    expect(latch.open).toBe(false)
  })

  it('sends nothing after the globe is ready', () => {
    const latch = createGlobeEndingLatch()
    latch.close()
    expect(latch.end('globe_abandon', { ms: 1, phase: 'labels' })).toBe(false)
    expect(trackMock).not.toHaveBeenCalled()
  })
})

describe('reportGateChoice', () => {
  beforeEach(() => trackMock.mockClear())

  it('the globe button is not an ending: the load goes on and can still end', () => {
    const latch = createGlobeEndingLatch()
    reportGateChoice('globe', latch)
    expect(trackMock).toHaveBeenCalledExactlyOnceWith('globe_gate', { choice: 'globe' })
    expect(latch.open).toBe(true)
  })

  it('any other choice is the ending of this load', () => {
    const latch = createGlobeEndingLatch()
    reportGateChoice('radar', latch)
    reportGateChoice('stories', latch)
    expect(trackMock.mock.calls).toEqual([['globe_gate', { choice: 'radar' }]])
    expect(latch.open).toBe(false)
  })
})

describe('loadPhase', () => {
  it('is the gate while the gate shows', () => {
    expect(loadPhase(true, new Set())).toBe('gate')
    expect(loadPhase(true, new Set(START_ITEMS))).toBe('gate')
  })

  it('is the first critical item still missing, in the order of START_ITEMS', () => {
    expect(START_ITEMS).toEqual(['sites', 'scene', 'basemap', 'labels', 'coastlines', 'countryBorders'])
    expect(loadPhase(false, new Set())).toBe('sites')
    expect(loadPhase(false, new Set<StartItem>(['sites', 'scene', 'labels']))).toBe('basemap')
    expect(loadPhase(false, new Set<StartItem>(['sites', 'scene', 'basemap', 'labels', 'coastlines']))).toBe('countryBorders')
  })

  it('is the last item once every item is in (the globe_ready check is its last step)', () => {
    expect(loadPhase(false, new Set(START_ITEMS))).toBe('countryBorders')
  })
})

describe('dropGlobeStartItems', () => {
  it("drops the unmounted Globe's items and keeps App's sites: the fresh Globe starts from its scene", () => {
    const done = new Set<StartItem>(START_ITEMS)
    dropGlobeStartItems(done)
    expect([...done]).toEqual(['sites'])
    expect(loadPhase(false, done)).toBe('scene')
  })
})

describe('createLoadClock', () => {
  let t = 0
  const now = () => t

  it('counts from navigation when no gate showed', () => {
    t = 0
    const clock = createLoadClock(now, false)
    clock.gate(false)
    t = 4000
    expect(clock.elapsed()).toBe(4000)
  })

  it('counts from the globe tap, not from navigation: reading the gate is no loading wait', () => {
    // A phone visitor reads the gate for 30 s, taps '3D Globe' and leaves 4 s into the load
    t = 0
    const clock = createLoadClock(now, true)
    t = 30_000
    clock.gate(true)
    expect(clock.elapsed()).toBe(30_000)
    clock.gate(false)
    t = 34_000
    expect(clock.elapsed()).toBe(4000)
  })

  it('starts again when a gate that appeared mid-load goes away (the fresh Globe starts from its scene)', () => {
    t = 0
    const clock = createLoadClock(now, false)
    t = 5000
    clock.gate(true) // a rotation below 768 px
    t = 20_000
    clock.gate(false)
    t = 21_000
    clock.gate(false) // later renders move nothing
    t = 23_000
    expect(clock.elapsed()).toBe(3000)
  })
})

describe('installGlobeAbandon', () => {
  let uninstall: (() => void) | null = null

  beforeEach(() => {
    trackMock.mockClear()
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
  })
  afterEach(() => {
    uninstall?.()
    uninstall = null
  })

  it('sends globe_abandon{ms, phase} once on pagehide', () => {
    const latch = createGlobeEndingLatch()
    uninstall = installGlobeAbandon({ latch, getPhase: () => 'labels', now: () => 4321.6 })
    window.dispatchEvent(new Event('pagehide'))
    window.dispatchEvent(new Event('pagehide'))
    expect(trackMock).toHaveBeenCalledExactlyOnceWith('globe_abandon', { ms: 4322, phase: 'labels' })
  })

  it('sends it when the page turns hidden, reading the phase at that moment', () => {
    const latch = createGlobeEndingLatch()
    let phase: 'gate' | 'sites' = 'gate'
    uninstall = installGlobeAbandon({ latch, getPhase: () => phase, now: () => 10 })
    setVisibility('visible')
    expect(trackMock).not.toHaveBeenCalled()
    phase = 'sites'
    setVisibility('hidden')
    setVisibility('visible')
    setVisibility('hidden')
    expect(trackMock).toHaveBeenCalledExactlyOnceWith('globe_abandon', { ms: 10, phase: 'sites' })
  })

  it('sends nothing once the globe is ready', () => {
    const latch = createGlobeEndingLatch()
    uninstall = installGlobeAbandon({ latch, getPhase: () => 'sites', now: () => 1 })
    latch.close()
    window.dispatchEvent(new Event('pagehide'))
    expect(trackMock).not.toHaveBeenCalled()
  })

  it('one ending per load: a gate link then the page leaving sends only the gate choice', () => {
    const latch = createGlobeEndingLatch()
    uninstall = installGlobeAbandon({ latch, getPhase: () => 'gate', now: () => 1 })
    reportGateChoice('journal', latch)
    window.dispatchEvent(new Event('pagehide'))
    expect(trackMock.mock.calls).toEqual([['globe_gate', { choice: 'journal' }]])
  })

  it('the cleanup removes both listeners', () => {
    const latch = createGlobeEndingLatch()
    installGlobeAbandon({ latch, getPhase: () => 'sites', now: () => 1 })()
    window.dispatchEvent(new Event('pagehide'))
    setVisibility('hidden')
    expect(trackMock).not.toHaveBeenCalled()
    expect(latch.open).toBe(true)
  })
})

describe('reportWebglLost', () => {
  beforeEach(() => {
    trackMock.mockClear()
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
  })

  it('a loss before globe_ready is this load\'s ending: webgl_lost{loading}, then no abandon', () => {
    const latch = createGlobeEndingLatch()
    const uninstall = installGlobeAbandon({ latch, getPhase: () => 'basemap', now: () => 3200 })
    reportWebglLost(latch, 'context_lost', false)
    window.dispatchEvent(new Event('pagehide'))
    uninstall()
    expect(trackMock.mock.calls).toEqual([['webgl_lost', { reason: 'context_lost', phase: 'loading' }]])
    expect(latch.open).toBe(false)
  })

  it('an abandon first (a hidden phone tab), then the context loss: one ending, the abandon', () => {
    const latch = createGlobeEndingLatch()
    const uninstall = installGlobeAbandon({ latch, getPhase: () => 'basemap', now: () => 3200 })
    setVisibility('hidden')
    reportWebglLost(latch, 'context_lost', false)
    uninstall()
    expect(trackMock.mock.calls).toEqual([['globe_abandon', { ms: 3200, phase: 'basemap' }]])
  })

  it('a loss after globe_ready is no ending: webgl_lost{live}, sent although the latch is closed', () => {
    const latch = createGlobeEndingLatch()
    latch.close()
    reportWebglLost(latch, 'context_lost', true)
    reportWebglLost(latch, 'context_lost', true) // lost again after a restore
    expect(trackMock.mock.calls).toEqual([
      ['webgl_lost', { reason: 'context_lost', phase: 'live' }],
      ['webgl_lost', { reason: 'context_lost', phase: 'live' }],
    ])
  })
})
