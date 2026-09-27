/**
 * MapboxTopdown: an exact top-down satellite frame (pipeline/studio/capture/
 * mapbox.py, Mapbox Static API) with its pins at the projected pixels the
 * capture recorded (events named "pin": target = case-file place id, label,
 * x/y in image pixels, lat/lng). Top-down imagery is orthographic, so distance
 * lines between two pins are allowed here; their text is computed from the
 * pins' coordinates, never typed. Cues:
 *   show <place>       the pin appears (without one: staggered from frame 8)
 *   highlight <place>  the camera flies onto the pin and holds
 * Lines draw once both of their pins are up.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'

import { firstCue } from '../cues'
import { formatDistance, haversineM } from '../format'
import { type ImageBox, blendCamera, cameraAt, focusCamera, kenBurnsCamera, viewFor } from '../layout/transform'
import { progress } from '../motion'
import { colors } from '../theme/colors'
import { ImageLayer } from './ImageLayer'
import { LowerThird } from './LowerThird'
import type { BlockProps, Capture, CaptureEvent, Label } from './types'

export type PinLine = { from: string; to: string }
export type MapboxTopdownProps = { map: Capture; lines?: PinLine[]; label?: Label }
export type Pin = { id: string; label: string; x: number; y: number; lat: number; lng: number }

const PIN_BOX = 24

export function pinsOf(map: Capture): Pin[] {
  return map.events
    .filter((e: CaptureEvent) => e.name === 'pin')
    .map((e) => ({ id: e.target as string, label: e.label as string, x: e.x as number, y: e.y as number, lat: e.lat as number, lng: e.lng as number }))
}

export function checkMapboxTopdown(p: MapboxTopdownProps): string[] {
  const pins = pinsOf(p.map)
  const errors: string[] = []
  if (pins.length === 0) errors.push(`capture ${p.map.id} has no pin events`)
  for (const pin of pins) {
    if ([pin.id, pin.label, pin.x, pin.y, pin.lat, pin.lng].some((v) => v === undefined)) errors.push(`capture ${p.map.id}: a pin event lacks target, label, x, y, lat or lng`)
    else if (pin.x < 0 || pin.y < 0 || pin.x > p.map.width || pin.y > p.map.height) errors.push(`pin ${pin.id} lies outside the ${p.map.width}x${p.map.height} image`)
  }
  const ids = new Set(pins.map((pin) => pin.id))
  for (const l of p.lines ?? []) {
    if (!ids.has(l.from) || !ids.has(l.to) || l.from === l.to) errors.push(`line ${l.from} -> ${l.to} must join two different pins of the capture`)
  }
  return errors
}

const pinBox = (pin: Pin): ImageBox => [pin.x - PIN_BOX / 2, pin.y - PIN_BOX / 2, PIN_BOX, PIN_BOX]

export const MapboxTopdown: React.FC<BlockProps<MapboxTopdownProps>> = ({ props: p, cues, durationInFrames, sceneId }) => {
  const frame = useCurrentFrame()
  const { width: fw, height: fh } = useVideoConfig()
  const { width: iw, height: ih } = p.map
  const pins = pinsOf(p.map)
  const t = (f: number) => (durationInFrames > 1 ? f / (durationInFrames - 1) : 0)
  const keys = kenBurnsCamera(iw, ih, 'in')
  let cam = cameraAt(keys, t(frame))
  const focus = cues.filter((c) => c.do === 'highlight' && c.frame <= frame).sort((a, b) => a.frame - b.frame).pop()
  if (focus) {
    const pin = pins.find((x) => x.id === focus.target)
    if (!pin) throw new Error(`highlight cue targets unknown pin ${focus.target}`)
    const area: ImageBox = [pin.x - iw * 0.12, pin.y - ih * 0.12, iw * 0.24, ih * 0.24]
    cam = blendCamera(cameraAt(keys, t(focus.frame)), focusCamera(iw, ih, fw, fh, area), progress(frame, focus.frame, 36))
  }
  const view = viewFor(iw, ih, fw, fh, cam)
  const appear = new Map(pins.map((pin, i) => [pin.id, firstCue(cues, 'show', pin.id) ?? 8 + i * 10]))
  const focused = focus ? focus.target : null
  const marks = pins.map((pin) => ({ id: pin.id, box: pinBox(pin), label: pin.label, appear: appear.get(pin.id) as number, focused: pin.id === focused, shape: 'pin' as const }))
  const byId = new Map(pins.map((pin) => [pin.id, pin]))
  const lines = (p.lines ?? []).map((l) => {
    const a = byId.get(l.from) as Pin
    const b = byId.get(l.to) as Pin
    return {
      id: `${l.from}-${l.to}`,
      from: { x: a.x, y: a.y },
      to: { x: b.x, y: b.y },
      text: formatDistance(haversineM(a, b)),
      appear: Math.max(appear.get(l.from) as number, appear.get(l.to) as number) + 20,
    }
  })
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: colors.bg }}>
      <ImageLayer sceneId={sceneId} src={p.map.src} width={iw} height={ih} view={view} marks={marks} lines={lines} />
      {p.label ? <LowerThird id={`${sceneId}:lt`} label={p.label} /> : null}
    </AbsoluteFill>
  )
}
