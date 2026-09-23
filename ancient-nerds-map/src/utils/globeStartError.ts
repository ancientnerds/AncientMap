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

/** The phase an error caught by the globe's boundary is reported under. */
export function failurePhase(error: unknown, globeReady: boolean): string {
  if (globeReady) return LIVE_PHASE
  return error instanceof GlobeStartError ? error.phase : 'start'
}
