/**
 * @vitest-environment jsdom
 *
 * Every entry imports analytics/boot before React mounts; that import is what
 * keeps page translation from blanking the page (utils/translatedDom.ts).
 */

import { describe, expect, it, vi } from 'vitest'

vi.mock('../index', () => ({ MAX_VALUE_CHARS: 200, pageType: () => 'radar', track: vi.fn() }))

describe('analytics/boot', () => {
  it('installs the translation guard: removing a node the translator detached no longer throws', async () => {
    const parent = document.createElement('span')
    const text = document.createTextNode('Searching 2 sources...')
    expect(() => parent.removeChild(text)).toThrow()
    await import('../boot')
    expect(() => parent.removeChild(text)).not.toThrow()
  })
})
