/**
 * The video recorder calls __DEMO.enterMapbox() right after the warp. Mapbox
 * is now created lazily, so the service may not exist yet when the call
 * arrives: the poll has to read the ref each time instead of capturing null.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { type GlobeDemoRefs, registerGlobeDemoApi } from '../demoApi'

type DemoWindow = { location: { search: string }; __DEMO?: { enterMapbox?: () => Promise<void> } }

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
    registerGlobeDemoApi({ mapboxServiceRef, enterMapboxMode } as unknown as GlobeDemoRefs)

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
})
