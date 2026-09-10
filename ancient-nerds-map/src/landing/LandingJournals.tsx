/**
 * The weekly Journal section: a NERV window with a portal on /articles.html.
 *
 * Same shape as the Stories section (2026-09-10, owner: "I want a kind of
 * portal to the pages — like a screenshot that shows the current state"):
 * the live journal hub runs scaled down in the window, the column beside it
 * lists every issue in the payload as a plain link — newest first, which is
 * also the crawlable half of the section.
 */
import type { LandingRoute } from '../types/anRoute'
import { shortDate } from '../seo/display'
import { dateRange } from './dates'
import LandingWindow from './LandingWindow'
import PagePortal from './PagePortal'
import SectionHead from './SectionHead'

interface Props {
  data: NonNullable<LandingRoute['journals']>
}

export default function LandingJournals({ data }: Props) {
  const { items, total } = data
  const newest = items[0]
  // Every meta line is assembled from the parts that exist and only then
  // joined: week_start/week_end and published_at are nullable, and a
  // hard-coded " · " between them prints a dangling separator.
  return (
    <section className="ll-section" id="journal-live" aria-labelledby="ll-fig-2">
      <SectionHead
        fig={2}
        name="weekly journal"
        status={[
          `No. ${newest.id}`,
          newest.published_at && `published ${shortDate(newest.published_at)}`,
          `${total} issues`,
        ]
          .filter(Boolean)
          .join(' · ')}
      />
      <LandingWindow
        title={
          <>
            {'>_ portal — '}
            <b>/articles.html</b>
          </>
        }
        openHref="/articles.html"
        openTitle="Open journals"
        listLabel="More journals"
        main={
          <PagePortal
            src="/articles.html"
            title="Weekly journals — live view"
            openHref="/articles.html"
            openLabel="Open journals"
          />
        }
        list={items.map(j => (
          <a key={j.id} className="ll-row" href={j.path}>
            <span>
              <span className="ll-row-title">{j.title}</span>
              <span className="ll-meta">
                {[`No. ${j.id}`, dateRange(j.week_start, j.week_end), `${j.minutes} min`]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </span>
            <span className="ll-arrow">→</span>
          </a>
        ))}
      />
      <div className="ll-foot">
        <span>every Sunday · sourced, cited, illustrated</span>
        <a href="/articles.html">all {total} journals →</a>
      </div>
    </section>
  )
}
