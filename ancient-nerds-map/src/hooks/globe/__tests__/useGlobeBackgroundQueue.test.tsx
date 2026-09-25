/**
 * @vitest-environment jsdom
 *
 * The globe's background queue as Globe wires it: which tasks a device gets
 * (from its real basemap tiers), a queue per mount that starts only when the
 * intro warp ends, the satellite toggle that moves its task to the front while
 * it is still to come and loads directly otherwise, and the unmount that aborts
 * the running task without a report.
 */

import { StrictMode, act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../analytics/globeBackground', () => ({
  trackBackgroundDone: vi.fn(),
  trackBackgroundFailure: vi.fn(),
}))

import { trackBackgroundDone, trackBackgroundFailure } from '../../../analytics/globeBackground'
import type { BgTaskName } from '../../../services/globeBackgroundQueue'
import { getBasemapTier, getStartTier } from '../../../utils/deviceTier'
import {
  buildGlobeBackgroundTasks,
  useGlobeBackgroundQueue,
  type GlobeBackgroundControl,
  type GlobeBackgroundRuns,
  type QueueScheduling,
} from '../useGlobeBackgroundQueue'
import { basemapPlanFor, type BasemapPlan } from '../useTextureLoading'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const ALL: BgTaskName[] = ['details', 'layers', 'mapbox', 'satellite', 'basemap', 'rivers_lakes', 'sw']

// ---------------------------------------------------------------------------
// Which tasks a device gets

interface Device {
  ua: string
  maxTouchPoints?: number
  maxTextureSize: number
  cssHeight: number
  dpr: number
}

const DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'
const IPAD_UA = 'Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
const PIXEL_UA = 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36'
const ANDROID_TABLET_UA = 'Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'

/** The plan useTextureLoading computes on this device (same tier functions). */
function planOn(device: Device): BasemapPlan {
  vi.stubGlobal('navigator', {
    userAgent: device.ua,
    platform: 'Win32',
    maxTouchPoints: device.maxTouchPoints ?? 0,
    deviceMemory: 8,
  })
  return basemapPlanFor({
    start: getStartTier(device.maxTextureSize, { cssHeight: device.cssHeight, dpr: device.dpr }),
    max: getBasemapTier(device.maxTextureSize),
  })
}

function namedRuns(sw: boolean): GlobeBackgroundRuns {
  const run = () => async () => {}
  return {
    details: run(), layers: run(), mapbox: run(), satellite: run(), basemap: run(), riversLakes: run(),
    sw: sw ? run() : null,
  }
}

