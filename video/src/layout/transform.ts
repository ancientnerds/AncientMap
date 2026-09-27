/**
 * Pure image-to-screen math for PhotoPlate, MapboxTopdown and PlatformClip.
 * An image (or captured video) of iw x ih pixels is fitted with "cover" into
 * the frame and zoomed around a camera centre. Markers are positioned in image
 * pixels inside the same transformed layer, so they move with the image
 * exactly; labels are placed in screen space through toScreen().
 */
import type { Rect } from './geometry'

export type Camera = { cx: number; cy: number; zoom: number }
export type CameraKey = Camera & { at: number }
export type ImageBox = readonly [number, number, number, number]
/** screen = image * scale + (tx, ty) */
export type View = { scale: number; tx: number; ty: number }

export function coverScale(iw: number, ih: number, fw: number, fh: number): number {
  return Math.max(fw / iw, fh / ih)
}

/** View that centres (cx, cy) at `zoom` times the cover scale, clamped so the image always fills the frame. */
export function viewFor(iw: number, ih: number, fw: number, fh: number, cam: Camera): View {
  const scale = coverScale(iw, ih, fw, fh) * Math.max(1, cam.zoom)
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
  const tx = clamp(fw / 2 - cam.cx * scale, fw - iw * scale, 0)
  const ty = clamp(fh / 2 - cam.cy * scale, fh - ih * scale, 0)
  return { scale, tx, ty }
}

export function toScreen(v: View, x: number, y: number): { x: number; y: number } {
  return { x: x * v.scale + v.tx, y: y * v.scale + v.ty }
}

export function rectToScreen(v: View, box: ImageBox): Rect {
  const p = toScreen(v, box[0], box[1])
  return { x: p.x, y: p.y, w: box[2] * v.scale, h: box[3] * v.scale }
}

/** A box given as fractions of the image ([x, y, w, h] in 0..1, the case file's marker boxes) in image pixels. */
export function fractionBox(box: readonly number[], iw: number, ih: number): ImageBox {
  return [box[0] * iw, box[1] * ih, box[2] * iw, box[3] * ih]
}

const smoothstep = (u: number) => u * u * (3 - 2 * u)

/** Blend two cameras (e = 0..1); zoom is interpolated in log space so it feels even. */
export function blendCamera(a: Camera, b: Camera, e: number): Camera {
  const lerp = (x: number, y: number) => x + (y - x) * e
  return { cx: lerp(a.cx, b.cx), cy: lerp(a.cy, b.cy), zoom: Math.exp(lerp(Math.log(a.zoom), Math.log(b.zoom))) }
}

/** Camera at fraction t (0..1) of the keyframes: smoothstep per segment. */
export function cameraAt(keys: readonly CameraKey[], t: number): Camera {
  if (keys.length === 0) throw new Error('cameraAt: no keyframes')
  const first = keys[0]
  const last = keys[keys.length - 1]
  if (keys.length === 1 || t <= first.at) return { cx: first.cx, cy: first.cy, zoom: first.zoom }
  if (t >= last.at) return { cx: last.cx, cy: last.cy, zoom: last.zoom }
  let i = 1
  while (keys[i].at < t) i++
  const a = keys[i - 1]
  const b = keys[i]
  return blendCamera(a, b, smoothstep((t - a.at) / Math.max(b.at - a.at, 1e-6)))
}

/** Camera that frames `box` so it fills `fill` of the frame on its tighter side (zoom 1..4). */
export function focusCamera(iw: number, ih: number, fw: number, fh: number, box: ImageBox, fill = 0.45): Camera {
  const base = coverScale(iw, ih, fw, fh)
  const zoom = Math.min(4, Math.max(1, Math.min((fw * fill) / (box[2] * base), (fh * fill) / (box[3] * base))))
  return { cx: box[0] + box[2] / 2, cy: box[1] + box[3] / 2, zoom }
}

/**
 * Camera at `frame` of a scene whose highlight cues fly the camera onto a target
 * (PhotoPlate markers, MapboxTopdown pins). Before the first highlight it is `base`
 * (the Ken Burns path). Each highlight flies from the camera in effect at its own frame
 * (the base path for the first, else wherever the previous flight had got to) onto
 * `focus(target)`, eased by `flight(frame, cueFrame)` (0 at the cue, 1 on arrival), and
 * holds there, so a scene that highlights one target after another never jumps back.
 */
export function highlightCamera(
  base: (frame: number) => Camera,
  cues: readonly { frame: number; do: string; target: string }[],
  focus: (target: string) => Camera,
  flight: (frame: number, start: number) => number,
  frame: number,
): Camera {
  const hs = cues.filter((c) => c.do === 'highlight' && c.frame <= frame).sort((a, b) => a.frame - b.frame)
  if (hs.length === 0) return base(frame)
  let from = base(hs[0].frame)
  for (let i = 1; i < hs.length; i++) from = blendCamera(from, focus(hs[i - 1].target), flight(hs[i].frame, hs[i - 1].frame))
  const last = hs[hs.length - 1]
  return blendCamera(from, focus(last.target), flight(frame, last.frame))
}

export type KenBurns = 'in' | 'out' | 'none'

/** Ken Burns keyframes on the image centre: an 8 % push in, pull out, or a still frame. */
export function kenBurnsCamera(iw: number, ih: number, mode: KenBurns): CameraKey[] {
  const centre = { cx: iw / 2, cy: ih / 2 }
  if (mode === 'none') return [{ at: 0, ...centre, zoom: 1 }]
  const [from, to] = mode === 'in' ? [1, 1.08] : [1.08, 1]
  return [
    { at: 0, ...centre, zoom: from },
    { at: 1, ...centre, zoom: to },
  ]
}
