/**
 * The search page is one input and a result list: a visitor who opens
 * /search.html to look for a site should be able to type at once, without
 * hunting for the field first.
 *
 * The field does not get the caret on mount, and the reason is the data load:
 * the input carries disabled={isLoading} while fetchSites() runs, and a disabled
 * element cannot take focus - so autoFocus fires during the load and lands
 * nowhere. Nothing focused the field afterwards, which is how the page opened
 * with the caret nowhere. The focus therefore has to wait for the load, and
 * autoFocus is not the way to ask for it.
 *
 * The page renders no smaller than its whole data load, so this pins the wiring
 * in the source, as searchAllSourcesWiring.test.ts does for the chip.
 */

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const PAGE = resolve(dirname(fileURLToPath(import.meta.url)), '../SearchPage.tsx')
const page = readFileSync(PAGE, 'utf-8')

describe('the search field is ready to type into when the page opens', () => {
  it('is disabled while the sites load, which is why the mount focus cannot work', () => {
    expect(page).toContain('disabled={isLoading}')
  })

  it('takes the focus once the load is over', () => {
    expect(page).toMatch(
      /useEffect\(\(\) => \{\s*if \(!isLoading\) searchInputRef\.current\?\.focus\(\)\s*\}, \[isLoading\]\)/
    )
  })

  it('focuses in exactly two places: after the load, and after clearing', () => {
    // The second one belongs to the clear button - a visitor who empties the
    // field wants to type the next query at once. A third call would steal the
    // caret from the filter panel while a result arrives.
    const focusCalls = page.match(/searchInputRef\.current\?\.focus\(\)/g) || []
    expect(focusCalls).toHaveLength(2)
    expect(page).toMatch(/onClick=\{\(\) => \{[\s\S]{0,400}searchInputRef\.current\?\.focus\(\)/)
  })

  it('does not keep autoFocus on the input, which cannot fire on a disabled field', () => {
    // The attribute, not the word: the effect above names it in its comment, and
    // it is the right name for the failure
    expect(page).not.toMatch(/<input[^>]*autoFocus/)
  })

  it('points the ref at the same input the visitor types into', () => {
    expect(page).toMatch(/<input[^>]*ref=\{searchInputRef\}/)
  })
})
