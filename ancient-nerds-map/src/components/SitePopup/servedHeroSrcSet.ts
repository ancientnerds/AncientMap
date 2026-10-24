import type { SiteData } from '../../data/sites'

/**
 * The srcset of the hero the popup shows, or none. The srcset belongs to the hero the
 * page was served with (the `site` prop, 2026-10-20): a hero an admin sets in the
 * lightbox (heroImageOverride, `?v=` appended), an edited record or another source's
 * picture has no 800 px phone copy, and the old hero's copy would show the replaced
 * picture on phones (review 2026-10-20).
 */
export function servedHeroSrcSet(
  site: SiteData | undefined,
  heroImageSrc: string | undefined,
): string | undefined {
  return site && heroImageSrc === site.image ? site.imageSrcSet : undefined
}
