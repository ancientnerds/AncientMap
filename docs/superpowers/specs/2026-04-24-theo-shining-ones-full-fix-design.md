# Theo Shining Ones — Full Fix Design

*Brainstormed 2026-04-24. Single umbrella spec for 6 remaining pipeline fixes + the already-published paper.*

## Problem

The published Theo paper at `/research/the-shining-ones-sky-gods-ancient-astronauts-and-human-genius` has 30 catalogued flaws. They trace to nine pipeline root causes, three of which are already shipped as Day-1 fixes (publish gate, non-numeric marker guard, card-from-conclusion). This spec covers the six remaining pipeline fixes plus the Shining Ones regeneration.

The published paper itself stays live through the sprint. At the end, we regenerate it from the original question through the fully-fixed pipeline and swap the new content into the existing slug.

## Goals

A Shining Ones regeneration must:

1. Contain no fabricated names, books, dates, or measurements.
2. Define "Shining Ones" (the title concept) in the body.
3. Address Watchers/Enoch, Giza pyramids, and the user's explicit quantum-manipulation sub-question, not just whatever the LLM surfaced.
4. Have ≤5% uncited factual paragraphs (the first run had 88/125).
5. Have a reference list with no version-padded duplicates and no multi-URL entries.
6. Have no paragraph with duplicate-subject images; multi-image paragraphs render as a carousel.
7. Have no internal contradictions across sections.
8. Pass every judge + audit gate without `?override=1`.
9. Have a card description that matches the conclusion, not the opener.

All 9 criteria must hold for the regen to replace the live paper.

## Non-goals

- Rewriting the V2 decomposition's pro-hypothesis bias. Users asking "what if aliens" still get a paper that investigates the hypothesis; we add canonical coverage around it.
- Switching prose generator model (MiniMax M2.7 → Anthropic).
- Re-auditing other already-published papers. Will run on demand once the new audit ships.
- Improving Why Files voice beyond what the claim-pack integrity repair pass achieves mechanically.

## Architecture overview

Six fixes, three new pipeline modules, one new frontend component, three new prompt files.

### New pipeline modules

| Module | Purpose | Called from |
|---|---|---|
| `pipeline/lyra/hallucination_gate.py` | Extract specifics from prose; verify against claim pack; auto-repair loop | `handlers/paper.py` per-section + per-hook |
| `pipeline/lyra/coherence_pass.py` | Post-assembly LLM pass for contradictions + title-term definitions; repair loop | `handlers/paper.py` between assembly and audit |
| `pipeline/lyra/canonical_coverage.py` | LLM-driven per-question canonical-subtopic extraction and gap detection | `handlers/decomposition.py` after Phase A |

### New prompts

- `prompts/hallucination_repair.txt` — repair instruction for the writer when specifics don't trace to the pack
- `prompts/coherence_pass.txt` — post-assembly consistency + title-terms check
- `prompts/canonical_coverage.txt` — "given this question, what are the canonical subtopics any serious paper must cover?"

### New frontend component

- `ancient-nerds-map/src/components/theo/TheoCarousel.tsx` — keyboard- and screen-reader-accessible carousel for multi-image paragraphs, replacing the stacked-mosaic rendering when a `gallery:<id>|` marker is present.

### Modified (touched, not rewritten)

- `theo_citations.py` — URL canonicalization + reference splitting
- `handlers/paper.py` — claim-pack collection rewrite + hallucination gate wiring + coherence pass wiring
- `handlers/decomposition.py` — canonical-coverage injection + user-sub-question extraction
- `handlers/probative_images.py` — subject-level dedup + gallery marker emission
- `handlers/judge.py` — new metrics from gates + badge polish
- `image_gates.py` — VLM prompt tightening
- `prompts/v2_paper_hook.txt`, `v2_paper_section.txt`, `v2_decomposition.txt`
- `components/theo/galleryParser.ts`, `TheoPaperBody.tsx`
- `scripts/apply_meaningful_gallery.py` — gallery marker emission on offline path

### Rollout

Long-lived branch `theo-fullfix` off `main`. No partial merges. All six fixes plus the Shining Ones regen land in one atomic merge after the full end-to-end verification passes.

