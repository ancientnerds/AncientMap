# Gallery-audit stage — design (plan §6.5 / Phase 2 items 2–5)

Status: **design, read-only recon**. No database write, no source edit, no commit.
Author: scout lane, 2026-09-21. Snapshot basis: `output/remediation/snapshot`
(exported 2026-09-20T20:20:01+02:00), T10 run `output/remediation/run_t10`.

This document answers the five assignment questions. Every number is either a
measured value carried from a named artifact or the real output of a command run
in this session; anything not measured is labelled **unverified** with the reason.

---

## 0. The one thing that had to be established first

**A vision-capable model IS reachable from this environment.** This was tested, not
assumed.

- The provider `opencode-go` (the only configured provider; `C:/Users/marti/.pi/agent/auth.json`
  holds exactly one key, `opencode-go`) exposes, in its model registry
  `C:/Users/marti/.pi/agent/models-store.json`, the model
  **`deepseek-v4-flash-vision-exp`** with `"input": ["text", "image"]` (same file shows
  `deepseek-v4.1-flash` with `"input": ["text"]`).
- Live probe 1 (96×96 PNG, solid red), POST to `https://opencode.ai/zen/go/v1/chat/completions`
  with `Authorization: Bearer <opencode-go key>` and header `x-opencode-session: probe-<ts>`:

  > `{"model":"deepseek-v4-flash-vision-exp", "choices":[{"message":{"content":"Red"}}],
  >  "usage":{"prompt_tokens":225,"completion_tokens":22}}`

  The answer was correct. Without the `x-opencode-session` header the gateway rejects
  the request (`MissingSessionID`); with it, routing succeeds.
- Live probe 2 (800×600 JPEG) with the plan's label schema returned
  `{"kind":"other","subject":"vertical striped pattern","other_site":false}` and
  `usage.prompt_tokens = 403`.
- Live probe 3 (1280×960 JPEG) returned `"Green"` and `usage.prompt_tokens = 774`.

Conclusion: the visual question **can** be answered here. A design that assumed "no VLM
available" would be wrong; a design that assumes MiniMax is the *only* transport would
also be wrong. Two independent transports exist (see §3).

**What is NOT proven:** semantic *competence* (does the model correctly label a real
Commons site photo vs a foreign site). Only capability — the endpoint accepts an image
and returns a schema-conforming answer — was measured. No local gallery image exists to
test competence against (see §2), and a probe on synthetic images cannot measure accuracy.
This is labelled **unverified** and is the first thing a pilot must measure.

---

## 1. Q1 — What the audit must DECIDE per image, split by evidence source

`wiki_images` (schema `pipeline/database.py:594-648`) carries for every row:
`original_url`, `commons_page_url`, `author`, `author_url`, `license`, `license_url`,
`title`, `filename`, `width`, `height`, `file_size_bytes`, `is_hero`, `is_lead`,
`is_excluded`, `sort_order`, `thumb_width`, `source_type`, `created_at`. T10 additionally
fetched and cached P373 category membership plus each file's Commons categories and their
parents (`output/remediation/cache/gallery_signals.json`; 4,618 P373 records, 46,070 file
category lists — T10 REPORT §1).

### 1.1 Decidable from metadata already held (no pixels needed)

| Decision | Evidence field | Measured volume |
|---|---|---|
| Proven clean → zero-call tier D | in P373 category **and** no word signal **and** own name in filename | **10,705 rows** |
| Exact reuse by a differently named site (signal S) | Commons file name shared across sites | 5,162 rows (4,750 without heroes) |
| Museum-word (A) | title/filename/Commons category | 3,355 rows |
| Place-token > 50 km (D, reconstructed) | title/filename vs curated-name dictionary | 2,089 rows |
| Non-photo word (E, 6 of 67 terms) | title/filename | 766 rows |
| Own name absent (F) | title/filename/Commons name | 31,399 rows |
| Category membership | P373 (proven/absent/no-qid) | 47,206 / 1,486 / 999 rows |
| Attribution completeness | `author IS NULL` / `license IS NULL` | 1,677 / 657 rows (plan §4, `wiki_images` audit line) |
| Dimension gate | `width`,`height` | all 3,858 heroes are `min < 900`; 914 are strips |
| Already excluded | `is_excluded` | 659 rows |

Source for the row volumes: `output/remediation/t10_scratch/REPORT.md` §2–§3.

### 1.2 Requires seeing the picture

- **is this actually *this* site** (foreign/same-subject-other-site) — the plan's 65
  foreign images of 652 labelled (10.0 %), §6.1.
