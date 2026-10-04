# Theo paper researcher: defects found in the 31 live papers, 04.10.2026

**Purpose.** The 31 research papers published on ancientnerds.com were audited claim
by claim against the sources they cite, repaired, and republished. This document is
the defect catalogue that came out of it, written for the next session, which is going
to upgrade the paper researcher so it produces papers that do not need this pass.

It is not a list of complaints. Each class names the failure, one verified example
with its paper, the count across the campaign, and the concrete rule the researcher
has to satisfy. The last section is the important one: the production gate passes
every one of these papers, so the gaps below are gaps in the gate as much as in the
writer.

**All numbers are measured, not estimated.** Sources: the per-paper `audit.json`,
`resourced.json` and `build_status.json` in `C:\tmp\papers\`, aggregated by
`C:\tmp\papers\aggregate_findings.py`, plus production state read read-only over
psql. Nothing here is written from memory.

## Scope and outcome

| | |
|---|---|
| papers audited | 31 (30 published with the corrected text, `mogollon-pithouse` held back) |
| findings | **2 105** |
| findings that were **supported as written** | **602 = 28.6 %** |
| findings that needed repair | **1 503 = 71.4 %** |
| fixes applied | 1 288 |
| claims deleted by the first pass, later recovered by re-sourcing | 101 |
| claims still deleted, each with a written reason | 176 |
| corrections published | 13 today (journal rows 102–114), plus a full first pass per paper |

### Findings by verdict

| verdict | count | share | what it means |
|---|---|---|---|
| `unsupported` | 858 | 40.8 % | the cited sources do not support the sentence |
| `supported` | 602 | 28.6 % | no repair needed |
| `misattributed` | 384 | 18.2 % | the sentence is true-ish but its marker points at the wrong source |
| `unverifiable_fetch` | 98 | 4.7 % | the reference could not be fetched (403, paywall, dead link) |
| `contradicted` | 84 | 4.0 % | the cited source says something different |
| `unverifiable_source` | 79 | 3.8 % | the source exists but carries nothing the sentence claims |

**The headline: the writer gets roughly one claim in three right on the first pass.**
And the single largest correctable class is not fabrication - it is
`misattributed` at 384. The researcher does not invent facts so much as it **hangs a
true-sounding sentence on a source that does not carry it**. 384 + 84 contradicted =
**468 sentences carried a citation that was wrong about them.**

### Fixes by kind

| kind | count |
|---|---|
| `replace_claim` | 716 |
| `reattribute` | 253 |
| `delete_claim` | 224 |
| `replace_number` | 56 |
| `replace_date` | 24 |
| `relink` | 14 |
| `insert_claim` | 1 |

`reattribute` at 253 is the tell: in one claim out of five the sentence did not need
rewriting at all, only its marker did.

---

## Defect classes

### A. The marker is on the wrong sentence or the wrong source — 384

The sentence survives; the citation does not. This is the cheapest defect to fix and
the most damaging to a reader, because the paper looks researched.

- **`pineal-dmt-in-near-death-and-cross-cultural-mysticism`**: a scale claim sat on
  reference `[11]`; the sentence belonged to `[38]`, the instrument paper, which was
  already cited elsewhere in the same paper.
- **`the-engineering-and-origins-of-the-baalbek-megaliths`**, **26 of 58 findings
  unverifiable**: 14 `unverifiable_fetch` plus 12 `unverifiable_source`, on top of 9
  misattributed. The markers point into a bibliography that was largely never read.
- **`stargate-project-and-sri-remote-viewing-evidence`**: 12 of 32 findings are
  misattributed. The 1519 Cholula episode is in reference `[28]`, not `[12]`.

**Rule for the researcher:** a marker is an assertion that *this specific reference*
carries *this specific sentence*. Before a marker is written, the supporting sentence
must be located in the fetched text. If it cannot be located, the marker does not go
there - the sentence is downgraded, re-sourced, or removed. A paragraph-level marker run
(`[4] [7] [12]` at the end) hides exactly this defect and is not a substitute.

### B. The claim is stronger than its source — 858

The most frequent finding in the campaign. The source says a weaker thing and the
writer sharpened it into a stronger one, usually by dropping the hedge.

- **`stargate`**: `"$20 million"` appears in **no** source in the paper's evidence; an
  "AIR" quotation is not in the cited material.
- **`the-squatter-man-petroglyph-and-auroral-sky-mythology`**: 31 sites across
  **> 50 km²** presented as **150**. The number is not invented - it is inflated, which
  is the same failure with better manners.
- **`panspermia-and-directed-panspermia-in-scientific-and-cultural-context`**: a
  quotation spliced together out of **two** sentences of the source, so it is verbatim
  in no contiguous stretch of the paper it is attributed to.

**Rule for the researcher:** a recovered or generated sentence may never be stronger
than the source that carries it. Hedges ("suggest", "may", "in one study", "estimated")
are part of the finding, not decoration - when a source hedges, the sentence hedges. A
number keeps its unit, its epoch and its uncertainty. **A quotation must be
contiguous in the source**; splicing two sentences is not a quotation.

### C. Entities merged that the sources keep apart — recurring, and never flagged

The writer fuses two real but distinct things into one, and every fact afterwards is
defensible-looking and wrong.

- **`mogollon-pithouse-sites-across-the-upper-gila`**: **Mogollon Village** (LA 11568)
  and the **SU Site** (16 houses) are merged into one site, and a count of "ten" where
  the source says **nine**. 8 of its 46 findings are `contradicted`.
- **`the-watchers-nephilim-tradition-across-ancient-cultures`**: a named
  sea-spirit was attributed to the wrong people - Radcliffe-Brown's *Jurua* is the
  North Andaman group, *Juruwin* the Aka-Bea of the South Andaman, and the paper gave
  one group's spirit to the other.
- **`ancient-astronaut-artifact-claims-and-scholarly-rebuttals`**: a 1974 IISc study's
  actual sentence ("from which its 'recent nature' cannot be asserted") was used to
  support the **opposite** claim.

**Rule for the researcher:** an entity key is `(name, site code, author, year)`. Two
entities merge only when all four agree. Site codes, catalogue numbers and accession
numbers are copied from the source, never inferred, and a site with an accession code
is never described without it.

### D. Sources that cannot be read, cited as if they had been — 177

98 `unverifiable_fetch` (403, paywall, dead link) and 79 `unverifiable_source`. The
writer cites what it *believes* a paper says.

- **`stargate`**: 5 references are dead CIA links.
- **`the-egyptian-hard-stone-precision-debate`**: the full **134-page** Ingalls thesis
  was judged from its abstract, and the thesis itself turned out to analyse the very
  lid the paper discussed - the claim was recoverable, the judgement was not.
- **`the-engineering-and-origins-of-the-baalbek-megaliths`**: 26 of its 58 findings are
  one of the two unverifiable classes.

**Rule for the researcher:** a reference may only carry a claim if the text was
**fetched and the claim located in it**. A reference that could not be fetched may
appear in the list as a bibliographic fact (author, title, year, DOI) but may not
carry a marker. `unverifiable_fetch` must be a first-class outcome of the research
stage, recorded per reference, not discovered months later by an auditor.

### E. Dates, identifiers and the "retraction" class — small count, high damage

- **`stargate`**: the year is **2023**, the paper says 2022. A "retraction" attributed
  to a named author does not exist - refuted through Crossref, OpenAlex and Europe PMC.
- **`pineal-dmt`**: the nirūpaṇa is dated 1577 CE and attributed to a text that is the
  sixth paṭala of a 1577 work - wrong on both counts.

**Rule for the researcher:** every date, DOI, PMID, ISBN and site code is copied from
the fetched record. **Never from memory** - an identifier guessed from memory is the
single most common cause of a dead link, and an agent in this campaign twice wrote a
wrong DOI and had to search by title to recover. An assertion that a work was
retracted or superseded is a claim about the bibliographic record and is checked
against Crossref/OpenAlex/Europe PMC before it is written.

### F. Structural text defects the gate does not see

Every one of these shipped to a live page.

| defect | where | what the reader saw |
|---|---|---|
| sentence cut mid-clause | `cargo-cults` ×2 | `…a pattern of colonial violence that.` and `…attack the people they.` |
| missing terminal full stop after a marker | `phaeton` ×2 | `…from a nearly aligned initial state [52] The evidence resolves…` |
| comma left in front of the full stop | `watchers-nephilim` | `…rather than consensus [11],.` |
| doubled full stop | `reincarnation`, `lost-universal-tongue` | `…roughly 16 months..` |
| prose cites references the list does not contain | `phaeton` | `[50]`–`[55]` in the text, no reference lines at all |
| a sentence with no clause after the marker | `pineal-dmt` | a replacement that swallowed the full stop |

Two of these were introduced **by the repair pass itself**, which is the important
part: a re-sourcing agent that rewrites a sentence must not be able to leave a
fragment.

**Rule for the researcher:** every generated or rewritten sentence must end on a
sentence terminator, and no sentence may end on a preposition, a conjunction or a
definite article. This is checkable mechanically and belongs in the gate, not in a
reviewer's eye.

### G. Images: the caption is not evidence of the picture

- **`p2_Halley_s_Comet.jpg`** shows a **hydrothermal vent** (precedent from an earlier
  paper in this campaign).
- **`p14_Manus_Island.jpg`** is **North Sentinel Island** - the caption says so itself;
  only the filename lies. The Commons record for its claimed source confirms a NASA
  Earth Observatory image from the 26 Dec 2004 Sumatra earthquake.
- **`cargo-cults`**: 8 image credits, **7** pictures; one credit links to a file the
  site answers **404** for.
- **`the-enuma-elish-…`**: 7 image references, all **404**. Measured across the whole
  campaign: of **511** image references in the 31 papers, **504** are served with 200
  and **7** are dead - all 7 in this one paper.

**Rule for the researcher:** an image is only correct if the picture was **opened and
recognised**. The filename, the caption and the alt text are not evidence. A file whose
picture was not verified carries no claim about what it shows. The image alt texts
already carry a QA flag, `![gallery:<hash>|verified:yes|no|<title>]`; `verified:no`
must mean "nobody has looked", and must never ship.

### H. Two defects in the publish path, not the writer

Both were found in this campaign and both produced visible damage.

1. **A re-send appends the same correction log entry again.** 42 byte-identical
   entries on 22 papers, because a build-status flag that stays `true` after a
   successful build was read as "not yet sent". *A write path must be idempotent per
   input, and the input's hash must be the thing that decides, not a boolean.*
2. **`correct_paper` does not write `probative_images`.** Images can therefore only
   change through a full republish, which replaces the entire stored text of a public
   paper. The owner's decision for the next session: **build a patch path for
   `probative_images` and deploy it** - not 30 full republications.

A third, structural: `theo_paper_publications.action` has
`CHECK (action IN ('publish','correct','register_video'))`, so **a correction to a
paper's own metadata cannot be journalled at all**. Cleaning up the duplicate entries
above had to happen with no journal row, because a `correct` row would have asserted
the very thing that caused the damage.

---

## What the gate already checks, and the gap that let all of this through

`pipeline/lyra/theo_citations.validate_paper_artifact` and
`pipeline/lyra/theo_publishing.check_quality` / `check_images` are artifact-only and
structural. They check:

- marker syntax: `invalid_markers`, `non_numeric_markers`, `placeholder_markers`
- list/prose agreement: `orphaned_refs`, `non_contiguous`, `duplicate_ref_nums`,
  `assigned but not cited`, `uncited_paragraphs`
- the reference line's tier tag: `reliability_tier`, `tier_label`
- `check_images`: every referenced path is a real file under
  `research-images/<request_id>/` and belongs to that paper
- `check_quality`: recomputes the LLM verdict against the fresh text

Every one of the 31 papers passed all of it. The gaps, each of which is a defect class
above:

| not checked | defects that passed |
|---|---|
| does the cited source say what the sentence says | 384 misattributed + 84 contradicted |
| is the claim no stronger than the source | 858 unsupported |
| is the reference's text actually readable | 177 unverifiable |
| is a quotation contiguous in the source | quote splicing (class B) |
| does a sentence end properly | class F, 6 shipped defects |
| does a picture show what its caption says | class G |
| can two entities be merged | class C |
| is a date/identifier copied rather than recalled | class E |
| is the correction log free of duplicates | class H.1 |

**Citation granularity, measured.** Over the 31 published papers: 1136/1136 reference
entries are cited at least once, and **0 of 853 prose paragraphs carry no marker at
all**. Individual sentences carrying their own marker: **530 of 4261 = 12.4 %**. The
owner's decision of 04.10.2026: paragraph level is the accepted unit, 100 % is reached,
the sentence-level upgrade is declined. So the upgrade target is **not** more markers -
it is markers that are true.

> Measurement trap, in case the next session reuses the script: a naive paragraph count
> calls a 24-image paper 72 paragraphs and reports half the paper as uncited. Each
> picture is three stored paragraphs - `![...](...)`, `*caption*`, `[Source](url)` - and
> must be filtered out first. The tell was 21 of 31 papers reporting the same 48
> uncited paragraphs.

---

## Concrete rules for the upgraded researcher

Ordered by how many findings each one retires.

1. **A marker requires a located sentence.** Find the supporting sentence in the
   fetched text before writing `[n]`. Not found → do not cite. *(classes A, D: 561)*
2. **Never sharpen a source.** Carry the hedge, the unit, the epoch and the
   uncertainty across. A quotation must be contiguous. *(class B: 858)*
3. **Entity keys are `(name, site code, author, year)`.** No merge without all four.
   Never infer a site code or accession number. *(class C)*
4. **Identifiers are copied, never recalled.** Date, DOI, PMID, ISBN, site code. If
   the identifier is not in front of you, search by title. Asserting a retraction
   requires a Crossref/OpenAlex/Europe PMC check. *(class E)*
5. **Every sentence ends on a terminator**, and no sentence ends on a preposition,
   conjunction or article. Checkable mechanically - put it in the gate. *(class F)*
6. **An image is cited only if the picture was opened.** `verified:no` never ships.
   A file that is not served is a defect on the page, not a cosmetic one. *(class G)*
7. **Writes are idempotent per input hash.** No boolean "already sent" flags.
   *(class H.1)*
8. **`probative_images` needs a patch path**, so changing a picture never means
   republishing a public paper's whole text. *(class H.2, owner's decision)*

## Where the artefacts are

- Per paper, `C:\tmp\papers\<request_id>\`: `live.md` (stored report), `audit.json`
  (findings and fixes), `resourced.json` (what was recovered and what stayed deleted,
  with a reason each), `corrected.md` (the built text that shipped), `build_status.json`,
  `image_audit.md` where an image pass has run (4 of 31 so far).
- Tooling, same directory: `build_corrected.py` (audit → corrected text, with the
  guards), `ship_paper.py` (dry run → apply → journal read-back),
  `aggregate_findings.py` (the tables above), `citation_coverage.py` (the coverage
  measurement), `seam_scan.py` (class F), `image_probe.py` (class G).
- The correction of the duplicate correction entries, with its safety copy:
  `output/paper-corrections-reversal/` on branch
  `chore/2026-10-04-corrections-reversal` (commits `d068e2c`, `cc641cc`), not pushed.
