/**
 * A background task of the globe (after the intro) failed. The already
 * visible globe stays as it is; the failure is logged with the task name and
 * tracked as `globe_error` with phase `bg:<task>`, which the dashboard keeps
 * apart from start failures (pipeline/umami_db.py SQL_GLOBE skips `bg:`).
 */

import { errorProps } from './boot'
import { track } from './index'

export function trackBackgroundFailure(task: string, err: unknown): void {
  console.error(`[globe bg] ${task}`, err)
  track('globe_error', { phase: `bg:${task}`, message: errorProps(err instanceof Error ? err.message : err).message })
}
