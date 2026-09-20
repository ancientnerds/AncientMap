import { getCountryFlatFlagUrl } from '../../utils/countryFlags'

import { countryName, fmtInt } from './format'
import type { CountryCount } from './types'

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

/**
 * The countries behind a tile's number, biggest first, in a box that fills the
 * space to the right of it. The box is exactly as tall as the number (its
 * wrapper is a flex item with no content of its own, the list inside is
 * absolute), the flags wrap to use every line of it, and whatever no longer
 * fits is cut off instead of shrinking the number (owner, 2026-09-19). The
 * fade marks the cut.
 */
export function Flags({ rows }: { rows: CountryCount[] }) {
  if (rows.length === 0) return null
  return (
    <div className="dash-flags-box">
      <ul className="dash-flags">
        {rows.map(r => (
          <li className="dash-flag" key={r.country} title={`${countryName(r.country)}: ${fmtInt(r.sessions)}`}>
            <Flag country={r.country} />
            {fmtInt(r.sessions)}
          </li>
        ))}
      </ul>
    </div>
  )
}
