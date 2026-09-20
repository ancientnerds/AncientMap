import { describe, expect, it } from 'vitest'

import { clusterItem } from '../Scrapers'
import type { Cluster } from '../types'

/** The two fingerprints SQL_CLUSTERS returns live on 2026-09-19. */
const mac: Cluster = { screen: '1366x1366', browser: 'chrome', os: 'Mac OS', sessions: 25 }

describe('Scrapers clusterItem', () => {
  it('joins screen, browser and os into one fingerprint label', () => {
    const row = clusterItem(mac)
    expect(row.label).toBe('1366x1366 · chrome · Mac OS')
    expect(row.value).toBe(25)
    expect(row.hint).toBe('sessions')
  })

  it('leaves out a field the session table has no value for', () => {
    expect(clusterItem({ ...mac, browser: null }).label).toBe('1366x1366 · Mac OS')
  })

  it('names a session that reported nothing at all', () => {
    const blank = clusterItem({ screen: null, browser: null, os: null, sessions: 3 })
    expect(blank.label).toBe('unknown machine')
    expect(blank.key).toBe('unknown')
  })

  it('gives two identical fingerprints the same key', () => {
    // SQL_CLUSTERS groups by exactly these three columns, so the list cannot
    // actually hold the pair — the key still has to be a pure function of
    // them, because React would silently drop the second row if it were not.
    expect(clusterItem(mac).key).toBe(clusterItem({ ...mac, sessions: 16 }).key)
    expect(clusterItem(mac).key).toBe('1366x1366|chrome|Mac OS')
  })
})
