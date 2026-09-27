/**
 * Prints src/theme/glyphs.ts DRAWABLE recomputed from the brand font files
 * (scripts/fontCoverage.ts): `npx tsx scripts/glyphs.ts`, cwd video/. Paste the
 * output over the constant when test/glyphs.test.ts reports drift.
 */
import { drawableRange } from './fontCoverage'

console.log(`export const DRAWABLE =\n  '${drawableRange()}'`)
