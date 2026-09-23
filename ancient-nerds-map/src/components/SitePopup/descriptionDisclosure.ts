/**
 * Which disclosure belongs to the description the popup shows.
 *
 * A disclosure is a statement about one text (api/services/description_provenance.py derives
 * it only for the description its provenance hashes). The popup can show two texts: a record
 * from a live source (the SSR payload, /api/sites/{id}) carries its own disclosure, but the
 * globe's records come from the static export, which lags the database until it is
 * re-exported. So the popup's own /api/sites/{id} answer is used only when its description is
 * the one on screen - otherwise the disclosure of the new text would stand under the old one.
 */

import type { SiteData } from '../../data/sites'
import type { DescriptionAi, DescriptionAttribution } from '../../types/anRoute'

/** What /api/sites/{id} said about the description it served. */
export interface ApiDisclosure {
  description: string | undefined
  ai: DescriptionAi
  attribution: DescriptionAttribution | null
}

type ShownSite = Pick<SiteData, 'description' | 'descriptionAi' | 'descriptionAttribution'>

export function disclosureFor(
  site: ShownSite,
  fromApi: ApiDisclosure | null,
): { ai: DescriptionAi; attribution: DescriptionAttribution | null } | null {
  if (site.descriptionAi) {
    return { ai: site.descriptionAi, attribution: site.descriptionAttribution ?? null }
  }
  if (fromApi && fromApi.description === site.description) {
    return { ai: fromApi.ai, attribution: fromApi.attribution }
  }
  return null
}
