/**
 * Empire ID to Seshat Polity ID Mapping
 *
 * Maps our 37 empire IDs to their corresponding Seshat polity IDs.
 * Some empires span multiple Seshat polities (different periods/phases),
 * which are handled via periodMappings.
 *
 * Scope: Civilizations that "touch ancient" (startYear before cutoff)
 * - Old World (Europe, Asia, Africa, Oceania): startYear <= 500 AD
 * - Americas: startYear <= 1500 AD
 *
 * Seshat polity IDs follow the format: {region_code}_{polity_name}
 * Examples: it_roman_principate, cn_han_dynasty, eg_new_kingdom
 */

export interface PeriodMapping {
  yearStart: number
  yearEnd: number
  seshatId: string
  seshatName: string
}

export interface SeshatMapping {
  /** Our empire ID (e.g., 'roman') */
  empireId: string
  /** Primary Seshat polity ID */
  seshatId: string
  /** Full Seshat polity name */
  seshatPolityName: string
  /** Optional period-specific mappings for multi-phase empires */
  periodMappings?: PeriodMapping[]
}

/**
 * Mappings between our empire IDs and Seshat polity IDs
 *
 * Seshat region codes:
 * - it = Italy
 * - tr = Turkey/Anatolia
 * - eg = Egypt
 * - iq = Iraq/Mesopotamia
 * - ir = Iran/Persia
 * - cn = China
 * - in = India
 * - pk = Pakistan
 * - af = Afghanistan
 * - gr = Greece
 * - lb = Lebanon
 * - sy = Syria
 * - mx = Mexico/Mesoamerica
 * - pe = Peru/Andes
 * - sd = Sudan
 * - et = Ethiopia
 * - fr = France
 */
