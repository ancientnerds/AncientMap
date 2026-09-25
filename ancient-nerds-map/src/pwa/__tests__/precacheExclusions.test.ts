/**
 * One precache URL that does not answer 200 fails the service worker's whole
 * install, and every returning browser keeps its old worker and old pages for
 * good: from 2026-09-12 to 2026-09-26 /site.html answered 404 and no worker
 * installed anywhere. Any built page whose own URL nginx hands to the API is
 * such a URL.
 */

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { PRECACHE_GLOB_IGNORES } from '../precacheExclusions'

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')
const NGINX = readFileSync(resolve(REPO, 'ancientnerds-nginx-config'), 'utf-8')

/** The .html pages nginx answers from a proxy instead of from dist/. */
function proxiedPages(config: string): string[] {
  const pages: string[] = []
  const block = /location\s*=\s*\/([\w-]+\.html)\s*\{([^}]*)\}/g
  for (let m = block.exec(config); m; m = block.exec(config)) {
    if (m[2].includes('proxy_pass')) pages.push(m[1])
  }
  return pages
}

describe('PRECACHE_GLOB_IGNORES', () => {
  it('finds the proxied pages in the nginx config it guards', () => {
    expect(proxiedPages(NGINX)).toEqual(expect.arrayContaining(['site.html', 'research.html']))
  })

  it('keeps every page nginx sends to the API out of the precache', () => {
    for (const page of proxiedPages(NGINX)) expect(PRECACHE_GLOB_IGNORES).toContain(page)
  })

  it('still keeps the data and the dashboard out', () => {
    expect(PRECACHE_GLOB_IGNORES).toEqual(expect.arrayContaining(['**/data/**', 'dashboard.html']))
  })
})
