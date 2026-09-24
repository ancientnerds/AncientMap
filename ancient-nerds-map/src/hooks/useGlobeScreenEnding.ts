/**
 * The ending event of a screen that ends a load of /globe.html:
 * GlobeUnsupported (globe_unsupported) and GlobeErrorScreen for a start failure
 * (globe_error). It is sent once the screen actually shows. While the phone gate
 * is up the screen waits behind it (App renders the gate first): the sites can
 * fail behind the gate, and a gate link used then is this load's ending
 * (globe_gate), not a failure the visitor never saw. The latch
 * (analytics/globeAbandon.ts) keeps it to one ending per load.
 *
 * A start failure whose load already ended - a tab switch while loading sent
 * globe_abandon, and the visitor came back to the error screen - is still sent
 * with its phase and message, marked `ending: 'no'`: they are the only
 * diagnosis of a failed start, and SQL_GLOBE's `failed` skips the mark, so the
 * load keeps one ending.
 *
 * Each ending is handled once: the effect runs again whenever the window passes
 * through the phone gate (a resize across the phone width), and a second pass
 * must not send the failure again - the latch would read it as closed by
 * another ending and send a marked copy of a failure already sent.
 */

import { useEffect, useRef } from 'react'

import { track, type EventProps } from '../analytics'
import type { GlobeEndingLatch } from '../analytics/globeAbandon'

export interface ScreenEnding {
  name: 'globe_unsupported' | 'globe_error'
  props: EventProps
}

export function useGlobeScreenEnding(latch: GlobeEndingLatch, ending: ScreenEnding | null, gateShowing: boolean): void {
  const handled = useRef<ScreenEnding | null>(null)
  useEffect(() => {
    if (!ending || gateShowing || handled.current === ending) return
    handled.current = ending
    if (latch.end(ending.name, ending.props) || ending.name !== 'globe_error') return
    track('globe_error', { ...ending.props, ending: 'no' })
  }, [latch, ending, gateShowing])
}
