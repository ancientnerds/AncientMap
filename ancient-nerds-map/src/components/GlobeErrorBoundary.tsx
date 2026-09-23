import React, { useCallback, useRef, useState } from 'react'
import { track } from '../analytics'
import { errorProps } from '../analytics/boot'
import { GlobeStartError, LIVE_PHASE } from '../utils/globeStartError'

/**
 * Catches what the globe throws - a WebGLRenderer that cannot be created, any
 * other error in its render or effects - and hands it to App, which shows the
 * error screen (GlobeErrorScreen) and reports it. Without it React unmounts the
 * whole page and leaves a black screen with only the footer.
 *
 * A boundary sees render and effect errors only. The globe's asynchronous
 * start steps (textures, labels, layers, shader compilation inside the frame
 * loop) reach it through useStartErrorBridge. Renders nothing once it caught:
 * App replaces the page.
 */
export default class GlobeErrorBoundary extends React.Component<
  { children: React.ReactNode; onError: (error: unknown) => void },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: unknown) {
    this.props.onError(error)
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

/** Contract C0: every critical loader of the globe reports its failure here, once. */
export type ReportStartError = (phase: string, err: unknown) => void

/**
 * The bridge from asynchronous start steps to GlobeErrorBoundary: a reported
 * failure is kept in state and thrown during the next render, which the
 * boundary catches. The first failure wins.
 *
 * After the globe is ready (isLive) nothing is torn down: the globe is on
 * screen, and a later failure of one of these loaders (a coastline switched
 * off and on again, labels reloaded after a context restore, a shader compiled
 * for a new layer) is logged and tracked as globe_error{phase: 'live'}.
 */
export function useStartErrorBridge(isLive: () => boolean): ReportStartError {
  const [startError, setStartError] = useState<GlobeStartError | null>(null)
  // isLive reads a ref of the caller; the report keeps one identity for every loader context
  const isLiveRef = useRef(isLive)
  isLiveRef.current = isLive
  const report = useCallback((phase: string, err: unknown) => {
    if (isLiveRef.current()) {
      console.error(`[globe ${LIVE_PHASE}] ${phase}`, err)
      const message = err instanceof Error ? err.message : String(err)
      track('globe_error', { phase: LIVE_PHASE, message: errorProps(`${phase}: ${message}`).message })
      return
    }
    // App logs and reports what the boundary hands over (failGlobe)
    setStartError(prev => prev ?? new GlobeStartError(phase, err))
  }, [])
  if (startError) throw startError
  return report
}
