/**
 * The globe's background queue (contract C6). What the first frame does not
 * show loads after the intro warp: the site details, the coastline and border
 * detail tier, Mapbox, the satellite, the sharper gray basemap, the rivers and
 * lakes a toggle would need, and the service worker.
 *
 * - One task at a time, in add order; `promote` moves a pending task to the
 *   front (the satellite toggle asks for its texture before its turn).
 * - Every task starts after an idle moment (`scheduleIdle`), so the frame that
 *   ends the warp and the frames between two tasks stay free.
 * - Nothing starts while the tab is hidden; the queue waits for it to be
 *   visible again. A task that is already running decides for itself (strip
 *   uploads pause with requestAnimationFrame, Mapbox deadlines count visible
 *   time).
 * - A failure is reported through `onTaskFailed` and the queue moves on. A
 *   task the queue aborted itself (dispose) is neither done nor failed; any
 *   other rejection, an AbortError included, is a failure.
 *
 * No browser access at module scope; `browserQueueScheduling` reads the
 * browser only when it is called.
 */

export type BgTaskName = 'details' | 'layers' | 'mapbox' | 'satellite' | 'basemap' | 'rivers_lakes' | 'sw'

export interface BgTask {
  name: BgTaskName
  run: (signal: AbortSignal) => Promise<void>
}

export interface GlobeBackgroundQueue {
  /** Appends; the order of add() is the run order. Inert after dispose. */
  add(task: BgTask): void
  /**
   * Moves a pending task to the front. True when the task is still to come
   * (now next in line) or running; false when it is done, failed, was dropped
   * or never added (the caller then does the work itself).
   */
  promote(name: BgTaskName): boolean
  /** Starts running (idempotent). */
  start(): void
  /** Aborts the running task and drops the rest; the queue is inert afterwards. */
  dispose(): void
}

export interface GlobeBackgroundQueueDeps {
  /** Calls `cb` at the next idle moment; returns a cancel function. */
  scheduleIdle: (cb: () => void) => () => void
  isHidden: () => boolean
  /** Subscribes to visibility changes; returns an unsubscribe function. */
  onVisibilityChange: (cb: () => void) => () => void
  now: () => number
  onTaskDone: (name: BgTaskName, ms: number) => void
  onTaskFailed: (name: BgTaskName, err: unknown) => void
}

export function createGlobeBackgroundQueue(deps: GlobeBackgroundQueueDeps): GlobeBackgroundQueue {
  const pending: BgTask[] = []
  let started = false
  let disposed = false
  /** The running task and its controller; null between tasks. */
  let running: { name: BgTaskName; ctrl: AbortController } | null = null
  /** Cancels the scheduled idle callback or the visibility wait; null when neither is booked. */
  let cancelWait: (() => void) | null = null

  const waiting = () => cancelWait !== null

  /** Books the next task (after an idle moment, and not while hidden) unless something is booked or running. */
  function scheduleNext(): void {
    if (disposed || !started || running || waiting() || pending.length === 0) return
    cancelWait = deps.scheduleIdle(() => {
      cancelWait = null
      if (deps.isHidden()) {
        waitUntilVisible()
        return
      }
      runNext()
    })
  }

  function waitUntilVisible(): void {
    const unsubscribe = deps.onVisibilityChange(() => {
      if (deps.isHidden()) return
      unsubscribe()
      cancelWait = null
      scheduleNext()
    })
    cancelWait = unsubscribe
  }

  function runNext(): void {
    const task = pending.shift()
    if (!task) return
    const ctrl = new AbortController()
    running = { name: task.name, ctrl }
    const startedAt = deps.now()
    let result: Promise<void>
    try {
      result = task.run(ctrl.signal)
    } catch (err) {
      result = Promise.reject(err)
    }
    result.then(
      () => {
        if (ctrl.signal.aborted) return // disposed while it ran
        running = null
        deps.onTaskDone(task.name, deps.now() - startedAt)
        scheduleNext()
      },
      (err: unknown) => {
        if (ctrl.signal.aborted) return // the queue cancelled it: not a failure
        running = null
        deps.onTaskFailed(task.name, err)
        scheduleNext()
      },
    )
  }

  return {
    add(task) {
      if (disposed) return
      pending.push(task)
      scheduleNext()
    },
    promote(name) {
      if (disposed) return false
      if (running?.name === name) return true
      const index = pending.findIndex(task => task.name === name)
      if (index === -1) return false
      const [task] = pending.splice(index, 1)
      pending.unshift(task)
      return true
    },
    start() {
      if (started || disposed) return
      started = true
      scheduleNext()
    },
    dispose() {
      if (disposed) return
      disposed = true
      pending.length = 0
      cancelWait?.()
      cancelWait = null
      running?.ctrl.abort(new DOMException('The globe background queue was disposed', 'AbortError'))
      running = null
    },
  }
}

/**
 * The browser side of the queue's scheduling. `requestIdleCallback` with a 2 s
 * timeout where the browser has it; Safari has none, so there a short timer
 * stands in (feature detection, not a fallback: the queue only needs "not in
 * this frame").
 */
export function browserQueueScheduling(): Pick<GlobeBackgroundQueueDeps, 'scheduleIdle' | 'isHidden' | 'onVisibilityChange' | 'now'> {
  return {
    scheduleIdle: cb => {
      if (typeof requestIdleCallback === 'function') {
        const id = requestIdleCallback(() => cb(), { timeout: 2000 })
        return () => cancelIdleCallback(id)
      }
      const id = setTimeout(cb, 50)
      return () => clearTimeout(id)
    },
    isHidden: () => document.hidden,
    onVisibilityChange: cb => {
      document.addEventListener('visibilitychange', cb)
      return () => document.removeEventListener('visibilitychange', cb)
    },
    now: () => performance.now(),
  }
}

/** The globe's background work; null where this device or build does not do it in the background. */
export interface GlobeBackgroundRuns {
  /** App: the site fields the globe payload leaves out (search and popups wait for them). */
  details: BgTask['run']
  /** Coastlines and borders to their detail tier. */
  layers: BgTask['run']
  /** mapbox-gl import and map init. */
  mapbox: BgTask['run']
  /** The satellite at the start tier (desktops whose maximum tier is high; touch devices load it on the first toggle). */
  satellite: BgTask['run'] | null
  /** The gray basemap at the maximum tier (when it is above the start tier). */
  basemap: BgTask['run'] | null
  /** The rivers and lakes files a toggle at the current zoom would load. */
  riversLakes: BgTask['run']
  /** App: the service worker (production builds only). */
  sw: BgTask['run'] | null
}

/** The tasks in their run order: what search and popups wait for first, the service worker last. */
export function globeBackgroundTasks(runs: GlobeBackgroundRuns): BgTask[] {
  const order: Array<[BgTaskName, BgTask['run'] | null]> = [
    ['details', runs.details],
    ['layers', runs.layers],
    ['mapbox', runs.mapbox],
    ['satellite', runs.satellite],
    ['basemap', runs.basemap],
    ['rivers_lakes', runs.riversLakes],
    ['sw', runs.sw],
  ]
  return order.flatMap(([name, run]) => (run ? [{ name, run }] : []))
}