describe('buildGlobeBackgroundTasks per device', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('a desktop whose maximum tier is high: everything, the satellite preloaded, the gray upgraded', () => {
    const plan = planOn({ ua: DESKTOP_UA, maxTextureSize: 16384, cssHeight: 1080, dpr: 1 })
    expect(plan).toEqual({ preloadSatellite: true, upgradeGray: true })
    expect(buildGlobeBackgroundTasks(plan, namedRuns(true)).map(t => t.name)).toEqual(ALL)
  })

  it('a desktop whose maximum tier is high and whose start is already high (4K, DPR 2): no gray upgrade', () => {
    const plan = planOn({ ua: DESKTOP_UA, maxTextureSize: 16384, cssHeight: 2160, dpr: 2 })
    expect(buildGlobeBackgroundTasks(plan, namedRuns(true)).map(t => t.name))
      .toEqual(['details', 'layers', 'mapbox', 'satellite', 'rivers_lakes', 'sw'])
  })

  it('a desktop whose GPU caps it at med: no satellite preload, the gray upgraded', () => {
    const plan = planOn({ ua: DESKTOP_UA, maxTextureSize: 8192, cssHeight: 1080, dpr: 1 })
    expect(plan).toEqual({ preloadSatellite: false, upgradeGray: true })
    expect(buildGlobeBackgroundTasks(plan, namedRuns(true)).map(t => t.name))
      .toEqual(['details', 'layers', 'mapbox', 'basemap', 'rivers_lakes', 'sw'])
  })

  it('touch devices starting at their maximum (iPad, a phone past the gate): neither satellite nor gray upgrade', () => {
    for (const device of [
      { ua: IPAD_UA, maxTouchPoints: 5, maxTextureSize: 16384, cssHeight: 1024, dpr: 2 },
      { ua: PIXEL_UA, maxTouchPoints: 5, maxTextureSize: 16384, cssHeight: 915, dpr: 2.625 },
    ]) {
      const plan = planOn(device)
      expect(plan).toEqual({ preloadSatellite: false, upgradeGray: false })
      expect(buildGlobeBackgroundTasks(plan, namedRuns(true)).map(t => t.name))
        .toEqual(['details', 'layers', 'mapbox', 'rivers_lakes', 'sw'])
    }
  })

  it('a touch device starting below its maximum (tablet at DPR 1): the gray upgraded, the satellite on first toggle', () => {
    const plan = planOn({ ua: ANDROID_TABLET_UA, maxTouchPoints: 5, maxTextureSize: 16384, cssHeight: 800, dpr: 1 })
    expect(plan).toEqual({ preloadSatellite: false, upgradeGray: true })
    expect(buildGlobeBackgroundTasks(plan, namedRuns(true)).map(t => t.name))
      .toEqual(['details', 'layers', 'mapbox', 'basemap', 'rivers_lakes', 'sw'])
  })

  it('a build without a service worker (dev) has no sw task', () => {
    expect(buildGlobeBackgroundTasks({ preloadSatellite: true, upgradeGray: true }, namedRuns(false)).map(t => t.name))
      .toEqual(['details', 'layers', 'mapbox', 'satellite', 'basemap', 'rivers_lakes'])
  })

  it('each task runs its own work', async () => {
    const calls: string[] = []
    const runs = namedRuns(true)
    for (const key of Object.keys(runs) as Array<keyof GlobeBackgroundRuns>) {
      runs[key] = async () => { calls.push(key) }
    }
    const signal = new AbortController().signal
    for (const task of buildGlobeBackgroundTasks({ preloadSatellite: true, upgradeGray: true }, runs)) await task.run(signal)
    expect(calls).toEqual(['details', 'layers', 'mapbox', 'satellite', 'basemap', 'riversLakes', 'sw'])
  })
})

// ---------------------------------------------------------------------------
// The hook

const flush = async () => {
  for (let i = 0; i < 5; i++) await Promise.resolve()
}

function fakeScheduling() {
  const idle: Array<() => void> = []
  const created = { count: 0 }
  const scheduling = (): QueueScheduling => {
    created.count++
    return {
      scheduleIdle: cb => {
        idle.push(cb)
        return () => {
          const i = idle.indexOf(cb)
          if (i !== -1) idle.splice(i, 1)
        }
      },
      isHidden: () => false,
      onVisibilityChange: () => () => {},
      now: () => 0,
      setTimer: () => () => {},
    }
  }
  /** Fires the oldest idle callback (the queue runs its next task there). */
  const runIdle = async () => {
    const cb = idle.shift()
    if (!cb) throw new Error('no idle callback is booked')
    await act(async () => {
      cb()
      await flush()
    })
  }
  return { idle, created, scheduling, runIdle }
}

/** Runs that record their start and stay pending until resolved by name. */
function pendingRuns(sw = true) {
  const started: string[] = []
  const signals = new Map<string, AbortSignal>()
  const settle = new Map<string, { resolve: () => void; reject: (err: unknown) => void }>()
  const run = (name: string) => (signal: AbortSignal) => {
    started.push(name)
    signals.set(name, signal)
    return new Promise<void>((resolve, reject) => settle.set(name, { resolve, reject }))
  }
  const runs: GlobeBackgroundRuns = {
    details: run('details'),
    layers: run('layers'),
    mapbox: run('mapbox'),
    satellite: run('satellite'),
    basemap: run('basemap'),
    riversLakes: run('rivers_lakes'),
    sw: sw ? run('sw') : null,
  }
  const finish = async (name: string) => {
    await act(async () => {
      settle.get(name)!.resolve()
      await flush()
    })
  }
  const fail = async (name: string, err: unknown) => {
    await act(async () => {
      settle.get(name)!.reject(err)
      await flush()
    })
  }
  return { runs, started, signals, finish, fail }
}

interface HarnessProps {
  plan: BasemapPlan | null
  runs: GlobeBackgroundRuns
  satellitePending: boolean
  requestSatellite: () => void
  scheduling: () => QueueScheduling
}

