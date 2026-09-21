# PIECE 3 — the model-call driver, with measured tokens and measured cost

Piece 1 (schema, ledger, offline plan) and piece 2 (evidence fetch) are committed (HEAD
`aa8ed1e`). This piece adds the stage that actually spends money, tested end to end against
captured transcripts and never against a live model.

**Zero live model calls were made in this piece.** The two fixtures are the captures that already
existed on disk, copied out of the gitignored `output/remediation/logs/`:

| fixture | bytes | sha256 | what it is |
|---|---|---|---|
| `tests/remediation/fixtures/pi_probe_no_extensions.json` | 8,984 | `ee59415be06e86e71f5a323625529d928b1b17116b93121f987ccc6d1be2c3b6` | the trace of **the argv this module builds** (`-ne`): `input=437`, `cost.total=6.615e-05`, every line a JSON event |
| `tests/remediation/fixtures/pi_probe2.json` | 17,592 | `eb33f38164036e06d590eb11adeb58ca86701f776ad0588d4f18030310f76581` | the earlier probe, extensions loaded and both streams merged; its last line is the OSC 777 notifier of `~/.pi/agent/extensions/10-benachrichtigung.ts` followed by `{"type":"agent_settled"}` |

Both copies are byte-identical to their sources (`sha256sum` above, originals in
`output/remediation/logs/`).

## What was built

| file | change |
|---|---|
| `scripts/remediation/phase3/model_stage.py` | **new.** `ModelRunner` protocol, `PiRunner` (the real driver), `parse_stream`, `Usage`/`ModelAnswer`/`ModelCall`/`Prompt`/`PreparedCall`/`BatchModelReport`, `prepare_call`/`prepare_batch`, `judge_site`/`judge_batch`, `write_report` |
| `scripts/remediation/phase3/run.py` | new `judge` subcommand; **dry run unless `--live`** |
| `scripts/remediation/phase3/ledger.py` | new optional `Entry.cost_usd` (model calls only) and `StageTotals.cost_usd`; the "USD is not computed" paragraph now records the provider's own figure |
| `tests/remediation/test_phase3_model.py` | **new.** 19 tests, no network, no model call, no database |
| `tests/remediation/fixtures/*.json` | two captured transcripts, copied verbatim |

### The transport, as measured — and why every flag is in the argv

```
pi -p --mode json -ne -nt -nc --no-session --model opencode-go/deepseek-v4.1-flash --thinking off <prompt>
```

`PI_FLAGS = ("-p", "--mode", "json", "-ne", "-nt", "-nc", "--no-session")`, built into a **list**
by `pi_argv()` and handed to `subprocess.run(..., shell=False)`. No command line is ever
string-formatted, so a metacharacter in a site name or in page text is data, not syntax (test 7
uses `site "Ötzi" $(rm -rf /) && echo | done` as the prompt and asserts it arrives as exactly one
undivided element).

`-ne` carries the measurement that has to stay visible next to the code, because dropping it to
"simplify" re-buys this: two live calls with an identical prompt, same model --

```
extensions loaded : 14,013 ms wall, input 2,271 tokens, cost $0.00034125
with -ne          :  2,698 ms wall, input   437 tokens, cost $0.00006615
```

i.e. **~1,830 input tokens, 5.2x the money and 5x the wall time on every single call.** These four
numbers were measured by the supervisor on 2026-09-21, not estimated, and they are quoted in the
comment above `PI_FLAGS`. The same probe pair is also what makes the fixture choice:

* the `-ne` capture parses line by line with no filtering at all (15 lines, all JSON), so it is
  the fixture every happy-path test uses;
* the with-extensions capture does not, and it is the fixture the "unparsable line raises" test
  uses - the real artefact, uncut, instead of a synthetic broken line.

`--thinking off` and `-nt`/`-nc` are the design: the model only judges text the runner already
fetched, so it needs no tool, no `CLAUDE.md`/`AGENTS.md` (the measured ~31,500-token fixed
overhead) and no reasoning budget.

**The launcher is platform data, resolved once.** On Windows the installed `pi` is a POSIX sh
script; measured 2026-09-21: `subprocess.run(["pi", "--version"])` → `FileNotFoundError [WinError
2]`, `subprocess.run(["pi.cmd", "--version"])` → rc 0, `0.86.1`. The `.cmd` shim execs the same
`dist/bundle/cli.js` with the same arguments, so `PROGRAM = "pi.cmd" if os.name == "nt" else "pi"`
changes the launcher only. The argv stays a list either way.

