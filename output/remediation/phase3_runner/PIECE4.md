# PIECE 4 — a failed fetch is data, and the guard that fired correctly stays

Pieces 1–3 are committed. This piece fixes the defect the **first live batch** exposed, and it fixes
it where the batch actually died: in `fetch_stage`, not in front of the guard that fired correctly.

**Zero live HTTP requests and zero model calls were made in this piece.** Every fetch test drives a
`httpx.MockTransport`; every model test drives a recorded transcript through a scripted runner.

## The defect, as it happened

`phase3-run fetch --live` on `batch-0001` (run directory `output/remediation/phase3_runner/`):

```
GET https://overpass-api.de/api/interpreter?data=...[around:2000,...]: ReadTimeout: The read operation timed out
```

exit **2**. Then `phase3-run judge --live`:

```
the evidence file for overpass_named is not at .../31860bc4-...%2Foverpass_named.txt;
the model is never asked to judge evidence that is not on disk
```

exit **2**. And the ledger holds exactly **one** line for the whole batch — the Wikipedia fetch
(`http_status: 200`, `bytes: 4356`). The 40-second timeout on one target bought:

* no ledger line (so the batch's spend is unanswerable),
* no report (the run stopped before `write_report`),
* no continuing: the remaining Overpass targets of that site were never asked,
* no verdict either way — the site became unjudgeable.

At 13 Overpass targets per batch × 121 batches, that design could not finish a wave.

The cause is a rule, not a bug in the ordinary sense: the brief said *"a transport failure must
RAISE"*, and it did. What was missing is that a raise in the wrong place destroyed the record of
everything it had already learned. **The judge-time guard is not weakened by one line** — it still
raises, and there is a mutation below (M08) that proves it.

## What was built

| file | change |
|---|---|
| `scripts/remediation/phase3/fetch_stage.py` | `PHASE3_USER_AGENT`; `MAX_ATTEMPTS`/`RETRY_BACKOFF_SECONDS`/`RETRYABLE_STATUSES`/`OVERPASS_TIMEOUT`; `is_retryable_status`/`timeout_for`; `FetchAttempt`, `TargetOutcome` (with `failure`), `SiteEvidence.outcomes/requests/failed`, `BatchFetchReport.requests/failed/failures_by_site/totals.failed`; `one_attempt`/`_ask`; the retry loop in `collect_batch` with an **injectable `sleep`** |
| `scripts/remediation/phase3/ledger.py` | `FetchOutcome` (`ok`/`http_error`/`transport_failure`); `Entry.outcome`/`attempt`/`error`/`given_up`; `_check_fetch_attempt`; `StageTotals.fetch_failures` |
| `scripts/remediation/phase3/model_stage.py` | `PARTIAL_EVIDENCE_NOTE`, `FAILED_TARGET_MARKER`/`ABSENT_TARGET_MARKER`, `<failed_targets>` block; `read_fetch_failures`; `EvidenceExcerpt.failure`; `prepare_call`/`prepare_batch(failures=...)`; `SkippedSite` + `unverifiable_findings`; the skip in `judge_batch` |
| `scripts/remediation/phase3/run.py` | `cmd_status` tolerates an absent run dir/plan/ledger; `_ledger_state`; `cmd_fetch` lost its `TransportFailure` → exit 2 handler; `cmd_judge` reads `fetch.json` for failures (dry run included) |
| `tests/remediation/test_phase3_fetch.py` | +7 tests; the transport-failure test, the non-2xx test and the fetch CLI test rewritten |
| `tests/remediation/test_phase3_model.py` | +6 tests; 2 updated (prompt trailing block, fetch-line guard) |
| `tests/remediation/test_phase3_runner.py` | +4 tests; 2 rewritten (`status`, the `_fetch()` helper) |

```
 scripts/remediation/phase3/fetch_stage.py | 356 +++++++++++++++++++++++++++---
 scripts/remediation/phase3/ledger.py      | 124 ++++++++++-
 scripts/remediation/phase3/model_stage.py | 274 +++++++++++++++++++++--
 scripts/remediation/phase3/run.py         |  98 +++++---
 tests/remediation/test_phase3_fetch.py    | 237 ++++++++++++++++++--
 tests/remediation/test_phase3_model.py    | 310 +++++++++++++++++++++++++-
 tests/remediation/test_phase3_runner.py   | 187 +++++++++++++++-
 7 files changed, 1457 insertions(+), 129 deletions(-)
```

### [A] One attempt, one ledger line — failures included

`one_attempt` writes the line **before** storing the page (piece 2's order, unchanged) and never
lets a transport failure propagate out of the target loop:

```
GET <url> could not be asked  ->  Entry(outcome="transport_failure", http_status=None,
                                       error="GET <url>: ReadTimeout: ...", attempt=1..3,
                                       given_up=<last attempt>)
GET <url> answered 502/429/…   ->  Entry(outcome="http_error",        http_status=502, bytes=N, …)
GET <url> answered 200         ->  Entry(outcome="ok",                http_status=200, bytes=N, …)
```

So the ledger answers both questions the brief puts to it. On the honest transcript of the live
failure (`test_a_transport_failure_is_recorded_and_the_next_target_is_still_asked`): **how many
requests did this batch spend** → `total.fetches == 4` (3 attempts on the dead target + 1 on the
next), **how many bought nothing** → `total.fetch_failures == 3`. The live run above would have
read `fetches: 1, fetch_failures: 3` instead of `ledger`-with-one-line.

`LedgerError` is unchanged in spirit and stricter in detail: a fetch line must carry an `outcome`;
`http_status` is required **iff** a response arrived (100–599) and forbidden for a transport
failure; `error` is required **iff** no response arrived; `attempt` is 1-based; `given_up` is a
recorded fact, not something a reader infers. A legacy line without `outcome` (the one real line in
`output/remediation/phase3_runner/LEDGER.jsonl`) is counted in `fetches` and in **neither** the
failure nor the success bucket — counting it as a failure would invent one.

**Interpretation, labelled:** the brief counts attempts by ledger *lines*. I did **not** add a
field to piece 1's frozen model-call contract, and no line carries a computed attempt count; the
count is `sum(1 for line in ledger)`, which is what "one line per attempt" means. Chainability
(`write_batch_id`) and the model-call validation are untouched.

### [B] Bounded retry, recorded, injectable sleeper

```
MAX_ATTEMPTS = 3                       # the brief's own number: "at most twice (3 attempts total)"
RETRY_BACKOFF_SECONDS = (1.0, 3.0)     # INTERPRETATION - see below
RETRYABLE_STATUSES = frozenset({408, 429})
```

Retried: a transport failure, `408`, `429`, and every `5xx` (the brief's "429/5xx"; `408` is the
same class of answer as `429` for a read timeout). Not retried: `400`, `403`, `404` — the same
question gets the same answer, and asking twice would buy it twice
(`test_a_429_is_retried_and_a_400_is_not`: the 400 target is asked once, the 429 target three times,
and the pauses observed are exactly `(1.0, 3.0)`). One line per attempt, `attempt=1,2,3`,
`given_up` false/false/true, the last one carrying the reason the target was given up on.

**No fallback endpoint and no silent host rotation**: the retry re-asks the *same URL*
(`test_the_same_url_is_asked_again_and_no_other_host_is_tried` asserts one distinct URL, three
times, all under `OVERPASS_ENDPOINT`). The pilot's hand-fallback to `overpass.kumi.systems` stays a
decision for the operator.

**`RETRY_BACKOFF_SECONDS = (1.0, 3.0)` is my interpretation, and no source states it.** The brief
says "a short backoff" and names no figure. The only measured anchor on disk: `fetch_log.jsonl` has
the failed 504 at `2026-09-20T22:21:01Z` (`Pannonian/overpass_stored_point`) and its successful
re-ask at `22:21:21Z` — a 20 s gap that *contains* the request, so it reads as "the pilot waited on
the order of seconds", not as a delay to copy. 1 s then 3 s is bounded, short and recorded in one
constant. The sleeper is injected (`collect_batch(..., sleep=...)`); the tests pass `list.append`,
so **no test sleeps**, and a real run uses `time.sleep`.

### [C] Partial evidence is named; no evidence buys no call

`read_fetch_failures` reads the batch's own `fetch.json` (`site_id -> {feature: reason}`). It then
splits three cases that used to collapse into one:

| case | what happens |
|---|---|
| file on disk | read into the prompt, `status="present"` |
| file absent, **and the fetch report records why** | prompt carries `<failed_target feature=… url=… reason=… />` in a `<failed_targets>` block plus `PARTIAL_EVIDENCE_NOTE`; `status="failed"` in the evidence block; the model can answer `unverifiable` about exactly that target |
| file absent, **nothing recorded** | `EvidenceUnusable` — unchanged, and proven by mutation M08 |

Then, per site:

* **at least one target present** → the call is made, and the prompt names what failed;
* **no evidence at all** → **no model call**, and one `unverifiable` `Finding` per census finding of
  that site (`findings`/`test_id`/`field`/`severity`/`current_value` read from the site's own input
  record, `verdict=UNVERIFIABLE`, `defect=False` derived, `note=<the reason>`), recorded in the
  batch report (`model.json`, `skipped`) and printed by `judge --live`.

The reason names every failed target with its own error text ("`no evidence file was read for this
site (no model call bought): enwiki: …ReadTimeout…; overpass_named: …`"), so "could not look" never
reads as "looked and found nothing".

**Interpretation, labelled — the skipped call is a report line, not a ledger line.** In the ledger,
a `model_call` line *is* a measurement: tokens, cache reads, the provider's own cost. A call that
was never made has no measurement, and writing one would mean inventing tokens and a price. The
ledger therefore gains **no new kind**; the skip is written where the other per-batch records live
(`model.json` → `skipped[]`, `totals.unverifiable_findings`). If the operator wants skips in the
ledger itself, that is a new line kind and a decision to take — it is *not* implied by "recorded
with a reason", and I did not take it silently.

### [D] `status` on a fresh run directory

`cmd_status` used to raise `FileNotFoundError("nothing has been prepared")` before printing a
single figure. Now a missing run dir, plan or ledger is a **fact**:

```
$ .../run.py status --run-dir <fresh>/runs --ledger <fresh>/LEDGER.jsonl
{
 "batches_with_input": [], "batches_with_result": [], "exists": false,
 "ledger": {"lines": 0, "measured": false, "stages": {},
            "reason": "no ledger at ...\\LEDGER.jsonl: nothing has been measured yet",
            "total": {"fetches": 0, "fetch_failures": 0, "model_calls": 0, "cost_usd": 0.0, ...}}
}
rc=0
```

`ledger.read_entries` **keeps raising** (`FileNotFoundError`) and `L.summarise` keeps raising — only
the status command handles "no ledger yet", and it says `measured: false` plus the reason rather
than reporting a zero it did not measure. A ledger that exists but cannot be read is a **different**
fact and still raises (`test_status_still_raises_on_a_ledger_it_cannot_read`: a truncated line →
`LedgerError: not JSON`); an unreadable ledger must never look like an empty one. The same run
against the **real** run directory (one legacy line, no `outcome` field) is below.

### Point 1 of the steering note — the User-Agent: no defect found, pinned instead

`output/remediation/phase3_pilot/evidence/Didnauri%2Foverpass_shiraki.txt` is 89 bytes:
*"Please include a meaningful User-Agent string with your requests to avoid rate-limiting."* The
steering note read that as this runner sending no user agent. **It does not.** `pipeline`-side
`census/fetch.py` already defines

```python
USER_AGENT = "AncientNerdsSiteAudit/1.0 (https://ancientnerds.com; database audit; ancient.nerds@protonmail.com)"
```

and `fetch_stage` has imported it since piece 2 — `HttpFetcher` passes it as the client's header.
So there is **no defect of that kind to fix**, and inventing one would have been the fabrication the
brief forbids. What I did instead is make it explicit and testable:
`PHASE3_USER_AGENT = USER_AGENT` with the 89-byte sentence quoted in the comment, plus a test that
reads the header off the wire (`test_every_request_carries_the_projects_identifying_user_agent`).

Two facts that must not be merged, both from the log: the JSONL shows that 89-byte body arriving
with **HTTP 429 from `overpass.kumi.systems`** (the pilot's hand-fallback mirror), so it is the
service's rate-limit body — and 429 is now retried and recorded. **Unverified, labelled:** whether
this project's exact string satisfies overpass-api.de is *not* tested here (that needs a live
request, forbidden in this piece). The test asserts *what is sent*, not *what is accepted*.

### Point 2 — "succeeded and found nothing" is a result

A 200 with an empty result is `outcome="ok"`, the body is stored, and `fetch_failures` does not
count it (`test_an_empty_result_is_a_success_while_a_failure_is_not`). The three states stay apart
everywhere: `transport_failure` (no response), `http_error` (a response that says no), and `ok`
(including "nothing there" — Overpass `"elements": []`).

**Correction to the steering note:** the file it named as the empty result,
`Karpasia%2Foverpass_site.txt`, is 465 bytes and contains **one** element (node *Ayios Philon Roman
harbor*) — it is a *hit*, not an empty answer. The genuinely empty files are
`Petroglyph%2Foverpass.txt` and `Petroglyph%2Foverpass_bbox.txt` (287 bytes each, valid JSON,
`"elements": []`), and `Didnauri%2Foverpass_area.txt` (695 bytes) is XHTML, i.e. a refusal body, not
JSON at all. The distinction the note asks for is real and is implemented; the example file was the
wrong one.

### Point 3 — Overpass stays, bounded, as the second opinion

`OVERPASS_TIMEOUT = 20.0` (versus the client's own `--timeout`, 40 s) is applied per target through
the request extension, so only `overpass-api.de` is cut short
(`test_the_overpass_target_gets_the_shorter_timeout_and_the_others_do_not`). Wikipedia's
`prop=extracts|coordinates` already carries the article's coordinate claim, and two of the three
pilot sites had a `coordinates` field, so a dead Overpass no longer makes a site unverifiable when
the enwiki evidence answered the question — that is exactly the partial-evidence path of [C].
`OVERPASS_TIMEOUT = 20.0` is **my interpretation** (a chosen bound): what is measured is only that
the batch lost the request to a read timeout at 40 s.

## Gates — real output

```
$ ./.venv/Scripts/python.exe -m pytest tests/remediation/ -q -rs
======================= 603 passed in 86.79s (0:01:26) ========================
    (no skips, so -rs printed nothing; 17 test functions are new in this piece, 3 obsolete ones
     were replaced and 4 rewritten in place. The three phase-3 modules now collect 79 tests:
     fetch 23, model 25, runner 31 - `--collect-only`.)

$ ./.venv/Scripts/python.exe -m ruff check scripts/remediation/phase3/
All checks passed!                                        rc=0

$ ./.venv/Scripts/python.exe -m ruff format --check scripts/remediation/phase3/
6 files already formatted                                 rc=0

$ ./.venv/Scripts/python.exe -m mypy scripts/remediation/phase3/
Success: no issues found in 6 source files                rc=0

$ ./.venv/Scripts/python.exe -m vulture scripts/remediation/phase3/ .vulture_whitelist.py --min-confidence 80
                                                          rc=0  (no findings)
```

`ruff format --check` first said `Would reformat: model_stage.py`; the file was formatted and **the
whole mutation sweep below was re-run afterwards**, so every hash refers to the final bytes. Two
things I did *not* hide: (1) `ruff check tests/remediation/` reports one **pre-existing** `UP032` at
`test_phase3_model.py:286` — it is in `git show HEAD:` too, and CI lints only `api/ pipeline/`;
(2) `ruff format --check tests/remediation/` has been red since before this piece (12 files,
8 of them untouched by me) — so the gate is quoted only for `scripts/remediation/phase3/`, where it
was green before and is green now.

`status` against the real, already-written run directory — the legacy line (no `outcome`) is
counted as a fetch and as **no** failure, and the report is readable:

```
$ .../run.py status --run-dir output/remediation/phase3_runner/runs \
      --ledger output/remediation/phase3_runner/LEDGER.jsonl \
      --plan output/remediation/phase3_runner/PLAN.jsonl
rc=0
 "batches_with_input": ["batch-0001"], "batches_with_result": [], "exists": true,
 "planned_batches": 121, "planned_sites": 1813,
 "ledger": {"lines": 1, "measured": true, "total": {"fetches": 1, "fetch_failures": 0,
   "fetch_bytes": 4356, "model_calls": 0, "cost_usd": 0.0,
   "first_at": "2026-09-21T06:17:36+00:00", "last_at": "2026-09-21T06:17:36+00:00"}}
```

## Mutation evidence: every new test was shown able to fail

`%TEMP%/mutate2.py` (scratch, not committed) replaces one anchored string per mutation, runs the
named test node, restores the file from memory and re-checks the sha256. Every mutation reddens
**exactly** the test written for it, and every file is byte-identical after the sweep:

| mutation | file | red test | pytest | sha256 after restore |
|---|---|---|---|---|
| M01 no retry at all (`last = True`) | `fetch_stage.py` | `…test_a_429_is_retried_and_a_400_is_not`, `…test_a_transport_failure_is_recorded_…` | 2 failed | `6a8578ac76ad…` unchanged |
| M02 transport failure re-raised | `fetch_stage.py` | `…test_a_transport_failure_is_recorded_and_the_next_target_is_still_asked` | 1 failed | `6a8578ac76ad…` unchanged |
| M03 no identifying User-Agent | `fetch_stage.py` | `…test_every_request_carries_the_projects_identifying_user_agent` | 1 failed | `6a8578ac76ad…` unchanged |
| M04 Overpass no longer bounded | `fetch_stage.py` | `…test_the_overpass_target_gets_the_shorter_timeout_and_the_others_do_not` | 1 failed | `6a8578ac76ad…` unchanged |
| M05 429 treated as stable | `fetch_stage.py` | `…test_a_429_is_retried_and_a_400_is_not` | 1 failed | `6a8578ac76ad…` unchanged |
| M06 failed targets not named in the prompt | `model_stage.py` | `…test_a_partially_failed_site_still_gets_a_call_and_the_prompt_names_the_failure` | 1 failed | `dcfc70408ab4…` unchanged |
| M07 no-evidence site still buys a call | `model_stage.py` | `…test_a_site_no_evidence_reached_is_recorded_unverifiable_without_a_model_call` | 1 failed | `dcfc70408ab4…` unchanged |
| M08 absent evidence with nothing recorded is judged anyway | `model_stage.py` | `…test_a_missing_evidence_file_with_no_recorded_failure_still_raises` | 1 failed | `dcfc70408ab4…` unchanged |
| M09 unreadable fetch report reads as empty | `model_stage.py` | `…test_read_fetch_failures_reads_what_the_fetch_stage_wrote` | 1 failed | `dcfc70408ab4…` unchanged |
| M10 `status` raises on a fresh run dir again | `run.py` | `…test_status_reports_a_fresh_run_directory_as_a_state_not_an_error` | 1 failed | `2acf6511b753…` unchanged |
| M11 an attempt that bought nothing is counted nowhere | `ledger.py` | `…test_the_ledger_counts_how_many_attempts_bought_nothing` | 1 failed | `eb22a7549d80…` unchanged |

Final hashes of the seven touched files:

```
6a8578ac76ad62c826d7082c65c928742333eeec84c1c684d06df10fbc19dd7d  scripts/remediation/phase3/fetch_stage.py
eb22a7549d80cfd7619d15308507b4cb0009520d03345acef77c94c136cf99e3  scripts/remediation/phase3/ledger.py
dcfc70408ab477c0f0dca14284cc071572ea9d03b188a4a6bb58d6534e387968  scripts/remediation/phase3/model_stage.py
2acf6511b753ddefad5b442b1495a8826c1af453ee1aed4bb67d8bcd42d649fc  scripts/remediation/phase3/run.py
e8ca17eed7e366d2a5816b5e74edbdab88a77fcd5bbdf95eb6a5756632866914  tests/remediation/test_phase3_fetch.py
c770a5fa43e0554e266796882d5809e72032bfc9819e8bc297af19c29a027b1f  tests/remediation/test_phase3_model.py
0f479b465dff92cc61e177351c3f7e2514cfd2dc7769b609fb755527ab3ebadc  tests/remediation/test_phase3_runner.py
```

`git grep -n MUTANT -- scripts/remediation/phase3 tests/remediation` → no match: nothing was left
behind. One side effect worth naming: the sweep's restore wrote `run.py` with LF endings (it had
CRLF on disk); that is the `2acf…` hash, and `git diff --stat` still shows the intended 67/31 lines
rather than a whole-file rewrite.

## Not verified — labelled

* **No live HTTP request and no model call were made.** That a real Overpass read timeout reaches
  `_ask` as `TransportFailure` is *assumed from the live failure's own text*; that the retry's 1 s/3 s
  help a rate-limited mirror is not measured at all.
* **The backoff and `OVERPASS_TIMEOUT` are chosen bounds**, not measurements (see above). The one
  number with a source is the brief's "3 attempts".
* **Whether `overpass-api.de` accepts this project's User-Agent** is untested — the 89-byte body on
  disk arrived with 429 from a mirror, so it is evidence about the mirror, not about the UA header's
  acceptability.
* **The skipped-site `unverifiable` findings are not yet part of a census report.** The next piece
  parses model answers into `Finding` records; the ones written here (no answer to parse) will have
  to meet that path, and only then is the round trip complete.
* **`status`'s zero figures** are a sum over an absent file, i.e. arithmetic on nothing, which is
  what the brief asked for; they are *not* a claim that nothing was spent.
* **The real run directory was read, not advanced**: `status` is the only command run against
  `output/remediation/phase3_runner/`; no ledger line was added and no evidence file was touched.

## State of the tree

Nothing is committed, nothing is staged (`git diff --cached` is empty). Only
`scripts/remediation/phase3/` and `tests/remediation/` were touched. The working tree still has the
first live batch's one-line `LEDGER.jsonl`, its 4,356-byte Wikipedia evidence file and
`runs/batch-0001/input.json` — kept as the record of the defect, exactly as they are.

## Next piece

1. **Re-run the first live batch** (`fetch --live` then `judge --live` on `batch-0001`) and read the
   report: `totals.failed` should now name the Overpass target, `totals.requests` should be 3 for it,
   `fetch_failures` should be 2–3, and `judge` should either call the model with a
   `<failed_targets>` block (enwiki evidence is on disk for that site) or record an `unverifiable`
   finding with the reason. That run is the measurement this piece cannot be.
2. **Parse answers into `Finding` records** (piece 5), merging the two sources of findings: the
   model's answer per site, and the `unverifiable` findings the skip path already emits.
3. **Decide, explicitly, whether a skipped call gets a ledger line kind of its own** — see the
   labelled interpretation in [C]; the answer decides whether `model.json` stays the only place a
   skip is visible.
4. **Batch-level budget guard**: with retries, one batch can now spend up to 3× its target count.
   `COST.md`'s per-batch arithmetic should be recomputed against the retry bound before the 121-batch
   wave, so the wave's cost ceiling is a decision rather than a surprise.
