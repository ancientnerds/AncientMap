/**
 * Scene-relative cue helpers for blocks. A cue fires at its frame and stays in
 * effect; blocks ask "since when" questions instead of reacting to events,
 * which keeps every frame a pure function of the frame number.
 */
import type { Cue } from './timeline'

/** A cue with its frame relative to the scene start. */
export type SceneCue = Cue

/** Frame of the first `verb` cue for `target`, or null. */
export function firstCue(cues: readonly SceneCue[], verb: string, target: string): number | null {
  let best: number | null = null
  for (const c of cues) {
    if (c.do === verb && c.target === target && (best === null || c.frame < best)) best = c.frame
  }
  return best
}

/** Frame an element appears: its first `verb` cue; without one, the block's staggered `defaultFrame`. */
export function appearFrame(cues: readonly SceneCue[], target: string, defaultFrame: number, verb = 'show'): number {
  return firstCue(cues, verb, target) ?? defaultFrame
}

/** Visible from its show cue (from the start without one) until a later hide cue. */
export function visibleAt(cues: readonly SceneCue[], target: string, frame: number): boolean {
  const start = firstCue(cues, 'show', target) ?? 0
  if (frame < start) return false
  const hides = cues.filter((c) => c.do === 'hide' && c.target === target && c.frame >= start).map((c) => c.frame)
  return hides.length === 0 || frame < Math.min(...hides)
}

/** Latest `verb` cue for `target` at or before `frame`, or null. */
export function latestCue(cues: readonly SceneCue[], verb: string, target: string, frame: number): SceneCue | null {
  let best: SceneCue | null = null
  for (const c of cues) {
    if (c.do === verb && c.target === target && c.frame <= frame && (best === null || c.frame >= best.frame)) best = c
  }
  return best
}
