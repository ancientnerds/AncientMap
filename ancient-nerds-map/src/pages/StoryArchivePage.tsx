/**
 * StoryArchivePage — the paginated listing at /news-archive/.
 *
 * Reached from the "Story Archive" nav entry. The listing arrives
 * pre-rendered in the server-injected route, so there is no fetch on
 * mount. Since the react-ssr Task 14 cutover the payload carries the raw
 * snake_case rows; blurbs and date display happen here.
 */

import AiNoticeBanner from '../components/layout/AiNoticeBanner'
import CommunityCta from '../components/layout/CommunityCta'
import PageHeader from '../components/layout/PageHeader'
import { longDate } from '../seo/display'
import { useRoute } from '../seo/RouteContext'
import { blurb } from '../seo/text'

import '../styles/story-page.css'

function pageHref(n: number): string {
  return n <= 1 ? '/news-archive/' : `/news-archive/page/${n}`
}

export default function StoryArchivePage() {
  // Das Payload kommt aus dem Route-Kontext; die Typen aus StoryArchiveRoute.
  const route = useRoute()
  if (route?.type !== 'storyArchive') return null
  const { page, total_pages: totalPages, total, stories } = route
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
          {/* Explizites en-US: das Default-Locale wäre das des SSR-Hosts —
              auf einer deutschen Maschine würde "2.248" gerendert, Pythons
              f"{total:,}" schrieb "2,248". */}
          {total.toLocaleString('en-US')} stories
          {totalPages > 1 && ` · page ${page} of ${totalPages}`}
        </div>

        {/* Art. 50 EU AI Act. The crawler fragment carries the notice, but
            React replaced #root without it — the only page type where the
            visible label vanished on hydration (audit 2026-08-09). */}
        <AiNoticeBanner message="Story summaries are AI-generated from YouTube video content. Always verify with original sources." />

        <div className="story-archive-list">
          {stories.map(s => {
            const summary = blurb(s.summary)
            const meta = [
              longDate(s.published_at),
              s.news_category,
              s.site_name,
              s.channel_name && `via ${s.channel_name}`,
            ].filter(Boolean)
            return (
              <a
                key={s.slug}
                className="story-archive-card site-list-card"
                href={`/news-archive/${s.slug}`}
              >
                {/* The video frame was stored per story all along and only
                    used as an og:image. 2,190 of 2,248 stories have one. */}
                {s.screenshot_url && (
                  <img
                    className="site-list-card-thumb"
                    src={s.screenshot_url}
                    alt=""
                    loading="lazy"
                  />
                )}
                <div className="site-list-card-body">
                  <h3>
                    {s.headline}
                    {s.speculative_tag && <span className="story-badge">{s.speculative_tag}</span>}
                  </h3>
                  {summary && <p>{summary}</p>}
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
