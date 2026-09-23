# Card descriptions: the extractive contract

`card_stats.card_description` is the up-to-200-character text on a site's card (Forgotten Worlds,
search previews, the shorts narration). Since the 2026-09 remediation (Phases 4 and 5, design entry
[6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, section card_texts; owner
decision O3: "same run, extractive") a card is **an extractive condensation of the site's own
published description, never a second free generation**. This file is that contract. It replaced
the 10-agent generation procedure of 2026-03, whose rules are listed under "Retired" below.

## What a card is

- The selector call that picks the description's sentences (`scripts/remediation/phase4/`
  `select_stage.py`, prompt in `prompts4.py`) also returns 1-2 `CARD:` items. Each is one of the
  description's own `DESC:` sentence ids plus offered spans to drop. The model writes no word.
- Code assembles the card (`phase4/assemble.py`): the source slice of each item minus its dropped
  spans (the description's own drops included). No citation marker, no parentheses, no pronoun
  opener.
- The only edit that is not the source's own is the closed spoken-form rule `c.`/`ca.` ->
  `circa`, so the narrator never reads a bare "c".
- Hedges, negations and restrictions ("possibly", "not", "only", "according to", ...) survive by
  construction: a span containing one is never offered for deletion
  (`phase4/model4.py:PROTECTED_TOKENS`).

## Rules (verifier V10, hash V13, the reviewer's CARD line)

| rule | why |
| --- | --- |
| 80-200 characters | the shorts floor, and the `varchar(200)` column |
| no country name (`pipeline.utils.country_lookup` names plus the stored country's variants) | the card already shows it; cultural adjectives (Roman, Egyptian, Maya) are allowed |
| no marker, no parentheses, no pronoun opener | the card stands alone |
| no unattributed evaluative superlative: "one of the most", "most important", "most significant", "most famous", "most remarkable", "finest", "best-known" | fame and importance claims are refused; size and age superlatives survive only with the source's own scope words |
| every glyph covered (`pipeline.video.shorts_brand.missing_glyphs`), every caption word fits `1080 - 2 x CAPTION_MARGIN` px | the card is narrated and captioned |
| `sha256(card) == _description_provenance.card.text_sha256` | the card is the one the provenance names (V13; the shorts gate's S13) |

"Legend says ..." and "believed to be ..." appear only in the source's own attributed wording,
because the verbatim sentence carries its attribution (the B5 cases of `HUMAN_ONLY.md` resolved by
rule; pilot fixtures Midford Castle `32429f3c`, Bulls of Guisando `0529af31`, Arc de Berà
`82f23c96`).

## Selection preferences (what the old tone guide became)

Cards read flatter than the 2026-03 tone guide asked for. That is the price of having no
unsupported claims: the guide's "age anchor", "one outstanding fact" and "hook" are now preferences
of the selector among source sentences, not text anybody writes:

- prefer a sentence that carries a date;
- prefer what the site is, where, when and by whom, and what was found there;
- prefer the concrete over the evaluative.

## How a card reaches production (the P5 sitting)

`public/data/card_descriptions.json` is the authoritative copy of the column
(`docs/procedures/FIELD_CONTRACT.md` section 2.3): every API boot upserts each key it carries into
`card_stats` (`api/services/card_descriptions.py`, and it logs every non-empty value it replaces as
`[STARTUP] Card description overwritten`). A normal blob, not LFS. Hence one order, in one sitting,
and only once Martin confirms he pushes straight afterwards (design, production_write step 3):

1. backup drill: `scripts/remediation/00_backup_and_drill.sh` with `DO_DRILL=1` on the VPS, judged
   by its printed `VERDICT` line;
2. record `docker inspect -f '{{.State.StartedAt}}'` of `ancient_nerds_api` and `ancient_nerds_api2`;
3. dry run of the P5 plan (`output/remediation/tools/write_gate4.py --group P5 --run <run>`), digest
   pinned;
4. `scripts/remediation/phase4/card_json.py --prerender` renders the file the plan leaves behind;
   commit it locally (not pushed);
5. `write_gate4.py --group P5 --run <run> --apply --step 100` writes one step and stops; then
   `verify_writes4.py --lane p5 --plan <apply root>/LANE_PLAN.jsonl --run <run dir>` (the command
   the gate prints), its output saved to a file and handed to
   `write_gate4.py --group P5 --run <run> --accept <file>`. The gate refuses the next `--apply`
   while the step it wrote (`STEP.json`) has no acceptance, and `--accept` records one
   (`ACCEPTED/step-NNNN.json`) only for an output that ends in `ACCEPT_EXIT=0` with
   `RESULT: 0 deviation(s)`, covers every stamp of the step, was run after it, and accepted no
   earlier step (`docs/procedures/PHASE4_CONTRACTS.md` section 7). Repeat until no batch is open;
6. `card_json.py --regenerate` from a read-only production SELECT: `WRITE_EXIT=0` only when it is
   byte for byte the pre-render;
7. re-read `StartedAt` of both containers;
8. Push #2 (owner);
9. after the deploy: 0 `[STARTUP] Card description overwritten` lines in the logs of both API
   containers, `card_json.py --check` (`ACCEPT_EXIT=0`) and `verify_writes4.py` in both directions.

**Pushing the file before the database write is forbidden**: the boot import would write the cards
without a journal, and the journalled write would then refuse every row with matched_0. If CI goes
red and no deploy happens in the sitting, `scripts/remediation/phase4/revert4.py --stamp-like
'phase5:%' --apply` and a `git revert` of the JSON commit bring the database back to the deployed
file. Rehearse the reversal first (`--rehearse`): its PL/pgSQL has not yet run on PostgreSQL.
`revert4` skips every write that already has its own reversal (its key and its stamp plus
`-rollback`), so in a second sitting after such a revert the same pattern reverts only the live
round; it refuses a pattern that matches no write, or only reverted ones.

The file's form is `json.dumps(obj, ensure_ascii=False, indent=2) + '\n'` (today's bytes); existing
keys keep their order, new keys (sites without a card, the card that exists only in the database)
are appended in UUID order, cleared keys are removed. Measured 2026-09-23 against production
(read-only): the 4,996 keys of the file are curated sites and equal the database; one curated card
exists only in the database (`95b33efa-d5eb-4cb8-ab61-746b3822762a`).

## Held cards

- A site whose card is held keeps its old card, with no card provenance; it is therefore not
  shorts-eligible.
- Exception: when that old card carries a Phase-3 reviewer-cleared defect (one of the 709 in
  `logs/_write_dry/ALL_REFUSED.jsonl`, rule `report-only-field`), it is cleared (`P5/card-clear`,
  new value NULL) and its key is removed from the file. The Phase-3 finding - the refusal record,
  the finder's answer and the reviewer's verdict - is the journal evidence. Known-wrong narration
  becomes absent.

## Licence and disclosure

Cards, and therefore the shorts narration, are CC BY-SA 4.0 snippets of Wikipedia text (lanes W, S,
T) or AI-generated text (lanes T, R). The video description must carry the attribution line; that
belongs to the shorts publishing step. On a SiteCard the card carries a machine-readable
`data-card-ai` attribute only; the visible notice is on the site's page.

## Retired

Never used for this work, and no longer a way to produce card texts:

- the 10-agent generation flow of 2026-03 (batch inputs, parallel agents, merge) and its rule
  "if the wiki excerpt is empty, write a brief factual description based on the site name, type
  and period" - a card is never written from anything but its own description's sentences;
- `scripts/import_card_descriptions.py`, `scripts/merge_rewrites.py` and the `audit_enrich.py`
  Wave-4 merge - none of them journals, and the last two write the file the boot import reads;
- `scripts/verify_descriptions.py` and `scripts/verify_agent.py` as gates: they penalise hedging
  (plan section 5.3). The Phase-4 verifier (`phase4/verify4.py`, V1-V15) is the gate.