export const SESHAT_MAPPINGS: SeshatMapping[] = [
  // ============= Ancient Near East (7) =============
  {
    empireId: 'egyptian',
    seshatId: 'eg_new_kingdom',
    seshatPolityName: 'New Kingdom Egypt',
    periodMappings: [
      { yearStart: -2401, yearEnd: -2181, seshatId: 'eg_old_kingdom', seshatName: 'Old Kingdom Egypt' },
      { yearStart: -2055, yearEnd: -1650, seshatId: 'eg_middle_kingdom', seshatName: 'Middle Kingdom Egypt' },
      { yearStart: -1550, yearEnd: -1070, seshatId: 'eg_new_kingdom', seshatName: 'New Kingdom Egypt' },
      { yearStart: -1069, yearEnd: -664, seshatId: 'eg_third_intermediate', seshatName: 'Third Intermediate Period' },
      { yearStart: -664, yearEnd: -332, seshatId: 'eg_late_period', seshatName: 'Late Period Egypt' },
      { yearStart: -332, yearEnd: -29, seshatId: 'eg_ptolemaic', seshatName: 'Ptolemaic Kingdom' }
    ]
  },
  {
    empireId: 'akkadian',
    seshatId: 'iq_akkadian_empire',
    seshatPolityName: 'Akkadian Empire'
  },
  {
    empireId: 'elam',
    seshatId: 'ir_elam_middle',
    seshatPolityName: 'Elamite Kingdom',
    periodMappings: [
      { yearStart: -3200, yearEnd: -2700, seshatId: 'ir_elam_proto', seshatName: 'Proto-Elamite' },
      { yearStart: -2700, yearEnd: -1500, seshatId: 'ir_elam_old', seshatName: 'Old Elamite' },
      { yearStart: -1500, yearEnd: -1100, seshatId: 'ir_elam_middle', seshatName: 'Middle Elamite' },
      { yearStart: -1100, yearEnd: -601, seshatId: 'ir_elam_neo', seshatName: 'Neo-Elamite' }
    ]
  },
  {
    empireId: 'babylonian',
    seshatId: 'iq_old_babylonian',
    seshatPolityName: 'Old Babylonian Empire',
    periodMappings: [
      { yearStart: -1894, yearEnd: -1595, seshatId: 'iq_old_babylonian', seshatName: 'Old Babylonian Empire' },
      { yearStart: -626, yearEnd: -539, seshatId: 'iq_neo_babylonian', seshatName: 'Neo-Babylonian Empire' }
    ]
  },
  {
    empireId: 'assyrian',
    seshatId: 'iq_neo_assyrian',
    seshatPolityName: 'Neo-Assyrian Empire',
    periodMappings: [
      { yearStart: -1975, yearEnd: -1750, seshatId: 'iq_old_assyrian', seshatName: 'Old Assyrian Period' },
      { yearStart: -1392, yearEnd: -1056, seshatId: 'iq_middle_assyrian', seshatName: 'Middle Assyrian Empire' },
      { yearStart: -911, yearEnd: -609, seshatId: 'iq_neo_assyrian', seshatName: 'Neo-Assyrian Empire' }
    ]
  },
  {
    empireId: 'hittite',
    seshatId: 'tr_hittite_empire',
    seshatPolityName: 'Hittite Empire'
  },
  {
    empireId: 'mitanni',
    seshatId: 'sy_mitanni_kingdom',
    seshatPolityName: 'Mitanni Kingdom'
  },

  // ============= Mediterranean (9) =============
  {
    empireId: 'minoan',
    seshatId: 'gr_crete_new_palace',
    seshatPolityName: 'Minoan Civilization'
  },
  {
    empireId: 'mycenaean',
    seshatId: 'gr_mycenae',
    seshatPolityName: 'Mycenaean Greece'
  },
  {
    empireId: 'phoenician',
    seshatId: 'lb_phoenician',
    seshatPolityName: 'Phoenicia'
  },
  {
    empireId: 'etruscan',
    seshatId: 'it_etruscan',
    seshatPolityName: 'Etruscan Civilization'
  },
  {
    empireId: 'greek',
    seshatId: 'gr_classical_athens',
    seshatPolityName: 'Classical Athens',
    periodMappings: [
      { yearStart: -1051, yearEnd: -750, seshatId: 'gr_dark_age', seshatName: 'Greek Dark Age' },
      { yearStart: -750, yearEnd: -480, seshatId: 'gr_archaic', seshatName: 'Archaic Greece' },
      { yearStart: -480, yearEnd: -323, seshatId: 'gr_classical_athens', seshatName: 'Classical Athens' },
      { yearStart: -323, yearEnd: -168, seshatId: 'gr_hellenistic', seshatName: 'Hellenistic Period' }
    ]
  },
  {
    empireId: 'macedonian',
    seshatId: 'gr_macedon_argead',
    seshatPolityName: 'Macedonian Empire (Argead Dynasty)'
  },
  {
    empireId: 'carthaginian',
    seshatId: 'tn_carthage',
    seshatPolityName: 'Carthaginian Empire'
  },
  {
    empireId: 'roman',
    seshatId: 'it_roman_principate',
    seshatPolityName: 'Roman Empire - Principate',
    periodMappings: [
      { yearStart: -509, yearEnd: -27, seshatId: 'it_roman_republic', seshatName: 'Roman Republic' },
      { yearStart: -27, yearEnd: 284, seshatId: 'it_roman_principate', seshatName: 'Roman Principate' },
      { yearStart: 284, yearEnd: 395, seshatId: 'it_roman_dominate', seshatName: 'Roman Dominate' },
      { yearStart: 395, yearEnd: 476, seshatId: 'it_western_roman', seshatName: 'Western Roman Empire' }
    ]
  },
  {
    empireId: 'byzantine',
    seshatId: 'tr_byzantine_empire',
    seshatPolityName: 'Byzantine Empire',
    periodMappings: [
      { yearStart: 395, yearEnd: 610, seshatId: 'tr_byzantine_early', seshatName: 'Early Byzantine Empire' },
      { yearStart: 610, yearEnd: 1071, seshatId: 'tr_byzantine_middle', seshatName: 'Middle Byzantine Empire' },
      { yearStart: 1081, yearEnd: 1204, seshatId: 'tr_byzantine_komnenian', seshatName: 'Komnenian Byzantine' },
      { yearStart: 1261, yearEnd: 1453, seshatId: 'tr_byzantine_palaiologan', seshatName: 'Palaiologan Byzantine' }
    ]
  },

  // ============= Persian/Central Asia (5) =============
  {
    empireId: 'achaemenid',
    seshatId: 'ir_achaemenid_empire',
    seshatPolityName: 'Achaemenid Persian Empire'
  },
  {
    empireId: 'seleucid',
    seshatId: 'ir_seleucid_empire',
    seshatPolityName: 'Seleucid Empire'
  },
  {
    empireId: 'parthian',
    seshatId: 'ir_parthian_empire',
    seshatPolityName: 'Parthian Empire'
  },
  {
    empireId: 'kushan',
    seshatId: 'af_kushan_empire',
    seshatPolityName: 'Kushan Empire'
  },
  {
    empireId: 'sassanid',
    seshatId: 'ir_sasanian_empire',
    seshatPolityName: 'Sasanian Empire'
  },

  // ============= East Asia (4) =============
  {
    empireId: 'shang',
    seshatId: 'cn_shang_dynasty',
    seshatPolityName: 'Shang Dynasty'
  },
  {
    empireId: 'zhou',
    seshatId: 'cn_zhou_dynasty',
    seshatPolityName: 'Zhou Dynasty',
    periodMappings: [
      { yearStart: -1046, yearEnd: -771, seshatId: 'cn_western_zhou', seshatName: 'Western Zhou' },
      { yearStart: -770, yearEnd: -476, seshatId: 'cn_spring_autumn', seshatName: 'Spring and Autumn Period' },
      { yearStart: -475, yearEnd: -221, seshatId: 'cn_warring_states', seshatName: 'Warring States Period' }
    ]
  },
  {
    empireId: 'qin',
    seshatId: 'cn_qin_dynasty',
    seshatPolityName: 'Qin Dynasty'
  },
  {
    empireId: 'han',
    seshatId: 'cn_han_dynasty',
    seshatPolityName: 'Han Dynasty',
    periodMappings: [
      { yearStart: -206, yearEnd: 9, seshatId: 'cn_western_han', seshatName: 'Western Han' },
      { yearStart: 25, yearEnd: 220, seshatId: 'cn_eastern_han', seshatName: 'Eastern Han' }
    ]
  },

  // ============= South Asia (3) =============
  {
    empireId: 'indus_valley',
    seshatId: 'pk_harappan',
    seshatPolityName: 'Indus Valley Civilization',
    periodMappings: [
      { yearStart: -3300, yearEnd: -2600, seshatId: 'pk_early_harappan', seshatName: 'Early Harappan' },
      { yearStart: -2600, yearEnd: -1900, seshatId: 'pk_mature_harappan', seshatName: 'Mature Harappan' },
      { yearStart: -1900, yearEnd: -1300, seshatId: 'pk_late_harappan', seshatName: 'Late Harappan' }
    ]
  },
  {
    empireId: 'maurya',
    seshatId: 'in_maurya_empire',
    seshatPolityName: 'Maurya Empire'
  },
  {
    empireId: 'gupta',
    seshatId: 'in_gupta_empire',
    seshatPolityName: 'Gupta Empire'
  },

  // ============= Africa (2) =============
  {
    empireId: 'kush',
    seshatId: 'sd_kingdom_kush',
    seshatPolityName: 'Kingdom of Kush'
  },
  {
    empireId: 'axum',
    seshatId: 'et_aksum_empire',
    seshatPolityName: 'Aksumite Empire'
  },

  // ============= Americas (6) =============
  {
    empireId: 'olmec',
    seshatId: 'mx_olmec',
    seshatPolityName: 'Olmec Civilization'
  },
  {
    empireId: 'zapotec',
    seshatId: 'mx_zapotec',
    seshatPolityName: 'Zapotec Civilization'
  },
  {
    empireId: 'teotihuacan',
    seshatId: 'mx_teotihuacan',
    seshatPolityName: 'Teotihuacan'
  },
  {
    empireId: 'maya',
    seshatId: 'mx_maya_classic',
    seshatPolityName: 'Classic Maya Civilization',
    periodMappings: [
      { yearStart: -2000, yearEnd: 250, seshatId: 'mx_maya_preclassic', seshatName: 'Preclassic Maya' },
      { yearStart: 250, yearEnd: 900, seshatId: 'mx_maya_classic', seshatName: 'Classic Maya' },
      { yearStart: 900, yearEnd: 1500, seshatId: 'mx_maya_postclassic', seshatName: 'Postclassic Maya' }
    ]
  },
  {
    empireId: 'aztec',
    seshatId: 'mx_aztec_empire',
    seshatPolityName: 'Aztec Empire'
  },
  {
    empireId: 'inca',
    seshatId: 'pe_inca_empire',
    seshatPolityName: 'Inca Empire'
  },

  // ============= Medieval Europe (1) =============
  {
    empireId: 'carolingian',
    seshatId: 'fr_carolingian_empire',
    seshatPolityName: 'Carolingian Empire'
  },
]

