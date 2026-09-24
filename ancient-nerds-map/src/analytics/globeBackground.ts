/**
 * The globe's background tasks (after the intro) in analytics. A finished task
 * sends `globe_bg` with its run time. A failed one leaves the already visible
 * globe as it is; the failure is logged with the task name and tracked as
 * `globe_error` with phase `bg:<task>`, which the dashboard keeps apart from
 * start failures (pipeline/umami_db.py SQL_GLOBE skips `bg:`).
 */

import { errorProps } from './boot'
import { track } from './index'
import type { BgTaskName } from '../services/globeBackgroundQueue'

export function trackBackgroundDone(task: BgTaskName, ms: number): void {
  track('globe_bg', { task, ms: Math.round(ms) })
}

/** A queue task, or the hi-res coastline (loaded on zoom when Mapbox is out, outside the queue). */
export function trackBackgroundFailure(task: BgTaskName | 'hires', err: unknown): void {
  console.error(`[globe bg] ${task}`, err)
  track('globe_error', { phase: `bg:${task}`, message: errorProps(err instanceof Error ? err.message : err).message })
}
