/**
 * What every block may read besides its own props: the episode-wide cue state,
 * the measured pixel sizes of the images (calculateMetadata measures them in
 * the browser, so a PhotoPlate can place fractional marker boxes exactly) and
 * the lint flag (lint renders skip video decoding: only the layout matters).
 */
import { createContext, useContext } from 'react'

import type { EpisodeState } from './state'

export type ImageSizes = Record<string, [number, number]>

export type EpisodeData = { state: EpisodeState; imageSizes: ImageSizes; lint: boolean }

export const EpisodeContext = createContext<EpisodeData | null>(null)

export function useEpisode(): EpisodeData {
  const data = useContext(EpisodeContext)
  if (!data) throw new Error('block rendered outside the EpisodeContext')
  return data
}

/** The measured size of a public-dir image; calculateMetadata guarantees every PhotoPlate image is measured. */
export function imageSize(sizes: ImageSizes, src: string): [number, number] {
  const size = sizes[src]
  if (!size) throw new Error(`image ${src} was not measured`)
  return size
}
