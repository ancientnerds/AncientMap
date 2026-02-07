/**
 * Centralized color definitions for the Ancient Nerds Map.
 *
 * All color constants should be defined here to avoid duplication
 * and ensure consistency across the application.
 */

// =============================================================================
// Source Colors - Colors for data sources
// =============================================================================

export const SOURCE_COLORS: Record<string, string> = {
  // Primary sources
  ancient_nerds: '#FFD700',  // Gold
  lyra: '#8b5cf6',           // Purple - Lyra auto-discoveries

  // Core ancient world databases
  pleiades: '#e74c3c',       // Red
  dare: '#3498db',           // Blue
  topostext: '#9b59b6',      // Purple
  wikidata: '#27ae60',       // Green
  unesco: '#f1c40f',         // Yellow

  // Regional databases
  osm_historic: '#e67e22',   // Orange
  historic_england: '#1abc9c', // Turquoise
  ireland_nms: '#2ecc71',    // Emerald
  arachne: '#e91e63',        // Pink

  // Specialized databases
  open_context: '#00bcd4',   // Cyan
  megalithic_portal: '#795548', // Brown
  eamena: '#ff5722',         // Deep Orange
  dinaa: '#607d8b',          // Blue Grey

  // Content sources
  inscriptions_edh: '#673ab7', // Deep Purple
  coins_nomisma: '#ffc107',  // Amber
  shipwrecks_oxrep: '#03a9f4', // Light Blue
  volcanic_holvol: '#f44336', // Red
  sacred_sites: '#4caf50',   // Green
  rock_art: '#ff9800',       // Orange
  boundaries_seshat: '#9c27b0', // Purple
  models_sketchfab: '#00bcd4', // Cyan
  europeana: '#3f51b5',      // Indigo
  david_rumsey: '#8bc34a',   // Light Green
  met_museum: '#cddc39',     // Lime
  geonames: '#009688',       // Teal

  // Default fallback
  default: '#9ca3af',        // Gray
}

// =============================================================================
// Category Colors - Colors for site categories/types
// =============================================================================

