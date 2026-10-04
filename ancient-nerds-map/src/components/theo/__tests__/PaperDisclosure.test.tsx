/**
 * The visible AI disclosure line of a model-written paper (studio spec
 * 2026-09-26 §3.7, EU AI Act Art. 50(4)/(5)), rendered as the SSR sidecar
 * renders it.
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { ResearchWriter } from '../../../types/anRoute'
import PaperDisclosure, { disclosureText } from '../PaperDisclosure'

const WRITER: ResearchWriter = {
  model: 'claude-opus-5-5',
  tool: 'claude-code',
  research_model: 'MiniMax-M3',
  published: 'automatic',
  human_review: false,
}

/** The studio's own WRITER since 2026-10-03: a paper written in MiniMax Code. */
const MCODE_WRITER: ResearchWriter = {
  model: 'MiniMax-M3.1-Flash-Preview',
  tool: 'mcode',
  research_model: 'MiniMax-M3',
  published: 'automatic',
  human_review: false,
}

describe('disclosureText', () => {
  it('is the spec §3.7 line for an automatic publish without review', () => {
    expect(disclosureText(WRITER)).toBe(
      'Researched by Theo (AI research agent) · written by Claude (Anthropic) · ' +
        'published automatically after automated source checks, without human editorial review',
    )
  })

  it('names a manual publish and a human review when the record says so', () => {
    expect(disclosureText({ ...WRITER, published: 'manual', human_review: true })).toBe(
      'Researched by Theo (AI research agent) · written by Claude (Anthropic) · ' +
        'published by the editor after automated source checks, with human editorial review',
    )
  })

  it('prints a non-Claude model id as stored', () => {
    expect(disclosureText({ ...WRITER, model: 'other-model-1' })).toContain(
      'written by other-model-1 ·',
    )
  })

  it('names MiniMax M3.1 Flash as the writer of a paper the studio wrote', () => {
    expect(disclosureText(MCODE_WRITER)).toBe(
      'Researched by Theo (AI research agent) · written by MiniMax M3.1 Flash (MiniMax) · ' +
        'published automatically after automated source checks, without human editorial review',
    )
  })
})

describe('PaperDisclosure', () => {
  it('renders the line as a machine-readable AI notice', () => {
    expect(renderToString(<PaperDisclosure writer={WRITER} />)).toBe(
      `<p class="theo-paper-disclosure" data-ai-generated="true">${disclosureText(WRITER)}</p>`,
    )
  })
})
