import gameConstants from '../data/game-constants.generated.json'

/** Cumulative duplicates needed for each star level (per-level cost: 2,3,5,8,13) */
export const STAR_LEVELS: Record<number, number> = Object.fromEntries(
  Object.entries(gameConstants.starLevels).map(([k, v]) => [Number(k), v])
) as Record<number, number>

export const MAX_STAR_LEVEL = gameConstants.maxStarLevel

/** Duplicates needed for the NEXT star from current (fibonacci: 2,3,5,8,13) */
export const DUPES_FOR_NEXT: Record<number, number> = {}
for (let i = 0; i < MAX_STAR_LEVEL; i++) {
  DUPES_FOR_NEXT[i] = (STAR_LEVELS[i + 1] ?? 0) - (STAR_LEVELS[i] ?? 0)
}
DUPES_FOR_NEXT[MAX_STAR_LEVEL] = 0