---

## Fix 1 — Writer claim-pack integrity

### Problem

The Shining Ones paper shipped with 88 of 125 factual paragraphs uncited. The writer is passed claims, some of which have empty `citations` fields, and the writer either invents `[N]` markers or omits them.

### Root cause

`_collect_claims_for_angles` in `pipeline/lyra/handlers/paper.py:1014-1063` falls through to a bare-claim branch (`"citations": ""`) when a finding doesn't match in `claim_lookup`. `_format_claims_for_prompt` then formats these for the writer without markers. The writer's prompt tells it to cite, but there's nothing on the pack to cite.

### Design

**1. `_collect_claims_for_angles` rewrite.** When a finding misses `claim_lookup`:

- If `finding.source_ids` is non-empty, synthesize `citations` by looking up each source_id in `self.state.registry.reference_numbers`. Pass the finding to the writer with real markers.
- If `source_ids` is empty, **drop the finding**. Do not pass bare-citation claims to the writer.

**2. `_format_claims_for_prompt` hardening.** Assert `citations` is non-empty; skip any that aren't. Zero-tolerance: a claim without markers never reaches the LLM.

**3. Writer prompt addition.** `prompts/v2_paper_section.txt` CITATIONS block gains:

> "If a sentence in your draft cannot carry an `[N]` marker from the claims pack, delete the sentence. Do not write about anything not in the pack."

**4. Per-section repair pass.** After each `_write_investigation_section()`, count uncited paragraphs via a simplified regex. If the ratio exceeds 20%, re-send to writer with:

> "Your previous draft had N uncited paragraphs out of M. Rewrite so every factual paragraph carries an `[N]` marker from the claim pack. Delete anything you cannot cite."

One retry; then accept whatever comes out and let the audit flag it.

### Integration points

- `handlers/paper.py:_collect_claims_for_angles`, `_format_claims_for_prompt`, `_write_investigation_section`
- `prompts/v2_paper_section.txt` CITATIONS block

### Tests

`tests/pipeline/test_paper_claim_pack.py`:

- `_collect_claims_for_angles` drops findings with empty source_ids.
- `_collect_claims_for_angles` synthesizes citations from source_ids when registry has them.
- `_format_claims_for_prompt` skips any claim with empty citations.
- End-to-end: pass claims with a mix of empty/non-empty citations; assert the formatted prompt has 0 empty-citation claims.

---

## Fix 2 — URL-normalized reference dedup

### Problem

References `[16]` through `[20]` in the Shining Ones paper are all `preprints.org/.../v5` through `/v9` — the same paper at five different version stamps, each registered as its own source. Reference `[13]` packs three URLs into one entry. Reference `[26]` links a ResearchGate profile, not a paper.

### Root cause

`register_source` in `pipeline/lyra/theo_citations.py:66-96` keys source_id by `sha256(url)[:12]`. Different version URLs hash differently; multi-source entries come from post-hoc formatter behaviour.

### Design

**1. `_normalize_url(url: str) -> str` helper.** New top-level function in `theo_citations.py`:

- Lowercase scheme + host; strip `www.`.
- Strip `?utm_*`, `?ref=*`, `?fbclid=*`, `#fragment`.
- `preprints.org`: strip trailing `/vN` or `/v/N` path segment.
- `arxiv.org`: strip trailing `vN` on the abs path.
- `biorxiv.org`, `medrxiv.org`: strip version path segment.
- `researchgate.net/profile/{user}/publication/{id}/...` → collapse to `researchgate.net/publication/{id}`.
- `doi.org`: preserve exactly (already canonical).

**2. `register_source` change.** Derive `source_id = sha256(_normalize_url(url))[:12]`. Preserve the original `url` on `CitedSource` for display; dedup keys on the canonical form.

**3. Reference splitter.** `format_references_list` currently emits multi-URL entries. Walk each line; if it aggregates multiple canonical sources, split them into sequential entries.

**4. Backfill.** No migration on existing rows. New runs only.

### Integration points

- `pipeline/lyra/theo_citations.py` — `_normalize_url`, `register_source`, `CitedSource`, `format_references_list`.

