/**
 * runMapboxLoadTask: the only place that imports MapboxGlobeService (and with
 * it mapbox-gl) at runtime. It drives the load state idle → loading →
 * ready | failed, never swallows a failure, and never touches state or refs
 * once its owner has cancelled it.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const fake = vi.hoisted(() => {
  const state = {
    instances: [] as FakeService[],
    initialize: (_container: unknown, _style: string): Promise<void> => Promise.resolve(),
  }
  class FakeService {
    dotSize: number | null = null
    style: string | null = null
    disposed = false
    constructor() {
      state.instances.push(this)
    }
    setDotSize(size: number) {
      this.dotSize = size
    }
    initialize(container: unknown, style: string) {
      this.style = style
      return state.initialize(container, style)
    }
    dispose() {
      this.disposed = true
    }
  }
  return { state, FakeService }
})

vi.mock('../MapboxGlobeService', () => ({ MapboxGlobeService: fake.FakeService }))

import {
  MAPBOX_LOAD_DEADLINE_MS,
  type MapboxLoadState,
  runMapboxLoadTask,
} from '../mapboxLoader'
import type { MapboxGlobeService } from '../MapboxGlobeService'

const doc = { hidden: false }

function setup(overrides: { cancelled?: () => boolean; satellite?: boolean; signal?: AbortSignal } = {}) {
  const states: MapboxLoadState[] = []
  const container = {} as HTMLDivElement
  const serviceRef = { current: null as MapboxGlobeService | null }
  const d = {
    containerRef: { current: container },
    serviceRef,
    satelliteRef: { current: overrides.satellite ?? false },
    dotSizeRef: { current: 9 },
    setState: (s: MapboxLoadState) => { states.push(s) },
    isCancelled: overrides.cancelled ?? (() => false),
    signal: overrides.signal ?? new AbortController().signal,
  }
  return { d, states, serviceRef, container }
}

beforeEach(() => {
  fake.state.instances.length = 0
  fake.state.initialize = () => Promise.resolve()
  doc.hidden = false
  vi.stubGlobal('document', doc)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('runMapboxLoadTask', () => {
  it('goes loading → ready and leaves the initialised service in the ref', async () => {
    const { d, states, serviceRef, container } = setup({ satellite: true })
    let seenContainer: unknown = null
    fake.state.initialize = (c) => { seenContainer = c; return Promise.resolve() }

    await runMapboxLoadTask(d)

    expect(states).toEqual(['loading', 'ready'])
    const service = fake.state.instances[0]
    expect(serviceRef.current).toBe(service)
    expect(seenContainer).toBe(container)
    expect(service.style).toBe('satellite')
    // A dot size set before the service existed is not lost.
    expect(service.dotSize).toBe(9)
  })

  it('starts with the dark style when satellite mode is off', async () => {
    const { d } = setup()
    await runMapboxLoadTask(d)
    expect(fake.state.instances[0].style).toBe('dark')
  })

  it('on an initialise failure disposes, clears the ref, reports failed and rethrows', async () => {
    const boom = new Error('style 401')
    fake.state.initialize = () => Promise.reject(boom)
    const { d, states, serviceRef } = setup()

    await expect(runMapboxLoadTask(d)).rejects.toBe(boom)

    expect(states).toEqual(['loading', 'failed'])
    expect(fake.state.instances[0].disposed).toBe(true)
    expect(serviceRef.current).toBeNull()
  })

  it('reports failed and rethrows when the container is gone', async () => {
    const { d, states } = setup()
    d.containerRef.current = null as unknown as HTMLDivElement

    await expect(runMapboxLoadTask(d)).rejects.toThrow('Mapbox container not mounted')
    expect(states).toEqual(['loading', 'failed'])
  })

  it('cancelled while the import was pending: no service, no ref, no further state', async () => {
    const { d, states, serviceRef } = setup({ cancelled: () => true })

    await runMapboxLoadTask(d)

    expect(states).toEqual(['loading'])
    expect(fake.state.instances).toHaveLength(0)
    expect(serviceRef.current).toBeNull()
  })

  it('aborted before the chunk arrived: settles with the abort reason, creates no service', async () => {
    const controller = new AbortController()
    const reason = new Error('unmounted')
    controller.abort(reason)
    const { d, states, serviceRef } = setup({ signal: controller.signal })

    await expect(runMapboxLoadTask(d)).rejects.toBe(reason)
    expect(states).toEqual(['loading'])
    expect(fake.state.instances).toHaveLength(0)
    expect(serviceRef.current).toBeNull()
  })

  it('cancelled during initialise: settles with the abort reason and leaves state and ref to the owner', async () => {
    fake.state.initialize = () => new Promise<void>(() => {}) // a removed map never settles
    const controller = new AbortController()
    const { d, states, serviceRef } = setup({ signal: controller.signal, cancelled: () => controller.signal.aborted })

    const run = runMapboxLoadTask(d)
    await vi.waitFor(() => expect(fake.state.instances).toHaveLength(1))
    const reason = new Error('unmounted')
    controller.abort(reason)

    await expect(run).rejects.toBe(reason)
    expect(states).toEqual(['loading'])
    expect(serviceRef.current).toBe(fake.state.instances[0])
    expect(fake.state.instances[0].disposed).toBe(false)
  })

  it('fails after 20 s of visible time when Mapbox never loads', async () => {
    vi.useFakeTimers()
    fake.state.initialize = () => new Promise<void>(() => {})
    const { d, states, serviceRef } = setup()

    const run = runMapboxLoadTask(d)
    const settled = expect(run).rejects.toThrow('Mapbox did not load within 20 s of visible time')
    await vi.advanceTimersByTimeAsync(MAPBOX_LOAD_DEADLINE_MS)
    await settled

    expect(MAPBOX_LOAD_DEADLINE_MS).toBe(20_000)
    expect(states).toEqual(['loading', 'failed'])
    expect(fake.state.instances[0].disposed).toBe(true)
    expect(serviceRef.current).toBeNull()
  })

  it('counts only visible time toward the deadline', async () => {
    vi.useFakeTimers()
    fake.state.initialize = () => new Promise<void>(() => {})
    const { d, states } = setup()
    let rejected: unknown = null

    const run = runMapboxLoadTask(d).catch((err: unknown) => { rejected = err })
    await vi.advanceTimersByTimeAsync(MAPBOX_LOAD_DEADLINE_MS / 2)
    doc.hidden = true
    await vi.advanceTimersByTimeAsync(5 * MAPBOX_LOAD_DEADLINE_MS)
    expect(rejected).toBeNull()
    expect(states).toEqual(['loading'])

    doc.hidden = false
    await vi.advanceTimersByTimeAsync(MAPBOX_LOAD_DEADLINE_MS / 2)
    await run
    expect(rejected).toBeInstanceOf(Error)
    expect(states).toEqual(['loading', 'failed'])
  })

  it('clears its deadline once Mapbox has loaded', async () => {
    vi.useFakeTimers()
    const { d, states } = setup()

    await runMapboxLoadTask(d)
    expect(vi.getTimerCount()).toBe(0)
    expect(states).toEqual(['loading', 'ready'])
  })
})
