/**
 * StoryPage — one story at /news-archive/{slug}, inside the normal app layout.
 *
 * "Story", not "news": a video published this week routinely covers a find
 * from decades ago, so the archive is dated by its source, not by recency.
 *
 * The payload arrives pre-rendered in window.__AN_ROUTE__, so there is no
 * fetch and no loading state — what the crawler was served and what the
 * visitor sees are built from the same data.
 */

import PageHeader from '../components/layout/PageHeader'
import type { StoryRoute } from '../types/anRoute'

import '../styles/story-page.css'

interface Props {
  story: StoryRoute
}

export default function StoryPage({ story }: Props) {
  const paragraphs = story.postText.split('\n').map(p => p.trim()).filter(Boolean)

  return (
    <div className="story-page">
      <PageHeader currentPage="news">
        <span className="page-header-title">Story Archive</span>
      </PageHeader>

      <main className="story-main">
        <nav className="story-crumb">
          <a href="/">Home</a> / <a href="/news-archive/">Story Archive</a>
        </nav>

        <h1 className="story-title">
          {story.headline}
          {story.speculativeTag && <span className="story-badge">{story.speculativeTag}</span>}
        </h1>

        <div className="story-meta">
          {story.publishedDisplay && <time dateTime={story.publishedAt}>{story.publishedDisplay}</time>}
          {story.category && <span className="story-tag">{story.category}</span>}
        </div>

        {(story.screenshotUrl || story.youtubeUrl) && (
          <figure className="story-video">
            {story.youtubeUrl ? (
              <a href={story.youtubeUrl} target="_blank" rel="noopener noreferrer" className="story-video-link">
                {story.screenshotUrl && <img src={story.screenshotUrl} alt={story.videoTitle || story.headline} loading="lazy" />}
                <span className="story-play" aria-hidden="true">▶</span>
              </a>
            ) : (
              story.screenshotUrl && <img src={story.screenshotUrl} alt={story.videoTitle || story.headline} loading="lazy" />
            )}
            {(story.videoTitle || story.channelName) && (
              <figcaption>
                Source:{' '}
                {story.youtubeUrl ? (
                  <a href={story.youtubeUrl} target="_blank" rel="noopener noreferrer">
                    {story.videoTitle || 'video'}
                  </a>
                ) : (
                  story.videoTitle
                )}
                {story.channelName && ` by ${story.channelName}`}
              </figcaption>
            )}
          </figure>
        )}

        {story.summary && <p className="story-summary">{story.summary}</p>}

        <div className="story-body">
          {paragraphs.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>

        {story.facts.length > 0 && (
          <>
            <h2>Key facts</h2>
            <ul className="story-facts">
              {story.facts.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </>
        )}

        {story.siteName && (
          <div className="story-site">
            <h2>Site mentioned</h2>
            <div className="story-chips">
              {story.sitePath ? (
                <a className="story-chip" href={story.sitePath}>📄 {story.siteName}</a>
              ) : (
                <span className="story-chip is-plain">📍 {story.siteName}</span>
              )}
              {/* The detail page needs a country, the globe only needs the id —
                  bulk-imported sites often lack a country. */}
              {story.siteId && (
                <a className="story-chip" href={`/globe.html?site=${encodeURIComponent(story.siteId)}`}>
                  🌍 Show on the globe
                </a>
              )}
            </div>
          </div>
        )}

        {story.sources?.length > 0 && (
          <div className="story-sources">
            <h2>Sources</h2>
            {story.sources.map((s, i) => (
              <div className="story-source" key={i}>
                <a href={s.url} target="_blank" rel="noopener nofollow">{s.title}</a>
                <span className="story-source-host">{s.host}</span>
                {s.snippet && <div className="story-source-snippet">{s.snippet}</div>}
              </div>
            ))}
          </div>
        )}

        {story.related?.length > 0 && (
          <div className="story-related">
            <h2>{story.related[0].kind === 'site' && story.siteName
              ? `More about ${story.siteName}`
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

        {/* Disclosure belongs on the page (EU AI Act Art. 50) but not as a
            banner above the story — a quiet footnote does the same job. */}
        <p className="story-ai-notice">
          AI-generated text · images from the original sources · always verify with the sources.
        </p>
      </main>
    </div>
  )
}
