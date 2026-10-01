import { slugify } from '../seo/meta'

/**
 * The journal a `#slug` fragment on /articles.html points at.
 *
 * `location.hash` is handed back percent-encoded: a slug with an accent
 * (`sacsayhuamán`) reads `sacsayhuam%C3%A1n`, so comparing it with the slug
 * itself never matched — journals 77, 72 and 52 could not be opened (found
 * 2026-10-01). The fragment is decoded first.
 *
 * The fragment is also user-editable. decodeURIComponent throws a URIError on
 * a malformed sequence (`#%`); that is a fragment which names no journal, the
 * same answer as an unknown slug. Any other error is a bug and propagates.
 */
export function articleForHash<T extends { title: string }>(hash: string, articles: T[]): T | undefined {
  const encoded = hash.replace(/^#/, '')
  if (!encoded) return undefined
  let slug: string
  try {
    slug = decodeURIComponent(encoded)
  } catch (e) {
    if (e instanceof URIError) return undefined
    throw e
  }
  return articles.find(a => slugify(a.title) === slug)
}
