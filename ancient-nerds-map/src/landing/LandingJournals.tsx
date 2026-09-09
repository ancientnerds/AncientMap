import type { JournalTeaser } from '../types/anRoute'
import LazyImage from '../components/LazyImage'
import { dateRange, shortDate } from './dates'
import SectionHead from './SectionHead'

interface Props {
  data: { lead: JournalTeaser; rail: JournalTeaser[]; total: number }
}

export default function LandingJournals({ data }: Props) {
  const { lead, rail, total } = data
  return (
    <section className="ll-section" id="journal-live" aria-labelledby="ll-fig-2">
      <SectionHead
        fig={2}
        name="weekly journal"
        status={`No. ${lead.id}${lead.published_at ? ` · published ${shortDate(lead.published_at)}` : ''} · ${total} issues`}
      />
      <div className="ll-two">
        <a className="ll-lead" href={lead.path}>
          {lead.image_url && (
            <span className="ll-img ll-img-21x9">
              <LazyImage src={lead.image_url} alt="" width={1280} height={549} />
            </span>
          )}
          <span className="ll-body">
            <span className="ll-meta-row">
              <span className="ll-badge ll-cat-journal">journal</span>{' '}
              <span className="ll-meta">
                {dateRange(lead.week_start, lead.week_end)} · {lead.words.toLocaleString('en-US')} words · {lead.minutes} min read · {lead.sources} sources
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
                <span className="ll-meta">No. {j.id} · {dateRange(j.week_start, j.week_end)} · {j.minutes} min</span>
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
