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

/** Every schema node below `schema` with its path: "claims" for a property, "claims[]" for the items of an array, "evidence.statement" nested. */
export function schemaNodes(schema: Schema, path = ''): [string, Schema][] {
  const own: [string, Schema][] = path ? [[path, schema]] : []
  const properties = Object.entries(schema.properties ?? {}).flatMap(([key, sub]) => schemaNodes(sub, path ? `${path}.${key}` : key))
  const items = schema.items ? schemaNodes(schema.items, `${path}[]`) : []
  return [...own, ...properties, ...items]
}
