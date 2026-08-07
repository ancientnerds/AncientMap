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

        <h1 className="story-title">{story.headline}</h1>

        <div className="story-meta">
          {story.publishedDisplay && <time dateTime={story.publishedAt}>{story.publishedDisplay}</time>}
          {story.category && <span className="story-tag">{story.category}</span>}
        </div>

        <p className="story-ai-notice">
          AI-generated text: the text on this page was produced automatically by an AI system.
          Images are from the original sources, not AI-generated. Always verify with the original sources.
        </p>

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
            <h2>Related site</h2>
            {story.sitePath ? (
              <p>
                <a href={story.sitePath}>{story.siteName}</a>
                {story.siteId && (
                  <>
                    {' · '}
                    <a href={`/globe.html?site=${encodeURIComponent(story.siteId)}`}>Show on the globe</a>
                  </>
                )}
              </p>
            ) : (
              <p>{story.siteName}</p>
            )}
          </div>
        )}

        <p className="story-back">
          <a href="/news-archive/">← All stories</a>
        </p>
      </main>
    </div>
  )
}