### Tests

Extend `tests/pipeline/test_theo_citations.py`:

- `_normalize_url` table: preprints.org/arxiv/biorxiv/researchgate/doi cases.
- `register_source` idempotency: registering `v5` then `v9` of same preprint returns the same source_id.
- `format_references_list`: single line per canonical source.

---

## Fix 3 — Canonical coverage + sub-question routing

### Problem

The Shining Ones paper skipped Watchers/Enoch, Giza pyramids, Dendera, Dogon, and Ezekiel — canonical sub-topics any serious paper on ancient astronaut theory must address. It also dismissed the user's explicit quantum-manipulation sub-question in a single paragraph.

### Root cause

`decomposition.py:decompose()` is LLM-only. The decomposition prompt caps at `max_angles` (6) and explicitly biases toward "building the strongest case for the hypothesis" with only one counter-angle. Compound user questions collapse into the LLM's interpretation, losing specific asks.

### Design

Per user decision: **LLM extracts canonical subtopics on-the-fly, no hand-curated registry.**

**1. New module `pipeline/lyra/canonical_coverage.py`.**

```python
async def find_coverage_gaps(
    question: str,
    proposed_angles: list[ResearchAngle],
    settings,
) -> list[str]:
    """Return subtopic labels that proposed angles do not cover."""
```

Internally:

- First LLM call (prompt `canonical_coverage.txt`): "Given this research question, list the canonical subtopics any serious research paper on this topic must address. Return a JSON array of 5-15 short labels." Cache by question hash.
- Second LLM call: "Given these proposed angles {A} and these canonical subtopics {C}, which subtopics are not covered by any angle? Return a JSON array of subtopic labels." This is just set-difference with semantic matching.

**2. User sub-question extraction.** Regex in `decomposition.py`:

- Split user question into sentences.
- Keep sentences ending with `?` OR containing one of: `"could they"`, `"what if"`, `"is it possible"`, `"can these"`.
- Each becomes its own required angle with `category: "user_subquestion"`.

**3. Inject missing coverage as angles.** After Phase A in `decompose()`:

- Call `find_coverage_gaps`; for each missing subtopic, create an angle with `category: "required_coverage"`, skip the 2-source validation minimum (canonical sub-topics sometimes have sparse web sources but must still be addressed).
- Cap total angles at `max(max_angles, len(proposed) + len(required_coverage) + len(user_subquestions))`. These papers will take longer; accept the cost.

**4. Decomposition prompt update.** `v2_decomposition.txt` line 3-8: keep the "thesis" framing for voice, but change "build the strongest possible case for the hypothesis" to "investigate the hypothesis thoroughly while also ensuring every canonical aspect of the topic is examined." Add instruction to echo the user's explicit sub-questions into angle descriptions.

### Integration points

- New `pipeline/lyra/canonical_coverage.py`
- New `prompts/canonical_coverage.txt`
- `pipeline/lyra/handlers/decomposition.py:decompose`
- `prompts/v2_decomposition.txt`

### Tests

New `tests/pipeline/test_canonical_coverage.py`:

- User sub-question extraction: "Could they have manipulated matter?" → extracted.
- Coverage gap detection: mock LLM returns fixed canonical list; assert `find_coverage_gaps` computes set-difference correctly.
- Integration: full decomposition flow with mocked LLM returns expected number of angles.

---

## Fix 4 — Hallucination gate (largest)

### Problem

The Shining Ones paper opened with "In 2007, acoustic archaeologist David Kisheton placed a frequency analyzer inside the Oracle Room of Hal Saflieni Hypogeum in Malta…" — David Kisheton does not exist. Later prose cites "the 1974 book *Fingerprints of the Fraud?* by archaeologists Donald Grayson and Steven Mellon" — no such book exists. Per user decision: auto-repair up to 2 LLM retries, then delete the sentence.

### Root cause

Writer prompts contain anti-hallucination warnings (`v2_paper_hook.txt:20-23`, `v2_paper_section.txt:36-40`) but there is no output validation. The audit checks citation markers but not content.

### Design

**1. New module `pipeline/lyra/hallucination_gate.py`.**

