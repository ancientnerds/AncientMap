/**
 * Measurements calculateMetadata takes in the browser before the first frame:
 * narration clip lengths (the music ducks under them) and image pixel sizes
 * (PhotoPlate places fractional marker boxes in image pixels). Both read the
 * files of the per-render public dir; a file that cannot be read fails the render.
 */
import { staticFile } from 'remotion'

import type { ImageSizes } from './context'

/** Length of an audio file in seconds, from its metadata. */
export function audioSeconds(src: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const el = document.createElement('audio')
    el.preload = 'metadata'
    el.onloadedmetadata = () => resolve(el.duration)
    el.onerror = () => reject(new Error(`cannot read audio metadata of ${src}`))
    el.src = staticFile(src)
  })
}

/** Natural pixel size of an image. */
function imagePixels(src: string): Promise<[number, number]> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve([img.naturalWidth, img.naturalHeight])
    img.onerror = () => reject(new Error(`cannot load image ${src}`))
    img.src = staticFile(src)
  })
}

export async function measureImages(srcs: readonly string[]): Promise<ImageSizes> {
  const unique = [...new Set(srcs)]
  const sizes = await Promise.all(unique.map(imagePixels))
  return Object.fromEntries(unique.map((src, i) => [src, sizes[i]]))
}
