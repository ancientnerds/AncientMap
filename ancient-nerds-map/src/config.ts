// Centralized configuration - reads from environment variables
// In production, set these via your hosting provider's environment settings

export const config = {
  // API endpoints
  api: {
    baseUrl: import.meta.env.VITE_API_BASE_URL || '/api',
    uploadUrl: import.meta.env.VITE_UPLOAD_URL || '/upload',
  },

  // Cloudflare Turnstile (bot protection)
  turnstile: {
    // Use test key for development (always passes)
    siteKey: import.meta.env.VITE_TURNSTILE_SITE_KEY || '1x00000000000000000000AA',
  },
} as const

// Type-safe access to config
export type Config = typeof config
