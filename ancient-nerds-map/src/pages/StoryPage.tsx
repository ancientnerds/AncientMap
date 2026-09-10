/**
 * StoryPage — one story at /news-archive/{slug}, inside the normal app layout.
 *
 * "Story", not "news": a video published this week routinely covers a find
 * from decades ago, so the archive is dated by its source, not by recency.
 *
 * The payload arrives pre-rendered as the server-injected route, so there
 * is no fetch and no loading state — what the crawler was served and what
 * the visitor sees are built from the same data. The article itself is
 * <StoryArticle>; this page adds the shell around it: breadcrumbs, the
 * "read next" block, the way back and the CommunityCta.
 */

import Breadcrumbs from '../components/layout/Breadcrumbs'
import CommunityCta from '../components/layout/CommunityCta'
import PageHeader from '../components/layout/PageHeader'
import StoryArticle from '../components/news/StoryArticle'
import { useRoute } from '../seo/RouteContext'

import '../styles/story-page.css'

export default function StoryPage() {
  // Das Payload kommt aus dem Route-Kontext (SeoRoute mountet die Seite nur
  // für story-Routen); außerhalb davon gibt es nichts zu rendern.
  const route = useRoute()
  if (route?.type !== 'story') return null
  const story = route

  return (
    <div className="story-page">
      <PageHeader currentPage="news">
        <span className="page-header-title">Story Archive</span>
      </PageHeader>

      <main className="story-main">
        <Breadcrumbs
          trail={[
            { name: 'Home', path: '/' },
            { name: 'Story Archive', path: '/news-archive/' },
            { name: story.headline },
          ]}
        />

        {/* Everything after the sources and before the Art.-50 footnote is
            this page's own tail — StoryArticle renders it as its children so
            the disclosure stays the last element on the page. */}
        <StoryArticle story={story}>
          {story.related.length > 0 && (
            <div className="story-related">
              <h2>{story.related[0].kind === 'site' && story.site_name
                ? `More about ${story.site_name}`
                : 'Related stories'}</h2>
              <ul>
                {story.related.map(r => (
                  <li key={r.slug}>
                    <a href={`/news-archive/${encodeURIComponent(r.slug)}`}>{r.headline}</a>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="story-back">
            <a href="/news-archive/">← All stories</a>
          </p>

          <CommunityCta />
        </StoryArticle>
      </main>
    </div>
  )
}
