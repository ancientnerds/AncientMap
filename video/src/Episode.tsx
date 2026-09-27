/**
 * The Episode composition: one <Sequence> per scene, the global overlays
 * (chapter tag, evidence ticker, hook captions), the narration clips and the
 * ducked music bed. In lint mode (inputProps.lint, set by scripts/lint.ts)
 * LayoutGuard reports every layout violation of the frame, no audio is mounted
 * and clips are not decoded.
 */
import React, { useMemo } from 'react'
import { Audio } from '@remotion/media'
import { AbsoluteFill, Sequence, staticFile } from 'remotion'

import { type Span, musicVolume } from './audio'
import { ChapterTag } from './blocks/ChapterTag'
import { HookCaptions } from './blocks/HookCaptions'
import { Ticker } from './blocks/Ticker'
import { EpisodeContext, type ImageSizes } from './context'
import { LayoutProvider, Registry } from './layout/LayoutBox'
import { LayoutGuard } from './layout/LayoutGuard'
import { SceneView } from './SceneView'
import { buildState } from './state'
import { colors } from './theme/colors'
import { type Timeline, sceneHasCaptions } from './timeline'

export type EpisodeProps = {
  timeline: Timeline
  lint: boolean
  /** Filled by calculateMetadata from the narration files; [] in inputProps. */
  narrationSpans: Span[]
  /** Filled by calculateMetadata from the images; {} in inputProps. */
  imageSizes: ImageSizes
  /** Filled by calculateMetadata: the render browser's WebGL renderer (src/gpu.ts); '' in inputProps. */
  gpu: string
}

/**
 * All scenes and, with `overlays`, the chapter tag, ticker and hook captions.
 * `shift` moves every scene earlier by that many frames: the one-frame
 * Thumbnail composition passes the wanted episode frame, so its frame 0 shows
 * exactly that moment.
 */
export const EpisodeVisuals: React.FC<{ timeline: Timeline; overlays: boolean; credits: boolean; shift: number }> = ({ timeline, overlays, credits, shift }) => {
  const creditsByScene = useMemo(() => {
    const map = new Map<string, string[]>()
    for (const c of timeline.credits) map.set(c.sceneId, [...(map.get(c.sceneId) ?? []), c.text])
    return map
  }, [timeline])
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      {timeline.scenes.map((scene) => (
        <Sequence key={scene.id} name={`${scene.id} ${scene.block}`} from={scene.from - shift} durationInFrames={scene.durationInFrames}>
          <SceneView scene={scene} credits={credits ? (creditsByScene.get(scene.id) ?? []) : []} captioned={overlays && sceneHasCaptions(timeline, scene)} />
        </Sequence>
      ))}
      {overlays ? (
        <>
          <ChapterTag chapters={timeline.chapters} />
          <Ticker steps={timeline.ticker.evidence} />
          <HookCaptions captions={timeline.captions} />
        </>
      ) : null}
    </AbsoluteFill>
  )
}

const EpisodeAudio: React.FC<{ timeline: Timeline; spans: readonly Span[] }> = ({ timeline, spans }) => {
  const music = timeline.audio.music
  return (
    <>
      {timeline.audio.narration.map((clip, i) => (
        <Sequence key={`${clip.src}-${i}`} name={`voice ${clip.src}`} from={clip.from} layout="none">
          <Audio src={staticFile(clip.src)} disallowFallbackToHtml5Audio />
        </Sequence>
      ))}
      {music ? (
        <Audio src={staticFile(music.src)} loop loopVolumeCurveBehavior="extend" volume={(f) => musicVolume(f, music, spans)} disallowFallbackToHtml5Audio />
      ) : null}
    </>
  )
}

export const Episode: React.FC<EpisodeProps> = ({ timeline, lint, narrationSpans, imageSizes }) => {
  const registry = useMemo(() => new Registry(lint), [lint])
  const data = useMemo(() => ({ state: buildState(timeline.scenes), imageSizes, lint }), [timeline, imageSizes, lint])
  return (
    <EpisodeContext.Provider value={data}>
      <LayoutProvider registry={registry}>
        <EpisodeVisuals timeline={timeline} overlays credits shift={0} />
        {/* Lint renders sparse frames (everyNthFrame) and checks layout only: no audio. */}
        {lint ? <LayoutGuard /> : <EpisodeAudio timeline={timeline} spans={narrationSpans} />}
      </LayoutProvider>
    </EpisodeContext.Provider>
  )
}
