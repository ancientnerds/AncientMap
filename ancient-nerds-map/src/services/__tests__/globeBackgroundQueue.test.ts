/**
 * The globe's background queue (contract C6): what the first frame does not
 * show loads after the intro, one task at a time, each after an idle moment,
 * never while the tab is hidden. A failure is reported and the queue moves on;
 * a task the queue itself aborted (dispose) is neither done nor failed.
 * Node environment, every browser dependency injected.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  browserQueueScheduling,
  createGlobeBackgroundQueue,
  globeBackgroundTasks,
  type BgTask,
  type BgTaskName,
} from '../globeBackgroundQueue'

const flush = async () => {
  for (let i = 0; i < 5; i++) await Promise.resolve()
}

interface Deferred {
  task: BgTask
  starts: number
  signal: AbortSignal | null
  resolve: () => void
  reject: (err: unknown) => void
}

function deferred(name: BgTaskName): Deferred {
  const d: Deferred = {
    starts: 0,
    signal: null,
    resolve: () => { throw new Error(`${name} has not started`) },
    reject: () => { throw new Error(`${name} has not started`) },
    task: {
      name,
      run: signal => {
        d.starts++
        d.signal = signal
        return new Promise<void>((resolve, reject) => {
          d.resolve = resolve
          d.reject = reject
        })
      },
    },
  }
  return d
}

function harness() {
  const idle: Array<() => void> = []
  const visibility = new Set<() => void>()
  const page = { hidden: false, time: 0 }
  const done: Array<[BgTaskName, number]> = []
  const failed: Array<[BgTaskName, unknown]> = []
  const queue = createGlobeBackgroundQueue({
    scheduleIdle: cb => {
      idle.push(cb)
      return () => {
        const i = idle.indexOf(cb)
        if (i !== -1) idle.splice(i, 1)
      }
    },
    isHidden: () => page.hidden,
    onVisibilityChange: cb => {
      visibility.add(cb)
      return () => { visibility.delete(cb) }
    },
    now: () => page.time,
    onTaskDone: (name, ms) => { done.push([name, ms]) },
    onTaskFailed: (name, err) => { failed.push([name, err]) },
  })
  /** Fires the oldest idle callback, then lets the promise chains settle. */
  const runIdle = async () => {
    const cb = idle.shift()
    if (!cb) throw new Error('no idle callback is scheduled')
    cb()
    await flush()
  }
  const setHidden = async (hidden: boolean) => {
    page.hidden = hidden
    for (const cb of [...visibility]) cb()
    await flush()
  }
  return { queue, idle, visibility, page, done, failed, runIdle, setHidden }
}