export const CATEGORY_COLORS: Record<string, string> = {
  // ==========================================================================
  // Colors organized by GROUP - each group has its own color family
  // ==========================================================================

  // -------------------------------------------------------------------------
  // SETTLEMENTS - Oranges (warm, inhabited feel)
  // -------------------------------------------------------------------------
  'city': '#ff8c00',                     // Dark Orange
  'town': '#ff7b00',                     // Orange
  'village': '#ff9933',                  // Light Orange
  'settlement': '#e67300',               // Burnt Orange
  'urban': '#ff6600',                    // Vivid Orange
  'villa': '#ffaa33',                    // Golden Orange
  'City/town/settlement': '#ff5500',     // Vivid Orange
  'Residence/villa/farmhouse': '#cc7700', // Amber
  'City/town/settlement, Pyramid complex': '#ff6622', // Red-Orange

  // -------------------------------------------------------------------------
  // FORTIFICATIONS - Reds (strength, defense)
  // -------------------------------------------------------------------------
  'castle': '#dc143c',                   // Crimson
  'citadel': '#cc0033',                  // Deep Red
  'fort': '#e60000',                     // Bright Red
  'fortress': '#b30000',                 // Dark Red
  'military': '#ff3333',                 // Light Red
  'wall': '#cc2222',                     // Medium Red
  'gate': '#e63946',                     // Rose Red
  'Fortress/citadel': '#dd1111',         // Bright Red
  'Castle/palace': '#cc0044',            // Deep Rose
  'Fortress': '#aa0000',                 // Maroon
  'Gate/archway/bridge': '#e64444',      // Coral Red
  'Wall': '#bb2233',                     // Dark Rose
  'Fortification': '#cc0000',            // Deep Red

  // -------------------------------------------------------------------------
  // RELIGIOUS - Yellows & Golds (spiritual, sacred)
  // -------------------------------------------------------------------------
  'church': '#ffd700',                   // Gold
  'mosque': '#ffcc00',                   // Bright Gold
  'temple': '#e6b800',                   // Dark Gold
  'monastery': '#ffdb4d',                // Light Gold
  'sacred_site': '#ccaa00',              // Antique Gold
  'sanctuary': '#e6c200',                // Medium Gold
  'religious': '#d4aa00',                // Old Gold
  'Temple complex': '#ffc300',           // Vivid Yellow
  'Church/cathedral': '#ffaa00',         // Amber Gold
  'Minaret/tower': '#cc9900',            // Dark Amber
  'Stone cross': '#e6b300',              // Warm Gold

  // -------------------------------------------------------------------------
  // BURIAL & DEATH - Purples (mystery, death)
  // -------------------------------------------------------------------------
  'cemetery': '#9933ff',                 // Bright Purple
  'necropolis': '#7722cc',               // Deep Purple
  'tomb': '#8844dd',                     // Medium Purple
  'burial': '#aa55ee',                   // Light Purple
  'funerary': '#6633bb',                 // Dark Purple
  'Necropolis/tombs complex': '#8833dd', // Vivid Purple
  'Cemetery': '#7700b3',                 // Deep Violet
  'Barrow': '#bb77ff',                   // Lavender Purple
  'Mound/tumulus': '#6622aa',            // Royal Purple
  'Cairn': '#9944cc',                    // Orchid Purple
  'Elongated skulls': '#aa33ff',         // Electric Purple

  // -------------------------------------------------------------------------
  // MEGALITHIC - Blues & Cyans (ancient, mysterious)
  // -------------------------------------------------------------------------
  'megalithic': '#0099ff',               // Azure Blue
  'standing_stone': '#0077cc',           // Ocean Blue
  'Megalithic stones': '#0088ee',        // Bright Blue
  'Megalithic structures': '#0066bb',    // Strong Blue
  'Megalithic statues': '#3399ff',       // Sky Blue
  'Megalithic walls': '#0055aa',         // Steel Blue
  'Stone circle': '#00aaff',             // Cyan Blue
  'Dolmen': '#0077dd',                   // Deep Sky Blue
  'Standing stone': '#0088cc',           // Teal Blue
  'Henge': '#00bbff',                    // Light Cyan
  'Timber circle': '#3388dd',            // Soft Blue
  'Polygonal masonry': '#4499cc',        // Slate Blue
  'Megalithic': '#0066cc',               // Navy Blue

  // -------------------------------------------------------------------------
  // ROCK & CAVE - Greens (nature, earth)
  // -------------------------------------------------------------------------
  'cave': '#22bb55',                     // Emerald Green
  'rock_art': '#44aa44',                 // Forest Green
  'Cave Structures': '#33cc66',          // Spring Green
  'Rock relief/carving': '#55aa33',      // Lime Green
  'Rock art': '#66bb44',                 // Grass Green
  'Petroglyphs': '#449933',              // Dark Green
  'Sculptured stone': '#55bb55',         // Medium Green
  'Cave Structures, Rock art': '#44cc55', // Sea Green
  'Geoglyphs': '#77cc44',                // Yellow Green

  // -------------------------------------------------------------------------
  // INFRASTRUCTURE - Browns & Ambers (earth, construction)
  // -------------------------------------------------------------------------
  'road': '#996633',                     // Saddle Brown
  'bridge': '#aa7744',                   // Peru
  'mine': '#885522',                     // Dark Brown
  'quarry': '#775533',                   // Umber
  'infrastructure': '#997755',           // Tan
  'Road/avenue/trackway': '#aa6633',     // Sienna
  'Reservoir/aqueduct/canal': '#bb8844', // Light Brown
  'Mine/quarry': '#886644',              // Medium Brown
  'Earthwork': '#996644',                // Clay Brown
  'Well': '#aa8855',                     // Khaki Brown

  // -------------------------------------------------------------------------
  // WATER & PORTS - Teals & Aquas (water, maritime)
  // -------------------------------------------------------------------------
  'aqueduct': '#00b3b3',                 // Teal
  'bath': '#00cccc',                     // Cyan
  'harbor': '#009999',                   // Dark Teal
  'port': '#00aaaa',                     // Medium Teal
  'Underwater structures': '#00dddd',    // Light Cyan
  'Bath': '#33cccc',                     // Turquoise
  'Shipwreck': '#03a9f4',               // Light Blue

  // -------------------------------------------------------------------------
  // MONUMENTS - Magentas & Pinks (grandeur, significance)
  // -------------------------------------------------------------------------
  'monument': '#dd44aa',                 // Rose Pink
  'memorial': '#cc3399',                 // Deep Pink
  'stadium': '#ee55bb',                  // Light Pink
  'theater': '#dd3388',                  // Hot Pink
  'theatre': '#cc4499',                  // Medium Pink
  'Theatre': '#dd55aa',                  // Orchid Pink
  'forum': '#ee66aa',                    // Soft Pink
  'palace': '#cc2288',                   // Magenta
  'Pyramid complex': '#dd2277',          // Vivid Pink
  'Museum': '#ee4499',                   // Bright Pink
  'Amphitheatre': '#ee55bb',             // Light Pink
  'scheduled_monument': '#cc55aa',       // Plum
  'heritage_site': '#dd3399',            // Deep Rose
  'archaeological_site': '#ee44aa',      // Rose Magenta
  'Monument': '#dd66bb',                 // Pink Lavender

  // -------------------------------------------------------------------------
  // OTHER - Grays (neutral, miscellaneous)
  // -------------------------------------------------------------------------
  'site': '#888899',                     // Blue Gray
  'ruin': '#7799aa',                     // Steel Gray
  'inscription': '#99aabb',              // Light Steel
  'natural_feature': '#88aa99',          // Sage Gray
  'impact_crater': '#778899',            // Slate Gray
  'Geological interest': '#669988',      // Teal Gray
  'Magnetic anomaly': '#9988aa',         // Purple Gray
  'unknown': '#999999',                  // Medium Gray
  'Unknown': '#888888',                  // Dark Gray
  'default': '#777777',                  // Charcoal Gray
}

