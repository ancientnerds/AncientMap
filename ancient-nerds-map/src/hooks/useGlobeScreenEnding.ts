/**
 * The ending event of a screen that ends a load of /globe.html:
 * GlobeUnsupported (globe_unsupported) and GlobeErrorScreen for a start failure
 * (globe_error). It is sent once the screen actually shows. While the phone gate
 * is up the screen waits behind it (App renders the gate first): the sites can
 * fail behind the gate, and a gate link used then is this load's ending
 * (globe_gate), not a failure the visitor never saw. The latch
 * (analytics/globeAbandon.ts) keeps it to one ending per load.
 */

import { useEffect } from 'react'

import type { EventProps } from '../analytics'
import type { GlobeEndingLatch } from '../analytics/globeAbandon'

export interface ScreenEnding {
  name: 'globe_unsupported' | 'globe_error'
  props: EventProps
}

export function useGlobeScreenEnding(latch: GlobeEndingLatch, ending: ScreenEnding | null, gateShowing: boolean): void {
  useEffect(() => {
    if (!ending || gateShowing) return
    latch.end(ending.name, ending.props)
  }, [latch, ending, gateShowing])
}
