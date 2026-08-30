/**
 * StoryArchivePage — the paginated listing at /news-archive/.
 *
 * Reached from the "Story Archive" nav entry. The listing arrives
 * pre-rendered in the server-injected route, so there is no fetch on
 * mount. Since the react-ssr Task 14 cutover the payload carries the raw
 * snake_case rows; blurbs and date display happen here.
 */

import Breadcrumbs from '../components/layout/Breadcrumbs'
import AiNoticeBanner from '../components/layout/AiNoticeBanner'
import CommunityCta from '../components/layout/CommunityCta'
import PageHeader from '../components/layout/PageHeader'
import { longDate } from '../seo/display'
import { useRoute } from '../seo/RouteContext'
import { blurb } from '../seo/text'

import '../styles/story-page.css'

function pageHref(n: number, q: string): string {
  // Der Pager muss die aktive Suche weitertragen, sonst blättert Seite 2
  // wieder im ungefilterten Archiv.
  const query = q ? `?q=${encodeURIComponent(q)}` : ''
  return n <= 1 ? `/news-archive/${query}` : `/news-archive/page/${n}${query}`
}

/**
 * Numbered pager: page 1, current ±2 and the last page, with ellipsis gaps
 * (1 … 22 23 [24] 25 26 … 46). Prev/Next alone meant a click depth of 46 to
 * the oldest story — the numbered bar caps it at 3 hops. Every entry is a
 * real <a href> so crawlers follow it; deliberately NO rel=prev/next
 * (Google has ignored it since 2019).
 */
function pagerItems(page: number, totalPages: number): (number | 'gap')[] {
  const wanted = new Set([1, totalPages])
  for (let n = page - 2; n <= page + 2; n++) {
    if (n >= 1 && n <= totalPages) wanted.add(n)
  }
  const items: (number | 'gap')[] = []
  let prev = 0
  for (const n of [...wanted].sort((a, b) => a - b)) {
    if (n - prev > 1) items.push('gap')
    items.push(n)
    prev = n
  }
  return items
}

export default function StoryArchivePage() {
  // Das Payload kommt aus dem Route-Kontext; die Typen aus StoryArchiveRoute.
  const route = useRoute()
  if (route?.type !== 'storyArchive') return null
  const { page, total_pages: totalPages, total, stories } = route
  const q = (route.q ?? '').trim()
  return (
    <div className="story-page">
      <PageHeader currentPage="news">
        <span className="page-header-title">Story Archive</span>
      </PageHeader>

      <main className="story-main">
        <Breadcrumbs trail={[{ name: 'Home', path: '/' }, { name: 'Story Archive' }]} />

        <h1 className="story-title">Story Archive</h1>
        <div className="story-meta">
          {/* Explizites en-US: das Default-Locale wäre das des SSR-Hosts —
              auf einer deutschen Maschine würde "2.248" gerendert, Pythons
              f"{total:,}" schrieb "2,248". */}
          {total.toLocaleString('en-US')} stories
          {q && ` matching “${q}”`}
          {totalPages > 1 && ` · page ${page} of ${totalPages}`}
          {q && (
            <a className="story-search-clear" href="/news-archive/">
              clear search
            </a>
          )}
        </div>

        {/* Plain GET aufs Archiv — die Suche funktioniert ohne JavaScript,
            der Server filtert (articles_html.py) und die ?q=-Seiten sind
            noindex (storyArchiveMeta). */}
        <form className="story-search" action="/news-archive/" method="get" role="search">
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder="Search stories…"
            aria-label="Search stories"
          />
          <button type="submit">Search</button>
        </form>

        {/* Art. 50 EU AI Act. The crawler fragment carries the notice, but
            React replaced #root without it — the only page type where the
            visible label vanished on hydration (audit 2026-08-09). */}
        <AiNoticeBanner message="Story summaries are AI-generated from YouTube video content. Always verify with original sources." />

        {stories.length === 0 && q && (
          <p className="story-archive-empty">
            No stories match “{q}”. <a href="/news-archive/">Browse all stories</a>
          </p>
        )}

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
          <nav className="story-pager" aria-label="Archive pages">
            {page > 1 && <a href={pageHref(page - 1, q)}>← Previous</a>}
            {pagerItems(page, totalPages).map((item, i) =>
              item === 'gap' ? (
                <span key={`gap-${i}`} className="story-pager-gap">
                  …
                </span>
              ) : item === page ? (
                <span key={item} className="story-pager-current" aria-current="page">
                  {item}
                </span>
              ) : (
                <a key={item} href={pageHref(item, q)}>
                  {item}
                </a>
              ),
            )}
            {page < totalPages && <a href={pageHref(page + 1, q)}>Next →</a>}
          </nav>
        )}
        <CommunityCta />
      </main>
    </div>
  )
}
