/**
 * PhotoPlate: a checked photo, full bleed, with a Ken Burns camera and the
 * case file's markers in the same transformed layer (ImageLayer), so a marker
 * stays on its object while the image moves (owner rule). Markers are the
 * case file's crop-checked boxes, given as fractions of the image; the image's
 * pixel size is measured by calculateMetadata. Cues:
 *   show <marker>       the marker appears (without a show cue: from the start)
 *   hide <marker>       it leaves
 *   highlight <marker>  the camera flies onto it (36 frames) from wherever it is and
 *                       holds; it turns amber
 * A close-up can push the other markers out of the frame, and the layout lint
 * refuses a clipped marker: the script hides them (hide) before it highlights.
 * There is deliberately no measuring line: photos are oblique, so lengths
 * drawn on them would lie (owner rule); ScaleDrawing makes the comparison.
 */
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'

import { type SceneCue, firstCue, visibleAt } from '../cues'
import { imageSize, useEpisode } from '../context'
import { LayoutBox } from '../layout/LayoutBox'
import { type Camera, type KenBurns, cameraAt, focusCamera, fractionBox, highlightCamera, kenBurnsCamera, viewFor } from '../layout/transform'
import { bootIn, progress } from '../motion'
import { colors } from '../theme/colors'
import { body, overFootage } from '../theme/type'
import { ImageLayer } from './ImageLayer'
import { LowerThird } from './LowerThird'
import type { BlockProps, Label, Media } from './types'

export type PhotoPlateProps = { image: Media; kenBurns?: KenBurns; label?: Label; caption?: string }

const FOCUS_FRAMES = 36

/** Camera at a scene frame: the Ken Burns path until the first highlight, then each highlight's flight from where the camera is. */
export function plateCamera(
  image: Pick<Media, 'markers'>,
  size: [number, number],
  kenBurns: KenBurns,
  cues: readonly SceneCue[],
  frame: number,
  durationInFrames: number,
  fw: number,
  fh: number,
): Camera {
  const [iw, ih] = size
  const keys = kenBurnsCamera(iw, ih, kenBurns)
  const t = (f: number) => (durationInFrames > 1 ? f / (durationInFrames - 1) : 0)
  const onto = (id: string) => {
    const marker = image.markers.find((m) => m.id === id)
    if (!marker) throw new Error(`highlight cue targets unknown marker ${id}`)
    return focusCamera(iw, ih, fw, fh, fractionBox(marker.box, iw, ih))
  }
  return highlightCamera((f) => cameraAt(keys, t(f)), cues, onto, (f, start) => progress(f, start, FOCUS_FRAMES), frame)
}

export function checkPhotoPlate(p: PhotoPlateProps): string[] {
  return p.image.markers
    .filter((m) => m.box[2] <= 0 || m.box[3] <= 0 || m.box[0] + m.box[2] > 1 || m.box[1] + m.box[3] > 1)
    .map((m) => `marker ${m.id} box ${JSON.stringify(m.box)} is not a box inside the image (fractions 0..1)`)
}

export const PhotoPlate: React.FC<BlockProps<PhotoPlateProps>> = ({ props: p, cues, durationInFrames, sceneId }) => {
  const frame = useCurrentFrame()
  const { width: fw, height: fh } = useVideoConfig()
  const { imageSizes } = useEpisode()
  const size = imageSize(imageSizes, p.image.src)
  const [iw, ih] = size
  const view = viewFor(iw, ih, fw, fh, plateCamera(p.image, size, p.kenBurns ?? 'in', cues, frame, durationInFrames, fw, fh))
  const focused = cues.filter((c) => c.do === 'highlight' && c.frame <= frame).map((c) => c.target)
  const marks = p.image.markers
    .filter((m) => visibleAt(cues, m.id, frame))
    .map((m) => ({ id: m.id, box: fractionBox(m.box, iw, ih), label: m.label, appear: firstCue(cues, 'show', m.id) ?? 0, focused: focused.includes(m.id), shape: 'ring' as const }))
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: colors.bg }}>
      <ImageLayer sceneId={sceneId} src={p.image.src} width={iw} height={ih} view={view} marks={marks} />
      {p.label ? <LowerThird id={`${sceneId}:lt`} label={p.label} /> : null}
      {p.caption ? (
        <LayoutBox
          id={`${sceneId}:caption`}
          kind="text"
          style={{ position: 'absolute', left: 1024, top: 846, width: 800, height: 64, overflow: 'hidden', textAlign: 'right', ...body(26, colors.white), ...overFootage, ...bootIn(frame, 10) }}
        >
          {p.caption}
        </LayoutBox>
      ) : null}
    </AbsoluteFill>
  )
}
