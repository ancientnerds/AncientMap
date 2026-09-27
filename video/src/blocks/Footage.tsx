/**
 * A captured clip (pipeline/studio/capture: HEVC from hevc_nvenc on GPU 0, constant 60 fps) through
 * @remotion/media <Video>, which extracts exact frames. There is no fallback
 * to OffthreadVideo: a clip Mediabunny cannot decode fails the render. In lint
 * mode the clip is not decoded at all (the lint checks layout only), a flat
 * panel of the clip's size stands in.
 */
import React from 'react'
import type { CSSProperties } from 'react'
import { Video } from '@remotion/media'
import { staticFile } from 'remotion'

import { useEpisode } from '../context'
import { colors } from '../theme/colors'

export const Footage: React.FC<{ src: string; trimBefore: number; style: CSSProperties }> = ({ src, trimBefore, style }) => {
  const { lint } = useEpisode()
  if (lint) return <div style={{ ...style, background: colors.bgPanel }} />
  return <Video src={staticFile(src)} trimBefore={trimBefore} muted objectFit="fill" disallowFallbackToOffthreadVideo style={style} />
}
