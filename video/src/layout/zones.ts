/**
 * Screen zones of the 1920x1080 episode frame. Overlays sit in fixed zones so
 * they cannot collide by construction; the lint pass (LayoutGuard) proves it
 * frame by frame.
 *
 *   chapter tag (top left) ........................ ticker (top right)   y 60..124
 *   stage: block content ...............................................  y 140..820
 *     (stageHook: y 140..680 in scenes with burned-in hook captions)
 *   hook captions (hook beats only) ....................................  y 700..820
 *   lower third (left) ......................... credit line (right)     y 846..954
 *   YouTube player controls: no text ...................................  y 960..1080
 */
import type { Rect } from './geometry'

export const FRAME: Rect = { x: 0, y: 0, w: 1920, h: 1080 }
/** 5 % title-safe inset. */
export const SAFE: Rect = { x: 96, y: 54, w: 1728, h: 972 }
/** Scrub bar and buttons of the YouTube player (bottom 120 px at 1080p). */
export const YT_CONTROLS: Rect = { x: 0, y: 960, w: 1920, h: 120 }

export const ZONES = {
  chapter: { x: 96, y: 60, w: 720, h: 48 },
  ticker: { x: 1464, y: 60, w: 360, h: 64 },
  stage: { x: 96, y: 140, w: 1728, h: 680 },
  stageHook: { x: 96, y: 140, w: 1728, h: 540 },
  caption: { x: 240, y: 700, w: 1440, h: 120 },
  lowerThird: { x: 96, y: 846, w: 760, h: 96 },
  credit: { x: 1024, y: 922, w: 800, h: 32 },
} as const satisfies Record<string, Rect>

/** The stage a scene's block may fill: shorter when the scene carries hook captions. */
export function stageFor(captioned: boolean): Rect {
  return captioned ? ZONES.stageHook : ZONES.stage
}
