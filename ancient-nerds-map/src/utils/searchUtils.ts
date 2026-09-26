/**
 * Shared search utilities used by both the globe (App.tsx) and standalone search page.
 */

/** Normalize string for search: lowercase + remove diacritics */
export const normalizeForSearch = (str: string): string =>
  str.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')

/** Words a visitor adds that no site name needs to contain: "the valley of
 *  kings" is the Valley of the Kings. The API's search drops the same ones
 *  (api/routes/sites.py SEARCH_STOPWORDS). */
const SEARCH_STOPWORDS = new Set(['the', 'of', 'and', 'an', 'in', 'at', 'on', 'to', 'near'])

/** The words of a normalized query that the word match requires: three
 *  characters or more, no filler, each once. Umami, 2026-09-17..25: "the
 *  valley of kings, egypt" and "giza, egypt" found nothing while the query was
 *  only ever matched as one string. */
export function searchWords(queryNorm: string): string[] {
  const words = queryNorm.split(/[^\p{L}\p{N}]+/u).filter(w => w.length >= 3 && !SEARCH_STOPWORDS.has(w))
  return [...new Set(words)]
}

const WORD_CHAR = /[\p{L}\p{N}]/u

/** True when `word` starts a word of `textNorm` ("kings" in "valley of the
 *  kings", not in "workings"). Both sides normalized. */
export function startsAWord(textNorm: string, word: string): boolean {
  for (let i = textNorm.indexOf(word); i !== -1; i = textNorm.indexOf(word, i + 1)) {
    if (i === 0 || !WORD_CHAR.test(textNorm[i - 1])) return true
  }
  return false
}

/** A word's trigrams the way pg_trgm builds them: two blanks before the word,
 *  one after. */
export function trigrams(word: string): Set<string> {
  const padded = `  ${word} `
  const out = new Set<string>()
  for (let i = 0; i + 3 <= padded.length; i++) out.add(padded.slice(i, i + 3))
  return out
}

/** pg_trgm's similarity(): the trigrams two words share, over all of theirs. */
export function trigramSimilarity(a: Set<string>, b: Set<string>): number {
  let shared = 0
  for (const t of a) if (b.has(t)) shared++
  return shared / (a.size + b.size - shared)
}

/** How close a mistyped word has to be to a word of a site's name. Measured
 *  on the searches that found nothing, 2026-09-17..26: "baalk" (Baalbek 0.40)
 *  and "gize" (Giza 0.43) pass; "crerre" (Crete 0.30) and "notswa" (Botswana
 *  0.23) do not, and a lower bar lets unrelated names in. */
export const TYPO_SIMILARITY = 0.4

/** A shorter word has too few trigrams to tell a typo from another word. */
export const TYPO_MIN_LENGTH = 4

/** Get approximate year from period string for filtering */
export function periodToYear(period: string): number {
  switch (period) {
    case '< 4500 BC': return -5000
    case '4500 - 3000 BC': return -3750
    case '3000 - 1500 BC': return -2250
    case '1500 - 500 BC': return -1000
    case '500 BC - 1 AD': return -250
    case '1 - 500 AD': return 250
    case '500 - 1000 AD': return 750
    case '1000 - 1500 AD': return 1250
    case '1500+ AD': return 1750
    default: return 0
  }
}

/** Extract country from location string (last part after comma, or whole string) */
export function extractCountry(location: string | undefined): string {
  if (!location) return 'Unknown'
  const parts = location.split(',')
  const country = parts[parts.length - 1].trim()
  return country || 'Unknown'
}
