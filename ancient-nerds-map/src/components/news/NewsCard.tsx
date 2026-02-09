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
 * - onAskLyra() — optional
 * - size — 'sm' | 'md' | 'lg'
 */

import { useState } from 'react'
import { config } from '../../config'
import { apiDetailToSiteData } from '../../utils/siteApi'
import { formatDuration, formatRelativeDate } from '../../utils/formatters'
import { SiteBadges, CountryFlag } from '../metadata'
import LazyImage from '../LazyImage'
import {
  getSignificanceColor,
  getSignificanceLabel,
  getSignificanceCardStyle,
  getNewsCategoryLabel,
} from './significance'
import type { SiteData } from '../../data/sites'
import type { NewsHighlight } from '../../types/ai'

export interface NewsCardProps {
  // Core data
  headline: string
  postText?: string | null
  channelName: string
  publishedAt?: string
  significance?: number | null
  newsCategory?: string | null
  screenshotUrl?: string | null
  deepLink: string
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

  // Callbacks — minimal, parent just reacts to results
  onSiteLoaded?: (site: SiteData) => void
  onSiteHover?: (hovering: boolean) => void
  onAskLyra?: () => void

  // Facts (from API expand)
  facts?: string[] | null

  // Size
  size?: 'sm' | 'md' | 'lg'
}

const PLAY_SIZE = { sm: 20, md: 24, lg: 32 }
const PIN_SIZE = { sm: 12, md: 14, lg: 14 }

export default function NewsCard({
  headline,
  postText,
  channelName,
  publishedAt,
  significance,
  newsCategory,
  screenshotUrl,
  deepLink,
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
  onSiteLoaded,
  onSiteHover,
  onAskLyra,
  facts,
  size = 'md',
}: NewsCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(false)

  const playSize = PLAY_SIZE[size]
  const pinSize = PIN_SIZE[size]
  const hasMatchedSite = !!(siteId || (siteName && (siteCountry || siteType || sitePeriodName)))
  const displaySiteName = siteName || siteNameExtracted
  const siteIdentifier = siteId || siteName
  const isClickable = !!(onSiteLoaded && siteIdentifier)

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
      {newsCategory && newsCategory !== 'general' && (
        <span className="news-category-badge">{getNewsCategoryLabel(newsCategory)}</span>
      )}

      <div className="news-card-meta">
        <span className="news-card-channel">{channelName}</span>
        {publishedAt && <span className="news-feed-date">{formatRelativeDate(publishedAt)}</span>}
      </div>

      {significance != null && significance >= 6 && (
        <div className="news-significance-stamp" style={{ color: getSignificanceColor(significance) }}>
          {getSignificanceLabel(significance)}
        </div>
      )}

      <div className="news-card-post-text">{postText || headline}</div>

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
                {loading ? 'Loading...' : (displaySiteName || 'Show on Map')}
              </button>
            ) : (
              <span className="lyra-news-site-name">
                <svg width={pinSize} height={pinSize} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                  <circle cx="12" cy="10" r="3" />
                </svg>
                {displaySiteName}
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
          <span className="news-feed-site-unmatched-name">{siteNameExtracted}</span>
        </div>
      )}

      {screenshotUrl && (
        <a
          className="news-card-thumb"
          href={deepLink}
          target="_blank"
          rel="noopener noreferrer"
          onClick={e => e.stopPropagation()}
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
      )}

      {expanded && (
        <div className="news-card-expanded">
          {facts && facts.length > 0 && (
            <ul className="news-card-facts">
              {facts.map((fact, i) => (
                <li key={i}>{fact}</li>
              ))}
            </ul>
          )}

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

          {onAskLyra && (
            <button
              className="ask-lyra-btn"
              style={{ marginTop: 6 }}
              onClick={e => { e.stopPropagation(); onAskLyra() }}
            >
              <img src="/lyra.gif" alt="" />
              Ask Lyra
            </button>
          )}

          {videoTitle && <div className="news-card-video-title">{videoTitle}</div>}
        </div>
      )}
    </div>
  )
}

/**
 * Adapter: convert NewsHighlight (from Lyra chat SSE) → NewsCardProps.
 */
export function newsHighlightToCardProps(news: NewsHighlight): NewsCardProps {
  const deepLink = news.timestamp_seconds
    ? `https://youtu.be/${news.video_id}?t=${news.timestamp_seconds}`
    : `https://youtu.be/${news.video_id}`
  const screenshotUrl = news.screenshot_url
    ? `${config.api.baseUrl}${news.screenshot_url.replace('/api', '')}`
    : `https://img.youtube.com/vi/${news.video_id}/mqdefault.jpg`

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
