# AI Literacy Record (Art. 4 EU AI Act)

**Operator:** Dominiak Consulting (sole proprietorship), Martin Dominiak — sole operator and developer.
**Last reviewed:** 2026-07-31

## Scope

Art. 4 AI Act requires providers and deployers to ensure a sufficient level of AI literacy
of persons operating AI systems on their behalf. AncientNerds is operated and developed by
a single person; no employees or contractors operate the AI systems.

## AI systems in operation

| System | Purpose | Models |
|---|---|---|
| Lyra news pipeline | Generates news stories from YouTube transcripts | Anthropic Claude (Haiku/Sonnet/Opus) |
| Lyra weekly journal | Weekly digest article generation | Anthropic Claude Opus |
| Lyra chat | Interactive RAG assistant | Anthropic Claude + Voyage AI embeddings |
| Theo research pipeline | Deep-research papers | MiniMax M3 |
| Theo TTS | Paper narration audio | MiniMax speech-2.8-hd |
| Radar site discovery | Site identification/enrichment | Claude + Mercury (Inception Labs) |

## Literacy measures

- The operator designs, builds, tests, and monitors all pipelines personally, including
  prompt design, output verification gates (hallucination gate, citation integrity gate,
  LLM quality judges), and incident handling — demonstrating working knowledge of LLM
  capabilities and failure modes (hallucination, citation fabrication, quota-related
  empty outputs).
- Known limitations are documented in-repo (`docs/research/`, project memory) and
  disclosed to users on every content surface ("AI-generated ... may contain errors").
- Regulatory tracking: EU AI Act obligations reviewed 2026-03-19 (initial analysis) and
  2026-07-31 (full audit, this plan); Commission guidelines of 2026-07-20 and the Code of
  Practice on marking/labelling (final 2026-06-10) reviewed.

## Review cadence

Revisit this record when: a new AI system goes into operation, a person other than the
operator begins operating the systems, or the Commission issues new Art. 4 guidance.