- **image kind** — site_photo / artifact / map_or_document / painting_or_artwork / people /
  other. The plan's 6.1 problem classes painting 23 + map 22 + diagram/text 19 = 64 of 652
  (9.8 %) are non-photo, and the word signal E catches only ~10 % of them (recall 10.1 %).
- **quality** — blur, exposure, low-resolution scan, damage. No metadata surrogate.
- **text/watermark/overlay** inside the frame.
- **visual duplicate** (crop/near copy) — needs pixels; `dhash` measured **not**
  crop-invariant (§9.2).

### 1.3 The split as counts (49,691 rows)

- **Metadata can decide "clear" (no VLM):** 10,705 (tier D).
- **Metadata cannot clear; only seeing can settle:** **49,691 − 10,705 = 38,986 rows.**
- Metadata can *flag* (but not confirm) for all 49,691 rows; the eight signals are
  computed for every row.
- The plan's spend concentrates the visual pass: tier B 9,559 + heroes 3,858
  (union **12,606**, since 811 heroes also carry CORE) get a call each; tier C is
  sampled. Tier volumes: A 3,858 · B 9,559 · C 25,569 · D 10,705 (sum 49,691).

---

## 2. The transport reality that shapes everything

- **The image files are not here.** `public/data/images` contains only `index.json(.gz)`
  (8 KB total, 0 image files). The 49,790 curated image files live on the VPS
  (plan §Phase 0), and `wiki_images.original_url` for the production corpus points at a
  **local path** (plan §6.2: the rows were re-indexed from disk, `original_url` = local
  path). Therefore **the audit must run on the VPS** where the bytes are — matching the
  plan's own instruction (§Phase 2 "run VLM work from the VPS", §9.2).
- The workstation *can* reach a vision model (proven above) but **cannot reach the images**
  without re-downloading ~50k files from Commons. Do not build a workstation pass.

  > **AUDIT CORRECTION (parent agent, 2026-09-21) — this premise is false as stated.** The image
  > bytes *are* on this workstation, in a complete offsite copy the recon did not survey:
  > `C:/PythonProjects/AncientMap-Offsite` holds **49,788 `.webp`** files / 20.4 GB across 4,017 shard
  > directories. Proven identical to the VPS per shard, not by a total: `vps shards=4017 files=49788`,
  > `local shards=4017 files=49788`, shards-only-on-VPS 0, shards-only-local 0, shards-with-differing-counts
  > 0. The claim above is true only of `public/data/images`, which holds 2 files (both `index.json`).
  > Consequence: the execution site is a **transport** decision, not an image-availability decision.
  > It also inverts the stated reason — the workstation has a *proven working* vision transport
  > (this lane's own probes) while VPS reachability of either model is unproven here. See §8.

---

## 3. Q2 — Is a vision-capable model available? (decisive answer)

**Yes, two transports:**

1. **`deepseek-v4-flash-vision-exp`** via `opencode-go`
   (`https://opencode.ai/zen/go/v1/chat/completions`, `openai-completions` API).
   - Reachable from the workstation with the existing `opencode-go` auth; headers required:
     `Authorization: Bearer <key>`, `x-opencode-session: <any unique id>`, `Content-Type`.
   - Accepts `data:image/jpeg;base64,...` and `data:image/png;base64,...`
     (webp/png/jpeg/gif; an 8×8 PNG was rejected as "unsupported image" — use ≥ ~96px).
   - Registry entry `models-store.json`: cost input 0.15 / output 0.60 / cacheRead 0.003
     per 1M tokens, `contextWindow` 1,000,000.
   - **Name contains `exp` → experimental.** A stability risk; keep transport 2 as fallback.
2. **MiniMax coding-plan VLM** — the project's existing image path,
   `pipeline/lyra/minimax_shared.py:537-559` (`MINIMAX_VLM_PATH = "/v1/coding_plan/vlm"`),
   called by `pipeline/video/shorts_select.py:judge_all`.
   - The API key is present locally (`.env:82`, `LYRA_MINIMAX_API_KEY=sk-cp-...`), and the
     plan E6 explicitly approves MiniMax for the VLM image scan (plan line 49).
   - Known defect (plan §9.2): `minimax_vlm()` does **not** check `base_resp`, so quota /
     rate-limit errors are silently recorded as rejections; 664 of 733 calls failed at the
     transport layer **from the workstation** (WinError 10053/10054, SSL EOF). **Must run
     from the VPS.** These are defects to fix, not reasons to avoid the transport.
   - Billing: covered by the MiniMax flat plan → marginal $0; binding constraint is the
     weekly quota shared with Lyra/Theo (plan §9.1 table, line 773).

**What each CANNOT decide:** neither transport can decide *whether the database row is
correct* by itself — both return a *model verdict* that must be reconciled against
metadata and, in the legal/metadata classes (attribution, license, dimensions), cannot
help at all. `deepseek-v4-flash-vision-exp` returns the label schema; it does not return
Commons categories, licenses or coordinates.

**Alternatives if a VLM were unavailable (it is not):** Commons structured data (categories,
P373, `prop=categories`) — decides membership/kind-by-word only, cannot clear ~2/3 of the
suspect set (§4); local `dhash`/`imagehash` — exact reuse only, not crop-invariant; PIL
dimension gates — file metadata only. None of these can decide foreign-site or quality.

---

## 4. Q3 — Commons structured data as the substitute

The starting signals are exactly those T10 already computed: S, A, D, E (§6.4 signals),
plus the fetched P (P373 membership; faithful). The plan's own precision/recall table
(§6.4, used verbatim, **not re-measured**) on 652 labelled images:

| Signal | Flagged | Precision | Recall |
|---|---|---|---|
| S same file, other site | 78 | 38.5 % | 46.2 % |
| A museum word | 62 | 35.5 % | 33.8 % |
| B museum city — **UNAVAILABLE here** | 14 | 92.9 % | 20.0 % |
| D place token | 11 | 54.5 % | 9.2 % |
| E non-photo word | 15 | 93.3 % | 10.1 % |
| P not in P373 category | 296 | 17.6 % | 80.0 % |
| F name absent | 232 | 16.8 % | 60.0 % |
| **CORE** S∣A∣B∣D∣E | 151 | 33.1 % | **76.9 %** |

**How many of the 9,559 suspect images would structured data settle?**

- Structured data **cannot clear** tier B: by construction tier B is CORE-positive, and the
  only structured "clear" rule reaches tier D. Clearing a CORE-positive row from metadata
  alone is not possible with any signal T10 has.
- Structured data can **confirm** at the plan's CORE precision: 33.1 % of 9,559 ≈ **3,164**
  rows settle as genuinely contaminated — *if* the plan's precision transfers.
- **It does not transfer cleanly.** Our CORE is a strict **subset** of the plan's (B
  unavailable; A narrow — one lexeme; E 6 of 67 terms); T10's own docstring says
  "the suspect tier is under-flagged by an unknown amount and the plan's stage-1
  precision/recall figures do **not** transfer." So 3,164 is an **upper bound on
  confirmation**, and ≥ 23 % of the plan's true contaminants (1 − recall 76.9 %) plus
  every error hidden by the missing B/E/A terms sit in tiers C and D.
