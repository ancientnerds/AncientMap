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
 * - A task that has not finished after BG_TASK_DEADLINE_MS of visible time
 *   is aborted (its signal carries the reason), reported through
 *   `onTaskFailed`, and the queue moves on: a request that never answers must
 *   not hold everything queued behind it. What the task still does after that
 *   is not reported. Tasks with tighter limits of their own (Mapbox: 60 s for
 *   the chunk, 20 s for the map) keep them.
 * - A failure is reported through `onTaskFailed` and the queue moves on. A
 *   task the queue aborted on dispose is neither done nor failed; any other
 *   rejection, an AbortError included, is a failure.
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

/** Visible time a task gets before the queue aborts it and moves on. */
export const BG_TASK_DEADLINE_MS = 90_000

export interface GlobeBackgroundQueueDeps {
  /** Calls `cb` at the next idle moment; returns a cancel function. */
  scheduleIdle: (cb: () => void) => () => void
  isHidden: () => boolean
  /** Subscribes to visibility changes; returns an unsubscribe function. */
  onVisibilityChange: (cb: () => void) => () => void
  now: () => number
  /** Calls `cb` after `ms`; returns a cancel function (the per-task deadline). */
  setTimer: (cb: () => void, ms: number) => () => void
  onTaskDone: (name: BgTaskName, ms: number) => void
  onTaskFailed: (name: BgTaskName, err: unknown) => void
}

export function createGlobeBackgroundQueue(deps: GlobeBackgroundQueueDeps): GlobeBackgroundQueue {
  const pending: BgTask[] = []
  let started = false
  let disposed = false
  /** The running task, its controller and the stop of its deadline; null between tasks. */
  let running: { name: BgTaskName; ctrl: AbortController; stopDeadline: () => void } | null = null
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

  /**
   * Calls `onExpire` once `ms` of visible time have passed: the clock stops
   * while the tab is hidden and goes on with what was left when it is visible
   * again. Returns the stop.
   */
  function visibleDeadline(ms: number, onExpire: () => void): () => void {
    let left = ms
    let since = 0
    let cancelTimer: (() => void) | null = null
    const arm = () => {
      since = deps.now()
      cancelTimer = deps.setTimer(expire, Math.max(0, left))
    }
    const unsubscribe = deps.onVisibilityChange(() => {
      if (deps.isHidden() && cancelTimer) {
        cancelTimer()
        cancelTimer = null
        left -= deps.now() - since
      } else if (!deps.isHidden() && !cancelTimer) {
        arm()
      }
    })
    function expire(): void {
      cancelTimer = null
      unsubscribe()
      onExpire()
    }
    if (!deps.isHidden()) arm()
    return () => {
      cancelTimer?.()
      cancelTimer = null
      unsubscribe()
    }
  }

  function runNext(): void {
    const task = pending.shift()
    if (!task) return
    const ctrl = new AbortController()
    const stopDeadline = visibleDeadline(BG_TASK_DEADLINE_MS, () => {
      const err = new Error(`Background task ${task.name} did not finish within ${BG_TASK_DEADLINE_MS / 1000} s of visible time`)
      ctrl.abort(err)
      running = null
      deps.onTaskFailed(task.name, err)
      scheduleNext()
    })
    running = { name: task.name, ctrl, stopDeadline }
    const startedAt = deps.now()
    let result: Promise<void>
    try {
      result = task.run(ctrl.signal)
    } catch (err) {
      result = Promise.reject(err)
    }
    result.then(
      () => {
        if (ctrl.signal.aborted) return // disposed or past its deadline: already settled for the queue
        stopDeadline()
        running = null
        deps.onTaskDone(task.name, deps.now() - startedAt)
        scheduleNext()
      },
      (err: unknown) => {
        if (ctrl.signal.aborted) return // the queue stopped it (dispose, deadline): reported there or not at all
        stopDeadline()
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
      running?.stopDeadline()
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
export function browserQueueScheduling(): Pick<GlobeBackgroundQueueDeps, 'scheduleIdle' | 'isHidden' | 'onVisibilityChange' | 'now' | 'setTimer'> {
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
    setTimer: (cb, ms) => {
      const id = setTimeout(cb, ms)
      return () => clearTimeout(id)
    },
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
