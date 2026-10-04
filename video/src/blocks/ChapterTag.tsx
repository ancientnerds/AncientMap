/**
 * Chapter tag (top left) for three seconds after each chapter start, so the
 * structure reads without narration. The chapter at frame 0 (the hook) gets no
 * tag: the video opens straight into the hook, never on a title card.
 */
import React from 'react'
import { useCurrentFrame, useVideoConfig } from 'remotion'

import { LayoutBox } from '../layout/LayoutBox'
import { ZONES } from '../layout/zones'
import { bootIn, typeOn } from '../motion'
import { colors } from '../theme/colors'
import { hud, overFootage } from '../theme/type'
import type { Chapter } from '../timeline'

/** Index of the chapter whose tag shows at `frame` (three seconds from its start), null for none; never the first chapter. */
export function chapterTagIndex(chapters: readonly Chapter[], frame: number, fps: number): number | null {
  const index = chapters.findIndex((c, i) => i > 0 && frame >= c.frame && frame < c.frame + 3 * fps)
  return index < 0 ? null : index
}

export const ChapterTag: React.FC<{ chapters: readonly Chapter[] }> = ({ chapters }) => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const index = chapterTagIndex(chapters, frame, fps)
  if (index === null) return null
  const chapter = chapters[index]
  const z = ZONES.chapter
  return (
    <LayoutBox id="chapter" kind="text" style={{ position: 'absolute', left: z.x, top: z.y, width: z.w, height: z.h, overflow: 'hidden', whiteSpace: 'nowrap', ...overFootage, ...bootIn(frame, chapter.frame) }}>
      <span style={hud(22, colors.crt300)}>{`CH ${String(index).padStart(2, '0')} // `}</span>
      <span style={hud(22, colors.green)}>{typeOn(chapter.title, frame, chapter.frame + 4, 1)}</span>
    </LayoutBox>
  )
}
