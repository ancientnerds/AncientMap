# The eight rules, in code — what each one is enforced by

The answer to `theo-paper-defects-2026-10-04.md` (commit `4135add`). That report is
the input; every number below is quoted from it, none is re-derived.

Every rule of its section "Concrete rules for the upgraded researcher" is now
enforced in code and covered by a test that fails on a real finding from the
report, or is declined here with the reason. Nothing is left in a prompt.

## Where the gate runs

| Gate | Runs | Decides |
| --- | --- | --- |
| `support` (`studio/paper/gates.py:gate_support`) | `paper check` | rules 1–5, against the archived source texts of the paper's own references |
| `picture` (`studio/paper/gates.py:gate_picture`) | `paper check` | rule 6, entry and report shape |
| `pictures` (`lyra/theo_publishing.py:check_pictures`) | every publish, correction and image patch | rule 6 against the *served* copy, on the stored text |

`paper bundle` refuses a workspace whose `check_report.json` is not passing, and
`theo_publish` re-runs the server-side gates on exactly the `result_json` it is
about to store. So a paper cannot reach `research_requests` without having passed
both.

## The rules

| # | Rule | Class | Enforced by | Failing test, on a real finding |
| --- | --- | --- | --- | --- |
| 1 | A marker requires a located sentence | A, D (561) | `lyra/claim_support.py:locate_support` + `lyra/paper_claim_gate.py:check_paragraph_markers` (`located_sentence`, `unreadable_marker`) | `test_paper_claim_gate.py::test_the_squatter_man_area_of_150_against_a_source_that_says_over_50`, `::test_stargate_session_yields_a_located_sentence_naming_the_values_it_lacks`, `::test_a_marker_on_a_reference_with_no_text_is_unreadable_not_unsupported` (baalbek, class D) |
| 2 | Never sharpen a source; a quotation is contiguous | B (858) | `claim_support.numbers_absent_from`, `claim_site_codes`, `claim_identifiers` + `paper_claim_gate` (`unsupported_specific`, `site_code`, `identifier`, `retraction`, `located_sentence` on a de-hyphenated quote) | `::test_the_squatter_man_area_of_150_against_a_source_that_says_over_50` (150 km² against "over 50"), `::test_a_year_in_the_prose_that_its_source_does_not_carry_reports_the_year` (ufos 1997 vs 1998), `::test_a_quotation_the_source_does_not_hold_verbatim_is_not_located` (stargate AIR, de-hyphenated) |
| 3 | Entity keys are (name, site code, author, year); never infer a site code | C | `claim_support.claim_site_codes` + `paper_claim_gate` (`site_code`) | `::test_la_11568_in_prose_with_no_source_carrying_it` (mogollon), `::test_the_same_code_on_the_reference_that_carries_it_is_not_an_issue` |
| 4 | Identifiers are copied, never recalled; a retraction needs a check | E | `claim_support.claim_identifiers`, `is_retraction_claim` + `paper_claim_gate` (`identifier`, `retraction`) | `::test_a_doi_in_the_prose_that_no_cited_source_carries`, `::test_a_retraction_claim_whose_located_quote_lacks_the_word`, `::test_a_retraction_the_source_states_is_not_an_issue` |
| 5 | Every sentence ends on a terminator | F | `claim_support.sentence_defects` + `paper_claim_gate.check_sentence_structure` | `::test_each_shipped_structural_defect_is_reported` (parameterised over the shipped cargo-cults seams) |
| 6 | A picture is cited only if it was opened; `verified:no` never ships; an unserved file is a defect | G | `lyra/theo_image_gate.py` + `gates.gate_picture` + `theo_publishing.check_pictures` | `test_theo_image_gate.py::test_alt_with_verified_no_is_exactly_one_unverified_issue`, `::test_real_enuma_elish_reference_is_not_served`, `::test_cargo_cults_ships_eight_credits_for_seven_pictures`; server side `test_theo_publishing_gates.py::test_a_verified_no_marker_never_ships`, `::test_a_picture_the_site_cannot_serve_fails` |
| 7 | Writes are idempotent per input hash | H.1 | `theo_publishing._already_applied`, read from `theo_paper_publications` | `test_theo_publishing_idempotence.py::test_the_same_correction_sent_twice_appends_its_entry_once` (the real 2026-10-04 audit note that landed 42 times), `::test_the_cli_sends_the_same_bytes_twice_and_writes_once` |
| 8 | `probative_images` needs a patch path | H.2 | `theo_publishing.patch_images` + migration `0028` + `paper patch-images` | `test_theo_publishing_patch_images.py::test_a_patch_replaces_the_image_block_and_nothing_else`, `::test_the_halley_picture_is_replaced_by_the_block_the_studio_wrote` |

