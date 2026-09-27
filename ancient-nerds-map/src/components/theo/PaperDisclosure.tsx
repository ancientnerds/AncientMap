/**
 * PaperDisclosure — the visible AI disclosure line of a Claude-written paper.
 *
 * EU AI Act Art. 50(4)/(5) (in force since 2026-08-02): AI-written text on
 * matters of public interest, published without human editorial review,
 * must say so at the latest on first exposure. So the line sits in the
 * paper header, right under the meta line, and carries the same
 * machine-readable marker as AiNoticeBanner (data-ai-generated).
 * The wording follows result_json.writer (studio spec 2026-09-26 §3.7).
 */

import type { ResearchWriter } from '../../types/anRoute'

import '../../styles/paper-extras.css'

/** "Claude (Anthropic)" for any claude-* model id; other ids are printed as stored. */
function writerName(model: string): string {
  return model.startsWith('claude') ? 'Claude (Anthropic)' : model
}

export function disclosureText(writer: ResearchWriter): string {
  const published =
    writer.published === 'automatic'
      ? 'published automatically after automated source checks'
      : 'published by the editor after automated source checks'
  const review = writer.human_review ? 'with human editorial review' : 'without human editorial review'
  return `Researched by Theo (AI research agent) · written by ${writerName(writer.model)} · ${published}, ${review}`
}

export default function PaperDisclosure({ writer }: { writer: ResearchWriter }) {
  return (
    <p className="theo-paper-disclosure" data-ai-generated="true">
      {disclosureText(writer)}
    </p>
  )
}
