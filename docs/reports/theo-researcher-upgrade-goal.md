# Goal: upgrade the Theo paper researcher so papers stop needing a correction pass

Paste the block below as the goal of a new session.

---

## GOAL

Upgrade the Theo paper researcher so the papers it generates are right the first
time, and do not need the 31-paper audit/correction pass we just ran. Work
autonomously with an agent fleet. Ask me all open questions now, not later — I go afk
after reading this.

## READ FIRST — the report is the whole input

`docs/reports/theo-paper-defects-2026-10-04.md` (commit `4135add`). It is the measured
defect catalogue from auditing all 31 live papers. Read it completely before you
design anything. Every number in it is measured; do not re-derive them, and do not
write any new number from memory — if the paper set changes, re-run
`C:\tmp\papers\aggregate_findings.py` and `C:\tmp\papers\citation_coverage.py`.

The diagnosis that shapes the whole job:

> Of 2 105 findings over 31 papers, only **602 (28.6 %)** were supported as written.
> The largest correctable class is not fabrication — it is **384 `misattributed`**:
> the sentence is true-sounding but its marker points at a source that does not carry
> it. 253 of the 1 288 fixes were a pure reattribution, where the sentence never needed
> rewriting. An upgrade aimed at "stop hallucinating" targets the wrong thing.

## WHAT TO BUILD

Work the report's eight rules, in its order — it ranks them by how many findings each
one retires:

1. **A marker requires a located sentence.** The supporting sentence must be found in
   the fetched text before `[n]` is written. Not found → do not cite; downgrade,
   re-source, or drop the claim. (retires 561)
2. **Never sharpen a source.** Carry the hedge, the unit, the epoch, the uncertainty
   across. A quotation must be contiguous in the source — splicing two sentences is
   not a quotation. (retires 858)
3. **Entity keys are `(name, site code, author, year)`.** No merge without all four
   agreeing. Never infer a site code or accession number.
4. **Identifiers are copied, never recalled.** Date, DOI, PMID, ISBN, site code. If the
   identifier is not in front of you, search by title. An assertion that a work was
   retracted requires a Crossref / OpenAlex / Europe PMC check.
5. **Every sentence ends on a terminator**, and no sentence ends on a preposition, a
   conjunction or a definite article. This is mechanically checkable — **put it in the
   gate**, do not leave it to a reviewer.
6. **An image may only be cited if the picture was opened.** The alt-text QA flag
   `![gallery:<hash>|verified:yes|no|…]` must mean what it says: `verified:no` means
   nobody has looked, and never ships.
7. **Writes are idempotent per input hash.** No boolean "already sent" flags — that
   bug put 42 byte-identical correction entries on 22 live papers.
8. **`probative_images` needs a patch path**, so changing a picture never means
   republishing a public paper's entire text.

## AND CLOSE THE GATE GAPS

The report's third section is the part that makes this stick. The production gate
already checks marker syntax, list/prose agreement, the tier tag, whether an image
path is a real file, and recomputes the LLM verdict — **and all 31 papers passed every
one of those.** So nothing today stops a wrong citation, a sharpened claim, a spliced
quotation, a sentence cut mid-clause, or a picture that does not match its caption.

Extend `pipeline/lyra/theo_citations.validate_paper_artifact`,
`pipeline/lyra/theo_publishing.check_quality` and `check_images` so the checks that
*can* be mechanical, are mechanical — at minimum rule 5 (sentence endings), a
duplicate-correction-entry check, and a reference-line/claim consistency check. Add a
test for each new rule that fails on a real example from the report.

For the judgement calls (does this source really say this?), do not pretend a regex
can decide it. Make the *research stage* emit a per-claim located quote with its
reference, so the judgement is auditable afterwards instead of being re-made blind.

## DECIDIONS ALREADY MADE — do not re-litigate

- **Citations are paragraph-level.** 1136/1136 reference entries are cited, 0/853 prose
  paragraphs carry no marker. The owner accepts this; the sentence-level upgrade
  (currently 530/4261 = 12.4 %) was explicitly declined. Do not propose more markers.
- **Images change through a new patch path for `probative_images` plus a deploy**, not
  through full republications of public papers. `correct_paper` does not write that
  field today, which is why this needs code.

## OUT OF SCOPE

- Do not restyle, rewrite or republish the 31 existing papers. They are corrected and
  live. This goal changes the *generator* and the *gate*.
- The image retrofit of the 31 papers (remove wrong pictures, 1–4 per paragraph) is a
  **separate session**. It has its own inventory in `C:\tmp\papers\<id>\image_audit.md`
  (4 of 31 done) and the brief in `C:\tmp\papers\IMAGE_BRIEF.md`. Only build the
  patch path they will need.
- No push to `main` without asking me. A push to main is a live deploy. Work on a
  branch, commit with the trailer
  `Co-Authored-By: MiniMax-M3.1-Flash-Preview (MiniMax Code)`.

## DONE WHEN

- Each of the eight rules is either enforced in code (with a failing test taken from
  the report) or explicitly declined by me with a reason.
- Every mechanical rule is inside the gate, not in a prompt, and the local gate suite
  and the frontend checks are green.
- I can read, for any single new paper the researcher produces, which source supports
  which sentence — and the answer is checkable without re-doing the research.
