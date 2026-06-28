# Why Files Tone — Spec #2

## Problem

The research pipeline produces AI slop: verbose meta-commentary, hedging cascades, empty profundity. Sentences like "The convergence achieves its aha moment when all five angles are read together" describe the investigation process instead of stating findings. The assessment section defaults to debunking even after investigation-first prompt changes.

Root cause: the prompts describe what to do ("write like a detective") but don't show it. The LLM defaults to its training distribution of academic/AI writing. Rules like "don't lecture" are ignored because the model has no concrete example of the target output.

## Solution

Inject Why Files tone into all 5 paper section prompts via:
1. **Narrator identity** — Theo writes in first person with opinions and admitted uncertainty
2. **Few-shot examples** — one concrete paragraph per prompt demonstrating the exact tone
3. **Anti-slop banned patterns** — specific phrases that are forbidden
4. **Assessment stance** — Theo leans toward the user's hypothesis, leads with supporting evidence

## Research Basis

Analysis of 10+ Why Files episode transcripts (Anunnaki, Göbekli Tepe, Tesla/Pyramids, Dark Pyramid of Alaska, Adam & Eve Story, Smithsonian Cover-Up, Roswell Interview, Lacerta Files, Lost Labyrinth of Hawara, Operation Sunray). Key findings:

### Why Files Tone Patterns

**Hooks:** Drop reader into a specific moment. Always contain a date, person, or measurement. Never open with "Throughout history" or "Scholars have debated."

**Investigation:** "This led to X, which revealed Y." Builds credibility through specific details, then pulls the rug: "But here's the part that doesn't sit right." Short sentences for impact, long ones for evidence chains.

**Connecting the Dots:** Presents the mundane explanation first, then lays out the suspicious timeline with specific dates, then names what the pattern looks like without insisting: "If you're building a case... the timeline fits."

**Other Side:** Counter-evidence presented at full strength, not strawmanned. "And they have a point." Names specific credential problems, delivers factual knockouts without editorializing.

**Assessment:** Debunks thoroughly where warranted, then pivots to empathy. Closes with an earned question: "Who flipped the switch?" The question comes AFTER honest assessment, not before it.

**Narrator voice:** First person. Has opinions: "I don't trust military intelligence whistleblowers." Admits uncertainty flat out: "Something is going on. I just don't know what." Never hedges with passive voice.

### AI Slop vs Why Files

| AI Slop | Why Files |
|---------|-----------|
| "It should be noted that researchers suggest..." | "The scans show something metallic. I don't know what it is." |
| "This challenges our fundamental understanding..." | "It only took 30,000 years to go from Göbekli Tepe to landing probes on other planets." |
| "As we continue to explore this fascinating topic..." | "But that was just the cover story." |
| "While definitive answers remain elusive..." | "Something is going on. I just don't know what." |
| "The evidence suggests this could potentially indicate..." | "The timeline fits." |

## Narrator Voice

Third person documentary style — like a well-produced investigative documentary, not a blog post or personal opinion piece. The papers are published to a shared research library with the user's name as reviewer, so they must be shareable and credible.

The Why Files tone elements that work in third person:
- Short declarative sentences for impact
- Specific dates/names/measurements in every paragraph opener
- Escalation transitions: "But here's where it gets interesting"
- Flat honesty: "The evidence doesn't support this" not "further research is needed"
- Concrete details over abstractions

## Prompt Changes

### All 5 prompts get:

**Narrator block (prepended to each prompt):**
```
Write as an investigative documentary narrator — third person, authoritative, curious. Follow evidence like a detective following leads. Be direct when evidence is strong. Admit uncertainty flat out: "The evidence doesn't resolve this" is better than "further research is needed." Use specific dates, names, and measurements. Never hedge with passive voice.
```

**Banned patterns block (appended to DO NOT section):**
```
BANNED PHRASES (never use these):
- "it should be noted" / "it is worth considering" / "it is important to emphasize"
- "Throughout history" / "Since the dawn of time" / "Scholars have long debated"
- "further research is needed" / "the answer remains elusive" / "only time will tell"
- "This challenges our fundamental understanding"
- "As we continue to explore this fascinating topic"
- "The evidence suggests this could potentially indicate"
- Any sentence where "the investigation" or "the evidence" or "the analysis" is the subject

INSTEAD USE:
- Short declarative statements: "The scans show something metallic."
- Flat honesty: "I don't know what this means."
- Escalation: "But here's where it gets interesting."
- Specificity: dates, names, measurements in every opening sentence of a paragraph
```

