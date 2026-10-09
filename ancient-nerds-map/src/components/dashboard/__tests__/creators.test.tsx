/** The creator panel: what the stories send the channels Lyra reads. */
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { channelItem, Creators } from '../Creators'
import type { CreatorsData } from '../types'

const text = (html: string) => html.replace(/<!-- -->/g, '')

const DATA: CreatorsData = {
  totals: { starts: 89, viewers: 86, clicks: 2, channels: 25, videos: 70 },
  channels: [
    { channel: 'Universe Inside You', starts: 13, viewers: 13, clicks: 0 },
    { channel: 'not attributed', starts: 0, viewers: 0, clicks: 2 },
  ],
  videos: [{ id: 'abcdefghijk', title: 'All Great Pyramid Construction Theories Explained', channel: 'Universe Inside You', starts: 4 }],
  days: [
    { day: '2026-10-08', starts: 7, clicks: 0 },
    { day: '2026-10-09', starts: 6, clicks: 2 },
  ],
  clicks_since: '2026-10-09T06:42:00+00:00',
}

describe('Creators', () => {
  it('ranks a channel by everything it got and says both counts', () => {
    expect(channelItem(DATA.channels[0])).toEqual({
      key: 'ch:Universe Inside You',
      label: 'Universe Inside You',
      value: 13,
      hint: '13 started here · 0 to YouTube',
    })
  })

  it('shows the tiles, the days and the two lists', () => {
    const html = text(renderToString(<Creators state={{ data: DATA, error: null }} />))
    expect(html).toContain('How much do we send to the creators?')
    expect(html).toContain('89')
    expect(html).toContain('since 09 Oct 06:42 UTC')
    expect(html).toContain('dash-bar-red')
    expect(html).toContain('href="https://www.youtube.com/watch?v=abcdefghijk"')
  })
})
