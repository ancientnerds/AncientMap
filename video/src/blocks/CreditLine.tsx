/**
 * The scene's in-frame credit (timeline.credits: photo licences, source pages,
 * Mapbox/OpenStreetMap/Maxar for map content), merged into one line. Visible for
 * the whole scene, by default right aligned in the credit zone above the YouTube
 * controls. `zone` puts it elsewhere (the Thumbnail's THUMBNAIL_CREDIT_ZONE,
 * bottom left); the line is aligned to the frame edge its zone is nearer to.
 */
import React from 'react'

import type { Rect } from '../layout/geometry'
import { LayoutBox } from '../layout/LayoutBox'
import { FRAME, ZONES } from '../layout/zones'
import { body, overFootage } from '../theme/type'

export const CreditLine: React.FC<{ id: string; text: string; zone?: Rect }> = ({ id, text, zone: z = ZONES.credit }) => {
  return (
    <LayoutBox
      id={id}
      kind="text"
      style={{
        position: 'absolute',
        left: z.x,
        top: z.y,
        width: z.w,
        height: z.h,
        overflow: 'hidden',
        textAlign: z.x + z.w / 2 > FRAME.w / 2 ? 'right' : 'left',
        whiteSpace: 'nowrap',
        ...body(18, 'rgba(255, 255, 255, 0.85)'),
        lineHeight: `${z.h}px`,
        ...overFootage,
      }}
    >
      {text}
    </LayoutBox>
  )
}
