// =============================================================================
// GLOBE CONSTANTS - Central configuration for all magic numbers
// =============================================================================

// -----------------------------------------------------------------------------
// Camera Settings
// -----------------------------------------------------------------------------
export const CAMERA = {
  FOV: 60,
  NEAR: 0.01,
  FAR: 1500,  // Must be > star distance (800-1200)
  MIN_DISTANCE: 1.02,       // Minimum zoom - slightly above globe surface (radius=1.0)
  MAX_DISTANCE: 2.44,       // Maximum zoom (farthest from globe)
  INITIAL_DISTANCE: 2.2,    // Default starting distance
  AUTO_ROTATE_SPEED: 0.15,  // Speed of auto-rotation
  DAMPING_FACTOR: 0.08,     // Controls inertia smoothness
  PAN_SPEED: 0.5,
  ROTATE_SPEED: 0.5,
  ZOOM_SPEED: 1.0,
} as const

// -----------------------------------------------------------------------------
// Extended Camera Settings for Mapbox Satellite Mode
// -----------------------------------------------------------------------------
export const CAMERA_EXTENDED = {
  MIN_DISTANCE: 0.20,             // Extended minimum for Mapbox (230% zoom)
  MAPBOX_ENABLE_DISTANCE: 1.12,   // Start showing Mapbox tiles (100% zoom)
  MAPBOX_FULL_DISTANCE: 0.80,     // Mapbox fully replaces basemap (~140% zoom)
} as const

// -----------------------------------------------------------------------------
// Animation Timing (milliseconds)
// -----------------------------------------------------------------------------
export const ANIMATION = {
  FADE_DURATION: 300,           // Default fade duration for layers
  LABEL_FADE_DURATION: 200,     // Label fade in/out
  FLY_TO_DURATION: 600,         // Camera fly-to animation
  CLICK_TIMEOUT: 250,           // Distinguish click from drag
  HOVER_THROTTLE: 100,          // Throttle hover callbacks
  DEBOUNCE_DELAY: 150,          // Default debounce delay
  TOOLTIP_FREEZE_DELAY: 1000,   // Time before tooltip freezes
  SCALE_UPDATE_INTERVAL: 200,   // Scale bar update throttle
  COORDS_UPDATE_INTERVAL: 50,   // Coordinate display update throttle
  HOVER_CHECK_INTERVAL: 16,     // Hover detection throttle (~60fps)
} as const

// -----------------------------------------------------------------------------
// Globe Geometry
// -----------------------------------------------------------------------------
export const GLOBE = {
  RADIUS: 1,                    // Base globe radius
  SEGMENTS_THETA: 48,           // Horizontal segments
  SEGMENTS_PHI: 48,             // Vertical segments
  LAYER_RADIUS: 1.002,          // Vector layer radius (slightly above globe)
  DOT_RADIUS: 1.008,            // Site dots radius
  STAR_SPHERE_RADIUS: 50,       // Starfield sphere radius
  STAR_COUNT: 2000,             // Number of stars
} as const

// -----------------------------------------------------------------------------
// LOD (Level of Detail) Settings
// -----------------------------------------------------------------------------
export const LOD = {
  ULTRA_LOW_THRESHOLD: 25,      // Zoom < 25% = ultra-low detail
  LOW_THRESHOLD: 50,            // Zoom < 50% = low detail
  MEDIUM_THRESHOLD: 75,         // Zoom < 75% = medium detail
  // Above 75% = high detail
} as const

export const DETAIL_SCALE = {
  'ultra-low': '110m',
  'low': '50m',
  'medium': '10m',
  'high': 'hires',
} as const

export type DetailLevel = keyof typeof DETAIL_SCALE

// -----------------------------------------------------------------------------
// Visual Effects
// -----------------------------------------------------------------------------
export const EFFECTS = {
  BACKSIDE_OPACITY: 0.25,       // Backside line/dot opacity
  DOT_CORE_RADIUS: 0.85,        // LED dot core size
  GLOW_INTENSITY_SCALE: 0.6,    // Reduced glow by 40%
  PULSE_SPEED: 3.14159,         // PI for 2-second pulse cycle
  HORIZON_FADE_START: -0.1,     // Label fade start (relative to horizon)
  HORIZON_FADE_END: 0.4,        // Label fade end
  BRIGHTNESS_BOOST: 1.3,        // Basemap brightness multiplier
  BRIGHTNESS_GAMMA: 0.8,        // Basemap gamma correction
} as const

// -----------------------------------------------------------------------------
// UI Defaults
// -----------------------------------------------------------------------------
export const UI = {
  DEFAULT_DOT_SIZE: 6,          // Site dot size (1-15)
  MIN_DOT_SIZE: 1,
  MAX_DOT_SIZE: 15,
  DEFAULT_HUD_SCALE: 0.9,       // HUD scale factor
  MIN_HUD_SCALE: 0.5,
  MAX_HUD_SCALE: 1.3,
  DEFAULT_SEA_LEVEL: -120,      // Last Glacial Maximum
} as const

