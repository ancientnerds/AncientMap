/**
 * Der Discord-Link im CTA-Block (steht auf allen ~7.400 indexierten Seiten)
 * muss durch den Mess-Redirect gehen — ein direkter discord.gg-Href wäre
 * wieder unmessbar. renderToString wie im SSR-Sidecar: kein DOM nötig.
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import CommunityCta from './CommunityCta'

describe('CommunityCta', () => {
  const html = renderToString(<CommunityCta />)

  it('verlinkt Discord über /goto/discord?src=seo', () => {
    expect(html).toContain('href="/goto/discord?src=seo"')
  })

  it('enthält keinen rohen discord.gg-Link', () => {
    expect(html).not.toContain('discord.gg')
  })
})
