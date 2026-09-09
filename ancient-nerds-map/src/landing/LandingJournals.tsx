import type { LandingRoute } from '../types/anRoute'
import { shortDate } from '../seo/display'
import { dateRange } from './dates'
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
      <div className="ll-two">
        <a className="ll-lead" href={lead.path}>
          {lead.image_url && (
            <span className="ll-img ll-img-21x9">
              <img src={lead.image_url} alt="" width={1280} height={549} loading="lazy" decoding="async" />
            </span>
          )}
          <span className="ll-body">
            <span className="ll-meta-row">
              <span className="ll-badge">journal</span>{' '}
              <span className="ll-meta">
                {[
                  dateRange(lead.week_start, lead.week_end),
                  `${lead.words.toLocaleString('en-US')} words`,
                  `${lead.minutes} min read`,
                  `${lead.sources} sources`,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </span>
            <span className="ll-title">{lead.title}</span>
            {lead.summary && <span className="ll-p">{lead.summary}</span>}
            {lead.sections.length > 0 && (
              <span className="ll-toc">
                {lead.sections.map(s => (
                  <span key={s}>{s}</span>
                ))}
              </span>
            )}
          </span>
        </a>
        <div className="ll-rail">
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
        </div>
      </div>
      <div className="ll-foot">
        <span>every Sunday · sourced, cited, illustrated</span>
        <a href="/articles.html">all {total} journals →</a>
      </div>
    </section>
  )
}
