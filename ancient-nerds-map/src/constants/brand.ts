/**
 * Brand identity constants — single source of truth.
 *
 * Every logo, header, footer, and SVG that renders "ANCIENT NERDS",
 * "RESEARCH PLATFORM", or sub-brands like "Forgotten Worlds" must
 * pull values from here. Never hardcode brand strings or colors elsewhere.
 */

// ---------------------------------------------------------------------------
// Text
// ---------------------------------------------------------------------------

export const BRAND_NAME = 'ANCIENT NERDS'
export const BRAND_SUBTITLE = 'RESEARCH PLATFORM'
export const BRAND_TAGLINE = 'Modern Tech for Ancient Mysteries'

/** Sub-brands / product names */
export const SUB_BRANDS = {
  forgottenWorlds: 'FORGOTTEN WORLDS',
  cardGame: 'Card Game',
} as const

// ---------------------------------------------------------------------------
// Colors
// ---------------------------------------------------------------------------

export const BRAND_COLORS = {
  /** Primary red — used for ANCIENT NERDS text, AN logo, accents */
  red: '#c02023',
  redHover: '#d42426',

  /** Red glow rgba values for text-shadow / drop-shadow */
  redGlow50: 'rgba(192, 32, 35, 0.5)',
  redGlow30: 'rgba(192, 32, 35, 0.3)',
  redGlow15: 'rgba(192, 32, 35, 0.15)',

  /** Subtitle text color */
  subtitle: '#bbb',
  subtitleMuted: '#888',

  /** Gold gradient stops for Forgotten Worlds */
  gold: {
    light: '#ffe082',
    mid: '#ffd54f',
    base: '#ffb300',
    dark: '#e65100',
    darkest: '#8d3200',
  },
} as const

// ---------------------------------------------------------------------------
// Fonts
// ---------------------------------------------------------------------------

export const BRAND_FONTS = {
  /** Primary brand font — ANCIENT NERDS, subtitles, headings */
  primary: "'Orbitron', sans-serif",
  /** Secondary brand font — Forgotten Worlds, decorative serif */
  serif: "'Cinzel', 'Trajan Pro', 'Palatino Linotype', serif",
  /** Body font */
  body: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
  /** Decorative / tagline */
  decorative: "'Cormorant Garamond', serif",
} as const

// ---------------------------------------------------------------------------
// Typography presets (for inline styles or SVG generation)
// ---------------------------------------------------------------------------

export const BRAND_TYPOGRAPHY = {
  /** "ANCIENT NERDS" in page headers (15px) */
  headerBrand: {
    fontFamily: BRAND_FONTS.primary,
    fontSize: '15px',
    fontWeight: 700,
    letterSpacing: '2px',
    color: BRAND_COLORS.red,
  },
  /** "ANCIENT NERDS" in filter panel logo (22px) */
  logoMain: {
    fontFamily: BRAND_FONTS.primary,
    fontSize: '22px',
    fontWeight: 700,
    letterSpacing: '3.4px',
    color: BRAND_COLORS.red,
  },
  /** "RESEARCH PLATFORM" subtitle (13px) */
  logoSub: {
    fontFamily: BRAND_FONTS.primary,
    fontSize: '13px',
    fontWeight: 500,
    letterSpacing: '4.6px',
  },
  /** "ANCIENT NERDS" on landing hero (large) */
  heroTitle: {
    fontFamily: BRAND_FONTS.primary,
    fontWeight: 700,
    letterSpacing: '0.15em',
    color: BRAND_COLORS.red,
  },
  /** "RESEARCH PLATFORM" on landing hero */
  heroSubtitle: {
    fontFamily: BRAND_FONTS.primary,
    fontWeight: 400,
    letterSpacing: '0.3em',
    color: BRAND_COLORS.subtitle,
  },
} as const

// ---------------------------------------------------------------------------
// Assets
// ---------------------------------------------------------------------------

export const BRAND_ASSETS = {
  /** AN triangle logo */
  logo: '/an-logo.svg',
  /** Forgotten Worlds card game logo */
  forgottenWorldsLogo: '/forgotten-worlds-logo.svg',
  /** Favicon */
  favicon: '/favicon.svg',
} as const

// ---------------------------------------------------------------------------
// Text shadows (CSS values)
// ---------------------------------------------------------------------------

export const BRAND_SHADOWS = {
  /** Full red glow for logo text on dark backgrounds */
  redGlow: [
    `0 0 10px ${BRAND_COLORS.redGlow50}`,
    `0 0 20px ${BRAND_COLORS.redGlow30}`,
    `0 0 40px ${BRAND_COLORS.redGlow15}`,
    '0 0 3px rgba(0, 0, 0, 0.8)',
    '0 0 6px rgba(0, 0, 0, 0.5)',
  ].join(', '),
  /** Lighter red glow (mobile, smaller text) */
  redGlowLight: [
    `0 0 10px ${BRAND_COLORS.redGlow50}`,
    `0 0 20px ${BRAND_COLORS.redGlow30}`,
  ].join(', '),
  /** Dark text shadow for readability over images */
  darkBackdrop: '0 0 4px rgba(0,0,0,1), 0 0 10px rgba(0,0,0,1)',
} as const

// ---------------------------------------------------------------------------
// AN logo SVG polygon paths (for inline SVG / canvas rendering)
// ---------------------------------------------------------------------------

export const AN_LOGO_PATHS = [
  '582.15 491.4 543.24 558.73 545.35 425.3 517.27 376.76 369.3 632.98 428.77 632.98 489.36 528.05 489.36 632.98 559.85 632.98 611.89 542.91 582.15 491.4',
  '516.34 218.3 276.93 632.98 336.4 632.98 516.34 321.32 666.54 581.47 622.34 581.47 592.6 632.98 755.76 632.98 516.34 218.3',
] as const

/** Original viewBox of an-logo.svg */
export const AN_LOGO_VIEWBOX = '200 200 620 500'