```python
@dataclass
class Specific:
    kind: Literal["person", "title", "date", "measurement", "quote"]
    text: str
    sentence: str

def extract_specifics(prose: str) -> list[Specific]: ...

def verify_against_pack(
    specifics: list[Specific],
    claim_pack: str,
    sources: dict[str, CitedSource],
    original_question: str,
) -> list[Specific]:
    """Return the subset of specifics not found in any source."""

async def repair_prose(
    prose: str,
    unsupported: list[Specific],
    pack: str,
    max_retries: int = 2,
) -> tuple[str, list[Specific]]:
    """Return (repaired_prose, still_unsupported). After max_retries, delete sentences."""
```

**2. Extraction heuristics.**

- **Persons:** regex `\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b` minus a stop-list of common place names, museum names, etc. Falls back to spacy `PERSON` entities if spacy is installed.
- **Titles:** quoted `"..."` or italicized `*...*` spans, 2-10 words, Title Case Or Sentence case.
- **Dates:** `\b\d{3,4}\s?(?:BCE?|CE?|AD|BC)\b` and `\b(?:19|20)\d{2}\b`.
- **Measurements:** `\d+(?:\.\d+)?\s?(?:hz|khz|kg|tonnes?|tons?|km|meters?|metres?|feet|ft|mm|cm)\b`.
- **Quotes:** `"..."` spans of 5+ words.

**3. Verification.**

For each specific, look case-insensitively for its text in:
- The claim pack (as formatted for the writer).
- Any `CitedSource.snippet` (accessed via the registry).
- The user's original question.

If substring-present in any: supported. Else: unsupported.

Normalize both sides: lowercase, strip honorifics (`Dr.`, `Prof.`, `PhD`), strip leading/trailing punctuation. Allows paraphrases like "Debertolis" to match a pack entry of "Dr. Paolo Debertolis".

**4. Repair loop.**

- Attempt 1: LLM with `hallucination_repair.txt` prompt: "Rewrite these sentences to not rely on the listed specifics. Either generalize or delete. Use only evidence from the provided pack. {list of unsupported specifics with their source sentences}."
- Attempt 2: same instruction with a more forceful preamble.
- After 2 retries: regex-delete sentences containing remaining unsupported specifics. Sentence segmentation: split on `. ` then rejoin non-deleted.

**5. Wiring in `handlers/paper.py`.**

- After `_write_hook()`: run gate on hook prose; replace `self.state.paper_hook` with repaired.
- After each `_write_investigation_section()`: run gate; replace section prose with repaired.
- Track metrics: `hallucination_gate_initial`, `hallucination_gate_final`, `repairs_attempted`.

**6. Judge integration.**

`handlers/judge.py` reads `hallucination_gate_final` from `quality_score.meta`. `passed` requires `hallucination_gate_final == 0`.

**7. Writer prompt hardening.**

`v2_paper_hook.txt:20-23` and `v2_paper_section.txt:36-40` gain an explicit enumeration:

> "Do NOT write any of these without a matching claim in the pack: person names, book titles, specific years, specific measurements, or quoted phrases. If the pack doesn't have it, don't write it. The hallucination gate will catch it and your sentence will be rewritten or deleted."

### Integration points

- New `pipeline/lyra/hallucination_gate.py`
- New `prompts/hallucination_repair.txt`
- `handlers/paper.py` (hook + section wiring)
- `handlers/judge.py` (metric + pass gate)
- `prompts/v2_paper_hook.txt`, `v2_paper_section.txt`

### Tests

New `tests/pipeline/test_hallucination_gate.py`:

- Extraction: regex + stop-list removes common places correctly.
- Verification: "David Kisheton" not in pack → flagged. "Debertolis" in pack → supported even when prose says "Dr. Debertolis".
- Repair: mocked LLM strips offending specific; unchanged prose passes through.
- Sentence deletion: after 2 failed retries, offending sentence is removed; surrounding prose preserved.
- Fixture replay: run against a synthetic prose blob containing Kisheton + Grayson/Mellon and assert both are deleted.

### Risks

