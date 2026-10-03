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

/**
 * The maker and family of the model that wrote the paper, as EU AI Act Art. 50 wants it
 * named, from the model id `result_json.writer` stores: "Claude (Anthropic)" for any
 * claude-* id, "MiniMax M3.1 Flash (MiniMax)" for any minimax id. Every other id is
 * printed exactly as stored (a paper published by an unknown tool stays honest about it).
 * The id itself never changes here: `result_json.writer.model` keeps it for the machine.
 */
function writerName(model: string): string {
  if (model.startsWith('claude')) return 'Claude (Anthropic)'
  if (/^minimax/i.test(model)) return 'MiniMax M3.1 Flash (MiniMax)'
  return model
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
