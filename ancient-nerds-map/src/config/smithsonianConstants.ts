// =============================================================================
// SMITHSONIAN CONSTANTS - Configuration for Open Access API
// =============================================================================

/**
 * Smithsonian Open Access API key from environment variable
 * Get your free key at: https://api.si.edu/
 */
const SMITHSONIAN_API_KEY = import.meta.env.VITE_SMITHSONIAN_API_KEY || ''

if (!SMITHSONIAN_API_KEY) {
  console.warn('[Smithsonian] No API key configured. Set VITE_SMITHSONIAN_API_KEY in .env file.')
}

/**
 * Get the Smithsonian API key
 */
export function getSmithsonianApiKey(): string {
  return SMITHSONIAN_API_KEY
}

/**
 * Smithsonian API configuration
 */
export const SMITHSONIAN = {
  get API_KEY() { return getSmithsonianApiKey() },
  BASE_URL: 'https://api.si.edu/openaccess/api/v1.0',
  DEFAULT_ROWS: 20,
  CACHE_TTL_MS: 15 * 60 * 1000, // 15 minutes
} as const
