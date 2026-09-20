# Gallery-audit stage — cost model

Companion to `DESIGN.md`. Read-only recon, 2026-09-21. No DB write, no source edit.

## 1. Inputs (all measured or cited, none invented)

| Quantity | Value | Source |
|---|---|---|
| Curated rows | 49,691 | T10 REPORT §1 |
| Tier A hero / B suspect / C grey / D clear | 3,858 / 9,559 / 25,569 / 10,705 | T10 REPORT §2 |
| Hero∩B overlap | 811 | T10 REPORT §2 |
| Unique visual-audit calls (B ∪ A) | 12,606 | 9,559 + 3,858 − 811 |
| Tier-C sample probes | ≈10,500 | plan §6.5 (3/site) |
| Vision-model price (opencode-go list) | in 0.15 / out 0.60 / cacheRead 0.003 per 1M tok | `models-store.json` |
| Image prompt tokens, 800×600 JPEG | **403** (measured, probe 2) | this session |
| Image prompt tokens, 1280×960 JPEG | **774** (measured, probe 3) | this session |
| Small text prompt | ≈60 tokens | measured (403 − image ≈ 380 @800px) |

Tokens scale roughly with pixel area: 0.48 Mpx → 403, 1.23 Mpx → 774. The project's
existing on-disk images are 800 px thumbnails (`THUMB_WIDTH = 800`), and `vlm_bytes()`
downscales originals to `VLM_MAX_SIDE = 1280` (`shorts_select.py`). Plan budget assumes
**~900 input tokens per image** (1280 path). Use 900 as the planning number.

## 2. Per-call token and dollar cost

Using 900 input tokens + ~40 output tokens (thinking off) per image, and a ~120-token
label prompt:

- input: (900 + 120) × 0.15 / 1e6 = **$0.000153**
- output: 40 × 0.60 / 1e6 = **$0.000024**
- **≈ $0.00018 per image**

With reasoning kept on (~200 reasoning tokens), output ≈ 230 → **≈ $0.00029 per image**.

## 3. Stage costs

| Stage | Calls | Tokens (in / out) | USD (list, thinking off) | USD (thinking on) |
|---|---|---|---|---|
| G0 persist stored verdicts | 0 | 0 | **$0** | $0 |
| G1 structured clearance | 0 | 0 | **$0** | $0 |
| G2 suspect (B) | 9,559 | 9.8 M / 0.38 M | ≈ **$1.7** | ≈ $2.7 |
| G3 heroes minus overlap | 3,047 | 3.1 M / 0.12 M | ≈ **$0.5** | ≈ $0.9 |
| G4 grey sampling | ≈10,500 | 10.7 M / 0.42 M | ≈ **$1.9** | ≈ $3.0 |
| **Total (G2–G4)** | **≈23,100** | **≈23.6 M / 0.9 M** | **≈ $4–5** | **≈ $7–8** |

**Dollar cost is not the binding constraint on the deepseek-vision transport** — the whole
audit is under $10 at list price. (The plan's "$0 on the MiniMax flat plan" still holds if
the MiniMax transport is used instead; then the binding constraint is the shared weekly
quota, plan §9.1.) A 4× safety multiplier for retries/oversized originals still lands under
$20.

## 4. Wall clock

Sequential single-call latency was not benchmarked here (**unverified**); the plan's
measured throughput anchor is ~10–14 concurrent workers (plan §9.1: "37 min at 10–14
parallel"). At a conservative 4 s/call:

- 23,100 calls ÷ 12 parallel × 4 s ≈ **7,700 s ≈ 2.1 h** of VLM time.
- Add Commons/Wikimedia fetches for G5 (API only, no VLM) and the escalation pass.

**Practical wall clock: one VPS night** for G2–G4 including escalation, plus retrieval
time. This matches the plan's "run VLM work from the VPS" instruction — the image bytes
are on the VPS, not in this repo (`public/data/images` holds no image files).

## 5. What each stage produces

- **G0** → `wiki_images.image_kind` + `is_excluded` for the 280 already-judged rows;
  end-to-end proof of the writer (migration 0019 → `apply_remediation_change` → journal →
  survives restart).
- **G1** → the existing tier assignment (`output/remediation/run_t10/findings.jsonl`),
  zero images cleared by VLM.
- **G2/G3** → per-image verdict `{kind, subject, people_prominent, text_or_overlay,
  quality, relevance, other_site, focus, vertical_crop_ok}`, mapped by `wiki_images.id`,
  persisted through `apply_remediation_change`.
- **G4** → same labels for the sample; a hit escalates the site's whole gallery.
- **G5** → new `wiki_images` rows for thin sites (Wikimedia API; no VLM).

## 6. Recommendation, costed

FIRST: G0 (≈$0, ~1 h) + a 200-image competence pilot (≈$0.04) + then G2/G3
(≈$2–3, one VPS night). NOT AT ALL: full 49,691-image pass (≈$9–15 and ~2× the wall clock
for images structured data already covers), and any workstation image pass (bytes not here).