### Per-prompt few-shot examples:

**v2_paper_hook.txt** — Add example:
```
EXAMPLE OF GOOD HOOK:
"In 1966, a CIA engineer named Chan Thomas published a 284-page manuscript called 'The Adam and Eve Story.' Within weeks, the Agency classified it. They released 57 pages — 'sanitized,' in their own words — and locked the rest away. For over fifty years, nobody outside Langley knew what the other 227 pages contained, or why a book about ancient geology was considered a national security threat."
```

**v2_paper_section.txt** — Add example:
```
EXAMPLE OF GOOD INVESTIGATION PROSE:
"Doug Mutchler reported for duty at Fort Richardson, just outside Anchorage. He was a counterintelligence officer — his DD-214 confirms that. In late 1992, he was monitoring news coverage of a Chinese nuclear test when a geologist appeared on screen describing a massive underground structure detected by seismographs. A giant pyramid made of dark stone, deep underground. Mutchler produced the documentation. His service record checks out. But here's the part that doesn't sit right: almost every detail beyond the initial broadcast traces back to a single interview, given decades later."
```

**v2_paper_connecting.txt** — Add example:
```
EXAMPLE OF GOOD CONNECTING PROSE:
"Romania applied for NATO membership repeatedly throughout the 1990s and was denied every time. Then, seven months after the alleged discovery beneath the Romanian Sphinx, Romania was admitted. March 29th, 2004. An application rejected for years was suddenly approved. That could be coincidence. But if you're building a case that powerful governments seize and control anomalous archaeological sites, the timeline fits."
```

**v2_paper_otherside.txt** — Add example:
```
EXAMPLE OF GOOD COUNTER-EVIDENCE:
"Zechariah Sitchin claimed to translate ancient Sumerian texts, but he had an economics degree and taught himself Sumerian while working for a shipping company in New York. His book came out in 1976 — there was no internet, no searchable databases of ancient writing. His translations are more interpretations than actual translations. And he misidentified the word 'Anunnaki' itself. Skeptics have a point here."
```

**v2_paper_assessment.txt** — Add example + stance instruction:
```
EXAMPLE OF GOOD ASSESSMENT:
"The material was fake, but the emotion was real. Spencer spent most of his life as a Scientologist. The interview transcript used words like 'computer' and 'database' in 1947 — terms that didn't enter common use until the 1960s. It doesn't hold up. But Spencer succeeded because people want a reason for why life is so hard. That's not gullibility. That's hope."

STANCE: The investigation built a case FOR the hypothesis. Lead with what was found that supports it. Categorize honestly — some findings are solid, some uncertain, some speculative. But do not debunk. End with what's genuinely still open.
```

## Files to Modify

| File | Change |
|------|--------|
| `pipeline/lyra/prompts/v2_paper_hook.txt` | Add narrator block, few-shot example, banned patterns |
| `pipeline/lyra/prompts/v2_paper_section.txt` | Add narrator block, few-shot example, banned patterns |
| `pipeline/lyra/prompts/v2_paper_connecting.txt` | Add narrator block, few-shot example, banned patterns |
| `pipeline/lyra/prompts/v2_paper_otherside.txt` | Add narrator block, few-shot example, banned patterns |
| `pipeline/lyra/prompts/v2_paper_assessment.txt` | Add narrator block, few-shot example, banned patterns, stance instruction |

No code changes. Pure prompt engineering.

## Verification

1. Run the Shining Ones test prompt (or wait for the citation blockchain test to complete)
2. Check: Does the paper use direct documentary voice (no hedging, no passive)?
3. Check: Are any banned phrases present? (grep for "it should be noted", "further research", etc.)
4. Check: Does the hook open with a specific date/person/event, not "Throughout history"?
5. Check: Does the assessment lead with supporting evidence, not debunking?
6. Check: Does "Connecting the Dots" state facts, not describe process?