### What is recorded, and what is never invented

One ledger line per call, through `ledger.append`, `kind=model_call`, `stage=finder|reviewer`,
`label=<site_id>/<stage>` (the fetch stage's `<site>/<feature>` shape), carrying `input_tokens`,
`output_tokens`, `cache_read_tokens`, `cache_write_tokens` **and `cost_usd` — the provider's own
`cost.total`, verbatim.** Piece 1 left dollars out because a price table would have been an
assumption; the provider reports the real number, so it is recorded and **no price is ever applied
to a token count** — the test pins both directions (`cost_usd == 6.615e-05` from the capture, and
`!= 437 * 0.15e-6 = 6.555e-05`, which is what a price table would have produced).

Unit check, so `cost_usd` is not a name that asserts something unverified: the captured `0.000342`
for 2,276 input tokens matches deepseek-v4.1-flash's $0.15/M input (0.15 x 2276 / 1e6 = 0.000341).

Fail-closed, all of it raising and none of it defaulting:

* non-zero exit → `ModelCallFailed` (stderr tail in the message, nothing read from it);
* missing `message_end` usage block → raise (never zero-fill);
* unparsable line, two settled usages in one stream → raise;
* empty assistant text → raise;
* no assistant `message_end` at all → raise;
* a subprocess that hangs → `subprocess.run(timeout=)` kills the child, the kill is turned into
  `ModelCallFailed`, the batch stops;
* absent evidence file in a live call → raise; evidence over `MAX_EVIDENCE_CHARS` → raise (silent
  truncation would judge a page the model never saw);
* **no retry anywhere.** A re-run of the stage is a second `judge` invocation and writes its own
  ledger lines, so the second charge is visible instead of hidden.

The line is written **before** the answer file: a crash after the call leaves the money visible.

### Prompt construction

One call per site, in batch order, with two blocks that `Prompt.render()` joins into the single
argv element (the transport takes one prompt argument, so the question travels as a labelled
block):

```
<question>
Is the site's stored value for the flagged field wrong, given only the evidence in this message?
Answer yes or no, then name the evidence that decides it in one sentence. You propose; you do not write.
</question>

<site id="31860bc4-476a-49bc-9f97-e25220063d19" name="Satsurblia Cave">
<finding test_id="T01/coords" field="lat/lon" severity="moderate" current_value="[42.37726777374251, 42.60097658321723]">Wikidata P625 is 1.28 km from the stored point …</finding>
…
</site>
<evidence feature="enwiki" url="https://en.wikipedia.org/w/api.php?…">
…the bytes piece 2 stored…
</evidence>
```

The question is the finder brief's own frame (`FINDER_BRIEF.md`: "You are the finder … You
propose; you do not write") and for the reviewer its job sentence (`REVIEWER_BRIEF.md`: "try to
refute every single one"); the two are pinned as different by a test. The evidence is read from
the path `fetch_stage.EvidenceStore` already defines - one spelling, no second store.

`MAX_EVIDENCE_CHARS = 2300 * 4 = 9,200` is **an interpretation, not a measurement**, and named as
such in the code: the brief sets this transport's design point at "~2,300 input tokens", and 4
characters per token is the usual reading. It is a bound, not a target.

## Dry run of the first 15-site batch (no model call)

```
$ export PYTHONIOENCODING=utf-8
$ ./.venv/Scripts/python.exe scripts/remediation/phase3/run.py plan
{ "batch_size": 15, "batches": 121, "sites": 1813, … }
$ ./.venv/Scripts/python.exe scripts/remediation/phase3/run.py prepare --batch-id batch-0001
{ "batches": 1, "written": ["batch-0001"], … }
$ ./.venv/Scripts/python.exe scripts/remediation/phase3/run.py judge --batch-id batch-0001 > …/piece3_dryrun_batch1.json
rc=0, 107,497 bytes, stderr empty
```

The exact argv of call 1 (13 elements, the last one the prompt) and the exact prompt text are in
`output/remediation/logs/piece3_dryrun_batch1.json`; shortened here:

```
argv = ["pi.cmd", "-p", "--mode", "json", "-ne", "-nt", "-nc", "--no-session",
        "--model", "opencode-go/deepseek-v4.1-flash", "--thinking", "off", "<prompt as below>"]
```

Prompt sizes of all 15 calls (evidence not fetched yet, so each `<evidence>` block renders
`[absent: …]`; a live call refuses to judge that state):

| site (first 8) | prompt chars | evidence targets |
|---|---|---|
| 31860bc4 | 2,302 | enwiki, overpass_named |
| 8c39badd | 2,705 | enwiki, overpass_named |
| db85cd62 | 1,946 | enwiki |
| e2dbb087 | 2,403 | enwiki, overpass_named |
| 593de422 | 2,291 | enwiki, overpass_named |
| 3dd0bac8 | 1,944 | enwiki |
| a939e800 | 3,276 | enwiki, overpass_named, wikidata_search |
| dbbef6f8 | 3,336 | enwiki, overpass_named, wikidata_search |
| d6d44645 | 2,934 | enwiki, overpass_named, wikidata_search |
| 4c5103a2 | 3,005 | enwiki, overpass_named, wikidata_search |
| 7759e372 | 2,596 | enwiki, overpass_named |
| 8747ac16 | 2,928 | enwiki, overpass_named, wikidata_search |
| b42c7181 | 3,000 | enwiki, overpass_named, wikidata_search |
| 109fcdea | 2,680 | enwiki, overpass_named, wikidata_search |
| e8a07988 | 3,250 | enwiki, overpass_named, wikidata_search |

Reading that table is the point of the dry run, and it says something the brief should hear: the
**site record alone is 1,944–3,336 characters**, before a single byte of evidence. That is roughly
500–850 tokens of record (at 4 chars/token) on top of pi's own ~400-token prompt, so a call cannot
come in at ~2,300 input tokens for the sites with three findings unless the evidence stays small.
The 9,200-character evidence bound is therefore looser than the design point; the number that will
settle this is one instrumented call per site, which is exactly what `judge --live` records. The
dry run started no process (proved by mutation M19 and by a test that fails if `subprocess.run` is
reached at all).

## Gates — real output

```
$ ./.venv/Scripts/python.exe -m pytest tests/remediation/ -q -rs
======================= 590 passed in 73.33s (0:01:13) ========================
    (571 before this piece + 19 new; no skips, so -rs printed nothing)

$ ./.venv/Scripts/python.exe -m ruff check scripts/remediation/phase3/
All checks passed!

$ ./.venv/Scripts/python.exe -m ruff format --check scripts/remediation/phase3/
6 files already formatted

$ ./.venv/Scripts/python.exe -m mypy scripts/remediation/phase3/
Success: no issues found in 6 source files
```

(`ruff format --check` first reported `Would reformat: model_stage.py`; the file was formatted and
the **entire mutation sweep was re-run afterwards** on the formatted sources, so the hashes below
refer to the final bytes.)

## Mutation evidence: every test was shown able to fail

`output/remediation/logs/mutation_sweep_piece3.py` (scratch, not committed) edits a source, runs
the test file, restores the file from memory and re-checks the hash. Full log:
`output/remediation/logs/piece3_mutation_sweep.txt`.

Baseline before the sweep: `19 passed`. After the sweep, all three touched files are
**byte-identical** to their pre-sweep state:

```
d7343da1d0bb55216fcb9b16f10590a8d9c7ecf0ca24b8d7218d8d397feeb44b  scripts/remediation/phase3/ledger.py  unchanged
0dca215ef9c969f7567214ada71510b32941df1a290fd07e105b3203cc2ae425  scripts/remediation/phase3/model_stage.py  unchanged
b8cd95fce00e65d6e6050e545f8c8cbd420f11e6a3057bf920e6282037667713  scripts/remediation/phase3/run.py  unchanged
all files restored byte-identically: True
```

| mutation | red test(s) | pytest |
|---|---|---|
| M01 argv loses `-ne` | `test_the_argv_is_a_list_with_the_measured_flags_and_the_exact_model_id` | 1 failed, 18 passed |
| M02 partial `message_update` read as settled | `test_usage_is_read_from_message_end_and_not_from_a_partial_update` | 1 failed |
| M03 missing usage defaulted to zero | `test_a_missing_usage_block_raises` | 1 failed |
| M04 non-zero exit ignored | `test_a_non_zero_exit_raises` | 1 failed |
| M05 no timeout passed to subprocess | `test_a_hung_process_is_killed_and_raises` | 1 failed (6.30s vs 3.7s) |
| M06 unparsable line skipped | `test_an_unparsable_line_raises_on_the_real_merged_capture` | 1 failed |
| M07 empty assistant text accepted | `test_empty_assistant_text_raises` | 1 failed |
| M08 no settled message returns an empty answer | `test_a_stream_without_a_settled_assistant_message_raises` | 1 failed |
| M09 reported cost dropped from the ledger line | `test_exactly_one_ledger_line_per_call_records_tokens_and_the_reported_cost` | 1 failed |
| M10 `shell=True` at the subprocess call | `test_the_runner_passes_the_argv_list_without_a_shell` | 1 failed |
| M11 two calls per prepared site | `test_exactly_one_ledger_line_per_call_records_tokens_and_the_reported_cost` | 1 failed |
| M12 a failed call is caught and skipped | `test_a_run_stops_at_the_first_call_it_could_not_measure`, `test_judge_live_reports_a_call_it_could_not_measure_with_exit_2` | 2 failed |
| M13 absent evidence tolerated in a live call | `test_a_call_refuses_evidence_that_is_not_on_disk` | 1 failed |
| M14 evidence bound disabled | `test_an_oversized_evidence_block_raises_instead_of_being_truncated` | 1 failed |
| M15 both stages ask the finder's question | `test_the_finder_and_the_reviewer_ask_different_questions` | 1 failed |
| M16 finding block loses its `test_id` | `test_the_prompt_says_which_census_finding_it_is_about` | 1 failed |
| M17 a fetch line may carry a cost | `test_a_fetch_line_cannot_carry_a_model_cost` | 1 failed |
| M18 `judge --live` returns 0 on a failed call | `test_judge_live_reports_a_call_it_could_not_measure_with_exit_2` | 1 failed |
| M19 judge is never a dry run | `test_judge_without_live_renders_the_argv_and_the_prompt_and_starts_nothing` | 1 failed |
| M20 reported cost doubled | the four cost-reading tests | 4 failed |

Every one of the 19 tests is covered by at least one mutation that turns it red.

## Not verified — labelled

* **No live call was made in this piece.** The happy path is proven against a captured transcript
  through the real `PiRunner` (with only `subprocess.run` replaced); that the same argv produces
  that stream on this machine today is *assumed from the capture*, not re-measured. The first
  `judge --live` call is the measurement.
* **The `-ne` measurement is the supervisor's**, quoted here, not re-derived (re-deriving it would
  have spent money this piece was told not to spend).