// =============================================================================
// Category Groups - For organizing categories in the UI
// =============================================================================

export type CategoryGroup =
  | 'Settlements'
  | 'Fortifications'
  | 'Religious'
  | 'Burial & Death'
  | 'Megalithic'
  | 'Rock & Cave'
  | 'Infrastructure'
  | 'Water & Ports'
  | 'Monuments'
  | 'Other'

export const CATEGORY_GROUP_ORDER: CategoryGroup[] = [
  'Settlements',
  'Fortifications',
  'Religious',
  'Burial & Death',
  'Megalithic',
  'Rock & Cave',
  'Infrastructure',
  'Water & Ports',
  'Monuments',
  'Other',
]

// Map categories to their groups (case-insensitive keys created below)
const CATEGORY_TO_GROUP: Record<string, CategoryGroup> = {
  // Settlements - Oranges & Reds
  'city': 'Settlements',
  'town': 'Settlements',
  'village': 'Settlements',
  'settlement': 'Settlements',
  'urban': 'Settlements',
  'villa': 'Settlements',
  'city/town/settlement': 'Settlements',
  'residence/villa/farmhouse': 'Settlements',
  'city/town/settlement, pyramid complex': 'Settlements',

  // Fortifications - Reds & Pinks
  'castle': 'Fortifications',
  'citadel': 'Fortifications',
  'fort': 'Fortifications',
  'fortress': 'Fortifications',
  'military': 'Fortifications',
  'wall': 'Fortifications',
  'gate': 'Fortifications',
  'fortress/citadel': 'Fortifications',
  'castle/palace': 'Fortifications',
  'gate/archway/bridge': 'Fortifications',
  'fortification': 'Fortifications',

  // Religious - Yellows & Golds
  'church': 'Religious',
  'mosque': 'Religious',
  'temple': 'Religious',
  'monastery': 'Religious',
  'sacred_site': 'Religious',
  'sanctuary': 'Religious',
  'religious': 'Religious',
  'temple complex': 'Religious',
  'church/cathedral': 'Religious',
  'minaret/tower': 'Religious',
  'stone cross': 'Religious',

  // Burial & Death - Purples
  'cemetery': 'Burial & Death',
  'necropolis': 'Burial & Death',
  'tomb': 'Burial & Death',
  'burial': 'Burial & Death',
  'funerary': 'Burial & Death',
  'barrow': 'Burial & Death',
  'mound/tumulus': 'Burial & Death',
  'necropolis/tombs complex': 'Burial & Death',
  'cairn': 'Burial & Death',
  'elongated skulls': 'Burial & Death',

  // Megalithic - Blues & Cyans
  'megalithic': 'Megalithic',
  'standing_stone': 'Megalithic',
  'megalithic stones': 'Megalithic',
  'megalithic structures': 'Megalithic',
  'megalithic statues': 'Megalithic',
  'megalithic walls': 'Megalithic',
  'stone circle': 'Megalithic',
  'dolmen': 'Megalithic',
  'standing stone': 'Megalithic',
  'henge': 'Megalithic',
  'timber circle': 'Megalithic',
  'polygonal masonry': 'Megalithic',

  // Rock & Cave - Greens
  'cave': 'Rock & Cave',
  'rock_art': 'Rock & Cave',
  'rock art': 'Rock & Cave',
  'cave structures': 'Rock & Cave',
  'rock relief/carving': 'Rock & Cave',
  'petroglyphs': 'Rock & Cave',
  'sculptured stone': 'Rock & Cave',
  'cave structures, rock art': 'Rock & Cave',
  'geoglyphs': 'Rock & Cave',

  // Infrastructure - Oranges & Browns
  'road': 'Infrastructure',
  'bridge': 'Infrastructure',
  'mine': 'Infrastructure',
  'quarry': 'Infrastructure',
  'infrastructure': 'Infrastructure',
  'road/avenue/trackway': 'Infrastructure',
  'reservoir/aqueduct/canal': 'Infrastructure',
  'mine/quarry': 'Infrastructure',
  'earthwork': 'Infrastructure',
  'well': 'Infrastructure',

  // Water & Ports - Blues
  'aqueduct': 'Water & Ports',
  'bath': 'Water & Ports',
  'harbor': 'Water & Ports',
  'port': 'Water & Ports',
  'underwater structures': 'Water & Ports',
  'shipwreck': 'Water & Ports',

  // Monuments - Mixed
  'monument': 'Monuments',
  'memorial': 'Monuments',
  'stadium': 'Monuments',
  'theater': 'Monuments',
  'theatre': 'Monuments',
  'forum': 'Monuments',
  'palace': 'Monuments',
  'pyramid complex': 'Monuments',
  'museum': 'Monuments',
  'amphitheatre': 'Monuments',
  'scheduled_monument': 'Monuments',
  'heritage_site': 'Monuments',
  'archaeological_site': 'Monuments',

  // Other - Catch-all
  'site': 'Other',
  'ruin': 'Other',
  'inscription': 'Other',
  'natural_feature': 'Other',
  'impact_crater': 'Other',
  'geological interest': 'Other',
  'magnetic anomaly': 'Other',
  'unknown': 'Other',
  'default': 'Other',
}

