/**
 * The Theo line under the papers window: the state of the agent, which is
 * not part of any one paper and so sits outside the portal. NERV orange —
 * the one deliberate colour beside green and red on this page
 * (landing-live.css).
 */
import type { TheoStatus } from '../types/anRoute'

import RelativeTime from './RelativeTime'

export default function TheoLine({ theo }: { theo: TheoStatus }) {
  return (
    <a className="ll-theo" href="/theo.html">
      <span>
        <i className="ll-pulse" /> Theo is researching: <b>{theo.question}</b>
        {theo.started_at ? <> · started <RelativeTime iso={theo.started_at} /></> : null} · {theo.sites_found.toLocaleString('en-US')} sites found
      </span>
      <span>watch live →</span>
    </a>
  )
}
