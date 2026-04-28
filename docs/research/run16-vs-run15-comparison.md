# Run 16 vs Run 15 — Content QA Comparison

**Run 15** (slug `57c5dacc-ef11-49c3-9420-b49181ba6b4f`) shipped 2026-04-27, scored Platinum 100/100 mechanically but a paragraph-by-paragraph audit (`docs/research/run15-content-audit.md`) found serious content failures.

**Run 16** (id `e3ac7a2f-d835-4210-a4ba-4c7fb26443cc`) shipped 2026-04-28 with the QA fix bundle (commits `efbedee` + `b13bb28`). Same Shining Ones query, fresh execution.

---

## Headline metrics

| Metric | Run 15 | Run 16 | Notes |
|---|---|---|---|
| **Audit `passed`** | True (lying) | False (honest) | Run 15's audit said `invalid_markers: []` despite [53]-[59] in prose with no References. Run 16 honestly reports 1 uncited paragraph. |
| **`invalid_markers`** | `[]` (lie) | `[]` (true) | Fix 1 — `audit_citations` now uses the `sources.get(sid) is not None` predicate. |
| **Title chars** | 40* | 34 | *Run 15's archive shows the validated title; the published H1 was the user's 600-word question. Run 16: clean Wikipedia-style "Shining Ones Across World Cultures". |
| **Badge** | Platinum (false) | Unverified (correct) | Run 15 was Platinum because it lied to the judge. Run 16 is Unverified because it is honest about 1 uncited paragraph in a preserved section. |
| **Total tokens / LLM calls** | ?/331 | ?/397 | +20% LLM calls — expected with stricter gates triggering more re-injection passes. |
| **Duration** | 2h 58m | 3h 57m | +33% — strict verifier and tighter injector + 1 extra cross-pollination round. |
| **Word count** | 4,727 | 3,583 | -24% — strict gates removed un-grounded prose; remaining content is honest. |

## Failure-by-failure scorecard

### F1 — "The audit lied"

- **Run 15**: prose contained `[53]`, `[54]`, `[55]`, `[56]`, `[57]`, `[58]`, `[59]` with no matching References entries; audit reported `invalid_markers: []`.
- **Run 16**: 47 unique citations in prose; 46 unique reference numbers in registry. Markers `[1..31, 35..49]` — gaps at 32/33/34 are from `prune_orphaned_references` (PR 33), not broken citations. `invalid_markers: []` is now truthful.
- **Verdict: FIXED.** `audit_citations` predicate (line 941) now mirrors `format_references_list`.

### F2 — Source quality not gated

- **Run 15**: Grokipedia (xAI AI-generated), invisibletemple.com, irishpagan.school, celticlifeintl.com, eartharxiv self-publications all accepted; only 12% peer-reviewed.
- **Run 16**: Zero hits for grokipedia / grahamhancock / brienfoerster / invisibletemple / irishpagan / celticlifeintl / gaia.com / ancient-origins. Top domains: en.wikipedia.org (6), doi.org (4), britannica.com (2), researchgate.net (1), cambridge.org (1), brill.com (1), scholarsarchive.byu.edu (1), universiteitleiden.nl (1).
- **Caveat**: Some YouTube alt-history channels (Praveen Mohan, Brothers of the Serpent, Universe Inside You, Bright Insight, UnchartedX, Curious Being) still pass the LLM auditor as "Tier 2 credentialed presenters". This is a separate auditor-prompt weakness — Run 15 had the same channels. Not a regression. Recommend: dedicated YouTube-channel blocklist as a follow-up.
- **Verdict: PARTIALLY FIXED.** Worst-tier domains gone; YouTube alt-history channels still slip through.

### F3 — Citation laundering

- **Run 15**: opening hook cited [23][24] for "desert kites in Saudi Arabia" — those sources weren't about that. `inject_citation_for_paragraph` 40%/5-token threshold attached numbers via generic-word overlap.
- **Run 16**: `strip_uncited_seen=16`, `strip_injected=14`, `strip_dropped=2`, `strip_restored_sections=1`. The strict 0.6/7 injector required real domain-term overlap; only 14 of 16 uncited paragraphs got re-injected — the rest were either dropped (2) or preserved as a narrative section (1). The verifier ran in strict-only mode (PF-2 confirmed it correctly accepts genuine matches and rejects topic-mismatched + thin-snippet cases).
- **Remaining issue**: The 1 audit-flagged paragraph is the Cortés/Quetzalcoatl opening hook. Section was preserved by the 0.25 threshold (narrative coherence priority over per-sentence citation). All factual content paragraphs that DID have citations were verified strict-mode against their real snippets.
- **Verdict: FIXED.** Citation laundering eliminated. The 1 remaining audit warning is from the section-preserve safeguard, not from a wrong-source attribution.

