/**
 * Errors of the globe's start and the phase they are reported under
 * (globe_error{phase, message}; pipeline/umami_db.py SQL_GLOBE counts every
 * phase except 'bg:*' and LIVE_PHASE as a start failure).
 *
 * Phases in use: 'renderer' (WebGLRenderer construction), 'scene' (the rest of
 * initializeScene), 'shader', 'basemap', 'labels', 'coastlines',
 * 'countryBorders', 'sites', and 'start' for any other error the boundary
 * catches before the globe is ready.
 */

/** Errors after globe_ready: the globe had been on screen. Not a start failure. */
export const LIVE_PHASE = 'live'

/** A failure of one step of the start, carrying the step's name. */
export class GlobeStartError extends Error {
  readonly phase: string
  readonly cause: unknown

  constructor(phase: string, cause: unknown) {
    super(cause instanceof Error ? cause.message : String(cause))
    this.name = 'GlobeStartError'
    this.phase = phase
    this.cause = cause
  }
}

/**
 * The phase and the error App's failGlobe gets for an error the globe's boundary
 * caught. After globe_ready the phase is LIVE_PHASE; a GlobeStartError then comes
 * from a Globe mounted again after the phone gate, and its step stays in the
 * message ('basemap: HTTP 502'), as the loader bridge's own live path keeps it.
 */
export function boundaryFailure(error: unknown, globeReady: boolean): { phase: string; error: unknown } {
  if (!(error instanceof GlobeStartError)) return { phase: globeReady ? LIVE_PHASE : 'start', error }
  if (!globeReady) return { phase: error.phase, error: error.cause }
  return { phase: LIVE_PHASE, error: new Error(`${error.phase}: ${error.message}`) }
}
