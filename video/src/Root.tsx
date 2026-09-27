/**
 * Compositions. Both take the timeline as an input prop; calculateMetadata
 * validates it (parseTimeline + checkBlocks), measures the narration clips and
 * the images in the browser, and sets duration, fps and size from the
 * timeline, so nothing about an episode is hard-coded here. The default props
 * are the graphics-only demo timeline for `npm run studio`.
 */
import React from 'react'
import { type CalculateMetadataFunction, Composition } from 'remotion'

import { narrationSpans } from './audio'
import { checkBlocks, imagesToMeasure } from './blocks'
import { Episode, type EpisodeProps } from './Episode'
import { DEMO_TIMELINE } from './fixtures/demo'
import { webglRenderer } from './gpu'
import { audioSeconds, measureImages } from './media'
import { loadBrandFonts } from './theme/fonts'
import { Thumbnail, type ThumbnailProps, teaserOf } from './Thumbnail'
import { parseTimeline } from './timeline'

loadBrandFonts()

const episodeMetadata: CalculateMetadataFunction<EpisodeProps> = async ({ props }) => {
  const timeline = parseTimeline(props.timeline)
  checkBlocks(timeline)
  const seconds = await Promise.all(timeline.audio.narration.map((n) => audioSeconds(n.src)))
  const imageSizes = await measureImages(imagesToMeasure(timeline))
  return {
    durationInFrames: timeline.durationInFrames,
    fps: timeline.fps,
    width: timeline.width,
    height: timeline.height,
    props: { ...props, timeline, imageSizes, narrationSpans: narrationSpans(timeline.audio.narration, seconds, timeline.fps), gpu: webglRenderer() },
  }
}

const thumbnailMetadata: CalculateMetadataFunction<ThumbnailProps> = async ({ props }) => {
  const timeline = parseTimeline(props.timeline)
  checkBlocks(timeline)
  teaserOf(timeline, props.candidate)
  if (!Number.isInteger(props.frame) || props.frame < 0 || props.frame >= timeline.durationInFrames) {
    throw new Error(`Thumbnail frame ${props.frame} is outside the episode (0..${timeline.durationInFrames - 1})`)
  }
  const imageSizes = await measureImages(imagesToMeasure(timeline))
  return { durationInFrames: 1, fps: timeline.fps, width: timeline.width, height: timeline.height, props: { ...props, timeline, imageSizes, gpu: webglRenderer() } }
}

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Episode"
      component={Episode}
      defaultProps={{ timeline: DEMO_TIMELINE, lint: false, narrationSpans: [], imageSizes: {}, gpu: '' }}
      calculateMetadata={episodeMetadata}
      durationInFrames={1}
      fps={60}
      width={1920}
      height={1080}
    />
    <Composition
      id="Thumbnail"
      component={Thumbnail}
      defaultProps={{ timeline: DEMO_TIMELINE, candidate: 1, frame: DEMO_TIMELINE.thumbnails[0].frame, lint: false, imageSizes: {}, gpu: '' }}
      calculateMetadata={thumbnailMetadata}
      durationInFrames={1}
      fps={60}
      width={1920}
      height={1080}
    />
  </>
)