- **Over-stripping** on legitimate names the pack paraphrases. Mitigation: honorific-and-case normalization; consider a per-claim `allow_variants: true` flag if false-positives accumulate.
- **Cost:** 2 extra LLM calls per section for repair × 6 sections = up to 12 extra calls per paper. Acceptable on MiniMax rates.

---

## Fix 5 — Image subject dedup + gallery carousel

### Problem

The Shining Ones paper has three near-identical Gilgamesh Flood Tablet photos stacked inline, three Dolmen of Menga photos, a Wounded Healer diagram illustrating a wise-old-man archetype discussion, and a modern Irish pub sign illustrating Oannes. No carousel rendering — images stack as a mosaic.

### Root causes

- `handlers/probative_images.py:466-507` dedupes via `seen_sources` (source-name string). Same subject from three different museum vendors → three different source names → all pass dedup.
- No `gallery:` alt-text marker is ever emitted by the backend. `galleryParser.ts:37-40` already has a `cleanAlt()` that strips such markers, but they never appear.
- Frontend `splitIntoImageSegments` groups only adjacent images into `mosaic`; no carousel variant.
- `image_gates.py:build_vlm_prompt` is permissive on archetype diagrams and decorative modern images.

### Design

**1. Backend subject dedup.**

In `probative_images.py:_process_one_opportunity`:

- Replace `seen_sources` with `seen_subjects`. Fingerprint: `f"{title.lower()[:60]}|{(description or '')[:40].lower()}"`.
- Same subject from different vendors → same fingerprint → only first embedded.
- Add `ctx.placed_subjects: set[str]` alongside `ctx.placed_source_urls`. Cross-opportunity dedup so a subject doesn't appear in two different sections either.

**2. Gallery marker emission.**

When `_process_one_opportunity` embeds more than one image for a paragraph, prefix each alt text with `gallery:<hash>|verified:<yes|no>|` where `<hash>` is `sha1(paragraph_first_100_chars)[:8]`. All images on the same paragraph share the same hash.

Also apply this in `scripts/apply_meaningful_gallery.py:render_block` for the offline gallery path.

**3. Frontend carousel.**

Extend `PaperSegment` in `galleryParser.ts:24-27`:

```ts
export type PaperSegment =
  | { kind: 'text'; content: string }
  | { kind: 'figure'; figure: ImageFigure }
  | { kind: 'mosaic'; figures: ImageFigure[] }
  | { kind: 'carousel'; galleryId: string; figures: ImageFigure[] }
```

`splitIntoImageSegments` detects matching `gallery:<id>|` prefixes (via the existing `cleanAlt` parser) and groups them into `carousel` segments. Images without a gallery marker still group into `mosaic` via the existing adjacency rule (backward compatible).

New component `TheoCarousel.tsx`:

- Left/right arrows; keyboard `←` / `→` navigation.
- Indicator dots for current slide.
- Click to open lightbox.
- Each slide: image + caption + source link.
- `role="region"` with `aria-roledescription="carousel"`; `aria-label` from paragraph context; `aria-live="polite"` on slide change for screen readers.

Update `TheoPaperBody.tsx` to render `carousel` segments via the new component.

**4. VLM prompt tightening.**

`image_gates.py:build_vlm_prompt` adds two rejection criteria:

> - If the image is a generic diagram (Jungian archetypes, alchemical symbols, architectural schematics), it must depict the EXACT subject named in the text. "Wise old man archetype" text + "Wounded Healer archetype" diagram = REJECT.
> - Reject decorative modern reproductions when an original artifact exists. Pub signs, tourist replicas, fan art, and modern illustrations when a period artifact, museum-quality diagram, or archaeological context photo is available = REJECT.

### Integration points

- `pipeline/lyra/handlers/probative_images.py` — subject dedup + gallery marker
- `scripts/apply_meaningful_gallery.py:render_block` — gallery marker
- `pipeline/lyra/image_gates.py:build_vlm_prompt` — archetype + decorative rejection
- `ancient-nerds-map/src/components/theo/galleryParser.ts` — carousel segment kind
- `ancient-nerds-map/src/components/theo/TheoPaperBody.tsx` — carousel render
- New `ancient-nerds-map/src/components/theo/TheoCarousel.tsx`

