/**
 * ArticleBody — the journal body as the indexed views render it.
 *
 * Lived in ArticlesPage.tsx until 2026-09-10; moved here so the homepage
 * journal window can render the very same body without pulling in the
 * 1,100-line page (and its SPA branch, its quality report, its citation
 * popovers). ArticlesPage imports it back — the standalone /articles.html
 * mode still uses ArticleScreenshot and formatTimestamp directly.
 */

import { useMemo } from 'react'

import SanitizedMarkdownHtml from '../../seo/SanitizedMarkdownHtml'
import type { NewsItemData } from '../../types/news'
import InlineVideo from './InlineVideo'

import '../../styles/journal-article.css'

/** Parse screenshot filename → video_id + timestamp.
 *  Format: /news/screenshots/{video_id}_{timestamp}.webp  */
function parseScreenshotUrl(src: string): { videoId: string; timestamp: number } | null {
  const m = src.match(/\/news\/screenshots\/([^/]+?)_(\d+)\.\w+$/)
  if (!m) return null
  return { videoId: m[1], timestamp: parseInt(m[2], 10) }
}

export function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

/**
 * Playable screenshot: the frame IS the video. Click it and the player takes
 * its place — the same behaviour the story cards have, via the same
 * InlineVideo component, which owns the play state, the channel that pauses
 * every other player on the page, and the embed.
 */
export function ArticleScreenshot({ src, alt, citationItems }: {
  src: string
  alt: string
  citationItems?: Map<string, NewsItemData>
}) {
  const parsed = parseScreenshotUrl(src || '')

  // Try to get video metadata from citations
  let videoId = parsed?.videoId
  let timestamp = parsed?.timestamp ?? 0
  if (videoId && citationItems && citationItems.size > 0) {
    for (const item of citationItems.values()) {
      if (item.video.id === videoId) {
        timestamp = item.timestamp_seconds ?? timestamp
        break
      }
    }
  }

  if (!videoId) {
    return (
      <figure className="article-figure">
        <img src={src} alt={alt || ''} loading="lazy" className="article-screenshot" />
        {alt && <figcaption className="article-figcaption">{alt}</figcaption>}
      </figure>
    )
  }

  const watchUrl = `https://youtube.com/watch?v=${videoId}&t=${timestamp}s`

  return (
    <figure className="article-figure">
      <InlineVideo
        videoId={videoId}
        startSeconds={timestamp}
        title={alt || 'Video frame'}
        watchUrl={watchUrl}
        embedClassName="article-video-embed"
      >
        {play => (
          // Ein echter Link auf YouTube: Rechtsklick und Strg-Klick behalten
          // ihre Bedeutung, ein normaler Klick spielt hier ab.
          <a
            className="article-video-thumb"
            href={watchUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={e => {
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
              e.preventDefault()
              play()
            }}
          >
            <img src={src} alt={alt || ''} loading="lazy" className="article-screenshot" />
            <svg className="article-video-play" width="48" height="48" viewBox="0 0 24 24" fill="currentColor">
              <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
            </svg>
          </a>
        )}
      </InlineVideo>
      <figcaption className="article-figcaption">
        {alt && <span>{alt}</span>}
        {alt && <span className="article-figcaption-sep"> — </span>}
        <a
          className="article-video-link"
          href={watchUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          &#9654; Watch on YouTube (at {formatTimestamp(timestamp)})
        </a>
      </figcaption>
    </figure>
  )
}

/** Die Figure-Blöcke, die article_html_renderer._figure_with_caption erzeugt. */
const FIGURE_RE = /<figure class="article-figure">[\s\S]*?<\/figure>/g
const FIGURE_SRC_RE = /<img[^>]*src="([^"]+)"/
const FIGURE_ALT_RE = /<img[^>]*alt="([^"]*)"/

/**
 * Der Artikelkörper der indexierten Ansicht. Sie bekommt fertiges HTML und
 * kann deshalb keine React-Renderer benutzen wie die SPA-Ansicht — dadurch
 * waren die Videoframes hier tote Bilder, während dieselben Frames in der
 * SPA-Ansicht und in den Story-Karten abspielbar sind.
 *
 * Der Körper wird darum an den Figure-Blöcken aufgetrennt: dazwischen das
 * sanitisierte HTML wie bisher, für jede Figure die echte Komponente. Der
 * Server rendert denselben Baum, ein Crawler sieht also weiterhin Bild und
 * Bildunterschrift.
 */
export default function ArticleBody({ html, className, citationItems }: {
  html: string
  className?: string
  citationItems?: Map<string, NewsItemData>
}) {
  const parts = useMemo(() => {
    const out: Array<{ kind: 'html' | 'figure'; value: string }> = []
    let last = 0
    for (const match of html.matchAll(FIGURE_RE)) {
      if (match.index! > last) out.push({ kind: 'html', value: html.slice(last, match.index) })
      out.push({ kind: 'figure', value: match[0] })
      last = match.index! + match[0].length
    }
    if (last < html.length) out.push({ kind: 'html', value: html.slice(last) })
    return out
  }, [html])

  return (
    <div className={className}>
      {parts.map((part, i) =>
        part.kind === 'figure' ? (
          <ArticleScreenshot
            key={i}
            src={(part.value.match(FIGURE_SRC_RE) || [])[1] || ''}
            alt={(part.value.match(FIGURE_ALT_RE) || [])[1] || ''}
            citationItems={citationItems}
          />
        ) : (
          <SanitizedMarkdownHtml key={i} html={part.value} />
        ),
      )}
    </div>
  )
}
