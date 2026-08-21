/**
 * NewsCard — Single self-contained news card component.
 *
 * Used by NewsFeedPanel, NewsFeedPage, and LyraChatModal.
 * Drop it anywhere — it handles expand/collapse and site fetching internally.
 *
 * Parent only provides:
 * - Data props (headline, site info, etc.)
 * - onSiteLoaded(siteData) — called after the card fetches a site; parent shows the popup
 * - onSiteHover(hovering) — optional, for globe highlighting
 * - size — 'sm' | 'md' | 'lg'
 */

import { useState, memo } from 'react'
import { config } from '../../config'
import { absoluteUrl, storyPath } from '../../seo/meta'
import { apiDetailToSiteData } from '../../utils/siteApi'
import { shareOrCopy } from '../../utils/share'
import { formatDuration, formatRelativeDate } from '../../utils/formatters'
import { SiteBadges, CountryFlag } from '../metadata'
import LazyImage from '../LazyImage'
import InlineVideo from './InlineVideo'
import { splitPostText } from './postText'
import {
  getSignificanceColor,
  getSignificanceLabel,
  getSignificanceCardStyle,
  getNewsCategoryLabel,
  getTopicColor,
} from './significance'
import type { SiteData } from '../../data/sites'
import type { NewsHighlight } from '../../types/ai'
import type { NewsItemData } from '../../types/news'
import './news-cards.css'

export interface NewsCardProps {
  // Core data
  headline: string
  postText?: string | null
  channelName: string
  publishedAt?: string
  significance?: number | null
  newsCategory?: string | null
  speculativeTag?: string | null
  screenshotUrl?: string | null
  deepLink: string
  videoId?: string
  videoTitle?: string
  durationMinutes?: number | null
  timestampSeconds?: number | null

  // Site info
  siteName?: string | null
  siteNameExtracted?: string | null
  siteId?: string | null
  siteCountry?: string | null
  siteType?: string | null
  sitePeriodName?: string | null
  sitePeriodStart?: number | null

  // Link to the story page — set it and the headline becomes a real <a>, so
  // right-click / ctrl-click / middle-click open the story in a new tab.
  // Null for stories without a public page (see storyHrefFor).
  storyHref?: string | null

  // Callbacks — minimal, parent just reacts to results
  onSiteLoaded?: (site: SiteData) => void
  onSiteHover?: (hovering: boolean) => void

  // Facts (from API expand)
  facts?: string[] | null

  // Web verification sources
  webSources?: Array<{ title: string; url: string; snippet: string }> | null

  // Verification status
  verified?: boolean

  // Display modes
  size?: 'sm' | 'md' | 'lg'
  headlinesOnly?: boolean
}

const PLAY_SIZE = { sm: 20, md: 24, lg: 32 }
const PIN_SIZE = { sm: 12, md: 14, lg: 14 }

