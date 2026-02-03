/**
 * Seshat Global History Databank Service
 *
 * Provides access to bundled Seshat polity data for empire popups.
 * Replaces Wikipedia-based data with comprehensive historical data.
 */

import seshatDataBundle from '../data/seshat/polities.json'
import {
  SeshatPolityData,
  SeshatWarfareData,
  SeshatWarfareDisplay,
  SeshatSocialComplexitySummary,
  SeshatDataBundle
} from '../types/seshat'
import {
  getSeshatMapping,
  getSeshatPolityIdForYear,
  hasSeshatData as hasSeshatMapping
} from '../config/seshatMapping'

// Type assertion for the imported JSON
const seshatData = seshatDataBundle as SeshatDataBundle

/**
 * Get Seshat polity data by Seshat ID
 */
export function getSeshatPolityById(seshatId: string): SeshatPolityData | null {
  return seshatData.polities[seshatId] || null
}

/**
 * Get Seshat data for an empire at a specific year
 * Returns the appropriate polity data based on period mappings
 */
export function getSeshatDataForEmpire(
  empireId: string,
  year?: number
): SeshatPolityData | null {
  // Get the mapping for this empire
  const mapping = getSeshatMapping(empireId)
  if (!mapping) return null

  // Get the appropriate Seshat polity ID for the given year
  const seshatId = getSeshatPolityIdForYear(empireId, year)
  if (!seshatId) return null

  // Return the polity data
  return getSeshatPolityById(seshatId)
}

/**
 * Check if an empire has Seshat data available
 */
export function hasSeshatData(empireId: string): boolean {
  if (!hasSeshatMapping(empireId)) return false

  const mapping = getSeshatMapping(empireId)
  if (!mapping) return false

  // Check if the primary polity data exists
  return seshatData.polities[mapping.seshatId] !== undefined
}

/**
 * Get the Seshat polity name for display
 */
export function getSeshatPolityName(empireId: string, year?: number): string | null {
  const mapping = getSeshatMapping(empireId)
  if (!mapping) return null

  // Check if there's a period-specific name
  if (year !== undefined && mapping.periodMappings) {
    for (const period of mapping.periodMappings) {
      if (year >= period.yearStart && year <= period.yearEnd) {
        return period.seshatName
      }
    }
  }

  return mapping.seshatPolityName
}

/**
 * Format a number for display (e.g., 1000000 -> "1M")
 */
