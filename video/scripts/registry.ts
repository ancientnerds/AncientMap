/**
 * Writes src/blocks/registry.json (plan C contract C5) from src/blocks/schemas.ts:
 *   npm run registry
 * pipeline/studio/blocks.py reads the file at runtime; test/registry.test.ts
 * fails when the committed file differs from this output.
 */
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { buildRegistry, registryJson } from '../src/blocks/schemas'

const out = fileURLToPath(new URL('../src/blocks/registry.json', import.meta.url))
writeFileSync(out, registryJson())
console.log(`${out}: ${Object.keys(buildRegistry().blocks).length} blocks`)
