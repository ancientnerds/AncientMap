/**
 * MapboxFlyover: a Mapbox satellite fly-in or orbit, recorded frame by frame
 * by the recorder (studio-mapbox-flyin / studio-mapbox-orbit). The in-frame
 * credit comes from the capture manifest via timeline.credits (CreditLine).
 */
import React from 'react'
import { AbsoluteFill, useVideoConfig } from 'remotion'

import { colors } from '../theme/colors'
import { clipProblems, trimFrames } from './clips'
import { Footage } from './Footage'
import { LowerThird } from './LowerThird'
import type { BlockProps, Capture, CheckContext, Label } from './types'

export type MapboxFlyoverProps = { clip: Capture; start_s?: number; label?: Label }

export function checkMapboxFlyover(p: MapboxFlyoverProps, ctx: CheckContext): string[] {
  const errors = clipProblems(p.clip, p.start_s ?? 0, ctx)
  if (!p.clip.credits.some((c) => c.includes('© Mapbox'))) errors.push(`capture ${p.clip.id} has no Mapbox credit: our vector globe belongs in GlobeShot`)
  return errors
}

export const MapboxFlyover: React.FC<BlockProps<MapboxFlyoverProps>> = ({ props: p, sceneId }) => {
  const { fps } = useVideoConfig()
  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: colors.bg }}>
      <Footage src={p.clip.src} trimBefore={trimFrames(p.start_s ?? 0, fps)} style={{ width: '100%', height: '100%' }} />
      {p.label ? <LowerThird id={`${sceneId}:lt`} label={p.label} /> : null}
    </AbsoluteFill>
  )
}
