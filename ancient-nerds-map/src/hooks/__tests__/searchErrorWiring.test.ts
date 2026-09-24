/**
 * A failed "All sources" API search (429 from the search limiter, a 5xx, a
 * network error) is shown as a failure where the result count would be, on the
 * globe (FilterPanel's searchError slot) and on /search.html, never as a
 * finished search with no results. useSiteSearch.test.tsx proves the hook;
 * this pins how App and SearchPage show it (neither renders without the whole
 * page).
 */

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const read = (path: string) => readFileSync(resolve(SRC, path), 'utf-8')

describe('the search failure reaches the page', () => {
  it("App passes the hook's searchError to FilterPanel after the details failure", () => {
    const app = read('App.tsx')
    expect(app).toContain(
      "searchError={detailsStatus === 'failed' ? 'Search unavailable: site details failed to load. Reload the page.' : siteSearch.searchError}",
    )
  })

  it('SearchPage shows the failure instead of a count and no "No sites found" for it', () => {
    const page = read('pages/SearchPage.tsx')
    expect(page).toContain('{search.searchError ? <span>{search.searchError}</span> : search.isSearching ? <span>Searching...</span>')
    expect(page).toContain('!search.isSearching && !search.searchError && search.searchResults.length === 0')
  })
})
