/**
 * Shared search utilities used by both the globe (App.tsx) and standalone search page.
 */

/** Normalize string for search: lowercase + remove diacritics */
export const normalizeForSearch = (str: string): string =>
  str.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')

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