/**
 * Get mapping for an empire ID
 */
export function getSeshatMapping(empireId: string): SeshatMapping | undefined {
  return SESHAT_MAPPINGS.find(m => m.empireId === empireId)
}

/**
 * Get the appropriate Seshat polity ID for a given empire and year
 */
export function getSeshatPolityIdForYear(empireId: string, year?: number): string | null {
  const mapping = getSeshatMapping(empireId)
  if (!mapping) return null

  // If no year specified or no period mappings, return primary ID
  if (year === undefined || !mapping.periodMappings) {
    return mapping.seshatId
  }

  // Find the period that contains the given year
  for (const period of mapping.periodMappings) {
    if (year >= period.yearStart && year <= period.yearEnd) {
      return period.seshatId
    }
  }

  // Fall back to primary ID
  return mapping.seshatId
}

/**
 * Get all empire IDs that have Seshat mappings
 */
export function getEmpiresWithSeshatData(): string[] {
  return SESHAT_MAPPINGS.map(m => m.empireId)
}

/**
 * Check if an empire has Seshat data
 */
export function hasSeshatData(empireId: string): boolean {
  return SESHAT_MAPPINGS.some(m => m.empireId === empireId)
}

/**
 * Get available periods with Seshat data for an empire
 * Returns array of periods with their year ranges and names
 */
export function getAvailablePeriodsForEmpire(empireId: string): PeriodMapping[] {
  const mapping = getSeshatMapping(empireId)
  if (!mapping) return []

  // If has period mappings, return those
  if (mapping.periodMappings && mapping.periodMappings.length > 0) {
    return mapping.periodMappings
  }

  // Otherwise return the primary mapping as a single period
  // We don't have exact year ranges, so return empty array
  // (only empires with periodMappings will show period selector)
  return []
}
