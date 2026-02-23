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
  { id: 'egyptian', name: 'Egyptian Empire', region: 'Ancient Near East', color: 0xFFD700, file: 'egyptian' },
  { id: 'akkadian', name: 'Akkadian Empire', region: 'Ancient Near East', color: 0xFFA07A, file: 'akkadian' },
  { id: 'elam', name: 'Elam', region: 'Ancient Near East', color: 0xE6A44C, file: 'elam' },
  { id: 'babylonian', name: 'Babylonian', region: 'Ancient Near East', color: 0xFFB347, file: 'babylonian' },
  { id: 'assyrian', name: 'Assyrian Empire', region: 'Ancient Near East', color: 0xFF6B6B, file: 'assyrian' },
  { id: 'hittite', name: 'Hittite Empire', region: 'Ancient Near East', color: 0xFFAA00, file: 'hittite' },
  { id: 'mitanni', name: 'Mitanni', region: 'Ancient Near East', color: 0xD4A574, file: 'mitanni' },

  // Mediterranean (9 empires)
  { id: 'minoan', name: 'Minoan Civilization', region: 'Mediterranean', color: 0x20B2AA, file: 'minoan' },
  { id: 'mycenaean', name: 'Mycenaean Greece', region: 'Mediterranean', color: 0x48D1CC, file: 'mycenaean' },
  { id: 'phoenician', name: 'Phoenicia', region: 'Mediterranean', color: 0x9370DB, file: 'phoenician' },
  { id: 'etruscan', name: 'Etruscan Civilization', region: 'Mediterranean', color: 0xDB7093, file: 'etruscan' },
  { id: 'greek', name: 'Greek City-States', region: 'Mediterranean', color: 0xFFA07A, file: 'greek' },
  { id: 'macedonian', name: 'Macedonian Empire', region: 'Mediterranean', color: 0xFF8866, file: 'macedonian' },
  { id: 'carthaginian', name: 'Carthaginian', region: 'Mediterranean', color: 0xFFAA88, file: 'carthaginian' },
  { id: 'roman', name: 'Roman Empire', region: 'Mediterranean', color: 0xFF7777, file: 'roman' },
  { id: 'byzantine', name: 'Byzantine Empire', region: 'Mediterranean', color: 0xFF99AA, file: 'byzantine' },

  // Persian/Central Asia (5 empires)
  { id: 'achaemenid', name: 'Achaemenid Persia', region: 'Persian/Central Asia', color: 0x00BFFF, file: 'achaemenid' },
  { id: 'seleucid', name: 'Seleucid Empire', region: 'Persian/Central Asia', color: 0x00CED1, file: 'seleucid' },
  { id: 'parthian', name: 'Parthian Empire', region: 'Persian/Central Asia', color: 0x40E0D0, file: 'parthian' },
  { id: 'kushan', name: 'Kushan Empire', region: 'Persian/Central Asia', color: 0x5F9EA0, file: 'kushan' },
  { id: 'sassanid', name: 'Sassanid Empire', region: 'Persian/Central Asia', color: 0x7FFFD4, file: 'sassanid' },

  // East Asia (4 empires)
  { id: 'shang', name: 'Shang Dynasty', region: 'East Asia', color: 0xFFD700, file: 'shang' },
  { id: 'zhou', name: 'Zhou Dynasty', region: 'East Asia', color: 0xFFE135, file: 'zhou' },
  { id: 'qin', name: 'Qin Dynasty', region: 'East Asia', color: 0xFF5733, file: 'qin' },
  { id: 'han', name: 'Han Dynasty', region: 'East Asia', color: 0xFF6347, file: 'han' },

  // South Asia (3 empires)
  { id: 'indus_valley', name: 'Indus Valley (Harappan)', region: 'South Asia', color: 0x66CDAA, file: 'indus_valley' },
  { id: 'maurya', name: 'Maurya Empire', region: 'South Asia', color: 0x7FFF00, file: 'maurya' },
  { id: 'gupta', name: 'Gupta Empire', region: 'South Asia', color: 0x00FF7F, file: 'gupta' },

  // Africa (2 empires)
  { id: 'kush', name: 'Kingdom of Kush', region: 'Africa', color: 0xFF8C00, file: 'kush' },
  { id: 'axum', name: 'Aksumite Empire', region: 'Africa', color: 0xCD853F, file: 'axum' },

  // Americas (6 empires)
  { id: 'olmec', name: 'Olmec Civilization', region: 'Americas', color: 0x228B22, file: 'olmec' },
  { id: 'zapotec', name: 'Zapotec Civilization', region: 'Americas', color: 0x3CB371, file: 'zapotec' },
  { id: 'teotihuacan', name: 'Teotihuacan', region: 'Americas', color: 0x2E8B57, file: 'teotihuacan' },
  { id: 'maya', name: 'Maya Civilization', region: 'Americas', color: 0x00FF7F, file: 'maya' },
  { id: 'aztec', name: 'Aztec Empire', region: 'Americas', color: 0x7CFC00, file: 'aztec' },
  { id: 'inca', name: 'Inca Empire', region: 'Americas', color: 0x7FFF00, file: 'inca' },

  // Medieval Europe (1 empire)
  { id: 'carolingian', name: 'Carolingian Empire', region: 'Medieval Europe', color: 0x6495ED, file: 'carolingian' },
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
