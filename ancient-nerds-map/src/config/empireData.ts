/**
 * Historical empire configuration
 * Contains empire definitions with time periods, colors, and regions
 *
 * Generated data from pipeline/historical_boundaries/empire_metadata.py
 * — run `python pipeline/generate_shared_data.py` to regenerate.
 *
 * Scope: Civilizations that "touch ancient" (startYear before cutoff)
 * - Old World (Europe, Asia, Africa, Oceania): startYear <= 500 AD
 * - Americas: startYear <= 1500 AD
 */

import empireJson from '../data/empires.generated.json'

export interface EmpireConfig {
  id: string
  name: string
  region: string
  color: number
  file: string
}

export const EMPIRES: EmpireConfig[] = empireJson.map(e => ({
  ...e,
  file: e.id,
}))

export const EMPIRE_REGIONS = [...new Set(EMPIRES.map(e => e.region))] as const
export type EmpireRegion = typeof EMPIRE_REGIONS[number]

export function getEmpiresByRegion(region: EmpireRegion): EmpireConfig[] {
  return EMPIRES.filter(e => e.region === region)
}

export function getEmpireById(id: string): EmpireConfig | undefined {
  return EMPIRES.find(e => e.id === id)
}
