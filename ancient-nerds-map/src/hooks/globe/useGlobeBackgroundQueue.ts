/**
 * The globe's background queue, wired: one queue per mount (services/globeBackgroundQueue.ts),
 * its tasks added once the basemap plan says what this device loads in the background,
 * started when the intro warp ends, disposed on unmount.
 *
 * - A finished task sends globe_bg, a failed one globe_error{phase:'bg:<task>'}
 *   (analytics/globeBackground.ts); unmounting aborts the running task (not a failure)
 *   and drops the rest.
 * - The plan exists before the start-tier gray is on the GPU, so always before the warp
 *   that starts the queue.
 * - A requested satellite that is not ready (never loaded, or its last load failed) loads
 *   at once, whoever asked for it (the panel toggle, demoApi.setSatellite): where the
 *   queue preloads it (desktops) its task moves to the front or is already running;
 *   elsewhere (touch devices, or its task is over) `requestSatellite` loads it directly.
 *   A context loss does not make it pending: useTextureLoading's restore reloads it.
 *
 * Every run is read when its task runs, so it may close over refs and context builders.
 */

import { useEffect, useMemo, useRef } from 'react'

import { trackBackgroundDone, trackBackgroundFailure } from '../../analytics/globeBackground'
import {
  createGlobeBackgroundQueue,
  type BgTask,
  type BgTaskName,
  type GlobeBackgroundQueue,
  type GlobeBackgroundQueueDeps,
} from '../../services/globeBackgroundQueue'
import type { BasemapPlan } from './useTextureLoading'

type Run = BgTask['run']

/** The browser side of the queue (browserQueueScheduling() in the app, a fake in tests). */
export type QueueScheduling = Pick<GlobeBackgroundQueueDeps, 'scheduleIdle' | 'isHidden' | 'onVisibilityChange' | 'now' | 'setTimer'>

/** The globe's background work. */
export interface GlobeBackgroundRuns {
  /** App: the site fields the globe payload leaves out (search and popups wait for them). */
  details: Run
  /** Coastlines and borders to their detail tier. */
  layers: Run
  /** mapbox-gl import and map init. */
  mapbox: Run
  /** The satellite at the start tier (queued only where the plan preloads it). */
  satellite: Run
  /** The gray basemap at the maximum tier (queued only where the plan upgrades it). */
  basemap: Run
  /** The rivers and lakes files a toggle at the current zoom would load. */
  riversLakes: Run
  /** App: the service worker; null where no worker is registered (dev builds). */
  sw: Run | null
}

/**
 * The tasks in their run order for this device: what search and popups wait for first, the
 * service worker last. The satellite only where the plan preloads it (desktops whose maximum
 * tier is high; touch devices load it on the first toggle), the gray upgrade only where the
 * maximum tier is above the start tier.
 */
export function buildGlobeBackgroundTasks(plan: BasemapPlan, runs: GlobeBackgroundRuns): BgTask[] {
  const order: Array<[BgTaskName, Run | null]> = [
    ['details', runs.details],
    ['layers', runs.layers],
    ['mapbox', runs.mapbox],
    ['satellite', plan.preloadSatellite ? runs.satellite : null],
    ['basemap', plan.upgradeGray ? runs.basemap : null],
    ['rivers_lakes', runs.riversLakes],
    ['sw', runs.sw],
  ]
  return order.flatMap(([name, run]) => (run ? [{ name, run }] : []))
}

export interface GlobeBackgroundControl {
  /** The intro warp ended: the queue starts (idempotent). Runs inside that frame: it only books an idle moment. */
  start(): void
  /** Moves a pending task to the front (see GlobeBackgroundQueue.promote); false after unmount. */
  promote(name: BgTaskName): boolean
}

interface UseGlobeBackgroundQueueOptions {
  /** null until the scene exists (useTextureLoading). */
  plan: BasemapPlan | null
  runs: GlobeBackgroundRuns
  /** The satellite is switched on and not ready: never loaded, or its last load failed (a context loss does not count). */
  satellitePending: boolean
  /** Loads the satellite outside the queue (useTextureLoading), reporting a failure itself. */
  requestSatellite: () => void
  /** Called once per mount, when the queue is created. */
  scheduling: () => QueueScheduling
}

export function useGlobeBackgroundQueue({
  plan,
  runs,
  satellitePending,
  requestSatellite,
  scheduling,
}: UseGlobeBackgroundQueueOptions): GlobeBackgroundControl {
  const runsRef = useRef(runs)
  runsRef.current = runs
  const schedulingRef = useRef(scheduling)
  schedulingRef.current = scheduling
  /** This mount's queue; null before the first effect and after unmount. */
  const backgroundRef = useRef<{ queue: GlobeBackgroundQueue; tasksAdded: boolean } | null>(null)

  useEffect(() => {
    const queue = createGlobeBackgroundQueue({
      ...schedulingRef.current(),
      onTaskDone: trackBackgroundDone,
      onTaskFailed: trackBackgroundFailure,
    })
    backgroundRef.current = { queue, tasksAdded: false }
    return () => {
      backgroundRef.current = null
      queue.dispose()
    }
  }, [])

  // The tasks, once per queue, as soon as the plan is known
  useEffect(() => {
    const background = backgroundRef.current
    if (!background || background.tasksAdded || !plan) return
    background.tasksAdded = true
    const now = (pick: (r: GlobeBackgroundRuns) => Run): Run => signal => pick(runsRef.current)(signal)
    const tasks = buildGlobeBackgroundTasks(plan, {
      details: now(r => r.details),
      layers: now(r => r.layers),
      mapbox: now(r => r.mapbox),
      satellite: now(r => r.satellite),
      basemap: now(r => r.basemap),
      riversLakes: now(r => r.riversLakes),
      // Fixed per build (App registers a worker only in production builds)
      sw: runsRef.current.sw,
    })
    for (const task of tasks) background.queue.add(task)
  }, [plan])

  // A requested satellite that is not ready: its task first, or a direct load
  useEffect(() => {
    if (!satellitePending || !plan) return
    if (backgroundRef.current?.queue.promote('satellite')) return
    requestSatellite()
  }, [satellitePending, plan, requestSatellite])

  return useMemo(() => ({
    start: () => { backgroundRef.current?.queue.start() },
    promote: name => backgroundRef.current?.queue.promote(name) ?? false,
  }), [])
}
