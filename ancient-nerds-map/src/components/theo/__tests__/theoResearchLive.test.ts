import { describe, expect, it } from 'vitest'
import { THEO_PHASES, doneSublabel, phaseForStage } from '../TheoResearchLive'

describe('Theo live panel (research only)', () => {
  it('has no write or judge phase and ends at the dossier', () => {
    expect(THEO_PHASES).not.toContain('writing')
    expect(THEO_PHASES).not.toContain('judging')
    expect(THEO_PHASES[THEO_PHASES.length - 1]).toBe('dossier')
  })

  it('moves debate -> moderating -> dossier -> done', () => {
    expect(phaseForStage('debate', 'done')).toBe('moderating')
    expect(phaseForStage('moderator', 'start')).toBe('moderating')
    expect(phaseForStage('moderator', 'done')).toBe('dossier')
    expect(phaseForStage('dossier', 'start')).toBe('dossier')
    expect(phaseForStage('dossier', 'done')).toBe('done')
  })

  it('keeps the research phases before it', () => {
    expect(phaseForStage('decomposition', 'start')).toBe('decomposing')
    expect(phaseForStage('search_ab12', 'done')).toBe('exploring')
    expect(phaseForStage('synthesis', 'start')).toBe('synthesizing')
  })

  it('ignores the removed writing stages', () => {
    expect(phaseForStage('paper', 'done')).toBeNull()
    expect(phaseForStage('quality_judge', 'done')).toBeNull()
  })

  it('says Dossier ready when the run ends researched', () => {
    expect(doneSublabel('researched')).toBe('DOSSIER READY')
    expect(doneSublabel('failed')).toBe('RESEARCH FAILED')
    expect(doneSublabel('cancelled')).toBe('RESEARCH CANCELLED')
    expect(doneSublabel(null)).toBe('RESEARCH FINISHED')
  })
})
