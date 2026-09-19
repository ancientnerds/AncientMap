import { getCountryFlatFlagUrl } from '../../utils/countryFlags'

import { countryName } from './format'

/** The flag images live on the main host; this one only serves the dashboard,
 *  where /flags-flat/ would be proxied to Umami. */
const FLAG_HOST = 'https://ancientnerds.com'

/**
 * One 18×12 flag with the country's name for screen readers. `loading="lazy"`
 * is deliberate: a flag clipped out of a row is never requested.
 */
export function Flag({ country }: { country: string | null }) {
  const url = country ? getCountryFlatFlagUrl(country) : null
  return (
    <>
      {url ? (
        <img src={`${FLAG_HOST}${url}`} alt="" width="18" height="12" loading="lazy" decoding="async" />
      ) : (
        <span className="dash-flag-blank" aria-hidden="true" />
      )}
      <span className="dash-sr">{countryName(country)}</span>
    </>
  )
}
