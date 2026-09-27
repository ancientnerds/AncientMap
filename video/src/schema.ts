/**
 * The JSON-Schema subset of the block registry (plan C contract C5). The
 * renderer validates scene props with it; pipeline/studio/blocks.py validates
 * script props against the same registry.json with its own implementation of
 * the same subset, and refuses any other keyword at load. test/schema.test.ts
 * and test/registry.test.ts keep every block schema inside SUPPORTED.
 */
export type SchemaType = 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array' | 'null'

export type Schema = {
  type?: SchemaType | SchemaType[]
  properties?: Record<string, Schema>
  required?: string[]
  additionalProperties?: boolean | Schema
  items?: Schema
  enum?: readonly (string | number | boolean | null)[]
  minimum?: number
  maximum?: number
  minItems?: number
  maxItems?: number
  minLength?: number
  maxLength?: number
  description?: string
  title?: string
  default?: unknown
  $comment?: string
}

export const SUPPORTED: ReadonlySet<string> = new Set([
  'type',
  'properties',
  'required',
  'additionalProperties',
  'items',
  'enum',
  'minimum',
  'maximum',
  'minItems',
  'maxItems',
  'minLength',
  'maxLength',
  'description',
  'title',
  'default',
  '$comment',
])

function typeOf(v: unknown): SchemaType {
  if (v === null) return 'null'
  if (Array.isArray(v)) return 'array'
  if (typeof v === 'number') return Number.isInteger(v) ? 'integer' : 'number'
  if (typeof v === 'string' || typeof v === 'boolean' || typeof v === 'object') return typeof v as SchemaType
  throw new Error(`unsupported JSON value of type ${typeof v}`)
}

function typeMatches(actual: SchemaType, wanted: SchemaType): boolean {
  return actual === wanted || (wanted === 'number' && actual === 'integer')
}

/** Errors as "<path>: <message>"; an empty list means valid. */
export function validate(schema: Schema, value: unknown, path = '$'): string[] {
  const errors: string[] = []
  const actual = typeOf(value)
  if (schema.type !== undefined) {
    const wanted = Array.isArray(schema.type) ? schema.type : [schema.type]
    if (!wanted.some((w) => typeMatches(actual, w))) return [`${path}: expected ${wanted.join('|')}, got ${actual}`]
  }
  if (schema.enum !== undefined && !schema.enum.includes(value as string | number | boolean | null)) {
    errors.push(`${path}: ${JSON.stringify(value)} is not one of ${JSON.stringify(schema.enum)}`)
  }
  if (typeof value === 'number') {
    if (schema.minimum !== undefined && value < schema.minimum) errors.push(`${path}: ${value} is below ${schema.minimum}`)
    if (schema.maximum !== undefined && value > schema.maximum) errors.push(`${path}: ${value} is above ${schema.maximum}`)
  }
  if (typeof value === 'string') {
    if (schema.minLength !== undefined && value.length < schema.minLength) errors.push(`${path}: shorter than ${schema.minLength}`)
    if (schema.maxLength !== undefined && value.length > schema.maxLength) errors.push(`${path}: longer than ${schema.maxLength}`)
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) errors.push(`${path}: fewer than ${schema.minItems} items`)
    if (schema.maxItems !== undefined && value.length > schema.maxItems) errors.push(`${path}: more than ${schema.maxItems} items`)
    if (schema.items) {
      const items = schema.items
      value.forEach((item, i) => errors.push(...validate(items, item, `${path}[${i}]`)))
    }
  }
  if (actual === 'object') {
    const obj = value as Record<string, unknown>
    for (const key of schema.required ?? []) {
      if (!(key in obj)) errors.push(`${path}.${key}: missing`)
    }
    for (const [key, v] of Object.entries(obj)) {
      const sub = schema.properties?.[key]
      if (sub) errors.push(...validate(sub, v, `${path}.${key}`))
      else if (schema.additionalProperties === false) errors.push(`${path}.${key}: not allowed`)
      else if (typeof schema.additionalProperties === 'object') errors.push(...validate(schema.additionalProperties, v, `${path}.${key}`))
    }
  }
  return errors
}

/** Keywords used anywhere in `schema` outside SUPPORTED, as JSON paths. */
export function unsupportedKeywords(schema: Schema, path = '$'): string[] {
  const out: string[] = []
  for (const key of Object.keys(schema)) {
    if (!SUPPORTED.has(key)) out.push(`${path}.${key}`)
  }
  for (const [name, sub] of Object.entries(schema.properties ?? {})) out.push(...unsupportedKeywords(sub, `${path}.properties.${name}`))
  if (typeof schema.additionalProperties === 'object') out.push(...unsupportedKeywords(schema.additionalProperties, `${path}.additionalProperties`))
  if (schema.items) out.push(...unsupportedKeywords(schema.items, `${path}.items`))
  return out
}