describe('createGlobeBackgroundQueue', () => {
  it('runs the tasks in add order, one at a time', async () => {
    const h = harness()
    const a = deferred('details')
    const b = deferred('layers')
    h.queue.add(a.task)
    h.queue.add(b.task)
    h.queue.start()
    await h.runIdle()
    expect([a.starts, b.starts]).toEqual([1, 0])
    a.resolve()
    await flush()
    await h.runIdle()
    expect([a.starts, b.starts]).toEqual([1, 1])
    b.resolve()
    await flush()
    expect(h.done.map(([name]) => name)).toEqual(['details', 'layers'])
    expect(h.idle).toHaveLength(0)
  })

  it('waits for an idle moment before the first task and between tasks', async () => {
    const h = harness()
    const a = deferred('details')
    const b = deferred('layers')
    h.queue.add(a.task)
    h.queue.add(b.task)
    h.queue.start()
    await flush()
    // start() only schedules: it runs inside the animation frame that ends the warp
    expect(a.starts).toBe(0)
    expect(h.idle).toHaveLength(1)
    await h.runIdle()
    expect(a.starts).toBe(1)
    expect(h.idle).toHaveLength(0)
    a.resolve()
    await flush()
    expect(b.starts).toBe(0)
    expect(h.idle).toHaveLength(1)
    await h.runIdle()
    expect(b.starts).toBe(1)
  })

  it('pauses while the tab is hidden and resumes when it is visible again', async () => {
    const h = harness()
    const a = deferred('details')
    const b = deferred('layers')
    h.queue.add(a.task)
    h.queue.add(b.task)
    h.queue.start()
    await h.runIdle()
    a.resolve()
    await flush()
    await h.setHidden(true)
    await h.runIdle() // the idle moment arrives while hidden: nothing starts
    expect(b.starts).toBe(0)
    expect(h.idle).toHaveLength(0)
    expect(h.visibility.size).toBe(1)
    await h.setHidden(false)
    expect(h.visibility.size).toBe(0) // listens only while it waits
    expect(b.starts).toBe(0) // visible again: first another idle moment
    await h.runIdle()
    expect(b.starts).toBe(1)
  })

  it('does not start while hidden at start(), and a hide/show without a pending task changes nothing', async () => {
    const h = harness()
    const a = deferred('details')
    h.queue.add(a.task)
    h.page.hidden = true
    h.queue.start()
    await h.runIdle()
    expect(a.starts).toBe(0)
    await h.setHidden(false)
    await h.runIdle()
    expect(a.starts).toBe(1)
    await h.setHidden(true) // hidden while running: the task itself decides (rAF pauses, deadlines count visible time)
    expect(h.visibility.size).toBe(0)
    a.resolve()
    await flush()
    expect(h.done).toEqual([['details', 0]])
  })

  it('reports a failing task and still runs the next one', async () => {
    const h = harness()
    const a = deferred('details')
    const b = deferred('layers')
    h.queue.add(a.task)
    h.queue.add(b.task)
    h.queue.start()
    await h.runIdle()
    const err = new Error('/api/sites/all: HTTP 502')
    a.reject(err)
    await flush()
    expect(h.failed).toEqual([['details', err]])
    expect(h.done).toEqual([])
    await h.runIdle()
    expect(b.starts).toBe(1)
  })

  it('reports a task that throws synchronously and moves on', async () => {
    const h = harness()
    const err = new Error('Vector layers: the layer worker is not running')
    const b = deferred('rivers_lakes')
    h.queue.add({ name: 'layers', run: () => { throw err } })
    h.queue.add(b.task)
    h.queue.start()
    await h.runIdle()
    expect(h.failed).toEqual([['layers', err]])
    await h.runIdle()
    expect(b.starts).toBe(1)
  })

  it('an AbortError the queue did not cause is a failure like any other', async () => {
    const h = harness()
    const a = deferred('mapbox')
    h.queue.add(a.task)
    h.queue.start()
    await h.runIdle()
    const err = new DOMException('The operation was aborted.', 'AbortError')
    a.reject(err)
    await flush()
    expect(h.failed).toEqual([['mapbox', err]])
  })

  it('promote moves a pending task to the front; true while the task is still to come or running', async () => {
    const h = harness()
    const a = deferred('details')
    const b = deferred('layers')
    const c = deferred('satellite')
    h.queue.add(a.task)
    h.queue.add(b.task)
    h.queue.add(c.task)
    h.queue.start()
    await h.runIdle()
    expect(h.queue.promote('details')).toBe(true) // running: nothing moves, the caller just waits for it
    expect(h.queue.promote('basemap')).toBe(false) // never added
    expect(h.queue.promote('satellite')).toBe(true)
    expect(a.starts).toBe(1)
    a.resolve()
    await flush()
    await h.runIdle()
    expect([b.starts, c.starts]).toEqual([0, 1])
    c.resolve()
    await flush()
    expect(h.queue.promote('satellite')).toBe(false) // done
    await h.runIdle()
    expect(b.starts).toBe(1)
  })

  it('promote before start puts the task first', async () => {
    const h = harness()
    const a = deferred('details')
    const c = deferred('satellite')
    h.queue.add(a.task)
    h.queue.add(c.task)
    expect(h.queue.promote('satellite')).toBe(true)
    h.queue.start()
    await h.runIdle()
    expect([a.starts, c.starts]).toEqual([0, 1])
  })

  it('start is idempotent', async () => {
    const h = harness()
    const a = deferred('details')
    h.queue.add(a.task)
    h.queue.start()
    h.queue.start()
    expect(h.idle).toHaveLength(1)
    await h.runIdle()
    h.queue.start()
    await flush()
    expect(h.idle).toHaveLength(0)
    expect(a.starts).toBe(1)
  })

  it('runs nothing before start', async () => {
    const h = harness()
    const a = deferred('details')
    h.queue.add(a.task)
    await flush()
    expect(h.idle).toHaveLength(0)
    expect(a.starts).toBe(0)
  })

  it('a task added after the queue ran dry runs after the next idle moment', async () => {
    const h = harness()
    const a = deferred('details')
    const b = deferred('sw')
    h.queue.add(a.task)
    h.queue.start()
    await h.runIdle()
    a.resolve()
    await flush()
    expect(h.idle).toHaveLength(0)
    h.queue.add(b.task)
    expect(h.idle).toHaveLength(1)
    await h.runIdle()
    expect(b.starts).toBe(1)
  })

  it('dispose aborts the running task, reports nothing for it and runs nothing more', async () => {
    const h = harness()
    const a = deferred('mapbox')
    const b = deferred('satellite')
    h.queue.add(a.task)
    h.queue.add(b.task)
    h.queue.start()
    await h.runIdle()
    h.queue.dispose()
    expect(a.signal?.aborted).toBe(true)
    a.reject(a.signal?.reason)
    await flush()
    expect(h.failed).toEqual([])
    expect(h.done).toEqual([])
    expect(h.idle).toHaveLength(0)
    expect(b.starts).toBe(0)
  })

  it('a task that finishes after dispose is not reported either', async () => {
    const h = harness()
    const a = deferred('details')
    h.queue.add(a.task)
    h.queue.start()
    await h.runIdle()
    h.queue.dispose()
    a.resolve()
    await flush()
    expect(h.done).toEqual([])
  })

  it('dispose cancels a scheduled idle callback and the visibility wait', async () => {
    const h = harness()
    const a = deferred('details')
    h.queue.add(a.task)
    h.queue.start()
    expect(h.idle).toHaveLength(1)
    h.queue.dispose()
    expect(h.idle).toHaveLength(0)

    const g = harness()
    g.queue.add(deferred('details').task)
    g.page.hidden = true
    g.queue.start()
    await g.runIdle()
    expect(g.visibility.size).toBe(1)
    g.queue.dispose()
    expect(g.visibility.size).toBe(0)
  })

  it('is inert after dispose', async () => {
    const h = harness()
    const a = deferred('details')
    h.queue.add(a.task)
    h.queue.dispose()
    h.queue.start()
    h.queue.add(deferred('layers').task)
    expect(h.queue.promote('details')).toBe(false)
    await flush()
    expect(h.idle).toHaveLength(0)
    expect(a.starts).toBe(0)
  })

  it('reports the measured run time of each task (idle waits excluded)', async () => {
    const h = harness()
    const a = deferred('layers')
    h.queue.add(a.task)
    h.queue.start()
    h.page.time = 100
    await h.runIdle()
    h.page.time = 350
    a.resolve()
    await flush()
    expect(h.done).toEqual([['layers', 250]])
  })

  it('gives every task its own signal', async () => {
    const h = harness()
    const a = deferred('details')
    const b = deferred('layers')
    h.queue.add(a.task)
    h.queue.add(b.task)
    h.queue.start()
    await h.runIdle()
    a.resolve()
    await flush()
    await h.runIdle()
    expect(a.signal).not.toBe(b.signal)
    h.queue.dispose()
    expect(b.signal?.aborted).toBe(true)
  })
})

