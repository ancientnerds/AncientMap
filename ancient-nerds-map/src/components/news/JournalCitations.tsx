/**
 * JournalCitations — the citation cards of a journal issue, on the canonical
 * page /articles/{slug}.
 *
 * The body arrives as server-rendered HTML whose citation markers are already
 * links: `pipeline/article_html_renderer.journal_citation_anchors` turns the
 * issue's "[6]" and "[V2]" into anchors carrying `data-citation`, so a crawler
 * and a reader without JavaScript follow them. What is left is the card a
 * reader gets on hover or on click — until 2026-10-17 only the standalone SPA
 * reader had one, which is why /articles.html#slug and /articles/{slug} were
 * two different pages.
 *
 * The cards come from /news/articles/{id}/citations, keyed by the marker
 * itself. An issue whose video has no card still shows its links; a marker
 * without a card keeps its plain link and is not decorated.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { config } from '../../config'
import { discordCtaUrl } from '../../constants/brand'
import type { NewsItemData } from '../../types/news'

import { formatTimestamp } from './ArticleBody'
import CitationPopover from './CitationPopover'

/** How long the card stays open after the pointer leaves it. */
const HOVER_CLOSE_MS = 150

const POPOVER_CLASS = ' has-popover'
const CITE_LINK_RE = /<a class="article-citation-link"([^>]*?)>/g

/**
 * The cards of one issue, empty until the fetch lands and forever if it fails:
 * a card is an enhancement, the link above it is the content.
 */
export function useCitationCards(articleId: number | null | undefined): Map<string, NewsItemData> {
  const [cards, setCards] = useState<Map<string, NewsItemData>>(new Map())

  useEffect(() => {
    if (!articleId) {
      setCards(new Map())
      return
    }
    let cancelled = false
    fetch(`${config.api.baseUrl}/news/articles/${articleId}/citations`)
      .then(r => (r.ok ? r.json() : {}))
      .then((data: Record<string, NewsItemData>) => {
        if (cancelled) return
        setCards(new Map(Object.entries(data || {})))
      })
      .catch(() => {
        /* non-critical: the links stay, the cards do not come */
      })
    return () => {
      cancelled = true
    }
  }, [articleId])

  return cards
}

/**
 * Mark the citation links that have a card, so the stylesheet can show the
 * dotted underline the reader's Markdown renderer added client-side.
 *
 * A string pass, not a DOM pass: the body is injected with
 * `dangerouslySetInnerHTML` and React never owns those nodes, and the markup a
 * crawler reads must not change when a fetch is slow.
 */
export function markPopoverLinks(html: string, cards: Map<string, NewsItemData>): string {
  if (cards.size === 0) return html
  return html.replace(CITE_LINK_RE, (tag, attrs: string) => {
    const match = /data-citation="([^"]*)"/.exec(attrs)
    if (!match || !cards.has(match[1])) return tag
    return `<a class="article-citation-link${POPOVER_CLASS}"${attrs}>`
  })
}

function citationAnchor(target: EventTarget | null): HTMLAnchorElement | null {
  if (!(target instanceof Element)) return null
  return target.closest('a[data-citation]')
}

interface PinnedCard {
  num: string
  rect: DOMRect
}

/**
 * Hover and pinned cards, driven by delegation over the injected body: React
 * renders no node of it, so the links are found from the event target.
 */
