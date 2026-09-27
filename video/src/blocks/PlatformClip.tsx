/**
 * PlatformClip: a platform moment, the real ancientnerds.com recorded by
 * pipeline/studio/capture/platform.py (1920x1080 CSS px at device scale 2; the
 * screencast delivers up to the display's pixel size, e.g. 2880x1620, at a
 * constant 60 fps), full bleed with a virtual camera:
 *   camera  explicit keys on the capture clock (t = clip seconds, cx/cy = capture pixels)
 *   follow  zoom onto every event with x/y (the cursor's clicks), easing in 0.35 s before it
 *   neither the whole frame
 * The in-frame map credit comes from the capture manifest via timeline.credits.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'

import { type Camera, type CameraKey, cameraAt, viewFor } from '../layout/transform'
import { colors } from '../theme/colors'
import { clipProblems, clipTime, trimFrames } from './clips'
import { Footage } from './Footage'
import { LowerThird } from './LowerThird'
import type { BlockProps, Capture, CaptureEvent, CheckContext, Label } from './types'

export type PlatformCameraKey = { t: number; cx: number; cy: number; zoom: number }
export type PlatformClipProps = { clip: Capture; start_s?: number; camera?: PlatformCameraKey[]; follow?: number; label?: Label }

/** Seconds the camera takes to reach an event it follows. */
export const FOLLOW_LEAD_S = 0.35

/** Camera keys (on the capture clock) that zoom onto each event with a position. */
export function followKeys(events: readonly CaptureEvent[], zoom: number, width: number, height: number): PlatformCameraKey[] {
  const keys: PlatformCameraKey[] = [{ t: 0, cx: width / 2, cy: height / 2, zoom: 1 }]
  for (const e of events) {
    if (e.x === undefined || e.y === undefined) continue
    const last = keys[keys.length - 1]
    const holdAt = Math.max(last.t, e.t - FOLLOW_LEAD_S)
    if (holdAt > last.t) keys.push({ ...last, t: holdAt })
    keys.push({ t: Math.max(e.t, holdAt), cx: e.x, cy: e.y, zoom })
  }
  return keys
}

/** Camera at capture time `time` (seconds): the keys eased on the capture clock; the whole frame without keys. */
export function platformCamera(keys: readonly PlatformCameraKey[] | undefined, width: number, height: number, time: number): Camera {
  if (!keys || keys.length === 0) return { cx: width / 2, cy: height / 2, zoom: 1 }
  const asKeys: CameraKey[] = keys.map((k) => ({ at: k.t, cx: k.cx, cy: k.cy, zoom: k.zoom }))
  return cameraAt(asKeys, time)
}

export function checkPlatformClip(p: PlatformClipProps, ctx: CheckContext): string[] {
  const errors = clipProblems(p.clip, p.start_s ?? 0, ctx)
  if (p.camera && p.follow !== undefined) errors.push('camera and follow exclude each other')
  for (const k of p.camera ?? []) {
    if (k.cx > p.clip.width || k.cy > p.clip.height) errors.push(`camera key at ${k.t} s points outside the ${p.clip.width}x${p.clip.height} capture`)
  }
  const times = (p.camera ?? []).map((k) => k.t)
  if (times.some((t, i) => i > 0 && t <= times[i - 1])) errors.push('camera keys must be in increasing time order')
  // The screencast is capped at the display's pixel size: past width / 1920 the camera would upscale it.
  const sharp = p.clip.width / 1920
  const zooms = [...(p.camera ?? []).map((k) => k.zoom), ...(p.follow === undefined ? [] : [p.follow])]
  for (const z of zooms) {
    if (z > sharp + 1e-9) errors.push(`zoom ${z} upscales the ${p.clip.width}x${p.clip.height} capture (sharp up to ${sharp.toFixed(2)})`)
  }
  return errors
}

export const PlatformClip: React.FC<BlockProps<PlatformClipProps>> = ({ props: p, sceneId }) => {
  const frame = useCurrentFrame()
  const { fps, width: fw, height: fh } = useVideoConfig()
  const start = p.start_s ?? 0
  const keys = p.follow !== undefined ? followKeys(p.clip.events, p.follow, p.clip.width, p.clip.height) : p.camera
  const view = viewFor(p.clip.width, p.clip.height, fw, fh, platformCamera(keys, p.clip.width, p.clip.height, clipTime(start, frame, fps)))
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: colors.bg }}>
      <div style={{ position: 'absolute', left: 0, top: 0, width: p.clip.width, height: p.clip.height, transformOrigin: '0 0', transform: `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})` }}>
        <Footage src={p.clip.src} trimBefore={trimFrames(start, fps)} style={{ width: p.clip.width, height: p.clip.height }} />
      </div>
      {p.label ? <LowerThird id={`${sceneId}:lt`} label={p.label} /> : null}
    </AbsoluteFill>
  )
}
