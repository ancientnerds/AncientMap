/**
 * NERV palette of the renderer: a mirror of the site's design tokens
 * (ancient-nerds-map/src/styles/tokens.css, `--_palette-*`) and of the brand red
 * (UI_COLORS.primary, ancient-nerds-map/src/constants/colors.ts), so video frames
 * and the site read as one product. Change a colour on the site first, then here:
 * test/colors.test.ts reads both site files and fails on any drift (MIRROR).
 */
export const colors = {
  bg: '#0a0e14', // --_palette-dark-900 (--surface-page)
  bgPanel: 'rgba(10, 18, 16, 0.88)', // --_palette-dark-850 at panel opacity
  green: '#00cc66', // --_palette-green-bright (--accent-primary)
  greenDim: '#2a5a2a', // --_palette-green-700 (--crt-700)
  crt300: '#b0d0b0', // --_palette-green-300 (--text-secondary)
  crt400: '#6ab06a', // --_palette-green-400 (--text-muted)
  cyan: '#00c8c8', // --_palette-cyan-500 (--accent-secondary)
  amber: '#fbbf24', // --_palette-amber-400 (--accent-amber)
  orange: '#f59e0b', // --_palette-orange-500 (--status-warning)
  red: '#ef4444', // --_palette-red-error (--status-error)
  okGreen: '#22c55e', // --_palette-status-green (--status-ok)
  brandRed: '#c02023', // UI_COLORS.primary (src/constants/colors.ts)
  white: '#ffffff',
  text: '#e0e0e0', // --_palette-neutral-50 (--text-body)
  muted: '#787878', // --_palette-neutral-300
} as const

type ColorKey = keyof typeof colors

/** Where each mirrored hex colour lives on the site: a tokens.css variable or a UI_COLORS key. */
export const MIRROR: readonly ({ key: ColorKey; token: string } | { key: ColorKey; constant: string })[] = [
  { key: 'bg', token: '--_palette-dark-900' },
  { key: 'green', token: '--_palette-green-bright' },
  { key: 'greenDim', token: '--_palette-green-700' },
  { key: 'crt300', token: '--_palette-green-300' },
  { key: 'crt400', token: '--_palette-green-400' },
  { key: 'cyan', token: '--_palette-cyan-500' },
  { key: 'amber', token: '--_palette-amber-400' },
  { key: 'orange', token: '--_palette-orange-500' },
  { key: 'red', token: '--_palette-red-error' },
  { key: 'okGreen', token: '--_palette-status-green' },
  { key: 'text', token: '--_palette-neutral-50' },
  { key: 'muted', token: '--_palette-neutral-300' },
  { key: 'brandRed', constant: 'primary' },
]

export type Tone = 'accent' | 'info' | 'warn' | 'alert' | 'muted'

export const TONES: readonly Tone[] = ['accent', 'info', 'warn', 'alert', 'muted']

export const toneColor: Record<Tone, string> = {
  accent: colors.green,
  info: colors.cyan,
  warn: colors.amber,
  alert: colors.red,
  muted: colors.muted,
}

/** Claim statuses of the case file (pipeline/studio/casefile.py CLAIM_STATUSES). */
export type ClaimStatus = 'pending' | 'supported' | 'weakened' | 'refuted' | 'open'

export const CLAIM_STATUSES: readonly ClaimStatus[] = ['pending', 'supported', 'weakened', 'refuted', 'open']

export const statusColor: Record<ClaimStatus, string> = {
  pending: colors.muted,
  supported: colors.okGreen,
  weakened: colors.orange,
  refuted: colors.red,
  open: colors.cyan,
}
