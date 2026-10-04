/**
 * MapboxTopdown: an exact top-down satellite frame (pipeline/studio/capture/
 * mapbox.py, Mapbox Static API) with its pins at the projected pixels the
 * capture recorded (events named "pin": target = case-file place id, label,
 * x/y in image pixels, lat/lng). Top-down imagery is orthographic, so distance
 * lines between two pins are allowed here; their text is computed from the
 * pins' coordinates, never typed. Cues:
 *   show <place>       the pin appears (without one: staggered from frame 8)
 *   highlight <place>  the camera flies onto the pin (36 frames, from wherever
 *                      it is) and holds a close-up of about half the capture
 * Lines draw once both of their pins are up.
 *
 * A highlight is a close-up of one place: from its cue on, only the focused pin
 * is drawn, and the other pins and every distance line leave. The capture keeps
 * every pin in a band where it and its label fit the full frame (PIN_BAND in
 * capture/mapbox.py), but a close-up of one pin puts the others, and the label
 * of a line between them, outside the frame, where the layout lint would refuse
 * the render. The focused pin stays up through a flight from the overview (the
 * flight only draws it towards the centre); after a highlight on another pin it
 * starts off the frame, so it appears once the camera holds on it.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'

import { type SceneCue, firstCue } from '../cues'
import { formatDistance, haversineM } from '../format'
import { type ImageBox, type View, cameraAt, focusCamera, highlightCamera, kenBurnsCamera, viewFor } from '../layout/transform'
import { progress } from '../motion'
import { colors } from '../theme/colors'
import { ImageLayer, type LayerLine, type LayerMark } from './ImageLayer'
import { LowerThird } from './LowerThird'
import type { BlockProps, Capture, CaptureEvent, Label } from './types'

export type PinLine = { from: string; to: string }
export type MapboxTopdownProps = { map: Capture; lines?: PinLine[]; label?: Label }
export type Pin = { id: string; label: string; x: number; y: number; lat: number; lng: number }
export type TopdownFrame = { view: View; marks: LayerMark[]; lines: LayerLine[] }

const PIN_BOX = 24
const FOCUS_FRAMES = 36
/** Box around a highlighted pin, as a share of the capture's sides; focusCamera fits it to 45 % of the frame (1.875x on a 16:9 capture). */
const CLOSE_UP = 0.24

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

/** What the block draws at a scene frame: the camera's view, the pins and the distance lines (the rule in the header). */
export function topdownFrame(p: MapboxTopdownProps, cues: readonly SceneCue[], frame: number, durationInFrames: number, fw: number, fh: number): TopdownFrame {
  const { width: iw, height: ih } = p.map
  const pins = pinsOf(p.map)
  const byId = new Map(pins.map((pin) => [pin.id, pin]))
  const pinAt = (id: string): Pin => {
    const pin = byId.get(id)
    if (!pin) throw new Error(`highlight cue targets unknown pin ${id}`)
    return pin
  }
  const t = (f: number) => (durationInFrames > 1 ? f / (durationInFrames - 1) : 0)
  const keys = kenBurnsCamera(iw, ih, 'in')
  const closeUp = (id: string) => {
    const pin = pinAt(id)
    return focusCamera(iw, ih, fw, fh, [pin.x - (iw * CLOSE_UP) / 2, pin.y - (ih * CLOSE_UP) / 2, iw * CLOSE_UP, ih * CLOSE_UP])
  }
  const cam = highlightCamera((f) => cameraAt(keys, t(f)), cues, closeUp, (f, start) => progress(f, start, FOCUS_FRAMES), frame)
  const view = viewFor(iw, ih, fw, fh, cam)
  const appear = new Map(pins.map((pin, i) => [pin.id, firstCue(cues, 'show', pin.id) ?? 8 + i * 10]))
  const mark = (pin: Pin, from: number, focused: boolean): LayerMark => ({ id: pin.id, box: pinBox(pin), label: pin.label, appear: from, focused, shape: 'pin' })
  const highlights = cues.filter((c) => c.do === 'highlight' && c.frame <= frame).sort((a, b) => a.frame - b.frame)
  if (highlights.length > 0) {
    // When the focused pin comes up: its own frame on the first close-up, on arrival after a close-up
    // of another pin. highlightCamera has resolved every one of these targets through pinAt already.
    let from = appear.get(highlights[0].target) as number
    for (let i = 1; i < highlights.length; i++) {
      const id = highlights[i].target
      if (id !== highlights[i - 1].target) from = Math.max(appear.get(id) as number, highlights[i].frame + FOCUS_FRAMES)
    }
    return { view, marks: [mark(pinAt(highlights[highlights.length - 1].target), from, true)], lines: [] }
  }
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
  return { view, marks: pins.map((pin) => mark(pin, appear.get(pin.id) as number, false)), lines }
}

export const MapboxTopdown: React.FC<BlockProps<MapboxTopdownProps>> = ({ props: p, cues, durationInFrames, sceneId }) => {
  const frame = useCurrentFrame()
  const { width: fw, height: fh } = useVideoConfig()
  const { view, marks, lines } = topdownFrame(p, cues, frame, durationInFrames, fw, fh)
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: colors.bg }}>
      <ImageLayer sceneId={sceneId} src={p.map.src} width={p.map.width} height={p.map.height} view={view} marks={marks} lines={lines} />
      {p.label ? <LowerThird id={`${sceneId}:lt`} label={p.label} /> : null}
    </AbsoluteFill>
  )
}
