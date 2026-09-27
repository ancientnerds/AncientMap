/**
 * GlobeShot: our vector globe recorded frame by frame by the Puppeteer
 * recorder (pipeline/studio/capture/globe.py: studio-globe-flyto and
 * studio-globe-places, 1920x1080 at 60 fps). The globe carries no third-party
 * map data, so a GlobeShot needs no map credit; Mapbox takes belong in
 * MapboxFlyover. Places come from the capture's "place" events: the pixel the
 * page drew the place at in every capture frame from the event on (`track`,
 * null while the place is behind the globe or outside the label band), so a
 * place moves with the globe when the camera moves (owner rule: globe markers
 * are projected per frame from their coordinates). A labelled place is a pin
 * with its label, lit at its event frame; a show <place> cue can only delay it.
 * An unlabelled place (a world distribution) is a small dot. The fly-to's
 * "arrive" event carries no label and draws nothing.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'

import { firstCue } from '../cues'
import { LayoutBox } from '../layout/LayoutBox'
import { toScreen, viewFor } from '../layout/transform'
import { bootIn, progress, ringPulse } from '../motion'
import { colors } from '../theme/colors'
import { hud, overFootage } from '../theme/type'
import { FPS } from '../timeline'
import { clipProblems, trimFrames } from './clips'
import { Footage } from './Footage'
import { LowerThird } from './LowerThird'
import type { BlockProps, Capture, CaptureEvent, CheckContext, Label } from './types'

export type GlobeShotProps = { clip: Capture; start_s?: number; label?: Label }
export type Track = ([number, number] | null)[]
/** A labelled place: `frame` is the capture frame of its event (captures run at the timeline's 60 fps). */
export type GlobePin = { id: string; frame: number; x: number; y: number; label: string; track: Track }
export type GlobeDot = { id: string; frame: number; track: Track }

const DOT = 12

type PlaceEvent = CaptureEvent & { target: string; x: number; y: number }

function placeEvents(clip: Capture): PlaceEvent[] {
  return clip.events.filter((e): e is PlaceEvent => e.name === 'place' && e.target !== undefined && e.x !== undefined && e.y !== undefined)
}

/** The labelled places: pins with their label. */
export function globePins(clip: Capture): GlobePin[] {
  return placeEvents(clip)
    .filter((e) => e.label !== undefined)
    .map((e) => ({ id: e.target, frame: Math.round(e.t * FPS), x: e.x, y: e.y, label: e.label as string, track: e.track ?? [] }))
}

/** The unlabelled places of a world distribution: dots without a label. */
export function globeDots(clip: Capture): GlobeDot[] {
  return placeEvents(clip)
    .filter((e) => e.label === undefined)
    .map((e) => ({ id: e.target, frame: Math.round(e.t * FPS), track: e.track ?? [] }))
}

/** Where a place sits at capture frame `clipFrame`: its track entry; null before its event frame and while hidden. */
export function pinAt(place: { frame: number; track: readonly ([number, number] | null)[] }, clipFrame: number): { x: number; y: number } | null {
  if (clipFrame < place.frame) return null
  const at = place.track[clipFrame - place.frame]
  return at ? { x: at[0], y: at[1] } : null
}

export function checkGlobeShot(p: GlobeShotProps, ctx: CheckContext): string[] {
  const errors = clipProblems(p.clip, p.start_s ?? 0, ctx)
  if (p.clip.credits.length > 0) errors.push(`capture ${p.clip.id} carries map credits: a Mapbox take belongs in MapboxFlyover`)
  if (p.clip.duration_s === null) return errors
  const frames = Math.round(p.clip.duration_s * FPS)
  for (const e of placeEvents(p.clip)) {
    const rest = frames - Math.round(e.t * FPS)
    if (!e.track) errors.push(`place ${e.target} has no track (re-capture the take)`)
    else if (e.track.length !== rest) errors.push(`place ${e.target}: the track holds ${e.track.length} points, the take has ${rest} frames from the event on`)
    else if (e.track.some((pt) => pt !== null && (pt[0] < 0 || pt[1] < 0 || pt[0] > p.clip.width || pt[1] > p.clip.height))) {
      errors.push(`place ${e.target} leaves the ${p.clip.width}x${p.clip.height} capture`)
    }
  }
  return errors
}

export const GlobeShot: React.FC<BlockProps<GlobeShotProps>> = ({ props: p, cues, sceneId }) => {
  const frame = useCurrentFrame()
  const { fps, width: fw, height: fh } = useVideoConfig()
  const trim = trimFrames(p.start_s ?? 0, fps)
  const clipFrame = trim + frame
  const view = viewFor(p.clip.width, p.clip.height, fw, fh, { cx: p.clip.width / 2, cy: p.clip.height / 2, zoom: 1 })
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: colors.bg }}>
      <Footage src={p.clip.src} trimBefore={trim} style={{ width: '100%', height: '100%' }} />
      {globeDots(p.clip).map((dot) => {
        const pos = pinAt(dot, clipFrame)
        if (!pos) return null
        const at = toScreen(view, pos.x, pos.y)
        return <div key={dot.id} style={{ position: 'absolute', left: at.x - DOT / 2, top: at.y - DOT / 2, width: DOT, height: DOT, borderRadius: DOT / 2, background: colors.green, boxShadow: `0 0 8px ${colors.green}`, opacity: progress(frame, dot.frame - trim, 12) }} />
      })}
      {globePins(p.clip).map((pin) => {
        // A pin follows its track from its event frame on (never before it): a cue can only delay it.
        const eventFrame = pin.frame - trim
        const appear = Math.max(eventFrame, firstCue(cues, 'show', pin.id) ?? eventFrame)
        if (frame < appear) return null
        const pos = pinAt(pin, clipFrame)
        if (!pos) return null
        const ring = ringPulse(frame, appear)
        const at = toScreen(view, pos.x, pos.y)
        const ringId = `${sceneId}:pin:${pin.id}`
        const labelId = `${sceneId}:pinlabel:${pin.id}`
        return (
          <React.Fragment key={pin.id}>
            <LayoutBox id={ringId} kind="mark" allow={[labelId]} style={{ position: 'absolute', left: at.x - 12, top: at.y - 12, width: 24, height: 24 }}>
              <div style={{ position: 'absolute', inset: 0, borderRadius: 12, background: colors.green, boxShadow: `0 0 12px ${colors.green}` }} />
              <div style={{ position: 'absolute', inset: 0, borderRadius: 12, border: `3px solid ${colors.green}`, transform: `scale(${ring.scale * 2.2})`, opacity: ring.opacity }} />
            </LayoutBox>
            <div style={{ position: 'absolute', left: at.x + 24, top: at.y - 22, ...bootIn(frame, appear + 4, 12) }}>
              <LayoutBox id={labelId} kind="text" allow={[ringId]} style={{ ...hud(28, colors.white), whiteSpace: 'nowrap', ...overFootage }}>
                {pin.label}
              </LayoutBox>
            </div>
          </React.Fragment>
        )
      })}
      {p.label ? <LowerThird id={`${sceneId}:lt`} label={p.label} /> : null}
    </AbsoluteFill>
  )
}