let control: GlobeBackgroundControl
function Harness(props: HarnessProps) {
  control = useGlobeBackgroundQueue(props)
  return null
}

let root: Root | null = null
async function render(props: HarnessProps, strict = false): Promise<void> {
  if (!root) root = createRoot(document.createElement('div'))
  const element = <Harness {...props} />
  await act(async () => root!.render(strict ? <StrictMode>{element}</StrictMode> : element))
}

const DESKTOP_HIGH: BasemapPlan = { preloadSatellite: true, upgradeGray: true }
const TOUCH: BasemapPlan = { preloadSatellite: false, upgradeGray: false }

beforeEach(() => {
  vi.mocked(trackBackgroundDone).mockClear()
  vi.mocked(trackBackgroundFailure).mockClear()
})

afterEach(async () => {
  await act(async () => root?.unmount())
  root = null
})

describe('useGlobeBackgroundQueue', () => {
  it('runs nothing before the intro ends; start() books the first task after an idle moment', async () => {
    const s = fakeScheduling()
    const r = pendingRuns()
    await render({ plan: DESKTOP_HIGH, runs: r.runs, satellitePending: false, requestSatellite: vi.fn(), scheduling: s.scheduling })
    await act(async () => { await flush() })
    expect(s.idle).toHaveLength(0)
    expect(r.started).toEqual([])
    control.start() // Globe calls it from the loop's onWarpComplete
    expect(s.idle).toHaveLength(1)
    expect(r.started).toEqual([])
    await s.runIdle()
    expect(r.started).toEqual(['details'])
  })

  it('runs the tasks one after the other and reports each finished one', async () => {
    const s = fakeScheduling()
    const r = pendingRuns()
    await render({ plan: DESKTOP_HIGH, runs: r.runs, satellitePending: false, requestSatellite: vi.fn(), scheduling: s.scheduling })
    control.start()
    for (const name of ALL) {
      await s.runIdle()
      expect(r.started.at(-1)).toBe(name)
      await r.finish(name)
    }
    expect(r.started).toEqual(ALL)
    expect(vi.mocked(trackBackgroundDone).mock.calls.map(([name]) => name)).toEqual(ALL)
  })

  it('a failed task is tracked as a background failure and the next one runs', async () => {
    const s = fakeScheduling()
    const r = pendingRuns()
    await render({ plan: TOUCH, runs: r.runs, satellitePending: false, requestSatellite: vi.fn(), scheduling: s.scheduling })
    control.start()
    await s.runIdle()
    const err = new Error('/api/sites/all: HTTP 502')
    await r.fail('details', err)
    expect(trackBackgroundFailure).toHaveBeenCalledExactlyOnceWith('details', err)
    await s.runIdle()
    expect(r.started).toEqual(['details', 'layers'])
  })

  it('adds the tasks once the plan is known, even when the queue started first', async () => {
    const s = fakeScheduling()
    const r = pendingRuns()
    const base = { runs: r.runs, satellitePending: false, requestSatellite: vi.fn(), scheduling: s.scheduling }
    await render({ ...base, plan: null })
    control.start()
    expect(s.idle).toHaveLength(0)
    await render({ ...base, plan: TOUCH })
    await s.runIdle()
    expect(r.started).toEqual(['details'])
  })

  it('a task runs the work of the latest render', async () => {
    const s = fakeScheduling()
    const r = pendingRuns()
    const base = { plan: TOUCH, satellitePending: false, requestSatellite: vi.fn(), scheduling: s.scheduling }
    await render({ ...base, runs: r.runs })
    const details = vi.fn(async () => {})
    await render({ ...base, runs: { ...r.runs, details } })
    control.start()
    await s.runIdle()
    expect(details).toHaveBeenCalledTimes(1)
    expect(r.started).toEqual([])
  })

  it('the satellite toggle moves the pending satellite task to the front instead of loading it twice', async () => {
    const s = fakeScheduling()
    const r = pendingRuns()
    const requestSatellite = vi.fn()
    const base = { plan: DESKTOP_HIGH, runs: r.runs, requestSatellite, scheduling: s.scheduling }
    await render({ ...base, satellitePending: false })
    await render({ ...base, satellitePending: true })
    expect(requestSatellite).not.toHaveBeenCalled()
    control.start()
    await s.runIdle()
    expect(r.started).toEqual(['satellite'])
  })

  it('a toggle while the satellite task runs joins it', async () => {
    const s = fakeScheduling()
    const r = pendingRuns()
    const requestSatellite = vi.fn()
    const base = { plan: DESKTOP_HIGH, runs: r.runs, requestSatellite, scheduling: s.scheduling }
    await render({ ...base, satellitePending: false })
    control.start()
    for (const name of ['details', 'layers', 'mapbox']) {
      await s.runIdle()
      await r.finish(name)
    }
    await s.runIdle()
    expect(r.started.at(-1)).toBe('satellite')
    await render({ ...base, satellitePending: true })
    expect(requestSatellite).not.toHaveBeenCalled()
  })

  it('loads the satellite directly where no task preloads it (touch) or its task is over', async () => {
    const s = fakeScheduling()
    const r = pendingRuns()
    const requestSatellite = vi.fn()
    await render({ plan: TOUCH, runs: r.runs, satellitePending: true, requestSatellite, scheduling: s.scheduling })
    expect(requestSatellite).toHaveBeenCalledTimes(1)
    await act(async () => root!.unmount())
    root = null

    const s2 = fakeScheduling()
    const r2 = pendingRuns()
    const request2 = vi.fn()
    const base = { plan: DESKTOP_HIGH, runs: r2.runs, requestSatellite: request2, scheduling: s2.scheduling }
    await render({ ...base, satellitePending: false })
    control.start()
    for (const name of ['details', 'layers', 'mapbox', 'satellite']) {
      await s2.runIdle()
      await r2.finish(name)
    }
    await render({ ...base, satellitePending: true }) // e.g. switched off and on again after a context loss
    expect(request2).toHaveBeenCalledTimes(1)
  })

  it('does nothing for the satellite before the plan exists', async () => {
    const s = fakeScheduling()
    const requestSatellite = vi.fn()
    await render({ plan: null, runs: pendingRuns().runs, satellitePending: true, requestSatellite, scheduling: s.scheduling })
    expect(requestSatellite).not.toHaveBeenCalled()
  })

  it('promote reaches the queue (demoApi.enterMapbox asks for Mapbox first)', async () => {
    const s = fakeScheduling()
    const r = pendingRuns()
    await render({ plan: TOUCH, runs: r.runs, satellitePending: false, requestSatellite: vi.fn(), scheduling: s.scheduling })
    expect(control.promote('mapbox')).toBe(true)
    expect(control.promote('satellite')).toBe(false) // not queued on touch
    control.start()
    await s.runIdle()
    expect(r.started).toEqual(['mapbox'])
  })

  it('the unmount aborts the running task, reports nothing and runs nothing more', async () => {
    const s = fakeScheduling()
    const r = pendingRuns()
    await render({ plan: TOUCH, runs: r.runs, satellitePending: false, requestSatellite: vi.fn(), scheduling: s.scheduling })
    control.start()
    await s.runIdle()
    const detailsSignal = r.signals.get('details')!
    await act(async () => root!.unmount())
    root = null
    expect(detailsSignal.aborted).toBe(true)
    await r.fail('details', detailsSignal.reason)
    expect(trackBackgroundFailure).not.toHaveBeenCalled()
    expect(trackBackgroundDone).not.toHaveBeenCalled()
    expect(s.idle).toHaveLength(0)
    expect(control.promote('layers')).toBe(false)
    control.start() // a late onWarpComplete after the unmount is harmless
    expect(s.idle).toHaveLength(0)
  })

  it('StrictMode (dev) remounts with a fresh queue that has every task exactly once', async () => {
    const s = fakeScheduling()
    const r = pendingRuns()
    await render({ plan: TOUCH, runs: r.runs, satellitePending: false, requestSatellite: vi.fn(), scheduling: s.scheduling }, true)
    expect(s.created.count).toBe(2)
    control.start()
    for (const name of ['details', 'layers', 'mapbox', 'rivers_lakes', 'sw']) {
      await s.runIdle()
      await r.finish(name)
    }
    expect(r.started).toEqual(['details', 'layers', 'mapbox', 'rivers_lakes', 'sw'])
    expect(s.idle).toHaveLength(0)
  })
})
