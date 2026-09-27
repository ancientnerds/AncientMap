import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { MIRROR, colors } from '../src/theme/colors'

/** A file of the frontend, read as text (the site is the source of every mirrored colour). */
const site = (rel: string) => readFileSync(fileURLToPath(new URL(`../../ancient-nerds-map/src/${rel}`, import.meta.url)), 'utf-8')
const TOKENS = site('styles/tokens.css')
const CONSTANTS = site('constants/colors.ts')

describe('the NERV palette mirrors the site (spec 4.8)', () => {
  it.each(MIRROR.map((m) => [m.key, m] as const))('%s', (_key, m) => {
    const hex = colors[m.key]
    if ('token' in m) expect(TOKENS).toContain(`${m.token}: ${hex};`)
    else expect(CONSTANTS).toContain(`${m.constant}: '${hex}'`)
  })
  it('mirrors every hex colour of the palette but white', () => {
    const hexKeys = Object.entries(colors)
      .filter(([key, value]) => key !== 'white' && /^#[0-9a-f]{6}$/i.test(value))
      .map(([key]) => key)
    expect(MIRROR.map((m) => m.key).sort()).toEqual(hexKeys.sort())
  })
})