* **`stopReason` is not judged.** A `length`-truncated answer is recorded like any other; there is
  no guard on it. Named in the module docstring as not covered.
* **A call that fails after the provider billed it writes no ledger line** - the ledger refuses a
  line it cannot total, and usage is never zero-filled. The batch stops, so the lost measurement is
  one call, but the ledger's dollar figure for a failed batch is incomplete. Recorded here rather
  than papered over.
* **The evidence-file read is strict UTF-8.** A page in another encoding raises and stops the
  batch instead of being decoded leniently; unverified whether any of the 76 pilot targets is not
  UTF-8 (all the pilot's pages were JSON/HTML APIs, so probably none).
* **`subprocess.run(timeout=)` kills the direct child only.** Whether a killed `pi` leaves a
  grandchild node process behind on Windows is unverified (the test proves the direct child is dead
  by the marker file it never writes).
* **The dry-run output is only reachable with `PYTHONIOENCODING=utf-8`** (the prompts carry
  non-ASCII site names and notes, and the Windows code page raises). The subcommand's `--help`
  says so; the code does not reconfigure stdout itself.
* **Cosmetic, but real:** a `current_value` that is a string renders inside the attribute as
  `current_value=""Georgia (country)""` (JSON quotes inside a quoted attribute). Harmless for a
  model reading prose, ugly for a human. Escaping convention chosen would be an invention, so it is
  left as is and named here.
* `output/remediation/phase3_runner/runs/` (from the dry-run demonstration) was **deleted** again;
  the dry-run evidence is `output/remediation/logs/piece3_dryrun_batch1.json`.

## State of the tree

Nothing is staged and nothing is committed (no live deploy). `git status --porcelain`:

```
 M scripts/remediation/phase3/ledger.py
 M scripts/remediation/phase3/run.py
?? scripts/remediation/phase3/model_stage.py
?? tests/remediation/fixtures/pi_probe2.json
?? tests/remediation/fixtures/pi_probe_no_extensions.json
?? tests/remediation/test_phase3_model.py
```

## Next piece

Piece 4 is the answer → `phase3.model.Finding` parser: read `answers/<site>%2F<stage>.txt`, turn
the one-sentence answer into the required `defect` boolean plus verdict, and refuse an answer that
does not carry the schema's fields. The raw text is stored verbatim for exactly that step, and the
`0.0`-confidence fallback is deliberately absent: an unparsable answer must be a recorded
`StageStatus.ERROR`, not a `review` with a guessed verdict.
