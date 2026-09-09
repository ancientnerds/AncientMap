import type { StoryTeaser } from '../types/anRoute'
import LazyImage from '../components/LazyImage'
import RelativeTime from './RelativeTime'
import SectionHead from './SectionHead'

export interface StoriesBlock {
  lead: StoryTeaser
  rail: StoryTeaser[]
  categories: string[]
}

interface Props {
  initial: StoriesBlock
  total: number
}

const PLACEHOLDER =
  'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9"><rect fill="%230a1a14" width="16" height="9"/></svg>'

function Badge({ category }: { category: string | null }) {
  if (!category) return null
  return <span className={`ll-badge ll-cat-${category}`}>{category}</span>
}

function Meter({ value }: { value: number | null }) {
  if (value == null) return null
  return (
    <span className="ll-sig" aria-label={`significance ${value} of 10`}>
      SIG <b>{value}</b>
      <span className="ll-meter">
        <i style={{ width: `${value * 10}%` }} />
      </span>
    </span>
  )
}

export function StoryLead({ story }: { story: StoryTeaser }) {
  return (
    <a className="ll-lead" href={story.path}>
      <span className="ll-img ll-img-16x9">
        <LazyImage src={story.screenshot_url ?? PLACEHOLDER} alt="" width={1280} height={720} fallbackSrc={PLACEHOLDER} />
      </span>
      <span className="ll-body">
        <span className="ll-meta-row">
          <Badge category={story.category} /> <Meter value={story.significance} />
        </span>
        <span className="ll-title">{story.headline}</span>
        <span className="ll-p">{story.summary}</span>
        <span className="ll-meta">
          <b>{story.channel}</b> · {story.sources} sources · <RelativeTime iso={story.created_at} />
          {story.site && (
            <>
              {' · '}
              <span className="ll-site">{story.site.name}{story.site.country ? ` · ${story.site.country}` : ''}</span>
            </>
          )}
        </span>
      </span>
    </a>
  )
}

export function StoryRow({ story }: { story: StoryTeaser }) {
  return (
    <a className="ll-row ll-row-thumb" href={story.path}>
      <span className="ll-img ll-img-16x9">
        <LazyImage src={story.screenshot_url ?? PLACEHOLDER} alt="" width={192} height={108} fallbackSrc={PLACEHOLDER} />
      </span>
      <span>
        <span className="ll-row-title">{story.headline}</span>
        <span className="ll-meta">
          <Badge category={story.category} /> · SIG {story.significance ?? '–'} · {story.site ? story.site.name : story.channel} ·{' '}
          <RelativeTime iso={story.created_at} />
        </span>
      </span>
    </a>
  )
}

export default function LandingStories({ initial, total }: Props) {
  const { lead, rail } = initial
  return (
    <section className="ll-section" id="stories-live">
      <SectionHead fig={1} name="stories, live" status={`${total.toLocaleString('en-US')} stories · newest first`} />
      <div className="ll-two">
        <StoryLead story={lead} />
        <div className="ll-rail">
          {rail.map(s => (
            <StoryRow key={s.id} story={s} />
          ))}
        </div>
      </div>
      <div className="ll-foot">
        <span>lead = highest significance of the last 48h · rail = newest</span>
        <a href="/news.html">all stories →</a>
      </div>
    </section>
  )
}
