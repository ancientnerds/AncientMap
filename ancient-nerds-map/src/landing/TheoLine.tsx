/**
 * The Theo line under the papers window: the state of the agent, which is
 * not part of any one paper and so sits outside the portal. NERV orange —
 * the one deliberate colour beside green and red on this page
 * (landing-live.css). The start date is absolute ("Sep 9"): the homepage
 * ships no React to the browser, so there is no one to turn it into "1d ago".
 */
import { shortDate } from '../seo/display'
import type { TheoStatus } from '../types/anRoute'

export default function TheoLine({ theo }: { theo: TheoStatus }) {
  return (
    <a className="ll-theo" href="/theo.html">
      <span>
        <i className="ll-pulse" /> Theo is researching: <b>{theo.question}</b>
        {theo.started_at ? (
          <>
            {' · started '}
            <time dateTime={theo.started_at}>{shortDate(theo.started_at)}</time>
          </>
        ) : null}{' · '}
        {/* The DB column is sites_found for V1 reasons, but it counts
            registry.sources — every search result registered across the 13
            connectors, not archaeological sites. LiveResearchPanel already
            says "sources"; this line was the last one saying "sites". */}
        {theo.sites_found.toLocaleString('en-US')} sources found
      </span>
      <span>watch live →</span>
    </a>
  )
}
