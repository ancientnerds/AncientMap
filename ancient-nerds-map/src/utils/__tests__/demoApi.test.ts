/**
 * The video recorder calls __DEMO.enterMapbox() right after the warp. Mapbox
 * is now created lazily by the globe's background queue, so the service may
 * not exist yet when the call arrives: the poll has to read the ref each time
 * instead of capturing null, the call moves the Mapbox task to the front of
 * the queue, and a Mapbox that failed ends the wait with an error. isReady
 * (the end of the warp) never waits for Mapbox.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { type GlobeDemoRefs, registerGlobeDemoApi } from '../demoApi'

type DemoWindow = { location: { search: string }; __DEMO?: { enterMapbox?: () => Promise<void>; isReady?: () => boolean } }

let win: DemoWindow

beforeEach(() => {
  vi.useFakeTimers()
  win = { location: { search: '?demo=1' } }
  vi.stubGlobal('window', win)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('__DEMO.enterMapbox', () => {
  it('resolves once a service created after the call is initialised', async () => {
    const mapboxServiceRef: { current: { getIsInitialized: () => boolean } | null } = { current: null }
    const enterMapboxMode = vi.fn()
    registerGlobeDemoApi({
      mapboxServiceRef,
      enterMapboxMode,
      mapboxStateRef: { current: 'loading' },
      requestMapbox: vi.fn(),
    } as unknown as GlobeDemoRefs)

    let resolved = false
    const entered = win.__DEMO!.enterMapbox!().then(() => { resolved = true })

    await vi.advanceTimersByTimeAsync(1000)
    expect(enterMapboxMode).not.toHaveBeenCalled()

    // The lazy loader creates the service, then initialise finishes later.
    let ready = false
    mapboxServiceRef.current = { getIsInitialized: () => ready }
    await vi.advanceTimersByTimeAsync(1000)
    expect(enterMapboxMode).not.toHaveBeenCalled()

    ready = true
    await vi.advanceTimersByTimeAsync(100)
    expect(enterMapboxMode).toHaveBeenCalledOnce()

    await vi.advanceTimersByTimeAsync(500)
    await entered
    expect(resolved).toBe(true)
  })

  it('moves the Mapbox task to the front of the background queue', () => {
    const requestMapbox = vi.fn()
    registerGlobeDemoApi({
      mapboxServiceRef: { current: null },
      enterMapboxMode: vi.fn(),
      mapboxStateRef: { current: 'idle' },
      requestMapbox,
    } as unknown as GlobeDemoRefs)
    void win.__DEMO!.enterMapbox!()
    expect(requestMapbox).toHaveBeenCalledOnce()
  })

  it('rejects once the Mapbox task has failed instead of waiting forever', async () => {
    const mapboxStateRef = { current: 'loading' }
    const enterMapboxMode = vi.fn()
    registerGlobeDemoApi({
      mapboxServiceRef: { current: null },
      enterMapboxMode,
      mapboxStateRef,
      requestMapbox: vi.fn(),
    } as unknown as GlobeDemoRefs)
    const entered = win.__DEMO!.enterMapbox!()
    const outcome = entered.then(() => 'resolved', (err: Error) => err.message)
    await vi.advanceTimersByTimeAsync(300)
    mapboxStateRef.current = 'failed'
    await vi.advanceTimersByTimeAsync(100)
    expect(await outcome).toMatch(/Mapbox failed to load/)
    expect(enterMapboxMode).not.toHaveBeenCalled()
  })
})

describe('__DEMO.isReady', () => {
  it('is the end of the warp and never waits for Mapbox', () => {
    registerGlobeDemoApi({
      mapboxServiceRef: { current: null },
      enterMapboxMode: vi.fn(),
      mapboxStateRef: { current: 'loading' },
      requestMapbox: vi.fn(),
      warpCompleteForLabelsRef: { current: true },
      dotsAnimationCompleteRef: { current: true },
    } as unknown as GlobeDemoRefs)
    expect(win.__DEMO!.isReady!()).toBe(true)
  })
})