function NewsCard({
  headline,
  postText,
  channelName,
  publishedAt,
  significance,
  newsCategory,
  speculativeTag,
  screenshotUrl,
  deepLink,
  videoId,
  videoTitle,
  durationMinutes,
  timestampSeconds,
  siteName,
  siteNameExtracted,
  siteId,
  siteCountry,
  siteType,
  sitePeriodName,
  sitePeriodStart,
  storyHref,
  onSiteLoaded,
  onSiteHover,
  facts,
  webSources,
  verified,
  size = 'md',
  headlinesOnly,
}: NewsCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  const playSize = PLAY_SIZE[size]
  const pinSize = PIN_SIZE[size]
  const hasMatchedSite = !!(siteId || (siteName && (siteCountry || siteType || sitePeriodName)))
  const displaySiteName = siteName || siteNameExtracted
  const siteIdentifier = siteId || siteName
  const isClickable = !!(onSiteLoaded && siteIdentifier)

  // Share the canonical public URL, not window.location — a story shared
  // from the globe panel or a localhost tab has to open the story page.
  const handleShare = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!storyHref) return
    const result = await shareOrCopy(headline, absoluteUrl(storyHref))
    if (result !== 'copied') return
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const handleSiteClick = async () => {
    if (loading || !siteIdentifier || !onSiteLoaded) return
    setLoading(true)
    const res = await fetch(`${config.api.baseUrl}/sites/${encodeURIComponent(siteIdentifier)}`)
    if (res.ok) {
      const detail = await res.json()
      onSiteLoaded(apiDetailToSiteData(detail))
    }
    setLoading(false)
  }

  return (
    <div
      className={`news-feed-item${expanded ? ' expanded' : ''}${hasMatchedSite ? ' has-site' : ''}`}
      style={significance ? getSignificanceCardStyle(significance) : undefined}
      onClick={() => setExpanded(prev => !prev)}
      onMouseEnter={() => hasMatchedSite && onSiteHover?.(true)}
      onMouseLeave={() => hasMatchedSite && onSiteHover?.(false)}
    >
      {(() => {
        const topic = speculativeTag || (newsCategory && newsCategory !== 'general' ? newsCategory : null)
        if (!topic) return null
        const color = getTopicColor(topic)
        return (
          <span
            className="news-category-badge"
            style={{ color, background: `${color}18`, borderLeftColor: `${color}40`, borderBottomColor: `${color}40` }}
          >
            {getNewsCategoryLabel(topic)}
          </span>
        )
      })()}

      {/* Head block — everything above the thumbnail. It exists to anchor the
          action icons: as a child of the card they sat at the bottom of
          whatever was currently rendered and jumped down on expand. Anchored
          here they stay put next to the site badges, expanded or not. Same
          flex column and 6px gap as the card, so the rhythm is unchanged. */}
      <div className="news-card-head">
      <div className="news-card-meta">
        <span className="news-card-channel">{channelName}</span>
        {publishedAt && <span className="news-feed-date">{formatRelativeDate(publishedAt)}</span>}
      </div>

      {significance != null && significance >= 6 && (
        <div className="news-significance-stamp" style={{ color: getSignificanceColor(significance) }}>
          {getSignificanceLabel(significance)}
        </div>
      )}

      <div className="news-card-headline">
        {storyHref ? (
          <a
            href={storyHref}
            onClick={e => {
              // Modifier clicks belong to the browser (new tab / new window) —
              // let them through, but stop the card from expanding underneath.
              // A plain left click keeps the card's expand/collapse behaviour,
              // so the link only ever navigates on purpose.
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) { e.stopPropagation(); return }
              e.preventDefault()
            }}
          >
            {headline}
          </a>
        ) : headline}
      </div>
      {/* Same tweet artefact as on the story page: the trailing source URL is
          plain, unclickable text in a teaser, so it goes. The story page
          renders it as a real link under Sources. */}
      {(!headlinesOnly || expanded) && postText && (
        <div className="news-card-post-text">{splitPostText(postText).paragraphs.join('\n')}</div>
      )}

      {hasMatchedSite && (
        <div className="news-feed-site-block">
          <div className="news-feed-site-row">
            {siteCountry && <CountryFlag country={siteCountry} size="sm" showName />}
            {isClickable ? (
              <button
                className="news-page-card-site-name"
                onClick={(e) => { e.stopPropagation(); handleSiteClick() }}
                disabled={loading}
              >
                <svg width={pinSize} height={pinSize} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                  <circle cx="12" cy="10" r="3" />
                </svg>
                <span className="site-name-text">{loading ? 'Loading...' : (displaySiteName || 'Show on Map')}</span>
              </button>
            ) : (
              <span className="lyra-news-site-name">
                <svg width={pinSize} height={pinSize} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                  <circle cx="12" cy="10" r="3" />
                </svg>
                <span className="site-name-text">{displaySiteName}</span>
              </span>
            )}
          </div>
          <SiteBadges category={siteType} period={sitePeriodName} periodStart={sitePeriodStart} size="sm" />
        </div>
      )}

      {!hasMatchedSite && siteNameExtracted && (
        <div className="news-feed-site-row news-feed-site-unmatched">
          <svg width={pinSize} height={pinSize} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" opacity="0.4">
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
            <circle cx="12" cy="10" r="3" />
          </svg>
          <span className="news-feed-site-unmatched-name site-name-text">{siteNameExtracted}</span>
        </div>
      )}

      {/* Icon-only actions, bottom right of the head block — the free space
          next to the site badges. Absolute, so they cost no height, and
          anchored to the head, so expanding the card never moves them. */}
      {storyHref && (
        <div className="news-card-actions">
          <button
            className={`news-card-action${copied ? ' copied' : ''}`}
            onClick={handleShare}
            title={copied ? 'Link copied' : 'Share story'}
            aria-label={copied ? 'Link copied' : 'Share story'}
          >
            {copied ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
              </svg>
            )}
          </button>
          <a
            className="news-card-action"
            href={storyHref}
            target="_blank"
            rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            title="Open story in new tab"
            aria-label="Open story in new tab"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </a>
        </div>
      )}
      </div>{/* /news-card-head */}

      {(!headlinesOnly || expanded) && screenshotUrl && (() => {
        const thumb = (play?: () => void) => (
          <a
            className="news-card-thumb"
            href={videoId ? undefined : deepLink}
            target={videoId ? undefined : '_blank'}
            rel={videoId ? undefined : 'noopener noreferrer'}
            onClick={e => { e.stopPropagation(); if (play) { e.preventDefault(); play() } }}
          >
            <LazyImage src={screenshotUrl} alt="" />
            <svg className="news-card-play" width={playSize} height={playSize} viewBox="0 0 24 24" fill="currentColor">
              <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
            </svg>
            {durationMinutes != null && (
              <span className="news-card-duration">{formatDuration(durationMinutes)}</span>
            )}
            {timestampSeconds != null && (
              <span className="news-card-timestamp">&#9654; {formatDuration(timestampSeconds / 60)}</span>
            )}
          </a>
        )
        // No video id means there is nothing to embed — the thumbnail stays a
        // plain link out to the source.
        if (!videoId) return thumb()
        return (
          <InlineVideo
            videoId={videoId}
            startSeconds={timestampSeconds}
            title={headline || 'YouTube video'}
            watchUrl={deepLink}
            embedClassName="news-card-embed"
          >
            {play => thumb(play)}
          </InlineVideo>
        )
      })()}

      {expanded && (
        <div className="news-card-expanded">
          {facts && facts.length > 0 && (
            <div className="news-card-facts">
              {facts.map((fact, i) => (
                <div key={i} className="news-card-fact">{fact}</div>
              ))}
            </div>
          )}

          {webSources && webSources.length > 0 ? (
            <div className="news-card-web-sources">
              <div className="news-card-web-sources-label">{verified && newsCategory !== 'unverified' ? '\u2713 Verified' : 'Sources'}</div>
              {webSources.map((src, i) => (
                <a
                  key={i}
                  className="news-card-web-source"
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={e => e.stopPropagation()}
                  title={src.snippet}
                >
                  {src.title}
                </a>
              ))}
            </div>
          ) : verified ? (
            <div className="news-card-web-sources">
              <div className="news-card-web-sources-label">No external sources</div>
            </div>
          ) : null}

          {deepLink && deepLink !== '#' && (
            <a
              className="news-card-watch"
              href={deepLink}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
            >
              <svg width={pinSize} height={pinSize} viewBox="0 0 24 24" fill="currentColor">
                <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
              </svg>
              Watch on YouTube
              {timestampSeconds != null && <span className="news-card-ts"> (at {formatDuration(timestampSeconds / 60)})</span>}
            </a>
          )}

          {videoTitle && <div className="news-card-video-title">{videoTitle}</div>}
        </div>
      )}
    </div>
  )
}