- Net: **≥ 6,395 of the 9,559 (≈ two thirds) still need the visual pass**, plus an unknown
  number that under-flagging pushed into tiers C/D. Structured data is a *router*, not a
  *settler*, for the suspect tier.

**Missed-signal budget (the honest caveat the hero repair inherited):** four of eight
signals are reconstructed (D) / partial (E) / narrow (A) / unavailable (B) — T10 REPORT §4.
The 2,719 images the hero repair just promoted were chosen from tiers D and C, i.e. on the
strength of those weaker signals. The gallery audit is where that assumption gets tested.

---

## 5. Q4 — The image-kind column (Phase 2 item 3)

**What it should hold.** The `kind` field the existing VLM prompt already produces
(`pipeline/video/shorts_select.py:51-75`):

```
site_photo | artifact | map_or_document | painting_or_artwork | people | other | unknown
```

`unknown` is the not-yet-judged state and is mandatory: "could not check" must never read
as "checked and clean" (house rule). Nothing else belongs in the column — `subject`,
`quality`, `relevance`, `other_site` are separate decisions and should not be crammed into
a single enum.

**Where the values come from.** `judge_all` returns one verdict dict per image
(`shorts_select.py:226-277`, `judge_one` and `judge_all`), persisted **today only** to
`video-assets/shorts/<slug>/selection.json` (280 stored verdicts from 16 sites already sit
there; plan §9.3). The stored entry carries `wiki_images.id`, so the mapping back to the
row is exact.

**Who writes it.** A new persister (proposed `scripts/remediation/gallery_audit/persist_verdicts.py`)
that reads `selection.json` verdicts and writes:

- `wiki_images.image_kind` (new column),
- `wiki_images.is_excluded` for the hard rejects (`kind != site_photo`, or `other_site`),

