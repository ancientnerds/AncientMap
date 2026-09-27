/**
 * Frame math of the audio tracks. Narration clips carry only their start
 * frame in timeline.json; calculateMetadata measures each clip's length and
 * hands narrationSpans() the durations. The music bed ducks under every span.
 */
import type { Music, NarrationClip } from './timeline'

/** [from, to) in absolute frames. */
export type Span = { from: number; to: number }

export function dbToGain(db: number): number {
  return 10 ** (db / 20)
}

export function narrationSpans(clips: readonly NarrationClip[], durationsS: readonly number[], fps: number): Span[] {
  if (clips.length !== durationsS.length) throw new Error(`narrationSpans: ${clips.length} clips but ${durationsS.length} durations`)
  return clips.map((c, i) => {
    const d = durationsS[i]
    if (!(d > 0)) throw new Error(`narration clip ${c.src} has no duration`)
    return { from: c.from, to: c.from + Math.ceil(d * fps) }
  })
}

/** 0 = no ducking, 1 = fully ducked; linear ramps of attackFrames before and releaseFrames after each span. */
export function duckAmount(frame: number, spans: readonly Span[], attackFrames: number, releaseFrames: number): number {
  let amount = 0
  for (const s of spans) {
    let a = 0
    if (frame >= s.from && frame < s.to) a = 1
    else if (frame < s.from && frame >= s.from - attackFrames) a = 1 - (s.from - frame) / Math.max(attackFrames, 1)
    else if (frame >= s.to && frame < s.to + releaseFrames) a = 1 - (frame - s.to + 1) / Math.max(releaseFrames, 1)
    amount = Math.max(amount, a)
  }
  return amount
}

/** Linear volume of the music bed at an absolute frame: gainDb in the pauses, gainDb + underNarrationDb under speech. */
export function musicVolume(frame: number, music: Music, spans: readonly Span[]): number {
  const duck = duckAmount(frame, spans, music.duck.attackFrames, music.duck.releaseFrames)
  return dbToGain(music.gainDb + duck * music.duck.underNarrationDb)
}
