/** Helpers over the block registry schemas shared by the registry and capacity tests. */
import type { Schema } from '../src/schema'

/** The schema a `drawn` pattern points at ('claims[].label': the label of every claim), or null. */
export function schemaAt(schema: Schema, pattern: string): Schema | null {
  let at: Schema | undefined = schema
  for (const part of pattern.split('.')) {
    const key = part.endsWith('[]') ? part.slice(0, -2) : part
    at = at?.properties?.[key]
    if (at && part.endsWith('[]')) at = at.type === 'array' ? at.items : undefined
  }
  return at ?? null
}
