# Hero repair - Phase 2 item 1

Snapshot `C:\PythonProjects\AncientMap\output\remediation\snapshot`, exported 2026-09-20T20:20:01+02:00 - scope `unified_sites.source_id = 'ancient_nerds'`.

Mechanical only: **one flag moved per site, no download**. `is_hero` is set to false on
the row that serves today and to true on a file the site already has at 1600 px.

## The rule

* candidate = not the hero, not `is_excluded`, T10 tier `D` (clear) or `C` (grey) - never
  the suspect tiers `A`/`B`;
* the **cached true Commons dimensions** (`commons_imageinfo.json`) say width >= 1600 and height >= 900 - the source really has the pixels;
* the row's **stored** dimensions say the same and never exceed the original (`width` is
  the local derivative's size, so this is what the page will serve);
* among a site's candidates: tier `D` before `C`, then the largest true Commons area, then
  the lowest image id.

Tiers come from the census's own artifact, read, not re-derived:
`C:\PythonProjects\AncientMap\output\remediation\run_t10\findings.jsonl` (`A` hero, `B` suspect, `C` grey, `D` clear -
`scripts/remediation/census/tests/t10_gallery_tiers.py:226`).

## Rows examined

| verdict | rows |
|---|---|
| is-the-hero | 3,858 |
| excluded-from-the-gallery | 659 |
| tier-B-suspect | 9,501 |
| local-file-too-small | 1,741 |
| commons-missing | 6 |
| original-too-small | 8,309 |
| eligible | 25,617 |

## Sites

| class | sites |
|---|---|
| sites | 5,004 |
| sites-with-images | 4,010 |
| sites-without-images | 994 |
| hero-rows | 3,858 |
| sites-without-hero-flag | 152 |
| already-hero-ready | 0 |
| repaired-sites | 2,719 |
| repaired-via-tier-D | 1,344 |
| repaired-via-tier-C | 1,375 |
| skipped-no-eligible-candidate | 1,139 |
| plan-rule-candidate-but-stricter-rule-rejected | 545 |
| no-1600px-candidate-under-either-rule | 594 |

## The write

* **2,719 rows** get `is_hero = false -> true` (the new hero),
* **2,719 rows** get `is_hero = true -> false` (the 800 px hero they replace),
* **2,719 sites** are touched, in one transaction, each row
  guarded by its old value, journalled in `remediation_change_log`.

Every repaired site ends with **exactly one** `is_hero` row. That invariant held before
the repair too (measured on the snapshot: 152 of 4,010 sites have none, the
other 3,858 have exactly one) and is re-asserted
in `scripts/remediation/hero_repair/plan.py::check_plan` before anything is written.

## Comparison with the plan's 3,264

§6.3 and T09 (the census's own `T09/hero-not-best` flag) both count **3,264** sites whose
hero can be replaced by an already-local 1600 px image under the rule *stored*
`width >= 1600 AND height >= 900`. That number reproduces exactly here, as
**2,719 + 545 = 3,264** - the claim is
not refuted, it is split. The rule was not tuned towards it; this plan is stricter, for the
reason in the module docstring.

### Which column decided

Both rules read `wiki_images.width`/`height`. Those columns hold the size of the local
derivative the site serves - and they are the column the brief forbids selecting on,
because T09 measured them larger than the Commons original on 11,653 rows. That is where
the two numbers part company: this plan keeps the stored size as one of two conditions and
requires the cached Commons truth as the other.

| class of site | sites | reads only the stored column? |
|---|---|---|
| 2,719 repaired: both conditions hold | 2,719 | no - the truth agreed |
| refused, and the stored size was the only witness | 276 | **yes** - of these the Commons answer contradicts it |
| refused on the census's own suspect tier alone | 269 | no - T10 refused them before any size test |
| neither rule finds a 1600 px candidate | 594 | - |

So **276 of the 545 rejected sites are rejected because
the stored column would have been the only thing speaking
(the Commons original is missing, below 1600x900, or - in every row measured - both small
and upscaled). Those are exactly the rows this plan refuses to trust the column on, and
the reason the executed number is smaller than the plan's. The other
269 were refused by the census's own tier, not by a size
test: T10 calls the candidate a suspect, so promoting it would fight the audit that
follows.

Why the rejected sites are rejected, counted per site (a site can be refused for more
than one reason, so these do not sum to the class above):

| reason | sites |
|---|---|
| all-candidates-refused-by-tier | 269 |
| all-originals-too-small | 191 |
| mix-suspect-and-truth | 84 |
| no-commons-truth | 1 |

At row level, over the candidates the plan's rule would have accepted:

| verdict | rows |
|---|---|
| tier-B-suspect | 3,332 |
| original-too-small | 680 |
| commons-missing | 1 |

One of the plan's own guards fired on **0** rows and is therefore absent from both
tables: `local-file-is-an-upscale`. Measured 2026-09-20 over the whole corpus, of the
31,878 already-1600 px rows whose Commons original is itself >= 1600x900, none exceeds
its original per axis. Every one of the 10,977 upscaled rows has an original below the
hero minimum, so `original-too-small` names them. The comparison stays in the rule
because it is the plan's central claim (the 1600 px file carries the original's real
detail); it is compared, not asserted in prose.

## Not in this plan

* the 545 sites above: they need a
  genuine large original (a fetch or a re-export - Phase 2 item 1's second half) or a
  different image once the gallery audit has judged the suspects;
* the 152 sites with **no** `is_hero` row (`T09/no-hero-flag` counts 133 of them under the
  looser rule): their page falls back to `is_lead DESC, sort_order`, `is_lead` is true
  for exactly the 3,858 hero rows, so they already serve their lowest-`sort_order`
  gallery file - a 1600 px local file. Planting a flag there would change which image
  the site serves without a size defect to justify it;
* `THUMB_WIDTH`/`HERO_WIDTH` - raising them is a code change with its own review; the
  flag move does not depend on it (the flag is the first sort key of the served-image
  query). Until it is raised, a *newly downloaded* hero still arrives at 800 px.

`SKIPPED.jsonl` lists every site this plan does not touch, with its class and the
row-level reasons behind it, so the second half of Phase 2 item 1 has its worklist.

## Reproduce

```bash
cd scripts/remediation
../../.venv/Scripts/python.exe -m hero_repair.plan --write \
    --snapshot ../../output/remediation/snapshot \
    --cache ../../output/remediation/cache/commons_imageinfo.json \
    --tiers ../../output/remediation/run_t10/findings.jsonl \
    --out ../../output/remediation/hero_repair
```

