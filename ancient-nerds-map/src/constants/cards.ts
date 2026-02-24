export const RARITY_CLASSES: Record<number, string> = {
  1: 'rarity-common',
  2: 'rarity-uncommon',
  3: 'rarity-rare',
  4: 'rarity-epic',
  5: 'rarity-legendary',
}

/** Duplicates needed for each star level (matches backend STAR_LEVELS) */
export const STAR_LEVELS: Record<number, number> = {
  1: 0,
  2: 3,
  3: 8,
}
