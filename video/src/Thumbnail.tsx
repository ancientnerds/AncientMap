/**
 * The Thumbnail composition (owner decisions 24-25): episode frame `frame`
 * without captions, ticker or chapter tag; with the scene's in-frame credit
 * line (spec 4.8), with the teaser of thumbnail candidate `candidate`
 * (timeline.thumbnails: 2-4 words, a question or riddle that never gives the
 * answer; plan C picks the frames and the words) in the NERV heading type on
 * its own dark glass. The composition is one frame long and shifts every scene
 * by `frame`, so its only frame shows that moment (scene motion included). The
 * teaser sits in TEASER_ZONE: inside the title-safe area and clear of the
 * bottom-right corner, where YouTube lays its duration badge over a thumbnail.
 * The credit line of the scene that shows the frame (photo licence, source
 * page, Mapbox/Maxar: the Mapbox terms want the attribution in the picture, and
 * the JPEG is also the paper page's poster) sits bottom left in
 * THUMBNAIL_CREDIT_ZONE, because the episode's credit zone lies under the
 * badge; a scene without credits gets none. In lint mode (scripts/lint.ts)
 * only the teaser is measured: the scene under it is linted with the episode,
 * and the teaser covers it on purpose; the credit line is the scene's own (same
 * text, same box size), which the episode lint measures, and it sits where the
 * episode's player controls would be, which a thumbnail does not have.
 * scripts/still.ts renders it at scale 2 (3840x2160 master) and as a 1280x720
 * JPEG under 2 MB.
 */
import React, { useMemo } from 'react'

import { CreditLine } from './blocks/CreditLine'
import { mergeCredits } from './captions'
import type { ImageSizes } from './context'
import { EpisodeContext } from './context'
import { EpisodeVisuals } from './Episode'
import type { Rect } from './layout/geometry'
import { LayoutBox, LayoutProvider, Registry } from './layout/LayoutBox'
import { LayoutGuard } from './layout/LayoutGuard'
import { buildState } from './state'
import { colors } from './theme/colors'
import { heading } from './theme/type'
import type { Timeline } from './timeline'

export type ThumbnailProps = { timeline: Timeline; candidate: number; frame: number; lint: boolean; imageSizes: ImageSizes; gpu: string }

/** Where the teaser goes: the top of the frame, inside the title-safe area. */
export const TEASER_ZONE: Rect = { x: 96, y: 72, w: 1440, h: 380 }
/** YouTube lays its duration badge over the bottom-right corner of a thumbnail (25 % x 20 % of the frame). */
export const DURATION_BADGE: Rect = { x: 1440, y: 864, w: 480, h: 216 }
/**
 * Where the credit line of the frame's scene goes: bottom left inside the title-safe area,
 * the size of ZONES.credit, clear of TEASER_ZONE, DURATION_BADGE and ZONES.lowerThird.
 */
export const THUMBNAIL_CREDIT_ZONE: Rect = { x: 96, y: 984, w: 800, h: 32 }

/** The teaser of candidate `candidate` (1-based, like still.ts --candidate). */
export function teaserOf(timeline: Pick<Timeline, 'thumbnails'>, candidate: number): string {
  const c = Number.isInteger(candidate) ? timeline.thumbnails[candidate - 1] : undefined
  if (!c) throw new Error(`thumbnail candidate ${candidate} does not exist (1..${timeline.thumbnails.length})`)
  return c.text
}

/** The timeline.credits texts of the scene that shows episode frame `frame`, in timeline order ([] for a scene without credits). */
export function creditsAt(timeline: Pick<Timeline, 'scenes' | 'credits'>, frame: number): string[] {
  const scene = timeline.scenes.find((s) => s.from <= frame && frame < s.from + s.durationInFrames)
  if (!scene) throw new Error(`no scene shows episode frame ${frame}`)
  return timeline.credits.filter((c) => c.sceneId === scene.id).map((c) => c.text)
}

export const Thumbnail: React.FC<ThumbnailProps> = ({ timeline, candidate, frame, lint, imageSizes }) => {
  const scenes = useMemo(() => new Registry(false), [])
  const teaser = useMemo(() => new Registry(lint), [lint])
  const data = useMemo(() => ({ state: buildState(timeline.scenes), imageSizes, lint }), [timeline, imageSizes, lint])
  const credits = creditsAt(timeline, frame)
  const z = TEASER_ZONE
  return (
    <EpisodeContext.Provider value={data}>
      <LayoutProvider registry={scenes}>
        <EpisodeVisuals timeline={timeline} overlays={false} credits={false} shift={frame} />
        {credits.length > 0 ? <CreditLine id={`thumbnail${candidate}:credit`} text={mergeCredits(credits)} zone={THUMBNAIL_CREDIT_ZONE} /> : null}
      </LayoutProvider>
      <LayoutProvider registry={teaser}>
        <div style={{ position: 'absolute', left: z.x, top: z.y, width: z.w, height: z.h, background: colors.bgPanel }} />
        <div style={{ position: 'absolute', left: z.x, top: z.y, width: 10, height: z.h, background: colors.green }} />
        <LayoutBox
          id={`thumbnail${candidate}:teaser`}
          kind="text"
          style={{ position: 'absolute', left: z.x + 44, top: z.y + 24, width: z.w - 72, height: z.h - 48, overflow: 'hidden', display: 'flex', alignItems: 'center', ...heading(104) }}
        >
          {teaserOf(timeline, candidate)}
        </LayoutBox>
        {lint ? <LayoutGuard /> : null}
      </LayoutProvider>
    </EpisodeContext.Provider>
  )
}