// Create case-insensitive lookup for category groups
const CATEGORY_TO_GROUP_NORMALIZED = new Map<string, CategoryGroup>()
for (const [key, value] of Object.entries(CATEGORY_TO_GROUP)) {
  CATEGORY_TO_GROUP_NORMALIZED.set(key.toLowerCase(), value)
}

/**
 * Get the group for a category (case-insensitive).
 */
export function getCategoryGroup(category: string): CategoryGroup {
  if (!category) return 'Other'
  const normalized = category.toLowerCase()
  return CATEGORY_TO_GROUP_NORMALIZED.get(normalized)
    || CATEGORY_TO_GROUP_NORMALIZED.get(normalized.replace(/_/g, ' '))
    || CATEGORY_TO_GROUP_NORMALIZED.get(normalized.replace(/ /g, '_'))
    || 'Other'
}

// =============================================================================
// Period Colors - Colors for time periods
// =============================================================================

export const PERIOD_COLORS: Record<string, string> = {
  '< 4500 BC': '#ff0000',          // Bright red (oldest)
  '4500 - 3000 BC': '#ff2200',     // Red-orange
  '3000 - 1500 BC': '#ff4400',     // Orange-red
  '1500 - 500 BC': '#ff6600',      // Orange
  '500 BC - 1 AD': '#ff8800',      // Orange
  '1 - 500 AD': '#ffaa00',         // Orange-yellow
  '500 - 1000 AD': '#ffcc00',      // Yellow-orange
  '1000 - 1500 AD': '#ffdd00',     // Yellow
  '1500+ AD': '#ffff00',           // Bright yellow (newest)
  'Unknown': '#9ca3af',            // Gray
}

// =============================================================================
// UI Colors - Colors for interface elements
// =============================================================================

export const UI_COLORS = {
  // Primary brand color
  primary: '#c02023',       // Red

  // Background colors
  bgDark: '#000000',
  bgCard: 'rgba(0, 20, 25, 0.55)',

  // Border colors
  border: 'rgba(0, 180, 180, 0.2)',  // Teal

  // Text colors
  textPrimary: '#ffffff',
  textSecondary: '#888888',

  // Globe colors
  ocean: '#0a1628',
  coastline: '#00b4b4',
  land: '#1a1a2e',
}

// =============================================================================
// Helper Functions
// =============================================================================

// Create case-insensitive lookup map for categories
const CATEGORY_COLORS_NORMALIZED = new Map<string, string>()
for (const [key, value] of Object.entries(CATEGORY_COLORS)) {
  CATEGORY_COLORS_NORMALIZED.set(key.toLowerCase(), value)
}

/**
 * Get a color for a source, with fallback to default.
 */
export function getSourceColor(sourceId: string): string {
  return SOURCE_COLORS[sourceId] || SOURCE_COLORS.default
}

/**
 * Get a color for a category, with fallback to default.
 * Case-insensitive lookup to handle variations in data.
 */
export function getCategoryColor(category: string): string {
  if (!category) return CATEGORY_COLORS.default
  // Try exact match first
  if (CATEGORY_COLORS[category]) return CATEGORY_COLORS[category]
  // Try case-insensitive, then with underscores↔spaces
  const normalized = category.toLowerCase()
  return CATEGORY_COLORS_NORMALIZED.get(normalized)
    || CATEGORY_COLORS_NORMALIZED.get(normalized.replace(/_/g, ' '))
    || CATEGORY_COLORS_NORMALIZED.get(normalized.replace(/ /g, '_'))
    || CATEGORY_COLORS.default
}

/**
 * Get a color for a period, with fallback to default.
 */
export function getPeriodColor(period: string): string {
  return PERIOD_COLORS[period] || PERIOD_COLORS['Unknown']
}
