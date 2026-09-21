# PIECE 2 — the evidence-fetch stage

Stage "fetch" of the Phase-3 runner: it turns one prepared batch's census findings into the
evidence the finder stage reads, under decision 12's two binding fetch rules, and measures every
request in the project ledger. Nothing was committed. Working tree after this piece
(`git status --porcelain`):

```
 M scripts/remediation/phase3/run.py
?? scripts/remediation/phase3/fetch_stage.py
?? tests/remediation/test_phase3_fetch.py
```

| file | state | sha256 (verified on disk) | lines |
|---|---|---|---|
| `scripts/remediation/phase3/fetch_stage.py` | new | `7a3580a9ecfbcb1c0a47daf09ee37285891945726839877f16f4a644abcca45c` | 594 |
| `scripts/remediation/phase3/run.py` | modified (added `fetch`) | `b814a6023481f7556a96a00e314dc5b9628e47eecabd548190a11a80a284ef10` | — |
| `tests/remediation/test_phase3_fetch.py` | new | `e6bd5954d434054621e25248325c42e6a846e8f794ad98a7c156e287d5251acf` | 479 |

`ledger.py` and `model.py` are **unchanged** — no fleet vocabulary was re-spelled.

---

## 1. What was built

**`fetch_stage.py`** — `Fetcher` protocol (`get(url) -> FetchedPage`) + `HttpFetcher` (real httpx
client, redirects followed, injectable `httpx.BaseTransport` the same way `census/fetch.py` takes
one) + the pure target builder + the evidence store + `collect_batch`.

* **Decision 12, rule 1 — the cap.** `MAX_PAGE_BYTES = 60 * 1024` with the arithmetic written out
  in the comment (`60 x 1024 = 61,440`), because the sources say "60 KB" and never a byte count.
  It **stops the stream** (`_read_capped` returns·breaks at the cap); the page is never buffered in
  full and then sliced. `bytes` in the ledger is what was actually read, so a truncated page
  records 61,440 and its true length is *unknown* rather than guessed.
* **Decision 12, rule 2 — named features.** `assert_named_feature` refuses `/api/0.6/map?bbox=`
  (the pilot's 598 KB + 400 KB = 1.0 MB of 2.34 MB) and `out geom` (URL-unquoted before the check,
  so `out%20geom` is caught too). It guards the URL builders *and* `HttpFetcher.get`, so no caller
  can route around it. The only Overpass query built is name-filtered and `around`-based:
  `[out:json];(node["name"~"<name>",i](around:2000,<lat>,<lon>);way[...](around:2000,<lat>,<lon>););out center tags;`
  — the shape the pilot measured at 4.1 KB / 287 bytes against the 400 KB dump of the same box.
* **Driven by the findings.** `targets_for_site(record)`: the census check family decides *whether*
  to fetch (`T02` buys none — decision 12: one human vocabulary decision, not 112 reviews), the
  field decides *what* (`lat/lon` → `enwiki` + `overpass_named`, `name` → `enwiki` +
  `wikidata_search`, `country`/`description`/`card_description` → `enwiki`), and the record supplies
  the name and the stored point. A field no rule covers **raises** (`InputError`); a site with no
  `lat/lon` finding never gets an invented Overpass centre.
