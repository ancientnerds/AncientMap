/**
 * Shared rules of the clip blocks (PlatformClip, GlobeShot, MapboxFlyover):
 * a clip must cover its whole scene (a clip that ends early would leave black
 * frames, which the render audit refuses), and the capture clock <-> scene
 * frame arithmetic.
 */
import type { Capture, CheckContext } from './types'

/** Every way `clip`, started `startS` seconds in, fails to fill a scene of ctx.durationInFrames. */
export function clipProblems(clip: Capture, startS: number, ctx: CheckContext): string[] {
  if (clip.fps === null || clip.duration_s === null) return [`capture ${clip.id} is a still, not a clip`]
  const need = startS + ctx.durationInFrames / ctx.fps
  if (need > clip.duration_s + 1e-6) {
    return [`capture ${clip.id} is ${clip.duration_s} s long; the scene needs ${need.toFixed(3)} s from ${startS} s (record a longer take or shorten the beat)`]
  }
  return []
}

/** trimBefore of the clip in composition frames. */
export function trimFrames(startS: number, fps: number): number {
  return Math.round(startS * fps)
}

/** Seconds on the capture clock at scene frame `frame`. */
export function clipTime(startS: number, frame: number, fps: number): number {
  return startS + frame / fps
}
