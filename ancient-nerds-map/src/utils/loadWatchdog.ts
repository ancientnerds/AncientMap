/**
 * Loading watchdog of the globe's start (spec §5.8). When no critical item
 * (sites, scene, basemap, labels, coastlines, borders) has progressed for
 * START_STALL_MS of visible time, onStall runs; App then offers a reload in the
 * overlay's hint box. Loading itself continues, and the next progress clears it.
 *
 * Plain timers, no requestAnimationFrame. The owner pauses it while the tab is
 * hidden (timers are throttled there and the page is not being watched) and
 * resumes it with a fresh wait when the tab comes back.
 */

export const START_STALL_MS = 20_000

export interface StallWatchdog {
  /** A critical item finished: the wait starts again. */
  progress(): void
  /** The tab went hidden: the clock stops. */
  pause(): void
  /** The tab is visible again: a fresh wait. */
  resume(): void
  /** The start ended (ready, failed, context lost): never fires again. */
  stop(): void
}

export function createStallWatchdog(opts: { timeoutMs: number; onStall: () => void; paused?: boolean }): StallWatchdog {
  let timer: ReturnType<typeof setTimeout> | null = null
  let paused = opts.paused ?? false
  let stopped = false

  const clear = () => {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }
  const arm = () => {
    clear()
    if (paused || stopped) return
    timer = setTimeout(() => {
      timer = null
      opts.onStall()
    }, opts.timeoutMs)
  }

  arm()
  return {
    progress: arm,
    pause() {
      paused = true
      clear()
    },
    resume() {
      paused = false
      arm()
    },
    stop() {
      stopped = true
      clear()
    },
  }
}