export default memo(NewsCard)

/**
 * URL of a story's own page, or null when /news-archive/{slug} would 404.
 *
 * Mirrors story_page_query() in api/routes/articles_html.py: a body is the
 * only requirement. Speculative stories do get a page (noindex) — the gate
 * here is not an editorial one, it only keeps us from handing the user a
 * dead link.
 */
export function storyHrefFor(item: NewsItemData): string | null {
  if (!item.post_text) return null
  return storyPath(item.headline, item.id)
}

/**
 * Adapter: convert NewsItemData (from API) → NewsCardProps.
 */
export function newsItemToCardProps(item: NewsItemData): NewsCardProps {
  // screenshot_url is passed through unchanged — /data/news/screenshots/ is
  // served by nginx in prod and servePublicData in dev; legacy /api/... rows
  // keep working through the retained mount until the DB backfill runs.
  const screenshotUrl = item.screenshot_url || item.video.thumbnail_url
  const deepLink = item.youtube_deep_url || item.youtube_url || '#'
  return {
    headline: item.headline,
    postText: item.post_text,
    channelName: item.video.channel_name,
    publishedAt: item.video.published_at,
    significance: item.significance,
    newsCategory: item.news_category,
    speculativeTag: item.speculative_tag,
    screenshotUrl,
    deepLink,
    videoId: item.video.id,
    videoTitle: item.video.title,
    durationMinutes: item.video.duration_minutes,
    timestampSeconds: item.timestamp_seconds,
    siteName: item.site_name || item.site_name_extracted,
    siteNameExtracted: item.site_name_extracted,
    siteId: item.site_id,
    siteCountry: item.site_country,
    siteType: item.site_type,
    sitePeriodName: item.site_period_name,
    sitePeriodStart: item.site_period_start,
    facts: item.facts,
    webSources: item.web_sources,
    verified: item.verified,
    storyHref: storyHrefFor(item),
  }
}

/**
 * Adapter: convert NewsHighlight (from Lyra chat SSE) → NewsCardProps.
 */
export function newsHighlightToCardProps(news: NewsHighlight): NewsCardProps {
  const deepLink = news.timestamp_seconds
    ? `https://youtu.be/${news.video_id}?t=${news.timestamp_seconds}`
    : `https://youtu.be/${news.video_id}`
  const screenshotUrl =
    news.screenshot_url || `https://img.youtube.com/vi/${news.video_id}/mqdefault.jpg`

  // Matched = has site metadata from unified_sites join (country/type/period)
  const isMatched = !!(news.site_name && (news.site_country || news.site_type || news.site_period_name))

  return {
    headline: news.headline,
    postText: news.post_text,
    channelName: news.channel,
    publishedAt: news.date,
    significance: news.significance,
    newsCategory: news.category,
    screenshotUrl,
    deepLink,
    videoId: news.video_id,
    videoTitle: news.video_title,
    timestampSeconds: news.timestamp_seconds,
    siteId: news.site_id,
    siteName: isMatched ? news.site_name : undefined,
    siteNameExtracted: !isMatched ? news.site_name : undefined,
    siteCountry: news.site_country,
    siteType: news.site_type,
    sitePeriodName: news.site_period_name,
    sitePeriodStart: news.site_period_start,
    facts: news.facts,
  }
}
