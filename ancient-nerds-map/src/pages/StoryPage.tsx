/**
 * StoryPage — one story at /news-archive/{slug}, inside the normal app layout.
 *
 * "Story", not "news": a video published this week routinely covers a find
 * from decades ago, so the archive is dated by its source, not by recency.
 *
 * The payload arrives pre-rendered as the server-injected route, so there
 * is no fetch and no loading state — what the crawler was served and what
 * the visitor sees are built from the same data. Since the react-ssr
 * Task 14 cutover the payload is the raw snake_case row; the display
 * decisions the Python renderer used to make — the http(s) source filter,
 * the &t= video deeplink, the curated-site link gate — live here.
 */

import CommunityCta from '../components/layout/CommunityCta'
import PageHeader from '../components/layout/PageHeader'
import { globeUrlForSite } from '../constants/brand'
import { isoDate, longDate } from '../seo/display'
import { absoluteUrl, sitePath } from '../seo/meta'
import { useRoute } from '../seo/RouteContext'
import { blurb } from '../seo/text'
import type { StoryRoute } from '../types/anRoute'

import '../styles/story-page.css'

/** _host_of(): nackter Hostname — Leser beurteilen einen Link an der Domain. */
function hostOf(url: string): string {
  // new URL wirft, wo Pythons urlparse ein leeres netloc liefert ("http://") —
  // derselbe Rückgabewert, nur als catch formuliert.
  try {
    return new URL(url).host.replace(/^www\./, '')
  } catch {
    return ''
  }
}

/**
 * Der Quellenblock aus den rohen web_sources: erst der [:8]-Schnitt, dann
 * der http(s)-Filter — die Liste ist LLM-derived, ein javascript:-Eintrag
 * darf nie ein href werden (Reihenfolge wie im Python-Payload).
 */
function storySources(raw: StoryRoute['web_sources']) {
  return (raw || [])
    .slice(0, 8)
    .filter((s): s is { url: string; title?: string | null; snippet?: string | null } => {
      const url = s?.url
      return typeof url === 'string' && (url.startsWith('http://') || url.startsWith('https://'))
    })
    .map(s => ({
      url: s.url,
      title: s.title || hostOf(s.url),
      host: hostOf(s.url),
      snippet: blurb(s.snippet, 200),
    }))
}

export default function StoryPage() {
  // Das Payload kommt aus dem Route-Kontext (SeoRoute mountet die Seite nur
  // für story-Routen); außerhalb davon gibt es nichts zu rendern.
  const route = useRoute()
  if (route?.type !== 'story') return null
  const story = route
  const paragraphs = story.post_text.split('\n').map(p => p.trim()).filter(Boolean)
  const summary = story.summary.trim()
  const facts = story.facts || []
  const screenshot = absoluteUrl(story.screenshot_url)
  // Sprung zur Videostelle: der Offset war pro Story gespeichert und wurde
  // bis zum Cutover in seo_pages.story_page angehängt.
  const ts = story.timestamp_seconds
  const youtubeUrl =
    story.youtube_url && typeof ts === 'number' && Number.isInteger(ts) && ts > 0
      ? `${story.youtube_url}&t=${ts}s`
      : story.youtube_url
  // Die Detailseite braucht ein Land (Teil der URL) UND eine kuratierte Site —
  // /sites/{country}/{slug} filtert auf source_id = 'ancient_nerds'.
  const sitePagePath =
    story.site_curated && story.site_country && story.site_name && story.site_id
      ? sitePath(story.site_country, story.site_name, story.site_id)
      : ''
  const sources = storySources(story.web_sources)

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
          {story.speculative_tag && <span className="story-badge">{story.speculative_tag}</span>}
        </h1>

        <div className="story-meta">
          <time dateTime={isoDate(story.published_at)}>{longDate(story.published_at)}</time>
          {story.news_category && <span className="story-tag">{story.news_category}</span>}
        </div>

        {(screenshot || youtubeUrl) && (
          <figure className="story-video">
            {youtubeUrl ? (
              <a href={youtubeUrl} target="_blank" rel="noopener noreferrer" className="story-video-link">
                {screenshot && <img src={screenshot} alt={story.video_title || story.headline} loading="lazy" />}
                <span className="story-play" aria-hidden="true">▶</span>
              </a>
            ) : (
              screenshot && <img src={screenshot} alt={story.video_title || story.headline} loading="lazy" />
            )}
            {(story.video_title || story.channel_name) && (
              <figcaption>
                Source:{' '}
                {youtubeUrl ? (
                  <a href={youtubeUrl} target="_blank" rel="noopener noreferrer">
                    {story.video_title || 'video'}
                  </a>
                ) : (
                  story.video_title
                )}
                {story.channel_name && ` by ${story.channel_name}`}
              </figcaption>
            )}
          </figure>
        )}

        {summary && <p className="story-summary">{summary}</p>}

        <div className="story-body">
          {paragraphs.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>

        {facts.length > 0 && (
          <>
            <h2>Key facts</h2>
            <ul className="story-facts">
              {facts.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </>
        )}

        {story.site_name && (
          <div className="story-site">
            <h2>Site mentioned</h2>
            <div className="story-chips">
              {sitePagePath ? (
                <a className="story-chip" href={sitePagePath}>📄 {story.site_name}</a>
              ) : (
                <span className="story-chip is-plain">📍 {story.site_name}</span>
              )}
              {/* The detail page needs a country, the globe only needs the id —
                  bulk-imported sites often lack a country. */}
              {story.site_id && (
                <a className="story-chip" href={globeUrlForSite(story.site_id)}>
                  🌍 Show on the globe
                </a>
              )}
            </div>
          </div>
        )}

        {sources.length > 0 && (
          <div className="story-sources">
            <h2>Sources</h2>
            {sources.map((s, i) => (
              <div className="story-source" key={i}>
                <a href={s.url} target="_blank" rel="noopener nofollow">{s.title}</a>
                <span className="story-source-host">{s.host}</span>
                {s.snippet && <div className="story-source-snippet">{s.snippet}</div>}
              </div>
            ))}
          </div>
        )}

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

        {/* Disclosure belongs on the page (EU AI Act Art. 50) but not as a
            banner above the story — a quiet footnote does the same job. */}
        <p className="story-ai-notice" data-ai-generated="true">
          AI-generated text · images from the original sources · always verify with the sources.
        </p>
      </main>
    </div>
  )
}
