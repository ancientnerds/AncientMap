/**
 * The srcset of a site page's hero: its 800 px copy for phones and the original for
 * desktop and retina screens (owner decision 2026-10-20). The 1600 px hero was shown
 * 412 px wide on a phone, 534-557 KiB of it wasted (SEO audit 2026-10-19, cwv-6); the
 * copy of the Göbekli Tepe hero is 95 KiB instead of 552 (measured on the VPS the same
 * day). The copy exists only where the server names it (url_800, api/routes/sites_html.py:
 * an original of known width, wider than 800 px), and nginx answers a copy that
 * pipeline/wiki_thumbs.py has not written yet with the original itself.
 */

/** The width of the phone copy, HERO_WIDTH of pipeline/wiki_thumbs.py. */
const HERO_COPY_WIDTH = 800

/**
 * `sizes` of the hero: the full viewport. A phone at 412 CSS px and PageSpeed's 1.75x
 * needs 721 px and takes the copy; a desktop window (>= 1024 px) or a 3x phone needs
 * more than 800 and keeps the original - which is what the owner asked for. The record's
 * figure is narrower on a desktop (at most 772 px), and saying so would hand a 1x
 * desktop the copy.
 */
export const HERO_SIZES = '100vw'

export interface HeroImage {
  url: string
  url_800: string | null
  width: number | null
}

/** The hero's srcset, or undefined where it has no phone copy (the page keeps one file). */
export function heroSrcSet(image: HeroImage): string | undefined {
  if (!image.url_800 || !image.width) return undefined
  // Both paths arrive percent-encoded once (encode_path in api/routes/sites_html.py):
  // srcset splits on whitespace and commas, and 1,019 of 3,887 hero file names carry a
  // space, 499 a comma (production 2026-10-20).
  return `${image.url_800} ${HERO_COPY_WIDTH}w, ${image.url} ${image.width}w`
}