### Tests

- Extend `tests/pipeline/test_image_diversity.py` — subject fingerprint dedup.
- Extend `tests/pipeline/test_image_gates.py` — VLM rejection for wrong archetype + decorative reproductions.
- Frontend: new jest test for `TheoCarousel` keyboard nav + aria attributes.

---

## Fix 6 — Cross-section coherence pass + title-concept check

### Problem

The Shining Ones paper says geopolymer evidence "lacks consistent supporting evidence" in section 3, then "presents material evidence that some scholars interpret as manufactured stone" in section 6. It oscillates for/against/for on whether mainstream explanations are sufficient. The title "The Shining Ones" appears in the title bar but is never defined or used in the body.

### Root cause

Sections are generated independently from the same claim pack. No post-assembly pass checks cross-section consistency. No check that title concepts are defined.

### Design

**1. New module `pipeline/lyra/coherence_pass.py`.**

```python
async def run_coherence_pass(
    paper_text: str,
    title: str,
    settings,
) -> CoherenceResult:
    """LLM pass returning contradictions, title-term definitions, stance oscillations."""
```

Single LLM call with `prompts/coherence_pass.txt` returning JSON:

```json
{
  "contradictions": [
    {
      "entity": "geopolymer",
      "stance_a": "lacks evidence",
      "section_a": "Megalithic Construction",
      "stance_b": "material evidence",
      "section_b": "What We Actually Know",
      "severity": "high"
    }
  ],
  "title_terms": ["Shining Ones", "Sky Gods"],
  "title_terms_defined_in_body": {
    "Shining Ones": false,
    "Sky Gods": true
  }
}
```

**2. Repair pass.** If any high/medium contradictions or any undefined title terms:

- For each contradiction: send the two section texts + the entity + the two stances to the section writer with "Reconcile these. Pick the stance backed by the stronger evidence in the pack and apply it to both sections. Do not invent new evidence."
- For each undefined title term: prepend a definition paragraph to section 1 with "Define '{term}' in the body before deeper analysis. Use only the evidence pack."
- One repair attempt. Then re-run coherence pass. If still flagged: accept and let audit fail, forcing either override or regen.

**3. Title term extraction.** Split title on `:` and `,`; strip filler words (`a`, `the`, `and`); keep phrases ≥2 words. Check each for body presence (case-insensitive).

**4. Wiring in `handlers/paper.py`.** New step between assembly (Step 8) and final audit (Step 9). Metrics persisted to `quality_score.meta`.

**5. Judge integration.**

`handlers/judge.py` reads `coherence` metrics. `passed` requires `contradictions_final == 0` AND all `title_terms_defined == True`.

### Integration points

- New `pipeline/lyra/coherence_pass.py`
- New `prompts/coherence_pass.txt`
- `handlers/paper.py` — new step
- `handlers/judge.py` — metrics + pass gate

### Tests

New `tests/pipeline/test_coherence_pass.py`:

- Synthetic paper with two sections contradicting on "geopolymer" → flagged.
- Title "The Shining Ones: Sky Gods" + body that doesn't mention "shining ones" → flagged.
- Title all terms defined → `title_terms_defined_in_body` all true.
- Repair loop: mocked writer returns consistent text → contradiction cleared.

### Risks

- **LLM cost:** one extra large-context call per paper (reads full 5-10k word paper). ~$0.05 on MiniMax.
- **Ambiguous stances:** a paper can legitimately present two-sided coverage (counter-arguments in "The Other Side"). Mitigation: prompt includes "If the paper labels contradicting stances as opposing positions (counter-arguments), do not flag as contradiction. Only flag when the same entity gets opposite assessments without framing."

---

## Fix 7 — Badge polish

### Problem

The Shining Ones paper has `badge="Gold"` while `passed=False`. Confusing for users seeing a gold badge on a paper that failed its own gate.

### Design

In `handlers/judge.py` after `passed` is computed: if `passed == False`, downgrade badge to `"Unverified"` regardless of score. One-line change.

### Tests

Extend `tests/pipeline/test_theo_quality.py`: paper with high score but `passed=False` → badge is `Unverified`.

---

