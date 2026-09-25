/**
 * How a load of /globe.html ends when it never reaches the globe.
 *
 * The dashboard (pipeline/umami_db.py SQL_GLOBE, folded by
 * stats_analysis.globe_funnel) splits the loads without globe_ready by their
 * ending event. Umami carries no page-load id, so the fold is per session and
 * trusts the frontend to send AT MOST ONE ending per load:
 *
 *   globe_gate        a phone-gate choice other than the globe
 *   globe_unsupported the capability check failed, once its screen shows
 *   globe_error       a start failure (not 'bg:' or 'live'), once its screen shows
 *                     (App: failGlobe, hooks/useGlobeScreenEnding.ts; never behind the gate).
 *                     After another ending it is sent marked {ending:'no'}: diagnosis only
 *   globe_abandon     the page was hidden or left before globe_ready
 *   webgl_lost        {phase:'loading'}: the WebGL context died before globe_ready
 *
 * All five go through one latch per load; globe_ready closes it too, so a
 * load that reached the globe never sends an ending afterwards.
 *
 * globe_abandon rides on the tracker's own transport: Umami 3.4's
 * `umami.track` issues fetch(…, {keepalive: true}) synchronously inside the
 * call, which survives the unload like a beacon would. Before the tracker has
 * loaded the event waits in analytics/index.ts's queue and is lost with the
 * page; the dashboard reads that as "no signal".
 *
 * Module scope touches no browser global (SSR-safe import).
 */

import { track, type EventProps } from './index'
import type { FallbackPage } from '../components/globeFallbackLinks'

/** The critical items of the start, in the order the abandon phase names the first one missing. */
export const START_ITEMS = ['sites', 'scene', 'basemap', 'labels', 'coastlines', 'countryBorders'] as const
export type StartItem = (typeof START_ITEMS)[number]

/** globe_abandon's phase: the gate, or the first critical item still missing. */
export type AbandonPhase = 'gate' | StartItem

/** The phone gate's controls (globe_gate's choice). */
export type GateChoice = 'globe' | FallbackPage

type GlobeEnding = 'globe_gate' | 'globe_unsupported' | 'globe_error' | 'globe_abandon' | 'webgl_lost'

export interface GlobeEndingLatch {
  /** Nothing has ended this load yet, and the globe is not ready. */
  readonly open: boolean
  /** Sends the ending if it is the first of this load; returns whether it was sent. */
  end(name: GlobeEnding, props: EventProps): boolean
  /** The globe is ready: this load sends no ending any more. */
  close(): void
}

export function createGlobeEndingLatch(): GlobeEndingLatch {
  let open = true
  return {
    get open() {
      return open
    },
    end(name, props) {
      if (!open) return false
      open = false
      track(name, props)
      return true
    },
    close() {
      open = false
    },
  }
}

/** A phone-gate control was used. The globe button lets the load go on; every link ends it. */
export function reportGateChoice(choice: GateChoice, latch: GlobeEndingLatch): void {
  if (choice === 'globe') track('globe_gate', { choice })
  else latch.end('globe_gate', { choice })
}

/**
 * The globe's WebGL context died: webgl_lost{reason, phase}. 'loading' means the
 * visitor never saw a globe; the dashboard counts it as this load's ending (an
 * error), so it goes through the latch, and a load that already ended (a hidden
 * phone tab that sent globe_abandon, then lost its context) sends nothing more.
 * 'live' follows globe_ready and is no ending: it is sent on every loss.
 */
export function reportWebglLost(latch: GlobeEndingLatch, reason: string, globeReady: boolean): void {
  const phase = globeReady ? 'live' : 'loading'
  if (phase === 'live') track('webgl_lost', { reason, phase })
  else latch.end('webgl_lost', { reason, phase })
}

/**
 * Where the load is: 'gate' while the phone gate shows, else the first
 * critical item not yet in. Once every item is in, the load waits only for
 * the focus lookup (focus links) and globe_ready itself, and the last item
 * names that step.
 */
export function loadPhase(gateShowing: boolean, done: ReadonlySet<StartItem>): AbandonPhase {
  if (gateShowing) return 'gate'
  return START_ITEMS.find(item => !done.has(item)) ?? START_ITEMS[START_ITEMS.length - 1]
}

/**
 * The phone gate unmounted the Globe before the load was complete
 * (useGlobeBehindGate): the Globe that mounts after it starts again from its
 * scene, so the unmounted Globe's items are no longer in. 'sites' is App's own
 * item and survives the remount.
 */
export function dropGlobeStartItems(done: Set<StartItem>): void {
  for (const item of START_ITEMS) if (item !== 'sites') done.delete(item)
}

/** How long this load has been going (globe_abandon's ms). */
export interface LoadClock {
  /** App's gateShowing, on every render. */
  gate(showing: boolean): void
  elapsed(): number
}

/**
 * globe_abandon's wait: the time since this load started - navigation, or the
 * last moment the phone gate went away. App renders the gate instead of the
 * Globe, so on a phone the load only starts with the tap on '3D Globe' (or when
 * a gate that appeared mid-load goes away and a fresh Globe starts from its
 * scene); the time spent reading the gate is no loading wait. App observes the
 * gate in its render, so the moment is taken before the fresh Globe's effects run.
 */
export function createLoadClock(now: () => number, gateShowing: boolean): LoadClock {
  let start = 0
  let gate = gateShowing
  return {
    gate(showing) {
      if (gate && !showing) start = now()
      gate = showing
    },
    elapsed() {
      return now() - start
    },
  }
}

/**
 * Sends globe_abandon{ms, phase} through the latch on pagehide or when the
 * page turns hidden. pagehide, not unload/beforeunload: it keeps the page
 * eligible for the back/forward cache and fires on mobile. Returns the uninstall.
 */
export function installGlobeAbandon(opts: {
  latch: GlobeEndingLatch
  getPhase: () => AbandonPhase
  now: () => number
}): () => void {
  const send = () => {
    opts.latch.end('globe_abandon', { ms: Math.round(opts.now()), phase: opts.getPhase() })
  }
  const onVisibility = () => {
    if (document.visibilityState === 'hidden') send()
  }
  window.addEventListener('pagehide', send)
  document.addEventListener('visibilitychange', onVisibility)
  return () => {
    window.removeEventListener('pagehide', send)
    document.removeEventListener('visibilitychange', onVisibility)
  }
}
