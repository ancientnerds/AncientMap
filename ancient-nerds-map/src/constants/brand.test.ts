/**
 * discordCtaUrl baut den Mess-Redirect (api/routes/goto.py). Die src-Werte
 * sind per DiscordCtaSource typgebunden; dass sie mit der Python-Allowlist
 * übereinstimmen, prüft tests/api/test_goto_discord.py gegen diese Datei.
 */

import { describe, expect, it } from 'vitest'

import type { DiscordCtaSource } from './brand'
import { DISCORD_INVITE_URL, discordCtaUrl } from './brand'

const SOURCES: DiscordCtaSource[] = ['seo', 'landing', 'app', 'account', 'lyra', 'disclaimer']

describe('discordCtaUrl', () => {
  it.each(SOURCES)('baut /goto/discord?src=%s', (src) => {
    expect(discordCtaUrl(src)).toBe(`/goto/discord?src=${src}`)
  })

  it('zeigt auf den Redirect, nicht auf den rohen Invite', () => {
    for (const src of SOURCES) {
      expect(discordCtaUrl(src)).not.toContain('discord.gg')
    }
  })

  it('der rohe Invite bleibt als Referenzwert erhalten (llms.txt, JSON-LD, goto.py-Ziel)', () => {
    expect(DISCORD_INVITE_URL).toMatch(/^https:\/\/discord\.gg\/.+/)
  })
})