## Fix 8 — Shining Ones regeneration and swap

After all pipeline fixes land on the `theo-fullfix` branch:

1. Deploy the branch to staging (or local-prod via Docker). Run the pipeline against the original Shining Ones question text from the DB row.
2. Run the 9-criterion verification (see Verification section below) on the new result.
3. If all pass: write a one-shot script `scripts/swap_theo_payload.py` that takes an old request_id and a new request_id and swaps their `result_json` / `slug` atomically. Run it: old id `edfff317-5240-42d1-9dec-1ad6a5805d9a` ← new id from regen.
4. Soft-delete the new request_id row (or mark as superseded) so the old URL continues to serve.
5. Invalidate any Qdrant indexing for the old row; re-index with the new content.
6. Manual smoke check in browser: live URL serves the regenerated content with working carousel, Shining Ones defined, no `[hex]` tokens.

---

## Verification criteria (the end-to-end test)

The regenerated paper must satisfy all 9 goals:

1. Does not contain the strings "David Kisheton" or "Kisheton".
2. Does not contain "Grayson and Mellon" or "Fingerprints of the Fraud".
3. Does not contain any bracketed token that isn't a numeric citation or markdown link (Day-1 Fix 2 gate).
4. Contains the phrase "Shining Ones" defined in the first 500 words of the body.
5. Has a section or at least 3 paragraphs addressing Watchers/Book of Enoch.
6. Has a section or at least 3 paragraphs addressing Giza pyramid construction.
7. Has a dedicated section or at least 3 paragraphs addressing the user's explicit "quantum manipulation of matter" sub-question.
8. Has ≤5% uncited factual paragraphs (audit metric).
9. Reference list: no two entries share a canonical URL; no multi-URL packed entries.
10. No paragraph has more than one image of the same subject.
11. Frontend renders groups of ≥2 images per paragraph as a carousel (manual browser check).
12. No internal contradictions reported by coherence pass (`contradictions_final == 0`).
13. `result.card_description` matches the paper's conclusion stance.
14. Passes every judge + audit gate without needing `?override=1`.

(14 criteria because 4-7 are the "covers canonical + user question" split.)

---

## Testing strategy

### Unit tests (per-fix)

Listed under each Fix section. Summary:

- `tests/pipeline/test_paper_claim_pack.py` (new) — Fix 1
- `tests/pipeline/test_theo_citations.py` (extend) — Fix 2 + existing non-numeric marker tests
- `tests/pipeline/test_canonical_coverage.py` (new) — Fix 3
- `tests/pipeline/test_hallucination_gate.py` (new) — Fix 4
- `tests/pipeline/test_image_diversity.py` (extend) — Fix 5
- `tests/pipeline/test_image_gates.py` (extend) — Fix 5
- `tests/pipeline/test_coherence_pass.py` (new) — Fix 6
- `tests/pipeline/test_theo_quality.py` (extend) — Fix 7
- Frontend: new jest test for `TheoCarousel` keyboard + aria

### Integration test

`tests/pipeline/test_shining_ones_regen.py` (new):

- Mock adapters with recorded Shining Ones search fixtures so the test is deterministic and offline.
- Run the full pipeline end-to-end against the captured question.
- Assert all 14 verification criteria.
- Runs in CI nightly (not per-commit — too slow).

### Manual verification

After staging deploy: run the live pipeline against the actual question (not fixtures). Spot-check in browser. Swap live only after this passes.

---

## Rollout

Single atomic merge from `theo-fullfix` → `main` after:

1. All unit tests pass.
2. Integration test `test_shining_ones_regen.py` passes.
3. Manual staging regen passes all 14 criteria.
4. Frontend carousel manually verified in browser with NVDA screen reader.

No feature flags. No partial merges. Revert plan: git revert the merge commit; old published paper stays online (never touched).

---

## Accepted limits and open decisions