## What the audit is supposed to read afterwards

`pipeline/studio/paper/evidence_card.py` builds `result["sentence_evidence"]` at
bundle time: per cited sentence, the reference numbers of its paragraph and, for
each of them, the quote `claim_support.locate_support` found in that reference's
fetched text, with the character span in that text. It is stored in
`result_json`, so the owner can read which source supports which sentence without
re-running the research.

The markers stay paragraph-level and the rendered report is byte-identical with
and without the key (`test_evidence_card.py::test_building_the_card_leaves_the_report_byte_identical`,
`test_paper_publish.py::test_the_bundle_carries_the_sentence_evidence_card_without_touching_the_report`).
The public API never reads the key: `PAPER_EXTRAS_COLUMNS` selects the columns it
returns.

## Two decisions that are not the gate's to make, and where they are written

1. **A sentence with no verifiable content is undecidable for rule 1, not failed.**
   A sentence with no number, date, person, title, measurement, quotation,
   institution, site code or identifier asserts nothing a fetched text could carry
   or fail to carry, so there is no support question to decide. Reporting it would
   be a citation defect where the truth is padding. Padding is the word count's and
   the writer's business. `paper_claim_gate._verifiable_content`, tested by
   `::test_a_sentence_with_no_verifiable_content_is_not_a_citation_failure` and
   `::test_one_number_the_source_lacks_makes_the_same_shape_a_finding`. Rule 2
   still applies to padding: a reference nobody fetched may not carry a marker at
   all.

2. **A marker is asked to carry its own sentence, not its whole paragraph.** The
   report's rule 1 names a *sentence*. With a paragraph-sized question, a
   paragraph that states one claim from `[1]` and another from `[2]` holds neither
   marker, because each is asked to carry the other one's specifics — and the
   studio brief explicitly allows one or two sentences per marker group. The
   marker itself stays where it is; only the question changed.
   `paper_claim_gate._carrying_sentence`. Consequence for the writer, now in
   `brief_template.md`: one marker per claim, and two claims from two sources go
   in two sentences.

## Declined, with the reason

- **Sentence-level markers.** The report measured 1136 of 1136 reference entries
  cited, 0 of 853 prose paragraphs without a marker, and 530 of 4261 sentences
  (12.4 %) carrying their own marker; the sentence-level upgrade was declined by
  the owner. The sentence appears here only as the unit the gate reasons about and
  as the unit the audit card is written in; no marker was added anywhere.
- **`number_exact` never fires on a sharpened figure.** `locate_support` accepts a
  window only when it carries every number, date and measurement of the claim, so
  a sharpened number does not locate at all and rule 1 reports it first, naming
  the value. The rule stays wired and its own test pins the subsumption:
  `::test_a_sharpened_number_never_reaches_number_exact_and_that_is_the_contract`.
- **The orphan-reference defect is already the artifact gate's** (`orphaned_refs`),
  so the claim gate does not restate it:
  `::test_the_orphan_reference_defect_is_already_the_artifact_gates`.

## What this does not do

The 31 published papers are untouched: they are corrected and live, and this
branch changes no stored text. The image retrofit of those papers is a separate
session and needs only `paper patch-images` (rule 8), which this branch adds.
Migration `0028` must be applied by a deploy before `patch_images` is writable —
the journal's action vocabulary is a `CHECK` constraint.