* **One ledger line per fetch**, `kind="fetch"`, carrying `url`, the site (through `label`, which is
  `f"{site_id}/{feature}"` — the pilot's `<site>/<feature>` shape with the stable id), the status
  actually observed and the bytes actually read. A non-2xx is data: `403/404/504/429` are appended
  to the report's `non_2xx` list and the batch continues.
* **A transport failure raises** (`TransportFailure`), inside the fetcher and through `collect_batch`;
  the CLI prints it and exits `2`. No empty result is ever returned.
* **Evidence files** under `<run_dir>/<batch_id>/evidence/<site_id>%2F<feature>.txt`, URL-encoded
  exactly like the pilot's `evidence/` (`quote(label, safe="")`), written to `.tmp` then replaced
  (the census cache's convention). **Existence is the record**: a target whose file is on disk is
  not fetched again, so a second run costs nothing and cannot pile up a second copy; it is reported
  as `skipped_existing`, not silently. Different bytes for an already-recorded target raise
  (`EvidenceConflict`) instead of overwriting.

**`run.py`** gained the `fetch` subcommand: `--run-dir`, `--batch-id` (required), `--ledger`,
`--stage` (`finder`/`reviewer`, the ledger's own enum), `--timeout`, and `--live`. **Without
`--live` it opens no socket and writes nothing** — it prints the targets, their reasons and their
URLs, so the cost of a batch is reviewable before it is paid. With `--live` it fetches, writes one
ledger line per fetch, one evidence file per fetch and `<batch_id>/fetch.json`.

---

## 2. The commands, with their real output

```
$ ./.venv/Scripts/python.exe -m pytest tests/remediation/test_phase3_fetch.py tests/remediation/test_phase3_runner.py -q -rs
..........................                                               [ 40%]
tests\remediation\test_phase3_runner.py ............................     [100%]
============================= 47 passed in 0.88s ==============================

$ ./.venv/Scripts/python.exe -m ruff check scripts/remediation/phase3/
All checks passed!

$ ./.venv/Scripts/python.exe -m ruff format --check scripts/remediation/phase3/
5 files already formatted

$ ./.venv/Scripts/python.exe -m mypy scripts/remediation/phase3/
Success: no issues found in 5 source files
```

19 of the 47 are new (the 28 are piece 1's, unchanged and still green). `PYTHONIOENCODING=utf-8`
was exported for these commands (the repo paths and the pilot's §-signs are non-ASCII).

**Offline CLI, on the real first batch of 15 sites** (temp run dir, nothing in the repo):

```
$ ./.venv/Scripts/python.exe -  # R.main(["fetch", "--batch-id", "batch-0001", ...]) without --live
exit code: 0
sites: 15 | targets: 36 | by feature: {'enwiki': 15, 'overpass_named': 13, 'wikidata_search': 8}
findings vs targets per site: [(3, 2), (3, 2), (3, 1), (3, 2), (3, 2), (3, 1), (4, 3), (4, 3), (3, 3), (3, 3), (3, 2), (3, 3), (3, 3), (3, 3), (3, 3)]
wrote ledger? False | wrote evidence? False | wrote report? False
```

36 fetches for 15 sites is **2.4/site** against the pilot's measured **15.2/site** — not a
like-for-like number (the pilot's 76 fetches included hand-driven research the runner will not
repeat), so it is an ordering, not a saving claim. Two sites have no `lat/lon` finding and so buy
no Overpass query; the 8 `wikidata_search` targets exist because the worklist carries **no Q-id**
(measured: 0 of the 2,210 findings' `note`/`current_value` contain `Q<digits>`), so the entity data
the pilot fetched by id has to be reached by search first.

---

## 3. Mutation evidence (every test shown able to fail)

Method: mutate `fetch_stage.py`, run the one test, restore the file from a byte copy, re-run the
test, compare sha256. All six mutations broke their test and every restore returned the same hash.

Harness output (verbatim):

```
sha256 before any mutation: 7a3580a9ecfbcb1c0a47daf09ee37285891945726839877f16f4a644abcca45c
tests: 6 mutations, file restored after each

M1 cap: buffer the page, then slice it
  mutated : exit=1 | ============================== 1 failed in 0.30s ==============================
  restored: exit=0 | ============================== 1 passed in 0.08s ==============================
  sha256 after restore == before: True  (7a3580a9ecfbcb1c...)
M2 non-2xx: raise instead of recording it as data
  mutated : exit=1 | ============================== 4 failed in 0.41s ==============================
  restored: exit=0 | ============================== 4 passed in 0.16s ==============================
  sha256 after restore == before: True  (7a3580a9ecfbcb1c...)
M3 transport failure: return an empty page instead of raising
  mutated : exit=1 | ============================== 1 failed in 0.28s ==============================
  restored: exit=0 | ============================== 1 passed in 0.09s ==============================
  sha256 after restore == before: True  (7a3580a9ecfbcb1c...)
M4 ledger: drop the one ledger.append per fetch
  mutated : exit=1 | ============================== 1 failed in 0.30s ==============================
  restored: exit=0 | ============================== 1 passed in 0.11s ==============================
  sha256 after restore == before: True  (7a3580a9ecfbcb1c...)
M5 re-run: fetch again although the evidence file is on disk
  mutated : exit=1 | ============================== 1 failed in 0.31s ==============================
  restored: exit=0 | ============================== 1 passed in 0.10s ==============================
  sha256 after restore == before: True  (7a3580a9ecfbcb1c...)
M6 decision 12: stop refusing raw geometry dumps
  mutated : exit=1 | ============================== 1 failed in 0.28s ==============================
  restored: exit=0 | ============================== 1 passed in 0.07s ==============================
  sha256 after restore == before: True  (7a3580a9ecfbcb1c...)

all 6 mutations broke their test; every restore returned the file to the same hash
```

| mutation | test that caught it |
|---|---|
| M1 `_read_capped` → `b"".join(chunks)` then slice | `test_the_cap_stops_the_stream_instead_of_buffering_the_page` (the counting stream showed all 614,400 bytes pulled, not ≤ 61,440 + 8,192) |
| M2 `if not page.ok: raise` | `test_a_non_2xx_is_recorded_as_data_and_never_raised` (all 4 statuses) |
| M3 `except httpx.HTTPError: return FetchedPage(status=0, ...)` | `test_a_transport_failure_raises_and_is_never_an_empty_result` |
| M4 remove the `ledger.append(...)` call | `test_one_ledger_line_per_fetch_carrying_the_site_the_url_the_status_and_the_bytes` |
| M5 `if store.exists(...)` → `if False:` | `test_a_second_run_skips_what_is_already_on_disk_and_duplicates_nothing` |
| M6 `assert_named_feature` → `return None` | `test_decision_12_refuses_the_two_raw_geometry_shapes_the_pilot_measured` |

No other file was touched by the harness: the sha256 above is the same hash the file has on disk
now, after all six mutations and restores.

---

## 4. The one live fetch

Exactly **one** HTTP request was made, through `HttpFetcher`, with a URL built by the new target
builder from the **real** first `WORKLIST.jsonl` record. Evidence, ledger line and report went to a
temp directory outside the repo (`C:\Users\marti\AppData\Local\Temp\phase3_smoke_3iegi__n`), so the
working tree stayed as listed above.

```
smoke site : 31860bc4-476a-49bc-9f97-e25220063d19 'Satsurblia Cave'
target     : 31860bc4-476a-49bc-9f97-e25220063d19/enwiki  (T01/coords lat/lon)
url        : https://en.wikipedia.org/w/api.php?action=query&prop=extracts%7Ccoordinates&explaintext=1&redirects=1&titles=Satsurblia%20Cave&format=json

RESULT     : HTTP 200 | 4356 bytes | truncated=False | 0.87s
sha256     : 1cbc7530d483cdb4...
evidence   : ...\phase3_smoke_3iegi__n\evidence\31860bc4-476a-49bc-9f97-e25220063d19%2Fenwiki.txt (4356 bytes on disk)
ledger line: {"at": "2026-09-21T05:52:34+00:00", "batch_id": "smoke-0001", "bytes": 4356, "cache_read_tokens": null, "cache_write_tokens": null, "http_status": 200, "input_tokens": null, "kind": "fetch", "label": "31860bc4-476a-49bc-9f97-e25220063d19/enwiki", "model": null, "output_tokens": null, "stage": "finder", "url": "https://en.wikipedia.org/w/api.php?action=query&prop=extracts%7Ccoordinates&explaintext=1&redirects=1&titles=Satsurblia%20Cave&format=json"}
head       : b'{"batchcomplete":"","query":{"pages":{"51631777":{"pageid":51631777,"ns":0,"extract":"Satsurbl'
```

**Real status: 200. Real byte count: 4,356.** That is byte-for-byte the pilot's own measurement for
the same request (`fetch_log.jsonl`, `Satsurblia/enwiki`: `"http": 200, "bytes": 4356`), which is a
genuine corroboration of the cap's not biting this page and of the UA being accepted.

---

## 5. Interpretations and deviations (each one named, none hidden)

1. **`"stage": "fetch"` in the deliverable.** The fetch line is written with `kind="fetch"`
   (the ledger's own `LedgerKind.FETCH`) and `stage` set to the audit stage that asked for it. Two
   reasons, both from the sources: `ledger.Entry` validates `stage` against `model.Stage`, which has
   exactly `finder`/`reviewer` — writing `"fetch"` needs a change to piece 1's model — and `COST.md`
   §1 splits its 76 fetches **by the `stage` field** (finder 62, reviewer 14) while
   `ledger.summarise` groups by stage. A `stage` of `"fetch"` would collapse the dimension the
   pilot reports with. The string `"fetch"` is on every fetch row as the `kind`, which is what a
   reader of `LEDGER.jsonl` sees. If the intent was literally the `stage` field, that is a piece-1
   contract change and a one-line follow-up, not something to decide silently here.
2. **61,440 = 60 x 1024 is an interpretation.** The brief and `COST.md` say "60 KB" and never a byte
   count; 60 x 1000 = 60,000 is the other reading and is not stated anywhere. The arithmetic is in
   the comment and pinned in the test.
3. **`NAMED_FEATURE_RADIUS_M = 2000`** is the pilot's own 2 km box (`COST.md` §3), the same box the
   400 KB dump covered; the pilot's named queries used `around:600`–`around:2000`. No new constant.
4. **No `final_url` in the ledger.** The pilot's `fetch_log.jsonl` carries it; `ledger.Entry` has no
   field for it and this piece does not extend piece 1's frozen line shape. A redirect is followed
   by the transport, so the line records the URL that was asked for and the final URL is recorded
   nowhere. That is a real gap against the pilot's shape, named here rather than papered over.
5. **`label` is `site_id/feature`, not the pilot's hand-written short tag** ("Satsurblia/wikidata"):
   the batch input carries the `site_id` and no stable short name, and a label derived from the
   mutable `name` column would move between runs.
6. **No retries.** One target is one fetch and one ledger line. The pilot's retried 504 appears as a
   *second* line in its own log; an automatic retry would be cost the ledger can see but the target
   builder did not plan. A transient non-2xx is therefore recorded and *skipped on the re-run*
   (existence is the record) — deleting the evidence file is how a human asks for that one page
   again.
7. **`T02` buys no fetch** (`NO_FETCH_PREFIXES`), per decision 12 / `COST.md` §7 item 5; that
   decision is visible in the report as a site with fewer targets than findings.
8. **Ledger line before evidence file.** The two cannot be written atomically; the line is fsynced
   first, so a crash leaves a *visible* measurement of a fetch that really happened, never an
   invisible one — the failure mode that would corrupt the measurement this ledger exists to
   replace the plan's two 2x-apart anchors with.

---

## 6. Unverified — labelled as such

* **The Overpass query shape was never run live.** The single permitted request went to the
  Wikipedia URL. Whether `[out:json];(node["name"~"…",i](around:2000,…);way[…]…);out center tags;`
  answers, and in how many bytes, is **unverified**; the nearest pilot measurement
  (`Petroglyph/overpass_stored_features`, a different shape, `around:600`) was 4,104 bytes.
* **The other 120 batches' target counts are unverified.** 36 targets / 15 sites is measured for
  `batch-0001` only (the worst-first top of the worklist, i.e. biased upward).
* **`run.py fetch --live` end-to-end was not run against the network** — running it would have made
  two more requests, and only one was allowed. The live path is covered by a monkeypatched
  `HttpFetcher`; the socket path is covered only by the one manual fetch above.
* **`Retry-After`, backoff and `maxlag` are not implemented** (deliberately: see §5 item 6), so
  nothing here verifies how Wikimedia or Overpass behave under load. `census/fetch.py` has that
  machinery; this stage does not use it.
* **A body of exactly 61,440 bytes is reported `truncated=True`.** Telling an exactly-capped page
  from a cut one needs a read past the cap, which the cap forbids. Documented in `_read_capped`; no
  source settles which is right.
* **The reviewer stage's own targets do not exist yet.** `--stage reviewer` sets the ledger's stage
  field only; the target rules in this piece are the census-driven finder set.
* **No database, no full backend suite** was involved; no integration test was run (they need
  Docker and production-like services, which this machine does not have).
