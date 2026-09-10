/**
 * The research Papers section: a NERV window with a portal on /research/.
 *
 * The cards used to sit under the window as a gallery of the six newest
 * papers. They moved into the library itself on 2026-09-11 (owner: "The
 * research paper examples should be inside the portal, not below it. And
 * the research library should have the cards, not plain headings.") —
 * /research/ renders PaperCard now, and the portal shows that page, so the
 * section says everything once instead of twice.
 *
 * The Theo line stays outside the window: it is the state of the agent, not
 * part of any one paper.
 */
import type { LandingRoute } from '../types/anRoute'
import LandingWindow from './LandingWindow'
import PagePortal from './PagePortal'
import RelativeTime from './RelativeTime'
import SectionHead from './SectionHead'

interface Props {
  data: NonNullable<LandingRoute['papers']>
}

export default function LandingPapers({ data }: Props) {
  const { total, theo } = data
  return (
    <section className="ll-section" id="papers-live" aria-labelledby="ll-fig-3">
      <SectionHead fig={3} name="research papers" status={`${total} public · CC BY 4.0 · by Theo`} />
      <LandingWindow
        title={
          <>
            {'>_ portal — '}
            <b>/research/</b>
          </>
        }
        openHref="/research/"
        openTitle="Open research library"
      >
        <PagePortal
          src="/research/"
          poster="/data/previews/research.jpg"
          title="Research library"
          openHref="/research/"
          openLabel="Open research library"
        />
      </LandingWindow>
      {theo && (
        <a className="ll-theo" href="/theo.html">
          <span>
            <i className="ll-pulse" /> Theo is researching: <b>{theo.question}</b>
            {theo.started_at ? <> · started <RelativeTime iso={theo.started_at} /></> : null} · {theo.sites_found.toLocaleString('en-US')} sites found
          </span>
          <span>watch live →</span>
        </a>
      )}
      <div className="ll-foot">
        <span>papers publish when the citation gate passes · all titles are listed below</span>
        <a href="/research/">research library →</a>
      </div>
    </section>
  )
}
