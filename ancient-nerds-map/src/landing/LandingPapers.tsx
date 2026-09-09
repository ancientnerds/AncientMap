/**
 * The research Papers section: a NERV window running the paper page.
 *
 * Same shape as the Stories and Journal sections (2026-09-10): the lead's
 * payload carries the report's body_html, so the window body is the very
 * <PaperArticle> /research/{slug} renders — hero, header, byline, reading
 * time, licence, report text — cut after a whole block by excerpt_html. The
 * evidence strip sits under it, the older papers beside it.
 *
 * The Theo line stays outside the window: it is the state of the agent, not
 * part of any one paper.
 */
import PaperArticle from '../components/theo/PaperArticle'
import type { LandingRoute, PaperTeaser } from '../types/anRoute'
import { shortDate } from '../seo/display'
import LandingWindow from './LandingWindow'
import RelativeTime from './RelativeTime'
import SectionHead from './SectionHead'

interface Props {
  data: NonNullable<LandingRoute['papers']>
}

function Evidence({ paper }: { paper: PaperTeaser }) {
  return (
    <span className="ll-evidence">
      <span><i>sources analyzed</i><b>{paper.sources_analyzed.toLocaleString('en-US')}</b></span>
      {paper.quality_score != null && <span><i>quality</i><b>{paper.quality_score}</b></span>}
      {paper.words != null && <span><i>length</i><b>{paper.words.toLocaleString('en-US')} words</b></span>}
      <span><i>license</i><b>CC BY 4.0</b></span>
    </span>
  )
}

export default function LandingPapers({ data }: Props) {
  const { lead, rail, total, theo } = data
  // published_at, words and minutes are all nullable — the meta lines are
  // joined from the parts that exist so no separator dangles.
  return (
    <section className="ll-section" id="papers-live" aria-labelledby="ll-fig-3">
      <SectionHead fig={3} name="research papers" status={`${total} public · CC BY 4.0 · by Theo`} />
      <LandingWindow
        title={
          <>
            {'>_ research.log — '}
            <b>{lead.title}</b>
          </>
        }
        openHref={lead.path}
        openTitle="Open the paper"
        archiveHref="/research/"
        archiveTitle="Research library"
        listLabel="More papers"
        article={
          <>
            <PaperArticle
              paper={lead}
              headingLevel="h3"
              headlineHref={lead.path}
              minutes={lead.minutes}
              aiNotice
            />
            {lead.excerpted && (
              <a className="ll-continue" href={lead.path}>
                continue reading →
              </a>
            )}
            <Evidence paper={lead} />
          </>
        }
        list={
          <>
            {rail.map(p => (
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
          </>
        }
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
