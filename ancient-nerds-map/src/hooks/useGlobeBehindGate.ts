/**
 * The phone gate can appear mid-load (a resize or a rotation below 768 px): App
 * renders it instead of the loading overlay and the Globe, which unmount, and
 * a fresh Globe mounts when it goes away. The load's ready moment belongs to the
 * Globe on screen (App's loadingComplete also requires the gate to be gone):
 * - before the load was complete, the old Globe's layers flag and its critical
 *   start items are dropped, so the overlay waits for the fresh Globe's own
 *   layers, globe_ready follows them and globe_abandon's phase names the fresh
 *   Globe's step;
 * - after it (the overlay faded or was fading), the overlay is removed: a fading
 *   overlay unmounted by the gate would come back with its fade already applied,
 *   so its transitionend, the only thing that removes it, never comes and the
 *   invisible overlay would take every click over the globe;
 * - either way a lost WebGL context goes with the Globe it belonged to: the
 *   fresh Globe has a context of its own and never reports a restore of the old
 *   one, so a kept loss would block its globe_ready and keep the loss notice
 *   over a working globe. The load's ending is already recorded by the latch.
 */

import { useEffect, useRef } from 'react'

export function useGlobeBehindGate(
  gateShowing: boolean,
  overlayFading: boolean,
  on: { resetLayers: () => void; removeOverlay: () => void; dropLostContext: () => void },
): void {
  const onRef = useRef(on)
  onRef.current = on
  useEffect(() => {
    if (!gateShowing) return
    if (overlayFading) onRef.current.removeOverlay()
    else onRef.current.resetLayers()
    onRef.current.dropLostContext()
  }, [gateShowing, overlayFading])
}
