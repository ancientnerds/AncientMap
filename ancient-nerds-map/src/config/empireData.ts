/**
 * Historical empire configuration
 * Contains empire definitions with time periods, colors, and regions
 *
 * Scope: Civilizations that "touch ancient" (startYear before cutoff)
 * - Old World (Europe, Asia, Africa, Oceania): startYear <= 500 AD
 * - Americas: startYear <= 1500 AD
 */

export interface EmpireConfig {
  id: string
  name: string
  region: string
  startYear: number  // negative = BCE
  endYear: number
  color: number
  file: string
}

export const EMPIRE_REGIONS = [
  'Ancient Near East',
  'Mediterranean',
  'Persian/Central Asia',
  'East Asia',
  'South Asia',
  'Africa',
  'Americas',
  'Medieval Europe',
] as const

export type EmpireRegion = typeof EMPIRE_REGIONS[number]

export const EMPIRES: EmpireConfig[] = [
  // Ancient Near East - Warm golds/oranges/reds (7 empires)
  { id: 'egyptian', name: 'Egyptian Empire', region: 'Ancient Near East', startYear: -2401, endYear: -29, color: 0xFFD700, file: 'egyptian' },  // Gold
  { id: 'akkadian', name: 'Akkadian Empire', region: 'Ancient Near East', startYear: -2276, endYear: -2151, color: 0xFFA07A, file: 'akkadian' },  // Light salmon
  { id: 'elam', name: 'Elam', region: 'Ancient Near East', startYear: -3200, endYear: -601, color: 0xE6A44C, file: 'elam' },  // Bronze orange
  { id: 'babylonian', name: 'Babylonian', region: 'Ancient Near East', startYear: -1781, endYear: -536, color: 0xFFB347, file: 'babylonian' },  // Bright orange
  { id: 'assyrian', name: 'Assyrian Empire', region: 'Ancient Near East', startYear: -1781, endYear: -608, color: 0xFF6B6B, file: 'assyrian' },  // Coral red
  { id: 'hittite', name: 'Hittite Empire', region: 'Ancient Near East', startYear: -1551, endYear: -1176, color: 0xFFAA00, file: 'hittite' },  // Amber
  { id: 'mitanni', name: 'Mitanni', region: 'Ancient Near East', startYear: -1500, endYear: -1241, color: 0xD4A574, file: 'mitanni' },  // Tan

  // Mediterranean - Warm reds/corals/magentas (8 empires)
  { id: 'minoan', name: 'Minoan Civilization', region: 'Mediterranean', startYear: -1600, endYear: -1401, color: 0x20B2AA, file: 'minoan' },  // Light sea green
  { id: 'mycenaean', name: 'Mycenaean Greece', region: 'Mediterranean', startYear: -1500, endYear: -1101, color: 0x48D1CC, file: 'mycenaean' },  // Medium turquoise
  { id: 'phoenician', name: 'Phoenicia', region: 'Mediterranean', startYear: -700, endYear: -616, color: 0x9370DB, file: 'phoenician' },  // Medium purple
  { id: 'etruscan', name: 'Etruscan Civilization', region: 'Mediterranean', startYear: -750, endYear: -265, color: 0xDB7093, file: 'etruscan' },  // Pale violet red
  { id: 'greek', name: 'Greek City-States', region: 'Mediterranean', startYear: -1051, endYear: -168, color: 0xFFA07A, file: 'greek' },  // Light salmon (warm)
  { id: 'macedonian', name: 'Macedonian Empire', region: 'Mediterranean', startYear: -613, endYear: -168, color: 0xFF8866, file: 'macedonian' },  // Coral orange
  { id: 'carthaginian', name: 'Carthaginian', region: 'Mediterranean', startYear: -641, endYear: -155, color: 0xFFAA88, file: 'carthaginian' },  // Peach
  { id: 'roman', name: 'Roman Empire', region: 'Mediterranean', startYear: -419, endYear: 476, color: 0xFF7777, file: 'roman' },  // Light coral red (brighter)
  { id: 'byzantine', name: 'Byzantine Empire', region: 'Mediterranean', startYear: 395, endYear: 1471, color: 0xFF99AA, file: 'byzantine' },  // Light rose

  // Persian/Central Asia - Cyans/teals/bright blues (5 empires)
  { id: 'achaemenid', name: 'Achaemenid Persia', region: 'Persian/Central Asia', startYear: -546, endYear: -329, color: 0x00BFFF, file: 'achaemenid' },  // Deep sky blue
  { id: 'seleucid', name: 'Seleucid Empire', region: 'Persian/Central Asia', startYear: -317, endYear: -65, color: 0x00CED1, file: 'seleucid' },  // Dark turquoise
  { id: 'parthian', name: 'Parthian Empire', region: 'Persian/Central Asia', startYear: -202, endYear: 230, color: 0x40E0D0, file: 'parthian' },  // Turquoise
  { id: 'kushan', name: 'Kushan Empire', region: 'Persian/Central Asia', startYear: 43, endYear: 237, color: 0x5F9EA0, file: 'kushan' },  // Cadet blue
  { id: 'sassanid', name: 'Sassanid Empire', region: 'Persian/Central Asia', startYear: 219, endYear: 642, color: 0x7FFFD4, file: 'sassanid' },  // Aquamarine

  // East Asia - Reds/oranges/yellows (4 empires)
  { id: 'shang', name: 'Shang Dynasty', region: 'East Asia', startYear: -1421, endYear: -1051, color: 0xFFD700, file: 'shang' },  // Gold
  { id: 'zhou', name: 'Zhou Dynasty', region: 'East Asia', startYear: -901, endYear: -256, color: 0xFFE135, file: 'zhou' },  // Banana yellow
  { id: 'qin', name: 'Qin Dynasty', region: 'East Asia', startYear: -216, endYear: -206, color: 0xFF5733, file: 'qin' },  // Vermillion
  { id: 'han', name: 'Han Dynasty', region: 'East Asia', startYear: -200, endYear: 230, color: 0xFF6347, file: 'han' },  // Tomato

  // South Asia - Bright greens/limes (3 empires)
  { id: 'indus_valley', name: 'Indus Valley (Harappan)', region: 'South Asia', startYear: -3000, endYear: -1701, color: 0x66CDAA, file: 'indus_valley' },  // Medium aquamarine
  { id: 'maurya', name: 'Maurya Empire', region: 'South Asia', startYear: -317, endYear: -180, color: 0x7FFF00, file: 'maurya' },  // Chartreuse
  { id: 'gupta', name: 'Gupta Empire', region: 'South Asia', startYear: 335, endYear: 550, color: 0x00FF7F, file: 'gupta' },  // Spring green

  // Africa - Warm earth tones (2 empires)
  { id: 'kush', name: 'Kingdom of Kush', region: 'Africa', startYear: 46, endYear: 230, color: 0xFF8C00, file: 'kush' },  // Dark orange
  { id: 'axum', name: 'Aksumite Empire', region: 'Africa', startYear: 93, endYear: 1933, color: 0xCD853F, file: 'axum' },  // Peru (includes Ethiopian Empire)

  // Americas - Bright greens/limes (6 empires)
  { id: 'olmec', name: 'Olmec Civilization', region: 'Americas', startYear: -650, endYear: -351, color: 0x228B22, file: 'olmec' },  // Forest green
  { id: 'zapotec', name: 'Zapotec Civilization', region: 'Americas', startYear: -500, endYear: 895, color: 0x3CB371, file: 'zapotec' },  // Medium sea green
  { id: 'teotihuacan', name: 'Teotihuacan', region: 'Americas', startYear: -50, endYear: 704, color: 0x2E8B57, file: 'teotihuacan' },  // Sea green
  { id: 'maya', name: 'Maya Civilization', region: 'Americas', startYear: 6, endYear: 1697, color: 0x00FF7F, file: 'maya' },  // Spring green
  { id: 'aztec', name: 'Aztec Empire', region: 'Americas', startYear: 1434, endYear: 1521, color: 0x7CFC00, file: 'aztec' },  // Lawn green
  { id: 'inca', name: 'Inca Empire', region: 'Americas', startYear: 1444, endYear: 1567, color: 0x7FFF00, file: 'inca' },  // Chartreuse

  // Medieval Europe - Soft blues/purples (1 empire)
  { id: 'carolingian', name: 'Carolingian Empire', region: 'Medieval Europe', startYear: 465, endYear: 984, color: 0x6495ED, file: 'carolingian' },  // Cornflower blue
]

/**
 * Get empires by region
 */
export function getEmpiresByRegion(region: EmpireRegion): EmpireConfig[] {
  return EMPIRES.filter(e => e.region === region)
}

/**
 * Get empire by ID
 */
export function getEmpireById(id: string): EmpireConfig | undefined {
  return EMPIRES.find(e => e.id === id)
}