- **No switching of prose generator.** MiniMax M2.7 stays. Hallucination gate compensates.
- **spacy as optional dep.** If `en_core_web_sm` is installed, hallucination gate uses it for NER. Falls back to regex otherwise. No new hard dependency.
- **Canonical coverage LLM cache.** Coverage queries cached by question hash. Rebuilds don't re-ask the LLM for the same question text.
- **Topic-family registry dropped.** Per user decision, coverage is fully LLM-driven per question.
- **No admin UI for coverage.** If the LLM misses a canonical subtopic systematically, we add it as a manual override in the `canonical_coverage.py` prompt, not as UI.
- **Other already-published papers.** Not re-audited. New audit runs on next publish.

---

## Module dependency map

```
decompose()
  → canonical_coverage.find_coverage_gaps() [new]
    → LLM

_write_hook()
  → hallucination_gate.run() [new]
    → LLM (repair)

_write_investigation_section() (×N)
  → hallucination_gate.run() [new]
    → LLM (repair)

after all sections assembled:
  → coherence_pass.run() [new]
    → LLM (read)
    → (if flags) section writer (repair)
    → LLM (re-read)

theo_citations.register_source()
  → _normalize_url() [new]

probative_images._process_one_opportunity()
  → seen_subjects fingerprinting [modified]
  → emit gallery:<hash>| alt prefix [new]

judge.compute_quality_score()
  → consume hallucination_gate metrics [new]
  → consume coherence_pass metrics [new]
  → badge downgrade when not passed [new]

frontend:
  galleryParser.ts → new carousel segment kind
  TheoPaperBody.tsx → render carousel via TheoCarousel
  TheoCarousel.tsx [new]
```

---

## File manifest

### New files

- `pipeline/lyra/hallucination_gate.py`
- `pipeline/lyra/coherence_pass.py`
- `pipeline/lyra/canonical_coverage.py`
- `pipeline/lyra/prompts/hallucination_repair.txt`
- `pipeline/lyra/prompts/coherence_pass.txt`
- `pipeline/lyra/prompts/canonical_coverage.txt`
- `ancient-nerds-map/src/components/theo/TheoCarousel.tsx`
- `scripts/swap_theo_payload.py`
- `tests/pipeline/test_paper_claim_pack.py`
- `tests/pipeline/test_canonical_coverage.py`
- `tests/pipeline/test_hallucination_gate.py`
- `tests/pipeline/test_coherence_pass.py`
- `tests/pipeline/test_shining_ones_regen.py`
- `ancient-nerds-map/src/components/theo/__tests__/TheoCarousel.test.tsx`

### Modified files

- `pipeline/lyra/theo_citations.py`
- `pipeline/lyra/handlers/paper.py`
- `pipeline/lyra/handlers/decomposition.py`
- `pipeline/lyra/handlers/probative_images.py`
- `pipeline/lyra/handlers/judge.py`
- `pipeline/lyra/image_gates.py`
- `pipeline/lyra/prompts/v2_paper_hook.txt`
- `pipeline/lyra/prompts/v2_paper_section.txt`
- `pipeline/lyra/prompts/v2_decomposition.txt`
- `scripts/apply_meaningful_gallery.py`
- `ancient-nerds-map/src/components/theo/galleryParser.ts`
- `ancient-nerds-map/src/components/theo/TheoPaperBody.tsx`
- `tests/pipeline/test_theo_citations.py`
- `tests/pipeline/test_theo_quality.py`
- `tests/pipeline/test_image_diversity.py`
- `tests/pipeline/test_image_gates.py`

---

## What this guarantees after merge

- No paper publishes with `quality_score.passed=False` or `audit.passed=False` (Day 1 ✅).
- No pipeline debug token leaks into prose (Day 1 ✅).
- Card description reflects the paper's conclusion (Day 1 ✅).
- No fabricated people, books, dates, or measurements in any published paper (Fix 4).
- No paragraph with a factual claim lacks a citation marker (Fix 1).
- Reference list has no version-padded duplicates and no multi-URL entries (Fix 2).
- Every paper covers the canonical subtopics the LLM identifies for its question + every user sub-question gets its own angle (Fix 3).
- No paragraph has duplicate-subject images; multi-image paragraphs render as carousels (Fix 5).
- No internal contradictions across sections; every title term is defined in the body (Fix 6).
- Badge never says "Gold" when the gate failed (Fix 7).

Every flaw in the Shining Ones catalogue is covered.