describe('globeBackgroundTasks', () => {
  const run = (label: string) => Object.assign(async () => {}, { label })
  const base = {
    details: run('details'),
    layers: run('layers'),
    labels: run('labels'),
    mapbox: run('mapbox'),
    satellite: run('satellite'),
    basemap: run('basemap'),
    riversLakes: run('rivers_lakes'),
    sw: run('sw'),
  }

  it('orders the tasks: details, layers, labels, mapbox, satellite, basemap, rivers_lakes, sw', () => {
    const tasks = globeBackgroundTasks(base)
    expect(tasks.map(t => t.name)).toEqual(['details', 'layers', 'labels', 'mapbox', 'satellite', 'basemap', 'rivers_lakes', 'sw'])
    expect(tasks.map(t => (t.run as unknown as { label: string }).label)).toEqual(tasks.map(t => t.name))
  })

  it('leaves out what this device or build does not do in the background', () => {
    const tasks = globeBackgroundTasks({ ...base, satellite: null, basemap: null, sw: null })
    expect(tasks.map(t => t.name)).toEqual(['details', 'layers', 'labels', 'mapbox', 'rivers_lakes'])
  })
})

describe('browserQueueScheduling', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('uses requestIdleCallback with a 2 s timeout where the browser has it', () => {
    const cancel = vi.fn()
    const ric = vi.fn().mockReturnValue(7)
    vi.stubGlobal('requestIdleCallback', ric)
    vi.stubGlobal('cancelIdleCallback', cancel)
    const cb = vi.fn()
    const stop = browserQueueScheduling().scheduleIdle(cb)
    expect(ric).toHaveBeenCalledWith(expect.any(Function), { timeout: 2000 })
    ;(ric.mock.calls[0][0] as () => void)()
    expect(cb).toHaveBeenCalledTimes(1)
    stop()
    expect(cancel).toHaveBeenCalledWith(7)
  })

  it('waits 50 ms where it does not (Safari)', () => {
    vi.useFakeTimers()
    vi.stubGlobal('requestIdleCallback', undefined)
    const cb = vi.fn()
    browserQueueScheduling().scheduleIdle(cb)
    vi.advanceTimersByTime(49)
    expect(cb).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(cb).toHaveBeenCalledTimes(1)
    const cb2 = vi.fn()
    const stop = browserQueueScheduling().scheduleIdle(cb2)
    stop()
    vi.advanceTimersByTime(100)
    expect(cb2).not.toHaveBeenCalled()
  })

  it('reads the page visibility from document and listens for its changes', () => {
    const listeners = new Map<string, () => void>()
    const doc = {
      hidden: true,
      addEventListener: vi.fn((type: string, cb: () => void) => { listeners.set(type, cb) }),
      removeEventListener: vi.fn((type: string) => { listeners.delete(type) }),
    }
    vi.stubGlobal('document', doc)
    const s = browserQueueScheduling()
    expect(s.isHidden()).toBe(true)
    doc.hidden = false
    expect(s.isHidden()).toBe(false)
    const cb = vi.fn()
    const off = s.onVisibilityChange(cb)
    listeners.get('visibilitychange')?.()
    expect(cb).toHaveBeenCalledTimes(1)
    off()
    expect(listeners.has('visibilitychange')).toBe(false)
  })

  it('touches no browser global until it is called (SSR-safe module scope)', async () => {
    vi.stubGlobal('document', undefined)
    vi.stubGlobal('window', undefined)
    vi.resetModules()
    const mod = await import('../globeBackgroundQueue')
    expect(typeof mod.createGlobeBackgroundQueue).toBe('function')
  })
})
