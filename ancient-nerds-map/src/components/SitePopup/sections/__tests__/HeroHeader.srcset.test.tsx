/**
 * The popup hero on the site page carries the same srcset as the server-rendered
 * record (owner decision 2026-10-20): the popup replaces the record on mount, and
 * without it a phone would load the 1600 px original after all.
 */
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { HeroHeader } from '../HeroHeader'

function hero(heroImageSrcSet?: string): string {
  return renderToString(
    <HeroHeader
      title="Göbekli Tepe"
      heroImageSrc="/data/images/wiki/d953e9b3/hero.webp"
      heroImageSrcSet={heroImageSrcSet}
      sourceInfo={undefined}
      sourceName=""
      sourceColor=""
      category=""
      period=""
      catColor=""
      periodColor=""
      titleCopied={false}
      onTitleCopy={() => {}}
      isStandalone
    />,
  )
}

describe('HeroHeader srcset', () => {
  it('passes the srcset with the full-viewport sizes', () => {
    const srcSet = '/data/images/wiki-800/d953e9b3/hero.webp 800w, /data/images/wiki/d953e9b3/hero.webp 1600w'
    const html = hero(srcSet)
    expect(html).toContain(`srcSet="${srcSet}"`)
    expect(html).toContain('sizes="100vw"')
    expect(html).toContain('src="/data/images/wiki/d953e9b3/hero.webp"')
  })

  it('renders the single file without one', () => {
    const html = hero(undefined)
    expect(html).not.toMatch(/srcset=/i)
    expect(html).not.toContain('sizes=')
  })
})
