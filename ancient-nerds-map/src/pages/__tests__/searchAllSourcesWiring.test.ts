/**
 * The search page's "All sources" button answers two searches: the one the
 * visitor switched on, and the one the hook switched on for them because their
 * own sources had no match at all (useSiteSearch.test.tsx proves the hook).
 * Both have to light the same chip, and one click has to switch both off -
 * otherwise the button shows a search the page is not running.
 *
 * The page renders no smaller than its whole data load, so this pins the wiring
 * in the source, as searchErrorWiring.test.ts does for the failure.
 */

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const PAGE = resolve(dirname(fileURLToPath(import.meta.url)), '../SearchPage.tsx')
const page = readFileSync(PAGE, 'utf-8')

describe('the search page runs the search its button shows', () => {
  it('asks the hook to widen a query its own sources cannot answer', () => {
    expect(page).toContain('widenToAllSources: true')
  })

  it('lights the chip for the automatic widening, not only for the visitor\'s own choice', () => {
    expect(page).toContain("className={`news-page-chip${allSourcesActive ? ' active' : ''}`}")
    expect(page).toContain('const allSourcesActive = search.allSourcesActive')
  })

  it('turns both off with one click on the chip', () => {
    expect(page).toContain('onClick={toggleAllSources}')
    expect(page).toMatch(/const toggleAllSources = useCallback\(\(\) => \{[\s\S]*setSearchAllSources\(next\)[\s\S]*if \(!next\) search\.dismissAutoAllSources\(\)/)
  })

  it('says in the result row that the whole database was searched', () => {
    expect(page).toContain('{search.autoAllSources && <span className="search-auto-note">')
  })

  it('hints at "All sources" only where it is not already searched', () => {
    // Otherwise the empty state tells a visitor to switch on what the hook
    // already searched for them
    expect(page).toContain('{!allSourcesActive && \' — try enabling "All sources"\'}')
  })
})
