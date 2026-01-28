/**
 * Theme constants for Video Factory
 *
 * Standalone theme extracted from Ancient Nerds design.
 * No imports from main codebase - completely independent.
 */

// =============================================================================
// Brand Colors
// =============================================================================

export const BRAND = {
  primary: '#c02023',      // Ancient Nerds Red
  gold: '#FFD700',         // Gold accent
  teal: '#00b4b4',         // Teal accent (coastlines)
  white: '#ffffff',
  black: '#000000',
};

// =============================================================================
// Background Colors
// =============================================================================

export const BACKGROUNDS = {
  dark: '#000000',
  darkBlue: '#0a1628',
  card: 'rgba(0, 20, 25, 0.85)',
  cardGlass: 'rgba(0, 20, 25, 0.55)',
  overlay: 'rgba(0, 0, 0, 0.7)',
  gradientTop: 'linear-gradient(to bottom, rgba(0,0,0,0.8) 0%, rgba(0,0,0,0) 100%)',
  gradientBottom: 'linear-gradient(to top, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0) 100%)',
};

// =============================================================================
// Text Colors
// =============================================================================

export const TEXT = {
  primary: '#ffffff',
  secondary: '#888888',
  muted: '#666666',
  accent: '#00b4b4',
  gold: '#FFD700',
};

// =============================================================================
// Border Colors
// =============================================================================

export const BORDERS = {
  teal: 'rgba(0, 180, 180, 0.2)',
  tealSolid: '#00b4b4',
  gold: '#FFD700',
  white: 'rgba(255, 255, 255, 0.2)',
};

// =============================================================================
// Category Colors (for badges)
// =============================================================================

export const CATEGORY_COLORS: Record<string, string> = {
  'Pyramid complex': '#ff6b35',
  'Temple complex': '#fbbf24',
  'City/town/settlement': '#f59e0b',
  'Fortress/citadel': '#ef4444',
  'Necropolis/tombs complex': '#e879f9',
  'Megalithic stones': '#fb923c',
  'Cave Structures': '#f97316',
  'Castle/palace': '#ec4899',
  'Megalithic structures': '#f472b6',
  'Stone circle': '#fb7185',
  'Monument': '#f9a8d4',
  'Unknown': '#fbbf24',
  default: '#ff00ff',
};

// =============================================================================
// Period Colors
// =============================================================================

export const PERIOD_COLORS: Record<string, string> = {
  '< 4500 BC': '#ff0000',
  '4500 - 3000 BC': '#ff2200',
  '3000 - 1500 BC': '#ff4400',
  '1500 - 500 BC': '#ff6600',
  '500 BC - 1 AD': '#ff8800',
  '1 - 500 AD': '#ffaa00',
  '500 - 1000 AD': '#ffcc00',
  '1000 - 1500 AD': '#ffdd00',
  '1500+ AD': '#ffff00',
  'Unknown': '#9ca3af',
};

// =============================================================================
// Typography
// =============================================================================

export const FONTS = {
  heading: "'Inter', 'Helvetica Neue', Arial, sans-serif",
  body: "'Inter', 'Helvetica Neue', Arial, sans-serif",
  mono: "'JetBrains Mono', 'Fira Code', monospace",
};

export const FONT_SIZES = {
  xs: '12px',
  sm: '14px',
  base: '16px',
  lg: '18px',
  xl: '20px',
  '2xl': '24px',
  '3xl': '30px',
  '4xl': '36px',
  '5xl': '48px',
  '6xl': '60px',
  '7xl': '72px',
};

export const FONT_WEIGHTS = {
  light: 300,
  normal: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
  black: 900,
};

// =============================================================================
// Spacing
// =============================================================================

export const SPACING = {
  xs: '4px',
  sm: '8px',
  md: '16px',
  lg: '24px',
  xl: '32px',
  '2xl': '48px',
  '3xl': '64px',
  '4xl': '96px',
};

// =============================================================================
// Border Radius
// =============================================================================

export const RADIUS = {
  sm: '4px',
  md: '8px',
  lg: '12px',
  xl: '16px',
  '2xl': '24px',
  full: '9999px',
};

// =============================================================================
// Shadows
// =============================================================================

export const SHADOWS = {
  sm: '0 1px 2px rgba(0, 0, 0, 0.5)',
  md: '0 4px 6px rgba(0, 0, 0, 0.5)',
  lg: '0 10px 15px rgba(0, 0, 0, 0.5)',
  xl: '0 20px 25px rgba(0, 0, 0, 0.5)',
  glow: '0 0 20px rgba(0, 180, 180, 0.3)',
  glowGold: '0 0 20px rgba(255, 215, 0, 0.3)',
};

// =============================================================================
// Animation Durations
// =============================================================================

export const DURATIONS = {
  fast: '150ms',
  normal: '300ms',
  slow: '500ms',
  slower: '1000ms',
};

// =============================================================================
// Z-Index Scale
// =============================================================================

export const Z_INDEX = {
  base: 0,
  content: 10,
  overlay: 20,
  modal: 30,
  popover: 40,
  tooltip: 50,
};

// =============================================================================
// Video-specific constants
// =============================================================================

export const VIDEO = {
  // Teaser (16:9)
  teaser: {
    width: 1920,
    height: 1080,
    fps: 30,
  },
  // Short (9:16)
  short: {
    width: 1080,
    height: 1920,
    fps: 30,
  },
};

// =============================================================================
// Helper Functions
// =============================================================================

export function getCategoryColor(category: string): string {
  return CATEGORY_COLORS[category] || CATEGORY_COLORS.default;
}

export function getPeriodColor(period: string): string {
  return PERIOD_COLORS[period] || PERIOD_COLORS['Unknown'];
}

/**
 * Create glass-morphism background style
 */
export function glassBackground(opacity = 0.55): React.CSSProperties {
  return {
    background: `rgba(0, 20, 25, ${opacity})`,
    backdropFilter: 'blur(12px)',
    border: `1px solid ${BORDERS.teal}`,
  };
}

/**
 * Create gradient overlay style
 */
export function gradientOverlay(direction: 'top' | 'bottom' = 'bottom'): React.CSSProperties {
  return {
    background: direction === 'top' ? BACKGROUNDS.gradientTop : BACKGROUNDS.gradientBottom,
  };
}