through the single supported path `apply_remediation_change(...)`
(`migrations/0017_remediation_change_log.sql`; allowlist already includes `wiki_images`).
A new migration `0019_wiki_images_image_kind.sql` must add the column **before** the first
write. Every write needs the conditional `WHERE` (old value) and a journal row — the
function enforces both.

**Does it survive a restart?** **Yes.** FIELD_CONTRACT §2 names exactly three boot-time
overwriters (`unified_sites.site_type`, `unified_sites.name_normalized`,
`card_stats.card_description`); none touches `wiki_images`. The plan's own wave-2 finding:
"`wiki_images.is_hero` has no restart writer, so hero repairs survive a restart"
(plan line 661). A new `wiki_images.image_kind` column inherits that — **provided no future
boot-time producer is added for `wiki_images`.** Residual: the re-index path
(`scripts/reindex_wiki_images.py`) could re-derive rows on a manual run; it is not a boot
writer, but a re-index would need to preserve the column.

**What a wrong value costs.** The gallery is thin: 2,296 sites already fall below
`MIN_SITE_IMAGES = 6` (gate S10). A false `map_or_document` / `other` on an actual
`site_photo` drops a good image out of shorts/hero selection and can tip a 6–10 image site
under the threshold; a false `site_photo` on a foreign image republishes contamination on
the page. Both are visible, publicly served errors. Because of this asymmetry the column
should be written **only** from a VLM verdict (never from a word signal), and `is_excluded`
should be set conservatively (hard rejects only), matching the plan's Tier policy.

---

## 6. Q5 — Costed design

Domain: 49,691 curated images / 4,010 sites. Tier volumes and reasons from
`output/remediation/t10_scratch/REPORT.md` §2. Token and price figures measured in this
session (probe 2/3) and from `models-store.json`. Wall-clock derived from the plan's own
measured parallelism (~10–14 concurrent) — labelled as derived, not measured here.

### Stages, in order

| # | Stage | Images touched | Calls | Produces | Cost |
|---|---|---|---|---|---|
| **G0** | **Persist the free verdicts** | 280 stored verdicts | 0 | `image_kind`, `is_excluded` for 280 rows; proves the writer end-to-end | $0 |
| **G1** | **Structured clearance** (already done by T10) | 49,691 ranked; 10,705 to tier D | 0 | tier assignment (existing `findings.jsonl`) | $0 |
| **G2** | **Suspect tier B** — one call each | 9,559 | 9,559 | per-image `kind`, `other_site`, `subject`, `quality` | see COST.md |
| **G3** | **Heroes (tier A)** — one call each, minus B overlap | 3,858 → **3,047 new** | 3,047 | same labels; drives hero re-selection | see COST.md |
| **G4** | **Grey sampling (tier C)** — 3 samples/site; one hit escalates the whole gallery | ≈10,500 probes → escalation ≈14 % of sites | ≈10,500 + escalated | same labels | see COST.md |
| **G5** | **Acquisition** (Phase 2 item 5) for the 2,296 thin sites | 0 VLM (Wikimedia API) | 0 VLM | new images; lever = the 1,691 sites whose P category is unproven | $0 |

Unique visual-audit calls (G2+G3 union) = 9,559 + 3,047 = **12,606**; plus G4 ≈10,500.
**Total ≈ 23,000–25,000 calls** — consistent with the plan's 25,000–30,000 (§6.5).

### Recommendation

**Do FIRST (highest value / lowest cost):**

1. **G0 + the writer + migration 0019.** Persisting the 280 free verdicts costs zero
   tokens, exercises the whole chain (VLM → column → `apply_remediation_change` →
   journalled write → survives restart), and is the plan's own named "single most valuable
   economic measure" (§9.3). It also de-risks everything else: if the writer is wrong, it is
   found on 280 rows, not 12,606.
2. **A pilot on ~200 real images** (50 site_photos + 50 known foreign + 50 maps/paintings +
   50 duplicates) to measure the vision model's *competence* — the thing this recon could
   not (no local images). Without it, the design is capability-proven but accuracy-unproven.
3. **G2+G3 (suspect + heroes, 12,606 calls)** on the VPS, with both transports wired
   (deepseek-vision primary, MiniMax fallback), `base_resp` checked on the MiniMax path,
   and a hard error — never an empty verdict — on transport failure.

**Do NOT do at all:**

- **A full 49,691-image VLM pass.** It spends ~2× for the 10,705 tier-D rows that 0 calls
  already cover with ≤1.5 % residual risk (§6.4 safe class), and for tier-C strays the
  per-site clustering (§6.1: 54 of 65 foreign images in 6 of 40 sites) makes sampling the
  cheaper detector.
