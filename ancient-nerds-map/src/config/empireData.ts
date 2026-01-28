/**
 * Historical empire configuration
 * Contains empire definitions with time periods, colors, and regions
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
  'Southeast Asia',
  'Africa',
  'Americas',
  'Medieval Europe',
  'Islamic'
] as const

export type EmpireRegion = typeof EMPIRE_REGIONS[number]

export const EMPIRES: EmpireConfig[] = [
  // Ancient Near East - Warm golds/oranges/reds
  { id: 'egyptian', name: 'Egyptian Empire', region: 'Ancient Near East', startYear: -2401, endYear: -29, color: 0xFFD700, file: 'egyptian' },  // Gold
  { id: 'akkadian', name: 'Akkadian Empire', region: 'Ancient Near East', startYear: -2276, endYear: -2151, color: 0xFFA07A, file: 'akkadian' },  // Light salmon
  { id: 'babylonian', name: 'Babylonian', region: 'Ancient Near East', startYear: -1781, endYear: -536, color: 0xFFB347, file: 'babylonian' },  // Bright orange
  { id: 'assyrian', name: 'Assyrian Empire', region: 'Ancient Near East', startYear: -1781, endYear: -608, color: 0xFF6B6B, file: 'assyrian' },  // Coral red
  { id: 'hittite', name: 'Hittite Empire', region: 'Ancient Near East', startYear: -1551, endYear: -1176, color: 0xFFAA00, file: 'hittite' },  // Amber

  // Mediterranean - Warm reds/corals/magentas (coherent warm color family)
  { id: 'roman', name: 'Roman Empire', region: 'Mediterranean', startYear: -419, endYear: 476, color: 0xFF7777, file: 'roman' },  // Light coral red (brighter)
  { id: 'greek', name: 'Greek City-States', region: 'Mediterranean', startYear: -1051, endYear: -168, color: 0xFFA07A, file: 'greek' },  // Light salmon (warm)
  { id: 'macedonian', name: 'Macedonian Empire', region: 'Mediterranean', startYear: -613, endYear: -168, color: 0xFF8866, file: 'macedonian' },  // Coral orange
  { id: 'byzantine', name: 'Byzantine Empire', region: 'Mediterranean', startYear: 395, endYear: 1471, color: 0xFF99AA, file: 'byzantine' },  // Light rose
  { id: 'carthaginian', name: 'Carthaginian', region: 'Mediterranean', startYear: -641, endYear: -155, color: 0xFFAA88, file: 'carthaginian' },  // Peach

  // Persian/Central Asia - Cyans/teals/bright blues (avoid ocean-like blues)
  { id: 'achaemenid', name: 'Achaemenid Persia', region: 'Persian/Central Asia', startYear: -546, endYear: -329, color: 0x00BFFF, file: 'achaemenid' },  // Deep sky blue
  { id: 'parthian', name: 'Parthian Empire', region: 'Persian/Central Asia', startYear: -202, endYear: 230, color: 0x40E0D0, file: 'parthian' },  // Turquoise
  { id: 'sassanid', name: 'Sassanid Empire', region: 'Persian/Central Asia', startYear: 219, endYear: 642, color: 0x7FFFD4, file: 'sassanid' },  // Aquamarine
  { id: 'seleucid', name: 'Seleucid Empire', region: 'Persian/Central Asia', startYear: -317, endYear: -65, color: 0x00CED1, file: 'seleucid' },  // Dark turquoise
  { id: 'mongol', name: 'Mongol Empire', region: 'Persian/Central Asia', startYear: 1207, endYear: 1693, color: 0xF0E68C, file: 'mongol' },  // Khaki/tan
  { id: 'timurid', name: 'Timurid Empire', region: 'Persian/Central Asia', startYear: 1379, endYear: 1504, color: 0xDDA0DD, file: 'timurid' },  // Plum

  // East Asia - Reds/oranges/yellows
  { id: 'shang', name: 'Shang Dynasty', region: 'East Asia', startYear: -1421, endYear: -1051, color: 0xFFD700, file: 'shang' },  // Gold
  { id: 'zhou', name: 'Zhou Dynasty', region: 'East Asia', startYear: -901, endYear: -256, color: 0xFFE135, file: 'zhou' },  // Banana yellow
  { id: 'qin', name: 'Qin Dynasty', region: 'East Asia', startYear: -216, endYear: -206, color: 0xFF5733, file: 'qin' },  // Vermillion
  { id: 'han', name: 'Han Dynasty', region: 'East Asia', startYear: -200, endYear: 230, color: 0xFF6347, file: 'han' },  // Tomato
  { id: 'tang', name: 'Tang Dynasty', region: 'East Asia', startYear: 624, endYear: 905, color: 0xFF7F50, file: 'tang' },  // Coral
  { id: 'song', name: 'Song Dynasty', region: 'East Asia', startYear: 961, endYear: 1275, color: 0xFFA500, file: 'song' },  // Orange
  { id: 'ming', name: 'Ming Dynasty', region: 'East Asia', startYear: 1379, endYear: 1643, color: 0xFFD700, file: 'ming' },  // Gold
  { id: 'qing', name: 'Qing Dynasty', region: 'East Asia', startYear: 1646, endYear: 1911, color: 0xFFB90F, file: 'qing' },  // Dark goldenrod

  // South Asia - Bright greens/limes
  { id: 'maurya', name: 'Maurya Empire', region: 'South Asia', startYear: -317, endYear: -180, color: 0x7FFF00, file: 'maurya' },  // Chartreuse
  { id: 'gupta', name: 'Gupta Empire', region: 'South Asia', startYear: 335, endYear: 550, color: 0x00FF7F, file: 'gupta' },  // Spring green
  { id: 'chola', name: 'Chola Dynasty', region: 'South Asia', startYear: 867, endYear: 1254, color: 0x7CFC00, file: 'chola' },  // Lawn green
  { id: 'mughal', name: 'Mughal Empire', region: 'South Asia', startYear: 1465, endYear: 1857, color: 0xADFF2F, file: 'mughal' },  // Green yellow

  // Southeast Asia - Light greens/teals
  { id: 'khmer', name: 'Khmer Empire', region: 'Southeast Asia', startYear: 802, endYear: 1431, color: 0x98FB98, file: 'khmer' },  // Pale green
  { id: 'majapahit', name: 'Majapahit Empire', region: 'Southeast Asia', startYear: 1318, endYear: 1517, color: 0x90EE90, file: 'majapahit' },  // Light green
  { id: 'srivijaya', name: 'Srivijaya', region: 'Southeast Asia', startYear: 677, endYear: 1289, color: 0x00FA9A, file: 'srivijaya' },  // Medium spring green

  // Africa - Warm earth tones (bright versions)
  { id: 'kush', name: 'Kingdom of Kush', region: 'Africa', startYear: 46, endYear: 230, color: 0xFF8C00, file: 'kush' },  // Dark orange
  { id: 'ghana', name: 'Ghana Empire', region: 'Africa', startYear: 938, endYear: 1231, color: 0xF0E68C, file: 'ghana' },  // Khaki
  { id: 'mali', name: 'Mali Empire', region: 'Africa', startYear: 1238, endYear: 1610, color: 0xFFDAB9, file: 'mali' },  // Peach puff
  { id: 'songhai', name: 'Songhai Empire', region: 'Africa', startYear: 1465, endYear: 1605, color: 0xFFA07A, file: 'songhai' },  // Light salmon

  // Americas - Bright greens/limes (keeping these as reference)
  { id: 'maya', name: 'Maya Civilization', region: 'Americas', startYear: 6, endYear: 844, color: 0x00FF7F, file: 'maya' },  // Spring green
  { id: 'aztec', name: 'Aztec Empire', region: 'Americas', startYear: 1434, endYear: 1521, color: 0x7CFC00, file: 'aztec' },  // Lawn green
  { id: 'inca', name: 'Inca Empire', region: 'Americas', startYear: 1444, endYear: 1567, color: 0x7FFF00, file: 'inca' },  // Chartreuse

  // Medieval Europe - Soft blues/purples
  { id: 'hre', name: 'Holy Roman Empire', region: 'Medieval Europe', startYear: 965, endYear: 1806, color: 0x87CEFA, file: 'hre' },  // Light sky blue

  // Islamic - Bright greens (traditional Islamic color)
  { id: 'umayyad', name: 'Umayyad Caliphate', region: 'Islamic', startYear: 658, endYear: 755, color: 0x00FF7F, file: 'umayyad' },  // Spring green
  { id: 'abbasid', name: 'Abbasid Caliphate', region: 'Islamic', startYear: 750, endYear: 1254, color: 0x7CFC00, file: 'abbasid' },  // Lawn green
  { id: 'fatimid', name: 'Fatimid Caliphate', region: 'Islamic', startYear: 916, endYear: 1172, color: 0x00FF00, file: 'fatimid' },  // Lime
  { id: 'ayyubid', name: 'Ayyubid Dynasty', region: 'Islamic', startYear: 1182, endYear: 1245, color: 0x32CD32, file: 'ayyubid' },  // Lime green
  { id: 'ottoman', name: 'Ottoman Empire', region: 'Islamic', startYear: 1315, endYear: 1922, color: 0x00FA9A, file: 'ottoman' },  // Medium spring green
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
