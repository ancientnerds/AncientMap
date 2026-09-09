import type { PaperTeaser, TheoStatus } from '../types/anRoute'
import LazyImage from '../components/LazyImage'
import { shortDate } from './dates'
import RelativeTime from './RelativeTime'
import SectionHead from './SectionHead'

interface Props {
  data: { lead: PaperTeaser; rail: PaperTeaser[]; total: number; theo: TheoStatus | null }
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
  return (
    <section className="ll-section" id="papers-live" aria-labelledby="ll-fig-3">
      <SectionHead fig={3} name="research papers" status={`${total} public · CC BY 4.0 · by Theo`} />
      <div className="ll-two">
        <a className="ll-lead" href={lead.path}>
          {lead.hero_image_url && (
            <span className="ll-img ll-img-16x9">
              <LazyImage src={lead.hero_image_url} alt="" width={1280} height={720} />
            </span>
          )}
          <span className="ll-body">
            <span className="ll-meta-row">
              <span className="ll-badge ll-cat-paper">paper</span>{' '}
              <span className="ll-meta">
                {lead.published_at ? `published ${shortDate(lead.published_at)}` : ''}
                {lead.minutes != null ? ` · ${lead.minutes} min read` : ''}
              </span>
            </span>
            <span className="ll-title">{lead.title}</span>
            {lead.summary && <span className="ll-p">{lead.summary}</span>}
            <Evidence paper={lead} />
          </span>
        </a>
        <div className="ll-rail">
          {rail.map(p => (
            <a key={p.slug} className="ll-row" href={p.path}>
              <span>
                <span className="ll-row-title">{p.title}</span>
                <span className="ll-meta">
                  {p.words != null ? `${p.words.toLocaleString('en-US')} words · ` : ''}
                  {p.sources_analyzed.toLocaleString('en-US')} sources
                  {p.published_at ? ` · ${shortDate(p.published_at)}` : ''}
                </span>
              </span>
              <span className="ll-badge ll-cat-paper">paper</span>
            </a>
          ))}
        </div>
      </div>
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