export function useCitationPopovers(cards: Map<string, NewsItemData>) {
  const [hover, setHover] = useState<PinnedCard | null>(null)
  const [pinned, setPinned] = useState<PinnedCard[]>([])
  const hoverTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastAnchor = useRef<HTMLAnchorElement | null>(null)

  const cancelHoverClose = useCallback(() => {
    if (hoverTimeout.current) {
      clearTimeout(hoverTimeout.current)
      hoverTimeout.current = null
    }
  }, [])

  const scheduleHoverClose = useCallback(() => {
    cancelHoverClose()
    hoverTimeout.current = setTimeout(() => setHover(null), HOVER_CLOSE_MS)
  }, [cancelHoverClose])

  useEffect(() => cancelHoverClose, [cancelHoverClose])

  // A click outside every pinned card dismisses them all.
  useEffect(() => {
    if (pinned.length === 0) return
    const onMouseDown = (e: MouseEvent) => {
      const popovers = document.querySelectorAll('.citation-popover--pinned')
      for (const popover of popovers) {
        if (popover.contains(e.target as Node)) return
      }
      setPinned([])
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [pinned])

  // A new issue means no card of the last one may stay open.
  useEffect(() => {
    setHover(null)
    setPinned([])
  }, [cards])

  const onMouseOver = useCallback(
    (e: React.MouseEvent) => {
      const anchor = citationAnchor(e.target)
      if (!anchor || anchor === lastAnchor.current) return
      lastAnchor.current = anchor
      const num = anchor.getAttribute('data-citation') || ''
      if (!num || !cards.has(num)) return
      cancelHoverClose()
      setHover({ num, rect: anchor.getBoundingClientRect() })
    },
    [cards, cancelHoverClose],
  )

  const onMouseOut = useCallback(
    (e: React.MouseEvent) => {
      const anchor = citationAnchor(e.target)
      if (!anchor || anchor !== lastAnchor.current) return
      lastAnchor.current = null
      const to = e.relatedTarget
      // Moving inside the same link is not leaving it.
      if (to instanceof Node && anchor.contains(to)) return
      if (to instanceof Node && (to as Element).closest?.('.citation-popover')) return
      scheduleHoverClose()
    },
    [scheduleHoverClose],
  )

  const onClick = useCallback(
    (e: React.MouseEvent) => {
      const anchor = citationAnchor(e.target)
      if (!anchor) return
      const num = anchor.getAttribute('data-citation') || ''
      if (!num || !cards.has(num)) return
      e.preventDefault()
      setHover(null)
      cancelHoverClose()
      const rect = anchor.getBoundingClientRect()
      setPinned(current =>
        current.some(c => c.num === num)
          ? current.filter(c => c.num !== num)
          : [...current, { num, rect }],
      )
    },
    [cards, cancelHoverClose],
  )

  const unpin = useCallback((num: string) => {
    setPinned(current => current.filter(c => c.num !== num))
  }, [])

  return {
    hover,
    pinned,
    unpin,
    scheduleHoverClose,
    cancelHoverClose,
    handlers: { onMouseOver, onMouseOut, onClick },
  }
}

/** The open cards: every pinned one, and the hovered one when it is not pinned. */
export function CitationPopoverLayer({
  cards,
  hover,
  pinned,
  onMouseEnter,
  onMouseLeave,
  onUnpin,
  toCardProps,
}: {
  cards: Map<string, NewsItemData>
  hover: PinnedCard | null
  pinned: PinnedCard[]
  onMouseEnter: () => void
  onMouseLeave: () => void
  onUnpin: (num: string) => void
  toCardProps: (item: NewsItemData) => Parameters<typeof CitationPopover>[0]['cardProps']
}) {
  const pinnedNums = new Set(pinned.map(p => p.num))
  return (
    <>
      {pinned.map(
        pin =>
          cards.has(pin.num) && (
            <CitationPopover
              key={pin.num}
              cardProps={toCardProps(cards.get(pin.num)!)}
              anchorRect={pin.rect}
              onMouseEnter={() => {}}
              onMouseLeave={() => {}}
              pinned
              onClose={() => onUnpin(pin.num)}
            />
          ),
      )}
      {hover && !pinnedNums.has(hover.num) && cards.has(hover.num) && (
        <CitationPopover
          cardProps={toCardProps(cards.get(hover.num)!)}
          anchorRect={hover.rect}
          onMouseEnter={onMouseEnter}
          onMouseLeave={onMouseLeave}
        />
      )}
    </>
  )
}

/**
 * The creators an issue is built from, grouped by channel.
 *
 * The reader used to REPLACE the issue's "### Sources" list with this
 * panel. Here it stands after the list instead: the list stays in the
 * served HTML, where a crawler follows it, and the panel is the part
 * that only a reader can use (it needs the fetched cards).
 */
export function SourcesAttribution({ cards }: { cards: Map<string, NewsItemData> }) {
  // Group citations by channel
  const channelGroups = useMemo(() => {
    const groups = new Map<string, { channelName: string; channelId: string; items: { num: string; item: NewsItemData }[] }>()
    for (const [num, item] of cards) {
      const key = item.video.channel_id || item.video.channel_name
      if (!groups.has(key)) {
        groups.set(key, {
          channelName: item.video.channel_name,
          channelId: item.video.channel_id || '',
          items: [],
        })
      }
      groups.get(key)!.items.push({ num, item })
    }
    // Sort groups by earliest citation number
    return [...groups.values()].sort((a, b) => a.items[0].num.localeCompare(b.items[0].num))
  }, [cards])

  if (channelGroups.length === 0) return null

  return (
    <div className="articles-attribution">
      <h3 className="articles-attribution-heading">Sources & Attribution</h3>
      <p className="articles-attribution-thanks">
        This journal wouldn&rsquo;t exist without these incredible creators who bring archaeology and ancient
        history to life. We are deeply grateful for their work &mdash; please visit their channels, like,
        subscribe, and support them.
      </p>

      <div className="articles-attribution-cards">
        {channelGroups.map(group => (
          <div key={group.channelId || group.channelName} className="articles-attribution-channel">
            <div className="articles-attribution-channel-header">
              <a
                href={`https://www.youtube.com/channel/${group.channelId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="articles-attribution-channel-name"
              >
                {group.channelName}
              </a>
              <span className="articles-attribution-count">
                {group.items.length} citation{group.items.length !== 1 ? 's' : ''}
              </span>
            </div>
            <div className="articles-attribution-items">
              {group.items.map(({ num, item }) => (
                <a
                  key={num}
                  className="articles-attribution-item"
                  href={item.youtube_deep_url || item.youtube_url || '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <span className="articles-attribution-num">[{num}]</span>
                  <span className="articles-attribution-video-title">{item.video.title}</span>
                  {item.timestamp_seconds != null && (
                    <span className="articles-attribution-ts">
                      {formatTimestamp(item.timestamp_seconds)}
                    </span>
                  )}
                </a>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="articles-attribution-optout">
        <p>
          Are you a YouTube creator? If you&rsquo;d like your channel excluded, reach out with
          subject &ldquo;Channel Opt-Out&rdquo;.
        </p>
        <div className="contact-links">
          <a href="mailto:ancient.nerds@protonmail.com?subject=Channel%20Opt-Out" target="_blank" rel="noopener noreferrer">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <path d="M22 7l-10 6L2 7" />
            </svg>
            Email
          </a>
          <a href={discordCtaUrl('app')} target="_blank" rel="noopener noreferrer">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20.317 4.37a19.791 19.791 0 00-4.885-1.515.074.074 0 00-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 00-5.487 0 12.64 12.64 0 00-.617-1.25.077.077 0 00-.079-.037A19.736 19.736 0 003.677 4.37a.07.07 0 00-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 00.031.057 19.9 19.9 0 005.993 3.03.078.078 0 00.084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 00-.041-.106 13.107 13.107 0 01-1.872-.892.077.077 0 01-.008-.128 10.2 10.2 0 00.372-.292.074.074 0 01.077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 01.078.01c.12.098.246.198.373.292a.077.077 0 01-.006.127 12.299 12.299 0 01-1.873.892.077.077 0 00-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 00.084.028 19.839 19.839 0 006.002-3.03.077.077 0 00.032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 00-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.095 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.095 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
            </svg>
            Discord
          </a>
        </div>
      </div>
    </div>
  )
}
