/**
 * The research Papers section: a NERV window with a portal on /research/.
 *
 * Same shape as the Stories and Journal sections (2026-09-10): the live
 * research library runs scaled down in the window, the column beside it
 * lists every public paper in the payload as a plain link.
 *
 * The Theo line stays outside the window: it is the state of the agent, not
 * part of any one paper.
 */
import type { LandingRoute } from '../types/anRoute'
import { shortDate } from '../seo/display'
import LandingWindow from './LandingWindow'
import PagePortal from './PagePortal'
import RelativeTime from './RelativeTime'
import SectionHead from './SectionHead'

interface Props {
  data: NonNullable<LandingRoute['papers']>
}

export default function LandingPapers({ data }: Props) {
  const { items, total, theo } = data
  // published_at and words are nullable — the meta lines are joined from the
  // parts that exist so no separator dangles.
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
        archiveHref="/research/"
        archiveTitle="Research library"
        listLabel="More papers"
        main={
          <PagePortal
            src="/research/"
            title="Research library — live view"
            openHref="/research/"
            openLabel="Open research library"
          />
        }
        list={items.map(p => (
          <a key={p.slug} className="ll-row" href={p.path}>
            <span>
              <span className="ll-row-title">{p.title}</span>
              <span className="ll-meta">
                {[
                  p.words != null && `${p.words.toLocaleString('en-US')} words`,
                  `${p.sources_analyzed.toLocaleString('en-US')} sources`,
                  p.published_at && shortDate(p.published_at),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </span>
            <span className="ll-badge">paper</span>
          </a>
        ))}
      />
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
