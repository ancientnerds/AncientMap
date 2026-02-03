/**
 * Seshat Global History Databank Type Definitions
 *
 * Types for representing polity data from Seshat, including social complexity,
 * warfare technology, economy, and crisis events.
 */

// ============= Core Polity Data =============

export interface SeshatPolityData {
  // Identity
  seshatId: string
  name: string
  alternateNames?: string[]

  // Time & Space
  startYear: number
  endYear: number
  peakYear?: number
  territory?: number           // km²
  peakTerritory?: number

  // Population
  population?: number
  capitalPopulation?: number
  largestSettlement?: string
  largestSettlementPopulation?: number

  // Hierarchy
  administrativeLevels?: number
  settlementHierarchy?: number
  militaryLevels?: number
  religiousLevels?: number

  // Political
  centralization?: 'none' | 'nominal' | 'loose' | 'unitary state'
  languages?: string[]
  religions?: string[]
  capital?: string

  // Succession
  precedingPolities?: SeshatPolityLink[]
  succeedingPolities?: SeshatPolityLink[]

  // Warfare Technology
  warfare?: SeshatWarfareData

  // Economy
  economy?: SeshatEconomyData

  // Crisis & Events
  crisis?: SeshatCrisisData

  // Sources
  seshatUrl?: string
  wikipediaUrl?: string
  lastUpdated?: string
}

export interface SeshatPolityLink {
  id: string
  name: string
  relation: 'succession' | 'conquest' | 'division' | 'unification' | 'continuation'
}

// ============= Warfare Data =============

export interface SeshatWarfareData {
  // Fortifications
  fortifications?: {
    earthRamparts?: boolean
    woodenPalisade?: boolean
    stoneWallsNonMortared?: boolean
    stoneWallsMortared?: boolean
    settlementsEnclosedFortified?: boolean
    moats?: boolean
    complexFortifications?: boolean
    longWalls?: boolean
    modernFortifications?: boolean
  }

  // Metals used in warfare
  metals?: ('copper' | 'bronze' | 'iron' | 'steel')[]

  // Projectile weapons
  projectileWeapons?: {
    slings?: boolean
    selfBows?: boolean
    javelins?: boolean
    atlatl?: boolean
    compositeBows?: boolean
    crossbows?: boolean
    tensionSiegeEngines?: boolean
    slingshotSiegeEngines?: boolean
    gunpowderSiegeArtillery?: boolean
    handHeldFirearms?: boolean
  }

  // Handheld weapons
  handheldWeapons?: {
    swords?: boolean
    spears?: boolean
    polearms?: boolean
    battleAxes?: boolean
    daggers?: boolean
    warClubs?: boolean
  }

  // Animals used in warfare
  warfareAnimals?: {
    horses?: boolean
    donkeys?: boolean
    camels?: boolean
    elephants?: boolean
    warDogs?: boolean
  }

  // Armor types
  armor?: {
    woodFabricShields?: boolean
    leatherShields?: boolean
    metalShields?: boolean
    chainmail?: boolean
    scaledArmor?: boolean
    plateArmor?: boolean
    limb?: boolean
    helmets?: boolean
    leatherClothArmor?: boolean
    lamellarArmor?: boolean
  }

  // Naval capabilities
  naval?: {
    smallVessels?: boolean
    merchantShips?: boolean
    warships?: boolean
  }
}

// ============= Economy Data =============

export interface SeshatEconomyData {
  // Information Systems
  writingSystem?: boolean
  mnemonicDevices?: boolean
  nonwrittenRecords?: boolean
  scripts?: string[]

  // Money & Trade
  coinage?: boolean
  indigenousCoins?: boolean
  foreignCoins?: boolean
  storedWealth?: boolean
  debtInstruments?: boolean

  // Trade routes
  tradeRoutes?: ('maritime' | 'overland' | 'riverine')[]
  longDistanceTrade?: boolean

  // Infrastructure
  roads?: boolean
  bridges?: boolean
  canals?: boolean
  irrigationSystems?: boolean
  ports?: boolean
  markets?: boolean
  foodStorageSites?: boolean
  drinkingWaterSupply?: boolean
}

// ============= Crisis Data =============

export interface SeshatCrisisData {
  crisisEvents?: SeshatCrisisEvent[]
  powerTransitions?: SeshatPowerTransition[]
}

export interface SeshatCrisisEvent {
  name: string
  startYear: number
  endYear: number
  type: 'civil war' | 'invasion' | 'plague' | 'famine' | 'political crisis' | 'economic crisis' | 'social crisis'
  description?: string
  severity?: 'minor' | 'moderate' | 'severe' | 'catastrophic'
}

export interface SeshatPowerTransition {
  year: number
  fromPolity?: string
  toPolity?: string
  type: 'succession' | 'conquest' | 'division' | 'unification' | 'collapse'
  peaceful?: boolean
}

// ============= Display Helpers =============

export interface SeshatWarfareDisplay {
  fortifications: string[]
  weapons: string[]
  armor: string[]
  animals: string[]
  naval: string
}

export interface SeshatSocialComplexitySummary {
  scale: {
    territory: string | null
    population: string | null
    capital: string | null
  }
  hierarchy: {
    administrative: number | null
    military: number | null
    religious: number | null
    settlement: number | null
  }
  infrastructure: string[]
}

// ============= Bundled Data Format =============

/** Format of the bundled polities.json file */
export interface SeshatDataBundle {
  version: string
  lastUpdated: string
  sources: {
    cliopatria: string
    equinox: string
  }
  polities: Record<string, SeshatPolityData>
}