function formatNumber(num: number | undefined): string | null {
  if (num === undefined || num === null) return null

  if (num >= 1000000000) {
    return `${(num / 1000000000).toFixed(1)}B`
  }
  if (num >= 1000000) {
    return `${(num / 1000000).toFixed(1)}M`
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(0)}K`
  }
  return num.toString()
}

/**
 * Format territory in km²
 */
function formatTerritory(km2: number | undefined): string | null {
  if (km2 === undefined) return null

  if (km2 >= 1000000) {
    return `${(km2 / 1000000).toFixed(1)}M km²`
  }
  if (km2 >= 1000) {
    return `${(km2 / 1000).toFixed(0)}K km²`
  }
  return `${km2} km²`
}

/**
 * Format warfare data for display
 */
export function formatWarfareDisplay(warfare: SeshatWarfareData | undefined): SeshatWarfareDisplay {
  const result: SeshatWarfareDisplay = {
    fortifications: [],
    weapons: [],
    armor: [],
    animals: [],
    naval: 'None'
  }

  if (!warfare) return result

  // Fortifications
  const fortMap: Record<string, string> = {
    earthRamparts: 'Earth Ramparts',
    woodenPalisade: 'Wooden Palisade',
    stoneWallsNonMortared: 'Stone Walls (Dry)',
    stoneWallsMortared: 'Stone Walls (Mortared)',
    settlementsEnclosedFortified: 'Fortified Settlements',
    moats: 'Moats',
    complexFortifications: 'Complex Fortifications',
    longWalls: 'Long Walls',
    modernFortifications: 'Modern Fortifications'
  }

  if (warfare.fortifications) {
    for (const [key, label] of Object.entries(fortMap)) {
      if (warfare.fortifications[key as keyof typeof warfare.fortifications]) {
        result.fortifications.push(label)
      }
    }
  }

  // Weapons (combine projectile and handheld)
  const projectileMap: Record<string, string> = {
    slings: 'Slings',
    selfBows: 'Self Bows',
    javelins: 'Javelins',
    atlatl: 'Atlatl',
    compositeBows: 'Composite Bows',
    crossbows: 'Crossbows',
    tensionSiegeEngines: 'Siege Engines',
    slingshotSiegeEngines: 'Catapults',
    gunpowderSiegeArtillery: 'Artillery',
    handHeldFirearms: 'Firearms'
  }

  const handheldMap: Record<string, string> = {
    swords: 'Swords',
    spears: 'Spears',
    polearms: 'Polearms',
    battleAxes: 'Battle Axes',
    daggers: 'Daggers',
    warClubs: 'War Clubs'
  }

  if (warfare.projectileWeapons) {
    for (const [key, label] of Object.entries(projectileMap)) {
      if (warfare.projectileWeapons[key as keyof typeof warfare.projectileWeapons]) {
        result.weapons.push(label)
      }
    }
  }

  if (warfare.handheldWeapons) {
    for (const [key, label] of Object.entries(handheldMap)) {
      if (warfare.handheldWeapons[key as keyof typeof warfare.handheldWeapons]) {
        result.weapons.push(label)
      }
    }
  }

  // Add metals to weapons
  if (warfare.metals) {
    const metalLabels = warfare.metals.map(m => m.charAt(0).toUpperCase() + m.slice(1))
    result.weapons.unshift(`Metals: ${metalLabels.join(', ')}`)
  }

  // Armor
  const armorMap: Record<string, string> = {
    woodFabricShields: 'Wood/Fabric Shields',
    leatherShields: 'Leather Shields',
    metalShields: 'Metal Shields',
    chainmail: 'Chainmail',
    scaledArmor: 'Scaled Armor',
    plateArmor: 'Plate Armor',
    limb: 'Limb Protection',
    helmets: 'Helmets',
    leatherClothArmor: 'Leather/Cloth Armor',
    lamellarArmor: 'Lamellar Armor'
  }

  if (warfare.armor) {
    for (const [key, label] of Object.entries(armorMap)) {
      if (warfare.armor[key as keyof typeof warfare.armor]) {
        result.armor.push(label)
      }
    }
  }

  // Animals
  const animalMap: Record<string, string> = {
    horses: 'Horses',
    donkeys: 'Donkeys',
    camels: 'Camels',
    elephants: 'War Elephants',
    warDogs: 'War Dogs'
  }

  if (warfare.warfareAnimals) {
    for (const [key, label] of Object.entries(animalMap)) {
      if (warfare.warfareAnimals[key as keyof typeof warfare.warfareAnimals]) {
        result.animals.push(label)
      }
    }
  }

  // Naval
  if (warfare.naval) {
    const navalCapabilities: string[] = []
    if (warfare.naval.smallVessels) navalCapabilities.push('Small Vessels')
    if (warfare.naval.merchantShips) navalCapabilities.push('Merchant Ships')
    if (warfare.naval.warships) navalCapabilities.push('Warships')

    if (navalCapabilities.length > 0) {
      result.naval = navalCapabilities.join(', ')
    }
  }

  return result
}

/**
 * Get social complexity summary for display
 */
export function getSocialComplexitySummary(data: SeshatPolityData | null): SeshatSocialComplexitySummary {
  const result: SeshatSocialComplexitySummary = {
    scale: {
      territory: null,
      population: null,
      capital: null
    },
    hierarchy: {
      administrative: null,
      military: null,
      religious: null,
      settlement: null
    },
    infrastructure: []
  }

  if (!data) return result

  // Scale
  result.scale.territory = formatTerritory(data.territory || data.peakTerritory)
  result.scale.population = formatNumber(data.population)
  result.scale.capital = data.capital || null

  // Hierarchy
  result.hierarchy.administrative = data.administrativeLevels || null
  result.hierarchy.military = data.militaryLevels || null
  result.hierarchy.religious = data.religiousLevels || null
  result.hierarchy.settlement = data.settlementHierarchy || null

  // Infrastructure from economy
  if (data.economy) {
    if (data.economy.roads) result.infrastructure.push('Roads')
    if (data.economy.bridges) result.infrastructure.push('Bridges')
    if (data.economy.canals) result.infrastructure.push('Canals')
    if (data.economy.irrigationSystems) result.infrastructure.push('Irrigation')
    if (data.economy.ports) result.infrastructure.push('Ports')
    if (data.economy.markets) result.infrastructure.push('Markets')
    if (data.economy.foodStorageSites) result.infrastructure.push('Food Storage')
    if (data.economy.drinkingWaterSupply) result.infrastructure.push('Water Supply')
  }

  return result
}

/**
 * Get economy summary for display
 */
export function getEconomySummary(data: SeshatPolityData | null): {
  informationSystems: string[]
  monetary: string[]
  trade: string[]
} {
  const result = {
    informationSystems: [] as string[],
    monetary: [] as string[],
    trade: [] as string[]
  }

  if (!data?.economy) return result

  const economy = data.economy

  // Information Systems
  if (economy.writingSystem) result.informationSystems.push('Writing System')
  if (economy.mnemonicDevices) result.informationSystems.push('Mnemonic Devices')
  if (economy.nonwrittenRecords) result.informationSystems.push('Non-written Records')
  if (economy.scripts && economy.scripts.length > 0) {
    result.informationSystems.push(`Scripts: ${economy.scripts.join(', ')}`)
  }

  // Monetary
  if (economy.coinage) result.monetary.push('Coinage')
  if (economy.indigenousCoins) result.monetary.push('Indigenous Coins')
  if (economy.foreignCoins) result.monetary.push('Foreign Coins')
  if (economy.storedWealth) result.monetary.push('Stored Wealth')
  if (economy.debtInstruments) result.monetary.push('Debt Instruments')

  // Trade
  if (economy.longDistanceTrade) result.trade.push('Long-Distance Trade')
  if (economy.tradeRoutes && economy.tradeRoutes.length > 0) {
    const routes = economy.tradeRoutes.map(r => r.charAt(0).toUpperCase() + r.slice(1))
    result.trade.push(`Routes: ${routes.join(', ')}`)
  }

  return result
}

/**
 * Format year for display (handles BCE/CE)
 */
export function formatYear(year: number): string {
  if (year < 0) {
    return `${Math.abs(year)} BCE`
  }
  return `${year} CE`
}

/**
 * Format year range for display
 */
export function formatYearRange(startYear: number, endYear: number): string {
  return `${formatYear(startYear)} - ${formatYear(endYear)}`
}

/**
 * Get the Seshat URL for a polity
 */
export function getSeshatUrl(empireId: string, year?: number): string | null {
  const data = getSeshatDataForEmpire(empireId, year)
  return data?.seshatUrl || null
}

/**
 * Get the Wikipedia URL for a polity (from Seshat data)
 */
export function getWikipediaUrl(empireId: string, year?: number): string | null {
  const data = getSeshatDataForEmpire(empireId, year)
  return data?.wikipediaUrl || null
}

/**
 * Get all available Seshat polity IDs
 */
export function getAvailableSeshatPolities(): string[] {
  return Object.keys(seshatData.polities)
}

/**
 * Get data bundle metadata
 */
export function getSeshatDataVersion(): { version: string; lastUpdated: string } {
  return {
    version: seshatData.version,
    lastUpdated: seshatData.lastUpdated
  }
}