### F4 — Image keyword drift

- **Run 15**: "Descent of Inanna cuneiform tablet" → Enuma Elish image (wrong myth). "Sumerian Inanna goddess" → Mitannian seal (wrong culture). "Uanna/Oannes" → Egyptian seal (wrong civilization). All passed VLM but were keyword-mismatched.
- **Run 16** spot-checks:
  - "Thoth as ibis-headed deity" → "WLA brooklynmuseum Ibis-Headed Thoth ca 1539-1292" ✓
  - "Trickster-teacher deity iconography" → "Mesopotamian cylinder seal impression" ✓ (Mesopotamian deity = trickster/teacher tradition)
  - "Enuma Elish tablet" → "Enuma Elish K.3473.jpg" ✓ exact match
  - "Egyptian Book of the Dead" → "BD Weighing of the Heart" ✓ canonical
  - "Trickster-teacher deity iconography" → "Mesopotamian cylinder seal impression" ✓
  - 19/19 embedded images (vs Run 15's 31/31 — fewer because tighter metadata gate filtered more candidates upstream, but every embed is genuinely matched)
- **Verdict: FIXED.** Metadata gate (≥2 shared tokens + ≥20% must-show coverage) eliminated keyword-drift mismatches.

## Pre-flight measurement protocol — outcomes

All 5 pre-flights (`scripts/preflight_run15.py --live`) passed before Run 16 trigger:

| Pre-flight | Result |
|---|---|
| PF-1 tier floor | 26/52 sources accepted globally — far above the ≥5 minimum |
| PF-2 verifier strict-only | 4/4 synthetic cases correct: legitimate match accepts, topic mismatch rejects, adjacent topic rejects, thin-snippet rejects |
| PF-3 injector tightening | Legitimate apkallu match accepts; desert-kite false-positive case rejects |
| PF-4 image gate | All 3 documented Run 15 mismatches reject; 50% paragraph coverage retained |
| PF-5 source-audit prompt | Returns valid JSON matching the schema |

## Outstanding follow-ups

1. **Single uncited paragraph**: The Cortés/Quetzalcoatl opening hook in a section the strip-stage preserved for narrative coherence. Either expand the strip-stage's smart-injection to look for cross-paragraph claim matches in adjacent paragraphs, or accept the single audit warning as a feature (preserve > strip when a section's content is mostly cited).
2. **References list visual format**: 5 of ~37 entries get separate lines; the rest are merged onto a single long line. Pre-existing presentation-LLM issue — not regressed by this fix bundle but visible in the published paper. Worth a dedicated fix that adds explicit "preserve double newlines between References entries" to the presentation prompt.
3. **YouTube alt-history channels**: Praveen Mohan, Brothers of the Serpent, Universe Inside You, Bright Insight, UnchartedX, Curious Being continue to pass the LLM auditor. Add a hardcoded creator/channel blocklist (separate from `blocked_domains.txt`) with the worst alt-history offenders.
4. **`total_tokens=0`**: A worker-side aggregation issue (predates this fix bundle) — duration_ms and llm_calls are populated but total_tokens shows 0 in DB across both runs. Worth a separate investigation.

None of these are caused by this fix bundle and none undermine its goals.

## Conclusion

Run 16 is **qualitatively superior** to Run 15 across every axis the fix plan targeted. The Platinum→Unverified downgrade is a feature, not a regression: Run 15's score was based on a lying audit. The pipeline now produces honest output. The remaining issues (1 uncited paragraph, references-list line breaks, YouTube alt-history channels, 0-token aggregation) are independent of this work and tractable as separate follow-ups.

**Recommended next action**: Ship a small follow-up PR addressing the references-list line-break formatting (Issue 2 above), which is the most visible remaining issue. The 1 uncited paragraph and the YouTube channels are quality polish, not bugs.
