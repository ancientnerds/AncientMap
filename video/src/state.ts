/**
 * Episode-wide state carried by the global cues (plan C contract C8): a claim
 * is introduced once and changes status over the episode, the probability
 * meter moves; the ClaimBoard or Meter shown later reflects everything cued
 * before it, whichever scene the cue sat in. Pure functions of the absolute
 * frame, precomputed once per timeline.
 */
import { progress } from './motion'
import type { ClaimStatus } from './theme/colors'
import type { MeterValue, Scene } from './timeline'

export type StatusChange = { frame: number; value: ClaimStatus }
export type MeterMove = { frame: number; value: MeterValue }
export type EpisodeState = {
  /** Claim id -> the frame of its first introduce cue. */
  introduced: ReadonlyMap<string, number>
  /** Claim id -> its status cues in frame order. */
  statuses: ReadonlyMap<string, readonly StatusChange[]>
  /** Meter cues in frame order. */
  meter: readonly MeterMove[]
}

/** Frames the meter takes to roll to a new split. */
export const METER_ROLL_FRAMES = 36

export function buildState(scenes: readonly Scene[]): EpisodeState {
  const introduced = new Map<string, number>()
  const statuses = new Map<string, StatusChange[]>()
  const meter: MeterMove[] = []
  const cues = scenes.flatMap((s) => s.cues).sort((a, b) => a.frame - b.frame)
  for (const cue of cues) {
    if (cue.do === 'introduce' && !introduced.has(cue.target)) introduced.set(cue.target, cue.frame)
    if (cue.do === 'status') statuses.set(cue.target, [...(statuses.get(cue.target) ?? []), { frame: cue.frame, value: cue.value as ClaimStatus }])
    if (cue.do === 'meter') meter.push({ frame: cue.frame, value: cue.value as MeterValue })
  }
  return { introduced, statuses, meter }
}

/** A claim's status at an absolute frame: the latest status cue at or before it, else the case file's. */
export function claimStatusAt(state: EpisodeState, id: string, initial: ClaimStatus, frame: number): { status: ClaimStatus; since: number | null } {
  let current: { status: ClaimStatus; since: number | null } = { status: initial, since: null }
  for (const change of state.statuses.get(id) ?? []) {
    if (change.frame <= frame) current = { status: change.value, since: change.frame }
  }
  return current
}

/** Share of hypothesis A at an absolute frame (fractional while rolling) and the frame of the last move. */
export function meterAt(state: EpisodeState, start: MeterValue, frame: number): { a: number; since: number | null } {
  let a = start[0]
  let since: number | null = null
  for (const move of state.meter) {
    if (move.frame > frame) break
    a = a + (move.value[0] - a) * progress(frame, move.frame, METER_ROLL_FRAMES)
    since = move.frame
  }
  return { a, since }
}
