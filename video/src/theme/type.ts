/** Text styles shared by every block (sizes in composition pixels at 1920x1080). */
import type { CSSProperties } from 'react'

import { colors } from './colors'
import { BODY, HEADING, SERIF } from './fonts'

export const heading = (size: number, color: string = colors.white): CSSProperties => ({
  fontFamily: HEADING,
  fontWeight: 700,
  fontSize: size,
  lineHeight: 1.15,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color,
})

export const body = (size: number, color: string = colors.text): CSSProperties => ({
  fontFamily: BODY,
  fontWeight: 400,
  fontSize: size,
  lineHeight: 1.35,
  color,
})

export const hud = (size: number, color: string = colors.green): CSSProperties => ({
  fontFamily: BODY,
  fontWeight: 500,
  fontSize: size,
  lineHeight: 1.2,
  letterSpacing: '0.14em',
  textTransform: 'uppercase',
  color,
})

export const serif = (size: number, color: string = colors.white): CSSProperties => ({
  fontFamily: SERIF,
  fontWeight: 400,
  fontSize: size,
  lineHeight: 1.25,
  color,
})

/** Readable over footage: a soft dark halo instead of a box. */
export const overFootage: CSSProperties = { textShadow: '0 2px 10px rgba(0, 0, 0, 0.95), 0 0 2px rgba(0, 0, 0, 0.9)' }
