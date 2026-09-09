/**
 * The weekly Journal section: a NERV window running the journal page.
 *
 * Same shape as the Stories section (2026-09-10, owner: "just a window that
 * shows the story page — and the same for the journals and research papers").
 * The lead's payload carries the issue's body_html, so the window body is the
 * very <JournalArticle> /articles/{slug} renders, cut after a whole block by
 * excerpt_html; the column beside it lists the older issues.
 *
 * No in-window swap here: an issue is a long read, not a card. Every row is
 * a plain link, and so are the section chips of the lead above them.
 */
import JournalArticle from '../components/news/JournalArticle'
import type { LandingRoute } from '../types/anRoute'
import { shortDate } from '../seo/display'
import { dateRange } from './dates'
import LandingWindow from './LandingWindow'
import SectionHead from './SectionHead'

interface Props {
  data: NonNullable<LandingRoute['journals']>
}

export default function LandingJournals({ data }: Props) {
  const { lead, rail, total } = data
  // Every meta line is assembled from the parts that exist and only then
  // joined: week_start/week_end and published_at are nullable, and a
  // hard-coded " · " between them prints a dangling separator.
  return (
    <section className="ll-section" id="journal-live" aria-labelledby="ll-fig-2">
      <SectionHead
        fig={2}
        name="weekly journal"
        status={[
          `No. ${lead.id}`,
          lead.published_at && `published ${shortDate(lead.published_at)}`,
          `${total} issues`,
        ]
          .filter(Boolean)
          .join(' · ')}
      />
      <LandingWindow
        title={
          <>
            {'>_ journal.log — '}
            <b>{lead.title}</b>
          </>
        }
        openHref={lead.path}
        openTitle="Open the journal"
        archiveHref="/articles.html"
        archiveTitle="Journal archive"
        listLabel="More journals"
        article={
          <>
            <JournalArticle article={lead} headingLevel="h3" headlineHref={lead.path} />
            {lead.excerpted && (
              <a className="ll-continue" href={lead.path}>
                continue reading →
              </a>
            )}
          </>
        }
        list={
          <>
            {lead.sections.length > 0 && (
              <span className="ll-toc">
                {lead.sections.map(s => (
                  <a key={s} href={lead.path}>
                    {s}
                  </a>
                ))}
              </span>
            )}
            {rail.map(j => (
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
          </>
        }
      />
      <div className="ll-foot">
        <span>every Sunday · sourced, cited, illustrated</span>
        <a href="/articles.html">all {total} journals →</a>
      </div>
    </section>
  )
}
