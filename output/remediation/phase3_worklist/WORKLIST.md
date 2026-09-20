# Phase 3 worklist — what the deterministic census could not settle

Generated read-only from `output/remediation/run_t01` … `run_t10` by
`build_worklist.py` (writes nothing outside this directory, never touches the DB).

Machine-readable list: **`WORKLIST.jsonl`** — one record per site, worst-first.
Arithmetic in `_counts.json`.

---

## 1. Which tests count as “factual”, and which were excluded

The plan's Phase 3 is *“only for sites Phase 1 could not conclusively settle”*. “Has any
census finding” is useless as a filter: T09 flags all 5,004 sites and T10 flags 4,010, so
every site would be Phase 3. The worklist therefore uses only the **factual** tests — the
ones whose finding is a claim about the world that a deterministic script cannot itself
confirm or refute.

**Included (factual):** `T01`, `T02`, `T03`, `T05`.

| Test | Dimension | Why factual |
|---|---|---|
| `T01` Wikidata label/P17/P625 vs name, country, coordinates | `D3-LOCATION / D4-NAME` | Disagreement with Wikidata can mean the DB is wrong, Wikidata is wrong, or the QID is wrong (anti-pattern 17). A script cannot say which. Every T01 finding is `proposal=review`, `confidence=unverifiable` — 0 are applicable. |
| `T02` point-in-polygon: lat/lon inside the claimed country | `D3-LOCATION` | A point outside its country polygon means *either* the coordinate or the country is wrong; T02 cannot tell which (`run_t02` note). |
| `T03` text years vs `period_start` bucket | `period / description text` | The description names a period the bucket contradicts — bucket or text, a human/agent must decide. Requires reading the site. |
| `T05` country is a country, spelled the project's way | `classification / country` | Whether a value is a real country is a world fact. Its `set` findings (ISO-known) a script *can* apply; its `review` findings (`Northern Ireland`, `Baltic Sea`, long forms) it cannot. |

**Excluded (mechanical/structural — a script settles these, no world-truth judgement):**

| Test | Dimension | Reason for exclusion | Findings | Sites |
|---|---|---|---|---|
| `T04` site_type canonical & restart-safe | `classification` | **0 findings** — nothing to do. | 0 | 0 |
| `T06` URL shapes | `URL` | Normalisation (scheme, entities, whitespace). 12,143 of its findings already carry `applicable=true`. | 13,020 | 3,010 |
| `T07` reference links reachable | `D8-URL / content_url` | HTTP status is a fact the sweep already measured; the 249 `clear` findings are applicable. | 5,071 | 2,806 |
| `T08` citation markers ↔ evidence array | `content / citation integrity` | Pure marker/array arithmetic on the row itself. | 99 | 94 |
| `T09` true Commons dimensions & hero eligibility | `images / dimensions` | Re-derivable from Commons imageinfo; flags **all 5,004** sites. | 17,315 | 5,004 |
| `T10` gallery triage tiers | `images / gallery triage` | Signal arithmetic over the same images. | 49,691 | 4,010 |

> Excluding T09/T10 is the single decision that turns “almost every site” into a bounded
> list. They are Phase 2 (image remediation), not Phase 3.
> The mechanical tests' union is the **whole database** (5,004 sites) — that is why they
> cannot be the Phase-3 worklist and must be a script instead.

---

## 2. The worklist, counted

Deduplicated across the four factual tests:

| Metric | Count |
|---|---|
| **Factual union — sites any factual check flagged** | **1,840** |
| of which **Phase 3** (no deterministic check can settle) | **1,813** |
| of which **mechanically settable** (a script applies the value) | **27** |

Per factual test (sites, then findings):

| Test | Sites flagged | Findings |
|---|---|---|
| `T01` | 1,063 | 1,175 |
| `T02` | 117 | 117 |
| `T03` | 875 | 875 |
| `T05` | 70 | 70 |
| **union (dedup)** | **1,840** | 2,237 |

Findings per **dimension** (not deduplicated):

| Dimension | Findings |
|---|---|
| `D3-LOCATION / D4-NAME` (T01) | 1,175 |
| `period / description text` (T03) | 875 |
| `D3-LOCATION` (T02) | 117 |
| `classification / country` (T05) | 70 |

Severity of the deduplicated factual sites (worst finding on the site):

| Max severity | Sites |
|---|---|
| severe | 488 |
| moderate | 1,181 |
| cosmetic | 171 |

Overlap — how many sites two checks agree on:

| Pair | Intersection |
|---|---|
| T01 ∩ T02 | 52 |
| T01 ∩ T03 | 203 |
| T01 ∩ T05 | 15 |
| T02 ∩ T03 | 12 |
| T02 ∩ T05 | 7 |
| T03 ∩ T05 | 7 |
| T01 ∩ T02 ∩ T03 | 5 |
| all four | 0 |

Multi-check burden (how many factual checks flagged a single site):

| Checks per site | Sites |
|---|---|
| 3 | 11 |
| 2 | 263 |
| 1 | 1,539 |

The 11 sites carrying all three of T01+T02+T03 (or the T05 combination) are the first to
route to a human — they are the ones where multiple independent signals agree something is
wrong.

---

## 3. The split that protects the budget

**a. Phase 3 — no deterministic check can settle these: 1,813 sites.** Every finding is
`proposal=review` with no `proposed_value`; 1,539 sites carry exactly one such finding.
These need the two-stage finder/reviewer method (`FINDER_BRIEF.md`, `REVIEWER_BRIEF.md`).

**b. Mechanically settable: 27 sites.** These are the T05 sites whose *only* findings are
`proposal=set` with `confidence=authoritative` (e.g. `Georgia (country)` → `Georgia`,
`Chile, Easter Island` → `Chile`) — `applicable=true`, so a script writes them with a
conditional `WHERE country = '<old>'` and a journal entry. **Do not spend LLM tokens on
them.** Eight further T05 sites carry *both* a mechanical `set` and a `review` finding;
they appear in the Phase-3 list (the review finding is the open question) while the script
applies the `set` finding independently.

> Conflating (a) and (b) is exactly how a ~$300 workstream silently becomes larger.

The larger mechanical workstream — T06 URL normalisation (12,143 applicable), T07 dead-link
clearing (249), T09 hero/image re-derivation (15,649 authoritative), T10 tiers — is Phase 1/2
work and is **not** in this worklist.

---

## 4. Batching plan and cost — see `BATCH_PLAN.md`

---

## 5. Provenance / how completeness was verified

* The ten runs are `run_t01` … `run_t10`. `run_t06_reverify` is a **duplicate of T06**, not
  an eleventh check; it is not counted.
* Every `run_t*/census.jsonl` was checked to hold exactly **5,004 rows and exactly one
  `test_id`** (see `_counts.json` → `integrity`), so no site and no test is silently missing.
* The top-level `output/remediation/findings.jsonl` was **not** used: it contains only
  `T03/all-outside` (707) + `T03/primary-outside` (166). The union was rebuilt from the
  `run_t*` directories.
* Snapshot names come from `output/remediation/snapshot/unified_sites.jsonl.gz`.
