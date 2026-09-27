/**
 * Frame-driven NERV motion: the renderer's port of
 * ancient-nerds-map/src/styles/nerv-animations.css. Every value is a pure
 * function of the frame (Remotion renders frames out of order in parallel
 * tabs, so CSS animations or transitions would freeze or flicker). Durations
 * are frames at the timeline's 60 fps (crt-open 0.4 s = 24, boot-in 0.5 s = 30).
 *
 * Deliberately absent (owner rule: no flicker): flicker, flicker-in,
 * glitch-tear, alert-flash, emergency-flash, warning-flash, led-blink and
 * blink-cursor. Periodic motion (ringPulse) fades smoothly, it never blinks.
 */
import type { CSSProperties } from 'react'
import { Easing, interpolate, spring } from 'remotion'

const CLAMP = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const

/** 0 before `start`, 1 from `start + duration` on, eased in between. */
export function progress(frame: number, start: number, duration: number, easing: (t: number) => number = Easing.out(Easing.cubic)): number {
  if (duration <= 0) return frame >= start ? 1 : 0
  return interpolate(frame, [start, start + duration], [0, 1], { ...CLAMP, easing })
}

/** crt-open: the panel opens from a bright horizontal line (scaleY .002 until 40 %, brightness 3 -> 1). */
export function crtOpen(frame: number, start = 0, duration = 24): CSSProperties {
  if (frame < start) return { opacity: 0 }
  const p = progress(frame, start, duration, Easing.linear)
  const scaleY = interpolate(p, [0, 0.4, 1], [0.002, 0.002, 1], CLAMP)
  const brightness = interpolate(p, [0, 0.4, 1], [3, 2, 1], CLAMP)
  return { opacity: 1, transform: `scaleY(${scaleY})`, filter: `brightness(${brightness})` }
}

/** boot-in: rises 8 px, fades in and settles from a brightness flash. `base` is prepended to the transform. */
export function bootIn(frame: number, start = 0, duration = 30, base = ''): CSSProperties {
  const p = progress(frame, start, duration)
  const brightness = interpolate(p, [0, 0.4, 1], [2, 1.5, 1], CLAMP)
  return {
    opacity: p,
    transform: `${base ? `${base} ` : ''}translateY(${(1 - p) * 8}px)`,
    filter: `brightness(${brightness})`,
  }
}

/** border-trace: stroke-dashoffset of an SVG outline of `perimeter` length. */
export function borderTrace(frame: number, start: number, duration: number, perimeter: number): number {
  return perimeter * (1 - progress(frame, start, duration, Easing.inOut(Easing.quad)))
}

/** type-on: the visible prefix of `text`, `charsPerFrame` characters per frame from `start`. */
export function typeOn(text: string, frame: number, start: number, charsPerFrame = 1.5): string {
  if (frame < start) return ''
  const n = Math.min(text.length, Math.floor((frame - start + 1) * charsPerFrame))
  return text.slice(0, n)
}

/** digit-roll: a number counting from `from` to `to`, rounded to `decimals`. */
export function digitRoll(from: number, to: number, frame: number, start: number, duration = 36, decimals = 0): number {
  const v = from + (to - from) * progress(frame, start, duration)
  const f = 10 ** decimals
  return Math.round(v * f) / f
}

/**
 * Stamp slam: drops in from 1.35x with a spring, tilted -6 degrees. The start
 * scale stays small enough that a stamp never covers its neighbours on its
 * first frames (the lint pass measures the transformed stamp).
 */
export function stampSlam(frame: number, start: number, fps: number): CSSProperties {
  if (frame < start) return { opacity: 0 }
  const s = spring({ frame: frame - start, fps, config: { damping: 11, stiffness: 190, mass: 0.7 } })
  const scale = interpolate(s, [0, 1], [1.35, 1])
  return { opacity: Math.min(1, (frame - start + 1) / 3), transform: `rotate(-6deg) scale(${scale})` }
}

/** ring-pulse: a ring expanding from 0.8x to 1.6x and fading from 0.6 to 0, every `period` frames. */
export function ringPulse(frame: number, start: number, period = 60): { scale: number; opacity: number } {
  if (frame < start) return { scale: 0.8, opacity: 0 }
  const phase = ((frame - start) % period) / period
  return { scale: 0.8 + phase * 0.8, opacity: 0.6 * (1 - phase) }
}

/** sweep: 0..1 position of a light wipe crossing once. */
export function sweep(frame: number, start: number, duration: number): number {
  return progress(frame, start, duration, Easing.inOut(Easing.sin))
}
