/**
 * StoryArchivePage — the paginated listing at /news-archive/.
 *
 * Reached from the "Story Archive" nav entry. The listing arrives
 * pre-rendered in the server-injected route, so there is no fetch on mount.
 */

import AiNoticeBanner from '../components/layout/AiNoticeBanner'
import CommunityCta from '../components/layout/CommunityCta'
import PageHeader from '../components/layout/PageHeader'

import '../styles/story-page.css'

export interface ArchiveEntry {
  slug: string
  headline: string
  summary: string
  /* Context the listing query already joins — cards looked identical without it. */
  publishedDisplay?: string
  category?: string
  siteName?: string
  channelName?: string
  speculativeTag?: string
  screenshotUrl?: string
}

interface Props {
  page: number
  totalPages: number
  total: number
  stories: ArchiveEntry[]
}

function pageHref(n: number): string {
  return n <= 1 ? '/news-archive/' : `/news-archive/page/${n}`
}

export default function StoryArchivePage({ page, totalPages, total, stories }: Props) {
  return (
    <div className="story-page">
      <PageHeader currentPage="news">
        <span className="page-header-title">Story Archive</span>
      </PageHeader>

      <main className="story-main">
        <nav className="story-crumb">
          <a href="/">Home</a> / Story Archive
        </nav>

        <h1 className="story-title">Story Archive</h1>
        <div className="story-meta">
          {total.toLocaleString()} stories
          {totalPages > 1 && ` · page ${page} of ${totalPages}`}
        </div>

        {/* Art. 50 EU AI Act. The crawler fragment carries the notice, but
            React replaced #root without it — the only page type where the
            visible label vanished on hydration (audit 2026-08-09). */}
        <AiNoticeBanner message="Story summaries are AI-generated from YouTube video content. Always verify with original sources." />

        <div className="story-archive-list">
          {stories.map(s => {
            const meta = [
              s.publishedDisplay,
              s.category,
              s.siteName,
              s.channelName && `via ${s.channelName}`,
            ].filter(Boolean)
            return (
              <a
                key={s.slug}
                className="story-archive-card site-list-card"
                href={`/news-archive/${s.slug}`}
              >
                {/* The video frame was stored per story all along and only
                    used as an og:image. 2,190 of 2,248 stories have one. */}
                {s.screenshotUrl && (
                  <img
                    className="site-list-card-thumb"
                    src={s.screenshotUrl}
                    alt=""
                    loading="lazy"
                  />
                )}
                <div className="site-list-card-body">
                  <h3>
                    {s.headline}
                    {s.speculativeTag && <span className="story-badge">{s.speculativeTag}</span>}
                  </h3>
                  {s.summary && <p>{s.summary}</p>}
                  {meta.length > 0 && <div className="story-card-meta">{meta.join(' · ')}</div>}
                </div>
              </a>
            )
          })}
        </div>

        {totalPages > 1 && (
          <nav className="story-pager">
            {page > 1 && <a href={pageHref(page - 1)}>← Previous</a>}
            {page < totalPages && <a href={pageHref(page + 1)}>Next →</a>}
          </nav>
        )}
        <CommunityCta />
      </main>
    </div>
  )
}