// -----------------------------------------------------------------------------
// Label Configuration
// -----------------------------------------------------------------------------
export interface LabelStyle {
  fontSize: number
  color: string
  italic: boolean
  bold: boolean
  uppercase: boolean
}

export const LABEL_STYLES: Record<string, LabelStyle> = {
  // Major features - bold and distinct (font sizes reduced 10%)
  continent:  { fontSize: 58, color: '#F5E6C8', italic: false, bold: true,  uppercase: true },
  ocean:      { fontSize: 58, color: '#5DADE2', italic: true,  bold: false, uppercase: true },

  // Political - warm earth tones
  country:    { fontSize: 44, color: '#E8D4B0', italic: false, bold: true,  uppercase: true },
  capitalNat: { fontSize: 28, color: '#F0E68C', italic: false, bold: true,  uppercase: false },
  capital:    { fontSize: 31, color: '#DEB887', italic: true,  bold: false, uppercase: false },
  city:       { fontSize: 23, color: '#D2B48C', italic: false, bold: false, uppercase: false },

  // Terrain - distinct earth colors
  mountain:   { fontSize: 35, color: '#CD853F', italic: true,  bold: false, uppercase: false },
  desert:     { fontSize: 25, color: '#C2B280', italic: true,  bold: false, uppercase: true },

  // Water features - bright blues
  sea:        { fontSize: 29, color: '#7EC8F0', italic: true,  bold: false, uppercase: true },
  lake:       { fontSize: 31, color: '#6BB3D9', italic: true,  bold: false, uppercase: false },
  river:      { fontSize: 31, color: '#7EC8E3', italic: true,  bold: false, uppercase: false },

  // Geological features - coral red to match tectonic plate boundaries
  plate:      { fontSize: 32, color: '#FF6B6B', italic: false, bold: true,  uppercase: true },

  // Natural features - matching layer colors
  glacier:    { fontSize: 38, color: '#88ddff', italic: true,  bold: false, uppercase: false },
  coralReef:  { fontSize: 38, color: '#ff6b9d', italic: true,  bold: false, uppercase: false },
}

// Base scale values per label type (for visual size AND collision detection)
export const LABEL_BASE_SCALE: Record<string, number> = {
  empire: 0.06,
  continent: 0.10,
  ocean: 0.08,
  country: 0.06,
  capital: 0.037,
  capitalNat: 0.045,
  sea: 0.035,
  mountain: 0.042,
  desert: 0.04,
  city: 0.032,
  lake: 0.042,
  river: 0.042,
  plate: 0.045,    // Tectonic plate labels
  glacier: 0.032,  // Glacier labels
  coralReef: 0.028, // Coral reef labels
}

// Typography
export const ATLAS_FONT_FAMILY = "'Orbitron', 'Inter', system-ui, sans-serif"

// -----------------------------------------------------------------------------
// Layer Colors
// -----------------------------------------------------------------------------
export const LAYER_COLORS = {
  COASTLINES: 0x00e0d0,         // Teal
  COUNTRY_BORDERS: 0x00e0d0,    // Teal (same as coastlines)
  RIVERS: 0x2196f3,             // Blue
  LAKES: 0x1976d2,              // Darker blue
  CORAL_REEFS: 0xff6b9d,        // Coral pink
  GLACIERS: 0x88ddff,           // Ice blue
} as const

// -----------------------------------------------------------------------------
// Render Order
// -----------------------------------------------------------------------------
export const RENDER_ORDER = {
  BASEMAP: -20,
  LAND_MASK_STENCIL: -16,
  MAPBOX_TILES: -14,        // Mapbox satellite tiles (between basemap and vector layers)
  STARS: -10,
  BACK_LINES: 0,
  FRONT_LINES: 1,
  EMPIRE_FILL: 5,
  EMPIRE_BORDERS: 6,
  BACK_DOTS: 10,
  FRONT_DOTS: 11,
  LABELS: 1000,
  TOOLTIP: 2000,
} as const

// -----------------------------------------------------------------------------
// Geographic Constants
// -----------------------------------------------------------------------------
export const GEO = {
  EARTH_RADIUS_KM: 6371,
  DEG_TO_RAD: Math.PI / 180,
  RAD_TO_DEG: 180 / Math.PI,
} as const

// -----------------------------------------------------------------------------
// Easing Functions
// -----------------------------------------------------------------------------
export const EASING = {
  // Ease-out cubic: smooth deceleration
  easeOutCubic: (t: number) => 1 - Math.pow(1 - t, 3),
  // Ease-in-out cubic: smooth acceleration and deceleration
  easeInOutCubic: (t: number) => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
  // Linear
  linear: (t: number) => t,
} as const

// -----------------------------------------------------------------------------
// Cuddle System - Country/Capital label overlap animation
// -----------------------------------------------------------------------------
export const CUDDLE = {
  DURATION: 250,           // Animation duration (ms)
  MAX_OFFSET_FACTOR: 0.3,  // Max displacement as factor of capital label height
} as const
