/**
 * The canonical journal page's citation cards.
 *
 * Until 2026-10-17 only the standalone SPA reader showed a card for a citation,
 * so /articles.html#slug and /articles/{slug} were two pages. The server now
 * writes the citation links itself
 * (pipeline/article_html_renderer.journal_citation_anchors) and this file pins
 * what the client adds on top of them.
 *
 * @vitest-environment jsdom
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ArticleBody from '../ArticleBody'
import { markPopoverLinks } from '../JournalCitations'
import type { NewsItemData } from '../../../types/news'

// React only flushes effects inside act() when this flag is set.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const ITEM = {
  id: 42,
  headline: 'Baalbek',
  post_text: 'The stones predate the Romans.',
  facts: null,
  timestamp_range: null,
  timestamp_seconds: null,
  screenshot_url: null,
  youtube_url: null,
  youtube_deep_url: null,
  video: {
    id: 'v1',
    title: 'Baalbek',
    channel_name: 'IntoTheMap',
    channel_id: 'c1',
    published_at: '2026-10-01',
    thumbnail_url: null,
    duration_minutes: 12,
  },
  created_at: '2026-10-01T00:00:00Z',
  site_id: null,
  site_name: null,
  site_lat: null,
  site_lon: null,
  site_type: null,
  site_period_name: null,
  site_period_start: null,
  site_country: null,
  site_name_extracted: null,
  significance: 4,
} as unknown as NewsItemData

/** What pipeline/article_html_renderer.journal_citation_anchors writes. */
const HTML = [
  '<p>The stones were moved with capstans.',
  '<a class="article-citation-link" data-citation="1" href="https://example.org/a"',
  ' target="_blank" rel="noopener noreferrer">[1]</a>, the video claims',
  '<a class="article-citation-link" data-citation="V2" href="#sources">[V2]</a>.</p>',
].join('')

describe('markPopoverLinks', () => {
  const cards = new Map<string, NewsItemData>([['V2', ITEM]])

  it('marks the citation that has a card', () => {
    expect(markPopoverLinks(HTML, cards)).toContain(
      'article-citation-link has-popover" data-citation="V2"',
    )
  })

  it('leaves a citation without a card a plain link', () => {
    const marked = markPopoverLinks(HTML, cards)
    expect(marked).toContain('class="article-citation-link" data-citation="1"')
    expect(marked).not.toContain('has-popover" data-citation="1"')
  })

  it('changes nothing when no card came', () => {
    expect(markPopoverLinks(HTML, new Map())).toBe(HTML)
  })
})

describe('the server render', () => {
  it('carries every citation link and fetches nothing', () => {
    global.fetch = vi.fn() as unknown as typeof fetch
    const html = renderToStaticMarkup(
      <ArticleBody html={HTML} className="articles-reader-body" articleId={42} />,
    )
    expect(html).toContain('data-citation="1"')
    expect(html).toContain('data-citation="V2"')
    expect(html).toContain('href="#sources"')
    expect(global.fetch).not.toHaveBeenCalled()
  })
})

describe('the client', () => {
  let container: HTMLDivElement
  let root: Root | null = null

  const flush = () => new Promise(resolve => setTimeout(resolve, 0))

  function mount(articleId: number | null) {
    act(() => {
      root = createRoot(container)
      root.render(<ArticleBody html={HTML} className="articles-reader-body" articleId={articleId} />)
    })
  }

  function link(key: string): HTMLAnchorElement {
    return container.querySelector(`a[data-citation="${key}"]`) as HTMLAnchorElement
  }

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ V2: ITEM }),
    }) as unknown as typeof fetch
  })

  afterEach(() => {
    act(() => root?.unmount())
    root = null
    container.remove()
    vi.restoreAllMocks()
  })

  it('asks the API for the cards of its own issue', async () => {
    mount(42)
    await act(async () => {
      await flush()
    })
    expect(String((global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0])).toContain(
      '/news/articles/42/citations',
    )
  })

  it('keeps the links the server sent', async () => {
    mount(42)
    await act(async () => {
      await flush()
    })
    expect(link('V2').getAttribute('href')).toBe('#sources')
    expect(link('V2').textContent).toBe('[V2]')
    expect(link('1').getAttribute('href')).toBe('https://example.org/a')
  })

  it('marks only the citation whose card arrived', async () => {
    mount(42)
    await act(async () => {
      await flush()
    })
    expect(link('V2').className).toContain('has-popover')
    expect(link('1').className).not.toContain('has-popover')
  })

  it('opens the card on hover', async () => {
    mount(42)
    await act(async () => {
      await flush()
    })
    await act(async () => {
      link('V2').dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
    })
    const popover = document.querySelector('.citation-popover')
    expect(popover).not.toBeNull()
    expect(popover?.textContent).toContain('Baalbek')
  })

  it('pins the card on click and lets a click outside dismiss it', async () => {
    mount(42)
    await act(async () => {
      await flush()
    })
    await act(async () => {
      link('V2').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    })
    expect(document.querySelectorAll('.citation-popover--pinned').length).toBe(1)

    await act(async () => {
      document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    })
    expect(document.querySelectorAll('.citation-popover--pinned').length).toBe(0)
  })

  it('asks for nothing on a page without an issue id', async () => {
    mount(null)
    await act(async () => {
      await flush()
    })
    expect(global.fetch).not.toHaveBeenCalled()
    expect(link('V2').className).not.toContain('has-popover')
  })

  it('keeps the links when the fetch fails', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('offline')) as unknown as typeof fetch
    mount(42)
    await act(async () => {
      await flush()
    })
    expect(link('V2').getAttribute('href')).toBe('#sources')
    expect(link('V2').className).not.toContain('has-popover')
  })
})