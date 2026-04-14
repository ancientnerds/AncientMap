# The Why Files Playbook — Theo Research Paper Restructure

## Context

Theo research papers read like academic liability disclaimers — every paragraph hedges with "no peer-reviewed evidence," "mainstream archaeologists disagree," and "caution is warranted." This kills readability, especially for a platform that supports investigating fringe and alternative archaeology topics.

The Why Files YouTube channel solves this exact problem: it investigates fringe topics with genuine curiosity (70% of the episode), then does an honest reality check at the end (30%). Viewers feel smart, not lectured. We're adopting this structure for Theo research papers.

## Paper Structure (Three Acts)

**Before:**
```
Title → Abstract → Introduction → Body → Discussion → Conclusion → Methodology → References
```

**After:**
```
Title → Abstract → Introduction → Body → Source Assessment → Conclusion → Methodology → References
```

- **Discussion is merged into Source Assessment** — one section that both synthesizes findings and honestly evaluates evidence quality
- **Body sections are purely investigative** — no hedging, no disclaimers, no "mainstream rejects this"
- **Source Assessment is the "reality check"** — written as narrative prose ("So what do we actually know?"), with access to real source tier data

### Section Purposes

| Section | Purpose | Voice |
|---------|---------|-------|
| Abstract | The hook — what mystery did we investigate, what did we find? | Compelling, direct |
| Introduction | Why this question is fascinating, what it would change | Draw the reader in |
| Body sections | THE INVESTIGATION — evidence, connections, discoveries | Documentary narrator |
| Source Assessment | THE REALITY CHECK — synthesize + rate the evidence honestly | "What do we know vs. think?" |
| Conclusion | Forward momentum — what should be explored next | Curious, forward-looking |

### Source Assessment Details

- Written by a dedicated pipeline stage (Stage 8.5) with access to the source registry
- Input: paper body + full source list with reliability tiers (Academic/Reputable/General)
- Output: narrative prose, 1 paragraph (brief/note), 2-4 paragraphs (article+)
- Naturally connects pattern synthesis with evidence evaluation
- Uses conversational tone: "The peer-reviewed geophysical surveys confirm X. That's solid. Where it gets murkier is..."

### Tier Scaling

| Tier | Body | Source Assessment |
|------|------|-------------------|
| Brief | 2-3 paragraphs | 1 paragraph |
| Note | 3-4 sections | 1-2 paragraphs |
| Article | 4-5 sections | 2-3 paragraphs |
| Review | 5-6 sections | 3-4 paragraphs |
| Thesis | 5-6 sections + debate appendix | 3-4 paragraphs |
| Dissertation | 5-6 deep sections + debate appendix | 3-4 paragraphs + source breakdown |

## Upstream Pipeline Changes

The investigation body is only as good as the specialist findings it's built from. If specialists produce cautious, hedged findings, the paper writer inherits that language.

### Specialist Analysis (`theo_specialist_analysis.txt`)
- Reframe from "evaluate claims against evidence" to "what does the evidence reveal?"
- Confidence levels stay (high/medium/low) — useful data
- Findings written as discoveries, not caveats

### Debate Stage (`theo_debate_challenge.txt`, `theo_debate_defense.txt`)
- Reframe from adversarial ("attack weak claims") to investigative ("explore competing hypotheses")
- Challenger: "What else could explain this?" instead of "This is wrong because..."
- Defender: "Why this interpretation fits best" instead of just surviving criticism
- "Qualify" response becomes "refine" — add nuance without defensiveness

### Moderator (`theo_moderator.txt`)
- Attribution check stays strict (drop fabricated claims)
- Revised claims reframed as "refined interpretations" not "weakened claims"
- Output language: "refined through debate" not "qualified with caveats"

### Devil's Advocate (`theo_devils_advocate.txt`)
- Reframe from "find problems" to "what alternative explanations exist?"
- Severity levels stay (critical for fabrication)
- Framing: "unexplored angles" not "weaknesses"

## Quality Judge Changes

D5 (currently "Hedging") becomes **"Evidence Honesty"**:
- Does the Source Assessment section honestly differentiate documented findings from speculation?
- Does the body avoid hedging language? (yes = good, body should be investigative)
- Papers are rewarded for being investigative in the body AND honest in Source Assessment

Critical gates unchanged: attribution accuracy + source fidelity still block publication.

## Files Changed (13 total)

### Prompts (12 files)
| File | Change |
|------|--------|
| `theo_paper_section.txt` | Reinforce investigative tone |
| `theo_paper_frame.txt` | Remove Discussion, produce Abstract + Intro + Conclusion + Methodology |
| `theo_paper_full.txt` | Same restructure for single-shot |
| `theo_paper_brief.txt` | Drop hedging mandate, add mini Source Assessment |
| `theo_paper_outline.txt` | Frame sections as investigation chapters |
| `theo_source_assessment.txt` | **NEW** — the reality check prompt |
| `theo_specialist_analysis.txt` | Discovery-oriented findings |
| `theo_debate_challenge.txt` | "Explore alternatives" framing |
| `theo_debate_defense.txt` | "Refine" instead of "qualify" |
| `theo_moderator.txt` | Refined interpretations |
| `theo_devils_advocate.txt` | "What else could explain this?" |
| `theo_quality_judge.txt` | D5 → Evidence Honesty |

### Pipeline code (1 file)
| File | Change |
|------|--------|
| `theo_pipeline.py` | New Stage 8.5 (Source Assessment), assembly order: body → Source Assessment → Conclusion |

## Verification

1. Run a brief-tier paper locally — check Source Assessment appears, body has no hedging
2. Run an article-tier paper on prod — check full three-act structure, narrative Source Assessment
3. Compare with previous papers — body should read more engagingly
4. Quality judge should still pass (attribution + fidelity gates unchanged)
5. Specialist findings should read as discoveries, not caveats
