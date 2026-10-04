/**
 * A video made from the paper, rendered as the SSR sidecar renders it: a real
 * YouTube link around our own poster image (owner decision #13, spec §2.7),
 * or the framed posterless player for a video registered without one. No
 * image from YouTube and no iframe until a visitor clicks.
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { ResearchVideo } from '../../../types/anRoute'
import PaperVideo from '../PaperVideo'

const POSTER = '/data/research-images/7f00aa00-0000-4000-8000-000000000000/video_dQw4w9WgXcQ.jpg'
const VIDEO: ResearchVideo = {
  youtube_id: 'dQw4w9WgXcQ',
  title: 'Baalbek: the 1,000-tonne question',
  published_at: '2026-10-01T15:00:00+00:00',
  poster: POSTER,
}

describe('PaperVideo', () => {
  it('draws our own poster inside the real YouTube link, no iframe before the click', () => {
    const html = renderToString(<PaperVideo video={VIDEO} />)
    expect(html).toContain(
      '<a href="https://www.youtube.com/watch?v=dQw4w9WgXcQ" target="_blank" rel="noopener noreferrer" ' +
        'class="story-video-link" aria-label="Play the video: Baalbek: the 1,000-tonne question">' +
        `<img src="${POSTER}" alt="" loading="lazy"/>`,
    )
    expect(html).not.toContain('is-posterless')
    expect(html).not.toContain('<iframe')
    expect(html).not.toContain('i.ytimg.com')
  })

  it('a video registered without a poster keeps the posterless player', () => {
    const html = renderToString(<PaperVideo video={{ ...VIDEO, poster: null }} />)
    expect(html).toContain('<a href="https://www.youtube.com/watch?v=dQw4w9WgXcQ" target="_blank"')
    expect(html).toContain('class="story-video-link is-posterless"')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('<iframe')
    expect(html).not.toContain('i.ytimg.com')
  })

  it('names the play link for screen readers in both variants', () => {
    // The poster is alt="" and the glyph aria-hidden: without a label the link has no name.
    for (const video of [VIDEO, { ...VIDEO, poster: null }]) {
      const html = renderToString(<PaperVideo video={video} />)
      expect(html).toContain('aria-label="Play the video: Baalbek: the 1,000-tonne question"')
    }
  })

  it('captions the title and the publication day', () => {
    const html = renderToString(<PaperVideo video={VIDEO} />)
    expect(html).toContain('Baalbek: the 1,000-tonne question</a> · October 01, 2026</figcaption>')
  })
})
