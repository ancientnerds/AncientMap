import { describe, expect, it } from 'vitest'
import { researchStatusLabel } from '../TheoPage'

describe('researchStatusLabel', () => {
  it('names a finished research run that waits for the Claude write', () => {
    expect(researchStatusLabel('researched')).toBe('Researched · awaiting write')
  })

  it('keeps the existing labels', () => {
    expect(researchStatusLabel('completed')).toBe('Done')
    expect(researchStatusLabel('failed')).toBe('Failed')
    expect(researchStatusLabel('cancelled')).toBe('Cancelled')
  })

  it('shows any other status verbatim', () => {
    expect(researchStatusLabel('deferred')).toBe('deferred')
  })
})