- **A workstation image pass.** The bytes are on the VPS; re-downloading 50k images is pure
  cost with no accuracy gain, and the plan already measured workstation transport failures.

  > **AUDIT CORRECTION — see §8.** The premise ("bytes are on the VPS" only) is false: a complete
  > local copy exists. The conclusion may still hold, but for a different reason — MiniMax's
  > recorded workstation failures (`WinError 10053/10054`) — and that reason applies to the MiniMax
  > transport only, not to `deepseek-v4-flash-vision-exp`, which this lane proved *works* from here.
- **Trusting `image_kind` from word signals.** E recall is 10.1 %; a word-written kind is
  worse than `unknown`.
- **Re-running the VLM on images already carrying a stored verdict** without first
  reconciling the 280 existing ones.

---

## 7. Open questions / risks (for the owner)

1. **Vision-model competence is unmeasured** (capability only). The pilot fixes this.
2. **`deepseek-v4-flash-vision-exp` is experimental** — name / registry entry. Fallback
   transport (MiniMax) must be wired, and the pipeline must not silently degrade to empty
   verdicts if it disappears.
3. **Under-flagging is inherited:** B unavailable, E 6/67, A narrow, D reconstructed.
   Tier B undercounts; the plan's CORE P/R does not transfer. Consider reconstructing the
   missing signal lists from the plan's cited sources before G2, or accept a wider G2.
4. **`other_site` may be absent from the 280 stored verdicts** — the Giza sample
   (`video-assets/shorts/giza-necropolis/selection.json`) has `kind`…`vertical_crop_ok`
   but no `other_site` key; the field was added to the prompt later. G0 must treat a
   missing `other_site` as `unknown`, not `false`.
5. **The 2,296 thin sites** are a separate workstream (G5); gallery cleanup can only lower
   that number, so G5 must run before any `is_excluded` sweep that removes images.

---

## 8. Audit correction — where the bytes actually are

Added by the parent agent, 2026-09-21, after this lane completed. The rest of this design is
unchanged and stands; one premise was wrong and it carried into §2 and §6.

**What the lane measured:** `public/data/images` holds 2 files (`index.json`, `index.json.gz`) and 0
images. That reading is correct, and the conclusion drawn from it was not.

**What was missed:** the offsite copy on the same machine, `C:/PythonProjects/AncientMap-Offsite`
(created earlier in this remediation as the offsite backup of the production images):

| | value |
|---|---|
| image files | **49,788** `.webp` (20.4 GB) |
| layout | `images/wiki/<hash>/<name>.webp` + `images/wiki/<hash>/hero.webp`, 4,017 shard dirs |
| plus | `images-case-collisions/wiki/…` — 3 files whose names differ only by case (Windows FS) + `README.md` |

**Proof, and why it is stated this way.** A total-count comparison is not sufficient here — my own
first attempt at this number was wrong because it compared *files* against *images* (49,787 counted
`index.json` and `index.json.gz`; the true image count is 49,785 in `images/` plus 3 in the sidecar).
The check therefore compares **per-shard counts**, keyed on hex shard names, so it cannot be distorted
by collation differences between Linux and Windows and it localises any gap to a named shard:

```
vps shards=4017  files=49788
loc shards=4017  files=49788
shards only on VPS      : 0
shards only locally     : 0
shards with differing counts: 0
```

This also corrects a number recorded earlier in the remediation: the VPS holds **49,788** images, not
49,790 (the extra two were `index.json`/`index.json.gz`). The offsite copy is complete; the earlier
figure was a unit error, not a real gap.

**What changes in this design:**

1. §6's "Do NOT do at all — a workstation image pass" is no longer justified by image availability.
2. The execution site becomes a transport question. As measured in *this* lane: the workstation has a
   working vision transport (`deepseek-v4-flash-vision-exp`, three live probes) and MiniMax fails from
   here (664 of 733 calls at the transport layer). **VPS reachability of either model was not tested by
   this lane at all** — it is the assumption that must be verified before committing to a VPS run.
3. A workstation pass over the offsite copy is therefore a real option and is *cheaper to try first*:
   it needs no new credentials on the server and no re-download. The counter-argument that survives is
   throughput (the VPS is the deploy host, the workstation is also the dev box), not reachability.
4. Everything else — the tier volumes, the G0-first recommendation, the competence-pilot gap, the
   `other_site`-missing trap, and the cost model — is unaffected and is accepted.
