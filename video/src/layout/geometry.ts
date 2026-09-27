/**
 * Pure rectangle geometry and the overlap checker behind the lint pass.
 * Boxes are in composition pixels (1920x1080), measured by LayoutBox.
 */
import { FRAME, SAFE, YT_CONTROLS } from './zones'

export type Rect = { x: number; y: number; w: number; h: number }

/** text: readable copy (captions, labels, card text); mark: a marker or pin drawn on an object. */
export type BoxKind = 'text' | 'mark'

export type Box = { id: string; kind: BoxKind; rect: Rect; allow: string[] }

export type ViolationReason = 'overlap' | 'outside-safe' | 'controls' | 'offscreen' | 'overflow'

export type Violation = { a: string; b: string | null; reason: ViolationReason }

/** Overlaps smaller than this (square px) are anti-aliasing contact, not a collision. */
const MIN_OVERLAP_AREA = 4

export function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
  return w > 0 && h > 0 ? w * h : 0
}

export function contains(outer: Rect, inner: Rect): boolean {
  const eps = 0.5
  return (
    inner.x >= outer.x - eps &&
    inner.y >= outer.y - eps &&
    inner.x + inner.w <= outer.x + outer.w + eps &&
    inner.y + inner.h <= outer.y + outer.h + eps
  )
}

/**
 * Rules:
 * - text sits inside the title-safe area and never under the YouTube player controls;
 * - text does not cover other text or a marker, unless one of the two lists the other in
 *   `allow` (a marker's own label may touch its ring);
 * - a marker is fully on screen (a clipped ring points at nothing) and, like text, out of
 *   the YouTube player controls (owner rule: nothing important in the control zone);
 * - `overflowIds`: text boxes whose content is clipped by their own box (measured in the DOM).
 */
export function findViolations(boxes: readonly Box[], overflowIds: readonly string[] = []): Violation[] {
  const out: Violation[] = []
  for (const id of overflowIds) out.push({ a: id, b: null, reason: 'overflow' })
  for (const box of boxes) {
    if (box.kind === 'text') {
      if (!contains(SAFE, box.rect)) out.push({ a: box.id, b: null, reason: 'outside-safe' })
    } else if (!contains(FRAME, box.rect)) {
      out.push({ a: box.id, b: null, reason: 'offscreen' })
    }
    if (overlapArea(box.rect, YT_CONTROLS) >= MIN_OVERLAP_AREA) out.push({ a: box.id, b: null, reason: 'controls' })
  }
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i]
      const b = boxes[j]
      if (a.kind === 'mark' && b.kind === 'mark') continue
      if (a.allow.includes(b.id) || b.allow.includes(a.id)) continue
      if (overlapArea(a.rect, b.rect) >= MIN_OVERLAP_AREA) out.push({ a: a.id, b: b.id, reason: 'overlap' })
    }
  }
  return out
}
