import { describe, expect, it } from 'vitest'

import { type Schema, unsupportedKeywords, validate } from '../src/schema'

const schema: Schema = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'n'],
  properties: {
    id: { type: 'string', minLength: 1, maxLength: 4 },
    n: { type: 'integer', minimum: 1, maximum: 9 },
    tone: { type: 'string', enum: ['accent', 'warn'] },
    box: { type: 'array', minItems: 4, maxItems: 4, items: { type: 'number' } },
    anchor: { type: ['string', 'null'] },
    extra: { type: 'object', additionalProperties: { type: 'number' } },
  },
}

describe('validate', () => {
  it('accepts a valid object (integers count as numbers, null where listed)', () => {
    expect(validate(schema, { id: 'c1', n: 3, tone: 'warn', box: [1, 2.5, 3, 4], anchor: null, extra: { a: 1 } })).toEqual([])
  })
  it('reports each defect with its path', () => {
    expect(validate(schema, { id: 'toolong', n: 12, tone: 'red', box: [1, 2], other: true })).toEqual([
      '$.id: longer than 4',
      '$.n: 12 is above 9',
      '$.tone: "red" is not one of ["accent","warn"]',
      '$.box: fewer than 4 items',
      '$.other: not allowed',
    ])
    expect(validate(schema, { id: 'a' })).toEqual(['$.n: missing'])
    expect(validate(schema, { id: 'a', n: 1.5 })).toEqual(['$.n: expected integer, got number'])
    expect(validate(schema, { id: 'a', n: 1, extra: { a: 'x' } })).toEqual(['$.extra.a: expected number, got string'])
  })
  it('applies hookMaxLength and hookMaxItems to a hook scene only: the stage under the hook captions is shorter', () => {
    const card: Schema = {
      type: 'object',
      properties: {
        statement: { type: 'string', maxLength: 100, hookMaxLength: 68 },
        note: { type: 'string', maxLength: 110, hookMaxLength: 0 },
        rows: { type: 'array', items: { type: 'string' }, maxItems: 6, hookMaxItems: 5 },
        over: { type: 'string', maxLength: 10, hookMaxLength: 5 },
      },
    }
    const value = { statement: 'x'.repeat(80), note: 'a note', rows: Array(6).fill('r'), over: 'x'.repeat(11) }
    expect(validate(card, value)).toEqual(['$.over: longer than 10'])
    expect(validate(card, value, '$', true)).toEqual([
      '$.statement: longer than 68 on a hook beat',
      '$.note: not allowed on a hook beat',
      '$.rows: more than 5 items on a hook beat',
      '$.over: longer than 10',
    ])
    expect(validate(card, { statement: 'x'.repeat(68), rows: Array(5).fill('r') }, '$', true)).toEqual([])
    // nested: a hook limit inside an array item binds with the flag too
    expect(validate({ type: 'array', items: card }, [{ statement: 'x'.repeat(69) }], '$', true)).toEqual(['$[0].statement: longer than 68 on a hook beat'])
  })
  it('keeps hookMaxLength and hookMaxItems inside the subset pipeline/studio/blocks.py accepts', () => {
    expect(unsupportedKeywords({ type: 'string', maxLength: 10, hookMaxLength: 5 })).toEqual([])
    expect(unsupportedKeywords({ type: 'array', maxItems: 5, hookMaxItems: 4 })).toEqual([])
  })
  it('finds keywords outside the subset pipeline/studio/blocks.py accepts', () => {
    expect(unsupportedKeywords({ type: 'object', properties: { a: { oneOf: [] } as unknown as Schema } })).toEqual(['$.properties.a.oneOf'])
    expect(unsupportedKeywords({ type: 'string', pattern: '^x$' } as unknown as Schema)).toEqual(['$.pattern'])
    expect(unsupportedKeywords({ type: 'array', items: { type: 'number', $comment: 'fine', title: 't', default: 1 } })).toEqual([])
  })
})
