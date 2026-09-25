/**
 * globe_ready: the load reached the globe. That is the moment the visitor sees
 * it - App's loading overlay fades once the sites, the critical layers and (focus
 * mode) the focus lookup are in, with no error screen and a live WebGL context.
 * The layers alone are not that moment: they are in at about 1.5 s on desktop,
 * often before the sites, and a sites failure or an abandon while the overlay
 * still waits is this load's ending (analytics/globeAbandon.ts).
 *
 * The latch closes before globe_ready is sent, so no ending follows it. The ref
 * turns true with it: later failures are 'live' (utils/globeStartError.ts).
 */

import { useEffect, useRef } from 'react'

import { track } from '../analytics'
import type { GlobeEndingLatch } from '../analytics/globeAbandon'

export function useGlobeReady(
  shown: boolean,
  latch: GlobeEndingLatch,
  readyRef: { current: boolean },
  onReady: () => void,
): void {
  const onReadyRef = useRef(onReady)
  onReadyRef.current = onReady
  useEffect(() => {
    if (!shown || readyRef.current) return
    readyRef.current = true
    latch.close()
    track('globe_ready', { ms: Math.round(performance.now()) })
    onReadyRef.current()
  }, [shown, latch, readyRef])
}
