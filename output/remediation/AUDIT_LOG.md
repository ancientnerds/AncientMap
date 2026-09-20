# Audit log — remediation 2026-09-20

Running record of what was checked, what was found, and the triage. Every entry has its
evidence. Findings against files a fleet worker is still writing are recorded here and fixed
in the audit pass afterwards — never edited underneath a live writer.

---

## 2026-09-20 — findings during wave 1 (in-flight worker files)

### T06 `t06_url_shape.py:209` — weak hash: **FALSE POSITIVE, no change**

pi-lens flags "Weak hash primitive detected (MD5/SHA1)". The code is:

```python
digest = hashlib.md5(unquote(name).encode("utf-8"), usedforsecurity=False).hexdigest()
return digest[0], digest[:2]
```

Not a security use. It reproduces Wikimedia's own upload-path layout (`md5(filename)[0]` /
`md5(filename)[0:2]`), which is defined by md5 in
`pipeline/wiki_image_downloader.py:612-613`. Switching to sha256 would break the comparison
this check exists to make. The worker already passed `usedforsecurity=False`, which is the
correct signal that this is a content-addressing use, not authentication.

Gate impact: none. `.semgrep/ancientmap.yml` contains no weak-hash rule
(`grep -rn -i "md5|sha1|weak.*hash" .semgrep/` → no match), so the `sast` CI job is not
affected. Triage: **false positive, documented, not suppressed and not "fixed" into
breakage.**

### T03 `t03_years_in_text.py:282-297` — undefined names: **REAL, fix in audit pass**

```
F821 scripts/remediation/census/tests/t03_years_in_text.py:290:24 Undefined name `prev_end`
F821 scripts/remediation/census/tests/t03_years_in_text.py:292:54 Undefined name `prev_start`
F841 scripts/remediation/census/tests/t03_years_in_text.py:296:9  `prev_start` assigned but never used
F841 scripts/remediation/census/tests/t03_years_in_text.py:296:21 `prev_end` assigned but never used
```

```python
out: list[_Mention] = []
for start, end, mention in kept:
    if out:
        prev = out[-1]
        gap = text[prev_end:start]          # <- never assigned if this is iteration 1
        if len(gap) <= 30 and _GAP.match(gap):
            out[-1] = _merge(prev, mention, text[prev_start:end])
            prev_end = end
            continue
    out.append(mention)
    prev_start, prev_end = start, end       # <- assigned here, after the use
return out
```

It does not crash today, but only by accident: on iteration 1 `out` is empty, so the `if out:`
branch is skipped and the attributes are assigned at the bottom on the way past. Relying on
that is fragile — reorder anything, or add a `continue` before the append, and it becomes a
`NameError` at scan time, i.e. the census run dies on 5,004 sites halfway through.

Fix in the audit pass: track the previous span explicitly instead of leaning on loop-carried
locals. Then re-run T03 and its pytest.

### Verified clean at the same time

- `ruff check tests/remediation/ scripts/remediation/` → the only 4 errors are the T03 ones
  above. My own four census-core modules, `t04_site_type.py`, and the pruner test are clean.
- `mypy tests/remediation/test_prune_backups.py` → no errors.
- `ruff check scripts/` → 142 pre-existing errors, none in `scripts/remediation/`; the CI lint
  gate covers `api/ pipeline/` only, so these are pre-existing and out of scope.

---

## Phase 0 safeguards — status against the plan (lines 648-670)

| Step | Status |
|---|---|
| Targeted backup of the six tables | done 2026-09-19 (pre-existing) |
| Full `pg_dump` + tested restore drill | **done 2026-09-20** — dump 654,604,671 bytes; `pg_restore exit=0`; all six tables row-for-row identical to production; `DRILL_REPORT.txt` written |
| Arm the backup cron / systemd timer | **done 2026-09-20** — see below |
| Define the change journal file format | **done** — `migrations/0017_remediation_change_log.sql`, 7/7 self-test |
| Field contract | **done** — `docs/procedures/FIELD_CONTRACT.md` |
| Gold standard 30–40 double-blind sites | open — needs the census first |
| Fix the `source_id` filter in Wave 0 (10.2) | **done 2026-09-20** — commit `96b365d`, scoped by test |
| Lock down the restart overwriters (10.1) | partially — documented and enforced for `site_type`/`name_normalized`; `card_description` requires the JSON file, see the field contract §2.3 |
| Offsite copy of `public/data/images` | **done 2026-09-20** — 49,790 files, 3 case-collisions in a sidecar (below) |
| Offsite copy of `video-assets/` | **done 2026-09-20** — verified by exact arithmetic |

### The backup schedule (installed 2026-09-20)

`deploy` has no sudo (password required) but is in the `docker` group, so the schedule is a
user-level crontab, not a systemd timer:

- nightly 03:15 — dump + CSVs, `DO_DRILL=0` (no drill: it costs ~2 min and 625 MB of container I/O)
- weekly Sunday 04:15 — `DO_DRILL=1`, which is the run that actually proves the dump restores

Retention is built in (`00_prune_backups.sh`, `KEEP=7`): a 654 MB daily dump would fill the
98 GB of free space in about five months, and a full disk takes the *database* down, not just
the backups. Only `*_remediation` directories are pruned, so
`/var/www/ancientnerds/backups/2026-09-19_pre-audit` can never be deleted by it.

Verified by running the actual cron command under `env -i` (cron's minimal environment) against
`BACKUP_ROOT=/tmp/cron_probe`: dump 654,621,587 bytes, all 8 CSVs, retention reached, exit 0.

---

## Defects in my own scripts, found by running them

Both were found by executing the scripts rather than reading them, which is the only reason
they surfaced.

### `00_prune_backups.sh` — a real run reported itself as a dry run

```bash
echo "prune-backups: kept $KEPT, pruned $PRUNED${DRY_RUN:+ (dry run)}"
```

`${VAR:+...}` tests whether the variable is *set*, not whether it equals 1, and the script
defaults `DRY_RUN=0` — so it printed "(dry run)" on **real** runs. Observed in the cron probe
above, on the VPS. An operator reading "pruned 3 (dry run)" would believe nothing had been
deleted while backups were being removed. Fixed to branch on the value and to print
"(deleted)" explicitly, with regression tests
`test_real_run_does_not_claim_to_be_a_dry_run` and `test_dry_run_says_so_and_deletes_nothing`.

### `00_backup_and_drill.sh` — the CSV "line count" was not a row count

It logged `unified_sites: 5025 lines incl. header` for 5,004 sites. `wc -l` counts newlines,
and a quoted CSV field may itself contain newlines. Verified rather than assumed:

```
SELECT count(*) FROM unified_sites WHERE source_id='ancient_nerds'          -> 5004
rows with a newline in name/source_url/description/thumbnail_url            ->   20
5004 + 1 header + 20 embedded newlines                                      =  5025  exact match
```

Relabelled as "newlines". The restore drill's row counts are unaffected: it counts rows in the
restored database with SQL, not lines in the file.

### The restore drill used to report success while the restore had failed

A background task named "Phase 0 backup + restore drill" reported **exit 0** with this output:

```
table                            source   restored verdict
ERROR:  relation "unified_sites" does not exist
LINE 1: SELECT count(*) FROM unified_sites
```

A check that exits 0 while its subject is broken is worse than no check, because it is trusted.

First established this was not a live defect: the log is timestamped **20:10:31** and the fixed
script **20:35:04**, so it is the old drill whose false green was already root-caused — the
`docker exec` without `-i` (empty stdin) and the host-side `pg_restore` against `127.0.0.1`
(`fe_sendauth`, arriving as `172.18.0.1`).

But "I fixed it" is not evidence, so the failure path was tested directly. The current script
fails loudly on all three failure modes I could construct:

| input | result |
|---|---|
| stamp that does not exist | exit 1 — `FATAL: no dump at ...` |
| directory holding 8 KB of random bytes | exit 1 — `FATAL: archive unreadable or has no table data` |
| first 4 KB of the real dump (truncated archive) | exit 1 — same |

The second case is the one that used to produce the misleading exit 0, and it is now caught by
`pg_restore --list | grep -c "TABLE DATA"` **before any database is touched** — so the failure
is reported as what it is, not as a confusing SQL error about a missing relation afterwards.
The script runs under `set -euo pipefail` and every guard exits through `die` (exit 1).

Probes were removed afterwards; the real backup directories are untouched, the good run's
`DRILL_REPORT.txt` still ends `VERDICT: dump is restorable and matches production row-for-row.`
(`unified_site_names 1760802 1760802 OK`), and no scratch drill database was left behind.

### The nightly chain propagates a failed drill — proved end to end

The second false green (`bb822b4a0`, 20:16:28) printed its own `FATAL: restore produced no schema`
and yet the task reported **exit 0**. Its log says `restoring on the host` with `pg_restore exit=1`,
i.e. the `fe_sendauth` host-side bug — so it too predates the fix (script changed 20:35:04).

Inspection said the chain was correct (`.sh:104` is
`"$HERE/00_restore_drill.sh" "$STAMP" || die "restore drill failed..."`, no pipe, under
`set -euo pipefail`). Inspection is not proof, so the chain was exercised directly: the real
backup script was run against a **stub drill that always exits 1**.

| run | exit | evidence |
|---|---|---|
| `DO_DRILL=1`, failing drill | **1** | `FATAL: restore drill failed - see .../DRILL_REPORT.txt` |
| `DO_DRILL=0`, nightly path | 0 | `drill SKIPPED (DO_DRILL=0). The dump is NOT verified by this run.` |

So a failed drill cannot pass unnoticed, and the skipped case states that the dump is unverified
rather than implying it was checked. Probes removed, real backups untouched, 96 GB free.

On the exit-0 reports: the script's exit code was measured directly above and through `ssh` in the
three failure-mode tests, so the code is right. What reported 0 was the **background task wrapper
for those older runs**, not the script. That matters for cron only if cron pipes the output — it
does not (the crontab entry is `cd ... && DO_DRILL=... ./00_backup_and_drill.sh >> cron.log 2>&1`,
a redirect with no pipe), so cron sees the true exit status.

**Residual gap, recorded rather than fixed:** cron has no `MAILTO` set, so a failed *Sunday* drill
lands in `backups/cron.log` and nowhere else. Mon-Sat runs the drill is off by design. Adding
mail/alerting means choosing a destination I do not have; flagged for Martin.

### Sweep of every earlier exit-0 claim

Two false greens made the rest untrustworthy, so all six task logs of this session were re-read.
Two were false (both drill versions above); three are genuinely good and one line is a
still-running transfer:

| task | verdict |
|---|---|
| `b9a378d5c` 20:10 | **FALSE GREEN** — exit 0, restore had failed |
| `bb822b4a0` 20:16 | **FALSE GREEN** — printed `FATAL`, wrapper reported exit 0 |
| `b3d6b468d` 20:26 | good — container-side probe, `pg_restore exit=0`, 1m36s, postgis extensions listed |
| `b08e92a3a` 20:27 | good — `drill PASSED`, six tables OK row-for-row |
| `b5dced21b` | running — images pull, source count captured: 49,790 files |
| `b95205d3a` | running — video-assets push |

`b08e92a3a`'s output matches `DRILL_REPORT.txt` on the VPS line for line, so that report is not a
stale artifact.

### `video-assets/` offsite copy — done, verified independently

The pushing task reported exit 0, which proves nothing on its own here (see the false greens).
Checked on the VPS directly:

| | local source | VPS copy |
|---|---|---|
| files | 1,416 | 1,415 |
| `*.env` files | 1 | **0** |
| `shorts/` (the 4.4 GB part) | — | 4.4 GB |

**1,416 - 1,415 = 1, exactly the one excluded credentials file.** Every other file arrived and the
assertion that no `*.env` lands on the VPS holds. This is why the copy excludes by pattern and
counts both sides instead of trusting `tar`'s exit code.

### A formatter touched already-verified files — re-proved, then committed (`95f3cb0`)

`ruff format` (via pi-lens) rewrote eight files that had already been committed and verified,
including `run.py` minutes after commit `205e173`. A formatter touching verified files invalidates
that verification until it is redone, so it was redone rather than assumed benign:

- the diff is purely wrapping and trailing commas — the `summary.append({...})` dict, for instance,
  is the same dict, just spread over lines
- the census was re-run on the same input and **`census.jsonl` and `findings.jsonl` are
  byte-identical to the pre-format hashes** (`c090710384a588d5`, `34a502227ea2ccc5`), i.e. a
  122-line diff in `run.py` that changes nothing observable
- `tests/remediation/` stays green at 246

No worker file was touched: every reformatted file was tracked and mine, while the in-flight worker
files are untracked. `ruff format --check` still flags five worker-owned files
(`t07_link_sweep.py`, `test_t01/t05/t07/t08.py`) — **post-wave cleanup, listed not fixed**, because
one of them is under a live writer right now.

### `public/data/images` offsite copy — byte-complete, but only after chasing the 3-file gap

The transfer's own verdict was honest where its exit code was not: it printed
`VERDICT: COUNT MISMATCH src=49790 dst=49787 - rerun needed` and still exited 0, because the
final `echo` in the check returns 0. **The self-check was right; the transport was short.**

A locale-sensitive `comm` then failed (`input is not in sorted order`), which is itself a lesson:
compare file sets in Python, not with `comm`, whose collation differs between environments. The
set difference named exactly three missing files.

**Root cause: Windows is case-insensitive.** The source tree holds filenames differing only in
case, and these are not duplicates:

| VPS (Linux) | bytes | local (Windows) |
|---|---|---|
| `Attock Fort.webp` | 134,680 | dropped in favour of `Attock fort.webp` |
| `Darius II.webp` | 152,748 | dropped in favour of `Darius ii.webp` |
| `Huelva.webp` | 4,222 | no room for it |

The three files were fetched individually into `AncientMap-Offsite/images-case-collisions/`,
preserving their relative paths, and **all three match the originals by sha256**
(`72d31def950c940b`, `8972f67b70af26f3`, `30241ff5581c99cb`). `49,787 + 3 = 49,790`, so the
backup is now complete in bytes, not just in count. The sidecar carries a `README.md` explaining
that a restore must happen on a case-sensitive filesystem or the same three files are lost again.

Two things this exposes, neither of which is a transfer bug:

- **A latent hazard in the production tree:** three filename pairs differ only in case. Harmless on
the Linux VPS, but any mirror, archive or deploy through a case-insensitive filesystem loses files
*silently*. Now counted and named.
- **`cp -r`/`tar` cannot be trusted to report an incomplete mirror.** Only comparing both sides
finds it. This is the same lesson as the false greens, in a different medium.

## Audit of lanes T02, T03, T06, T09 (2026-09-20)

Verified the same way as T01/T05/T08: independent offline re-run, determinism, gates, mutation teeth.

**Numbers reproduce exactly.** Every figure the workers reported came back identical from a fresh
run against the snapshot and warm cache - no network:

| lane | findings (reported → reproduced) | flagged | n/a | errors |
|---|---|---|---|---|
| T02 | 117 → **117** | 117 | 0 | 0 |
| T03 | 875 → **875** | 875 | 15 | 0 |
| T06 | 13,020 → **13,020** | 3,010 | 0 | 0 |
| T09 | 17,315 → **17,315** | 5,004 | 0 | 0 |

Status tallies sum to 5,004 in every lane. **Determinism: `census.jsonl` and `findings.jsonl` are
byte-identical across two runs** for all four (T02 `8caff689c35f044b`, T03 `1e62d5dd185c4374`,
T06 `e962323f4d48184f`, T09 `65ea257e5312d2fa`). 119 tests pass (14 + 40 + 43 + 22). `ruff` and
per-file `mypy` are clean on all four modules.

**Mutation teeth - each `run()` forced to `return []`, then restored byte-identical:**

| lane | tests failing under the mutation |
|---|---|
| T02 | 7 of 14 |
| T03 | 8 of 40 |
| T06 | 28 of 43 |
| T09 | 19 of 22 |

T03's lower share is expected, not weakness: its 40 tests mostly drive the year-extraction helpers
directly (`test_citation_marker_is_not_a_span_endpoint`,
`test_relative_age_governs_a_leading_endpoint`, `test_span_connectors_only_join_a_bare_endpoint`),
so disabling `run()` leaves the helper-level tests standing. The eight that do fail are the ones
that reach the check's actual verdict.

### Two defects I recorded earlier were fixed by the workers before they finished

Both items on the post-wave list are gone - re-checked with executable tools, not by trusting the
earlier note:

- **T03 `prev_start`/`prev_end` F821** - `grep` finds no occurrence of either name, and `ruff`
  reports clean. The latent unbound-local I flagged is fixed.
- **T03 test `Evidence.quote` Optional** - `mypy tests/remediation/test_t03.py` exits with no output.

A LSP report saying "inconclusive" or a stale advisory is not proof of clean; these were closed by
running `ruff` and `mypy` against the current files.

### T06 md5 re-confirmed as a false positive (line moved 209 → 281)

pi-lens flags `t06_url_shape.py:281` as a weak hash primitive. It is the same finding triaged
earlier; the worker's continued edits moved the line. Re-verified at the new location:
`_md5_dirs()` computes `md5(filename)[0]` and `md5(filename)[0:2]` to reproduce **Wikimedia's own
upload-directory layout**, which `pipeline/wiki_image_downloader.py:612-613` produces and
`upload.wikimedia.org` uses. It is `usedforsecurity=False`, and `.semgrep/` contains no weak-hash
rule, so the `sast` CI gate is unaffected. Swapping in sha256 would break the check in order to
satisfy the checker - the one thing not to do. No change.

## Wave 1 close-out and wave 2 (2026-09-20, evening)

### T07 was never dead - the lane timed out, the sweep did not

T07's worker hit its own 70-minute limit and the workflow reported the child as failed. The
obvious reading is "lane lost, re-run it". That reading would have been wrong. The worker had
started the head sweep as a detached background process, which **outlived its parent**. Checked
rather than assumed:

- `t07_sweep.log` was being appended to 13 seconds before I looked at it, and another 25-second
  window showed **+2,840 bytes and +5 probe records** - demonstrably progressing.
- The module is genuinely resumable: `pending = [u for u in urls if not _is_final(read_probe(...))]`,
  with `PROBE_NS = "t07_links"` and the on-disk layout `key[:2]/key.json` matching what exists.
- Progress measured properly, by **final** records rather than file count: started 20:29:25 with
  `15230 distinct reference URLs, 15230 to probe, 0 already cached`; now 11,290 final
  (8,442 × 2xx, 2,671 × 4xx, 175 × 5xx, 2 × 3xx) and 322 non-final, which stay non-final by
  design so the next run retries them. `MIN_SWEEP = 50` guards both halves of the sweep against
  recording a local network outage as thousands of dead links.

**Decision: do not interrupt, and do not re-launch.** A watcher (`b0bd922df`) waits for 600 s of
log silence - far longer than any single request, so it cannot overlap the sweep - and then
resumes `collect()` and runs T07 offline. Interrupting a demonstrably-progressing child to tidy
up a status field is how 70 minutes of legitimate work gets thrown away.

### Wave 2 launched (3 lanes) - it completes Phase 0 and Phase 1 together

`c89a4f85-1072-46ec-b5c4-790f8d955e89`, all lanes on `opencode-go/deepseek-v4.1-flash`, all
non-writing against production so none can collide with the others or with the running sweep:

| lane | what it is | why now |
|---|---|---|
| T10 | gallery signals S/A/B/D/E/P/F → tier per image | the last Phase-1 check; unblocked because T09's imageinfo cache is verified |
| GOLD | 30-40 double-blind sites, false-negative rate | the last open Phase-0 measurement |
| OVERWRITER | lock down the restart overwriters (§10.1, §10.3) | Phase 2 will write `is_hero`; a value a restart can clobber makes every write pointless |

**T10's brief carries a constraint I verified myself, and it changes the task:** the curated word
lists that plan table 6.4 was measured with **are not in this repository**. Nothing mentions the
41 museum cities, the 67 non-photo terms, the 4,396-token place dictionary, or any
`place_token`/`museum_city`/`non_photo` identifier, and they are absent from git history - they
were scratch artifacts of the measurement and were never preserved. The table prints six of the
67 terms and no more.

So the lane was told to split the signals by what is actually knowable: **S** and **F** are fully
faithful from the snapshot alone, **P** (not in the site's P373 category) is fully faithful and
fetchable (`wikidata.py`; `wiki_image_downloader.py:341,401-402,492`), and **A/B/D/E** must be
either reconstructed from a principle the plan states and *documented as a reconstruction*, or
omitted with the gap stated. For **D** the plan names its own source - "place token of a curated
site > 50 km away" - and the curated sites and their coordinates are in the snapshot, so that
dictionary is derivable rather than invented. It is explicitly forbidden to silently invent the
lists or to tune the tier counts to reach the plan's extrapolation.

This matters because it is the third time this project has met the same shape: **a plan figure
that reads like a spec but is a measurement whose inputs no longer exist.** The honest output is
real numbers plus the divergence.

### Durability gap found and fixed: the evidence log was one disk from gone

`.gitignore:211` ignored `output/` wholesale, and `git ls-files output/` was **empty** - nothing
under `output/` was tracked. That included `output/remediation/AUDIT_LOG.md`, the hand-written
evidence record of this entire remediation.

Bulk intermediate data under `output/` *should* stay ignored - the plan says so and it is right.
But the evidence record cannot be regenerated from anything; it was living on exactly one
filesystem, with no git copy and no backup. That is the same failure class as the backup and
offsite gaps Phase 0 fixed, just harder to notice because the file is small.

Fix: `output/` became `output/*`, with `!output/remediation/`, `output/remediation/*` and
`!output/remediation/AUDIT_LOG.md`. Verified rather than assumed - `git check-ignore -v` prints
negated patterns too, which makes it a misleading test here, so the check was
`git ls-files --others --exclude-standard output/`, which returns exactly one path:

```
output/remediation/AUDIT_LOG.md
```

and the bulk paths (`cache/`, `census.jsonl`, `t07_sweep.log`, `run_t09/`) all still classified as
ignored. The evidence trail now lives in version control.

**But that alone is not offsite, and saying otherwise would be the exact kind of claim this
project keeps catching.** The git repository is also on this one machine, and pushing is a stop
case for me - a push to `main` is a live deploy, and that decision is Martin's. Version control
protects the log against my own mistakes, not against losing the workstation.

So the log is now also on the VPS, which is a genuinely different machine:

```bash
ssh ancientnerds "mkdir -p /var/www/ancientnerds/backups/remediation-evidence"
scp output/remediation/AUDIT_LOG.md ancientnerds:/var/www/ancientnerds/backups/remediation-evidence/
```

Verified by matching sha256 on both sides (`7e4b3d6d3cdd1e639facb4c1bdb94d16626ef015a10105027587e657fd1a75b1`),
and the file was scanned for credential-shaped content before it left the machine - the only
matches were prose (the word "password" inside a sentence about sudo, "token" inside
"4,396-token"). Two machines now hold the evidence trail; the same copy must be repeated as
each wave adds to it. The remaining gap is a **push**, which only Martin can decide.

The db backup cron cannot do this itself: it runs *on* the VPS, so it can only copy files that
are already there. Evidence that lives on the workstation needs the workstation to send it.

### The five "unformatted" worker files block nothing (measured, not assumed)

pi-lens reports `ruff format` debt on five files. Checked what actually gates the project rather
than fixing on reflex: CI runs `ruff check api/ pipeline/` and `ruff format --check api/ pipeline/`
(`.github/workflows/ci.yml:114,117`) and the pre-push hook likewise only `ruff check api/
pipeline/` (`.githooks/pre-push:155`, whose own comment at `:18` records that `ruff format --check`
is CI-only). **No gate covers `scripts/remediation/` or `tests/remediation/` at all.** The debt is
cosmetic; it is tidied after the wave, not treated as a blocker, and it is not reported as one.

## Two architecture decisions taken with the OVERWRITER lane (10.1 / 10.3)

The lane finished its read-only assessment and hit a genuine conflict with the example fix in its
brief, then asked instead of guessing. Both answers were decided on evidence from the repo.

### Q1 - `card_stats.card_description`: keep the file authoritative, log the discards

New measurement (in the api container): production's **4,996 card texts are byte-identical to
`public/data/card_descriptions.json`** - 4,996 entries, 4,996 rows, 4,996 identical,
`would_be_overwritten 0`. There is no drift today, and the reason is that the startup import is
the step that carries the file into the rows.

The chain is already wired end to end: `output/card_descriptions.json` ->
`scripts/import_card_descriptions.py` (reads `:25`, writes `public/data/...` `:58`) -> commit and
deploy -> `api/main.py:496` startup import. `scripts/merge_rewrites.py:2` is the other half.

So the plan's §10.1 alarm is right that this overwrites, and wrong to call it a defect **for this
field**: it is the propagation mechanism. Decisions:

- **Rejected "write only into an empty target"** - it kills the chain, so an edited file could
  never reach a row that already holds text.
- **Rejected guarding the import against `remediation_change_log`** - that would give production
  API boot code a permanent dependency on a table that exists for one audit; a `to_regclass`
  guard is a band-aid over the coupling, not a fix.
- **Taken: keep the semantics, log every discarded non-empty value** (site_id and both values) so
  a reverted write is loud at boot instead of silent - plus the contract rule, now recorded in
  `FIELD_CONTRACT.md` §2.3, that Phase 5 writes the JSON and lets the import carry it.

The remediation is then correct **by construction** rather than by a guard. The lane was also told
to assess the second 10.1 entry (`orchestrator.py:1621-1627`) per column, and specifically that
`name_normalized`'s survival condition makes a well-formed but **wrong** value durable.

### Q2 - `restore_snapshot()`'s missing `raw_data`: fixed, not merely reported

The plan names it a defect in §10.3; it is one line and inside the lane's writable area. Writing a
report *about* a known data-integrity bug rather than fixing it is the failure mode this whole
effort exists to avoid, so it is fixed in-lane under two conditions: the restored row must end up
**consistent** (description and `raw_data` from the same snapshot, or neither), and a teeth test
must fail before the change and pass after.

Checked the snapshot really can supply it: `unified_sites.jsonl.gz` holds 5,004 sites, 2,787 with
empty-or-missing `raw_data`, and **2,217 carrying `description_citations`** - which lines up with
the 2,216 production citations §10.3 complains about after a restore. The lane must also report
the discrepancy that `api/routes/sites.py:988` documents restoring `raw_data`,
`parent_site_id` and `source_record_id` while the implementation does not - the same
phantom-documentation class as §10.3's "raw year parsing".

Blast radius stated to the lane and worth repeating: `restore_snapshot` is live through
`api/routes/sites.py:955` -> `:963`, so this is a real behaviour change on a live endpoint, and
it must be reported as one.

## The T07 watcher was under-budgeted - caught by arithmetic, not by a timeout

A watcher that expires *before* the work it watches is worse than no watcher: the sweep would
finish at ~06:30 with nobody awake to notice. Checked the numbers instead of trusting the
launch.

**Rate, measured:** 11,290 final records at ~21:5x → 11,444 at 22:17 ⇒ **~460 URLs/hour**, with
3,786 still open. That is **~8 hours**, finishing around 06:30. The watcher was launched with
`timeoutSeconds: 14400` (4 h) and would have expired around **01:10** - five hours early.

### Proving the kill was safe *before* killing

`bg_kill` on a task can take a whole process tree with it, and the sweep holds ~11,400 URLs of
network work. So the tree was read first rather than assumed:

```
32648  parent=10332  python -u scripts/remediation/census/run.py --tests T07 ...   <- the sweep
10332  parent=14708  nohup.exe ./.venv/Scripts/python.exe -u scripts/.../run.py     <- detached
33956  parent=3276   bash.exe -c "cd /c/PythonProjects/AncientMap && bash output/.../t07_finish.sh"
```

Two independent trees. The sweep is under **`nohup`**, which is precisely why it outlived its own
worker's 70-minute timeout in the first place; the watcher is a separate bash. Killing the watcher
could not reach it.

**And that was then confirmed by measurement rather than left as a conclusion:** after the kill,
the watcher was `GONE` while both `32648` and its `nohup` parent were `ALIVE`, with the sweep log
written **4 seconds** before the check. The kill was surgical.

Replaced by `bf568f766` with `timeoutSeconds: 43200` (12 h), which spans the measured finish time
with margin. The sweep itself was never restarted - restarting it would have discarded nothing
(the cache is resumable) but would have thrown away the ~460/hour of live progress for no reason.

Worth naming the general shape: **the sweep is guarded against a stall by design.** If the log
goes quiet for 600 s the watcher proceeds anyway and finishes with whatever it has, and
`MIN_SWEEP` refuses a partial sweep that would look like thousands of dead links. So a hung sweep
degrades to a documented partial result instead of hanging forever - which is why a long budget
is safe rather than a way to wait indefinitely.

## The GOLD lane's "600 s bash call": a retry storm, found by reading its scratch

A worker holding one tool call for 600 s raises the stall signal. The rule is to check cheaply
before steering, and the check paid off - the lane was neither hung nor productively busy.

**What the inspection showed:** `gold_scratch/failed.txt` listed **27 FAILs out of 33 sampled
sites**, with `retry2.txt` re-running 26 of the same ones. The reason was in the evidence files:
`retry 1/2/3 for wd_Q11120743: HTTP Error 429: Too Many Requests` - a **rate-limit retry storm**.
Retrying an immediate 429 is self-defeating: it deepens the throttle and burns the budget.

**And the lane already held what it needed.** `xcaret` had enwiki + dewiki + eswiki cached, each
with coordinates and an extract; `metsamor` had enwiki + eswiki; `priene` had commons + dewiki +
dawiki. It had marked all three FAIL because **one** secondary fetch (the Wikidata call) was 429'd,
while the gold standard's own requirement - two independent sources - was already satisfied on disk.

**A real bug in its own reader surfaced at the same moment:** `dewiki_Priene.json` and
`dawiki_Priene.json` came back "unreadable 'charmap' codec can't encode character '\u03a0'" - JSON
opened with the Windows default codepage instead of UTF-8. That silently discards every non-ASCII
source and then mislabels the site a failure.

**Course set, without killing the lane** (it was demonstrably alive and had produced genuine work):
fix the UTF-8 reader; stop the retry loop and use a real politeness delay with at most one retry;
re-process the FAIL list **from cache** instead of re-fetching; and record `UNVERIFIABLE` with its
reason for anything still short after one polite pass.

Two points worth carrying forward:

- **`UNVERIFIABLE` is an outcome of this measurement, not a lane failure.** It is one of the things
a false-negative rate measures, so it belongs in the denominator instead of being chased until the
budget runs out.
- **Language editions of Wikipedia are not independent sources.** enwiki + dewiki + eswiki mirror
each other and share Wikidata-derived infoboxes, so counting them as two independent sources would
manufacture confidence. The lane must pair Wikipedia with a non-Wikipedia source (heritage register,
excavation report, official site) where one exists, and say so plainly where none does.

The general lesson, and the reason the 600 s signal is worth heeding rather than muting: **a long
tool call is a prompt to diagnose the CONTENT of the failure, not merely to wait it out.** Waiting
here would have produced a lane that spent its whole budget re-asking a rate limiter for
permission it had already been denied, while its own cache sat full of usable answers.

## Wave 2: T10 done, overwriters locked down, and the gold standard measured after all

All three lanes ran on `deepseek-v4.1-flash`, none wrote to production, and none could collide with
the running T07 sweep. Gates after all of it: **1954 passed, 3 skipped, 57 deselected** in 144 s.

### The GOLD lane: the deliverable said "2 of 36" and had actually finished 36 of 36

The report's own header read *"Status: partial run. 2 of 36 sampled sites were completed before the
run was cut short"* and pointed at a §"Not measured" section. **Both statements were false.**
`sites.json` held `sites_completed = 36` with 36 records, every record carried **15 field verdicts**
(540 = 36 x 15: 449 CORRECT, 40 WRONG, 51 UNVERIFIABLE), and no "Not measured" section existed.

The header had been written early and never re-rendered. This is worth recording as a failure mode
of its own: **the prose lagged the data, and the prose is what a reader believes.** Had the header
been trusted, a finished Phase-0 measurement would have been re-run from scratch.

What genuinely did not happen was the **comparison**, so it was computed here, in
`output/remediation/gold_standard/compare_fnr.py`.

### The false-negative rate, and why it had to be field-level

A site-level comparison would have measured nothing and flattered the census: **T10 alone flags
4,010 of the 5,004 sites** and **T09 flags all 5,004**, so "some check mentioned this site" is true of
almost everything. A blinded error counts as caught only when a finding names the **same site and the
same field**.

    FALSE-NEGATIVE RATE = 24/40 = 60.0 %     95 % Clopper-Pearson [43.3 %, 75.1 %]
    weighted (N_h/n_h)  = 62.4 %

By field: hero_image 8/8 caught and gallery_images 3/3 caught - all 11 image-tier errors were found.
The misses are description 8, card_description 5, period_start 4, site_type 4, scope 3.

**The decomposition is the usable part of that number**, and it sums exactly to 24:

- **3 - no check exists.** Every one is the E3 scope window (Midford Castle, a folly of 1775;
  Ksar el Barka, 1690). Nothing in the ten checks examines the cutoff, and it is a pure comparison of
  stored values needing no network. The cheapest real win available.
- **13 - a check exists and under-fires.** Nine are dates in prose, T03's own target, where it caught
  one: Ahu Tongariki ("constructed between 1-500 AD" against a source saying 1250-1500), The Gop
  ("5th-4th millennium BC" for a cairn starting c. 4000 BC), The Merry Maidens (self-contradictory in
  a single sentence), Ocriticum (a century out), Font dels Coms (a *fabricated* -3500). Four are
  `site_type`, where **T04 ran to completion and flagged 0 of 5,004 sites** while a 36-site sample
  holds four wrong types. A check that flags nothing while its targets sit in the sample is
  under-firing, not clean.
- **8 - beyond a deterministic census.** Wrong subject (a description paraphrasing the article about
  the god Dedun), fabricated attribution, measurements inflated against two sources, an SSSI area
  given as the site's, a misspelling. These need the semantic/VLM pass; no string check decides them.

So "60 % false negatives" does **not** license "the census is untrustworthy". It says the census is
strong exactly where it was built to be (URL shape, image dimensions, hero/gallery triage, citation
integrity) and has three specific gaps, two of which are mechanically closable.

### A bug in my own comparison, caught because the number was impossible

The first run printed the Clopper-Pearson interval as **`[100.0 %, 0.0 %]`**. An interval outside
[0,1] that excludes its own point estimate cannot be a result, so it was treated as a defect in the
checker rather than reported. Both bisection branches had their monotonicity inverted - `P(X >= k|p)`
*increases* in p, `P(X <= k|p)` *decreases* - so the interval had collapsed. Fixed, and the function
now asserts that the interval contains `k/n` and lies in [0,1], which makes the same class of bug
impossible to emit again. Corrected interval: [43.3 %, 75.1 %] around 60.0 %.

The general rule, and it has now paid twice in this session: **a number that cannot be true is a bug
in the instrument, not a finding about the world.**

### OVERWRITER: the Phase-2 question answered, and one blast radius avoided by measurement

The decisive answer for Phase 2: **`wiki_images.is_hero` has no restart writer at all** - only API
routes (`api/routes/sites.py:1867`, `api/routes/wiki_images.py:127,140,153,236,246`) and manual
scripts; `api/services/snapshots.py:660`, `api/routes/public_v1.py:1727` and
`pipeline/video/shorts_export.py:252` only read it. Independently re-verified here by grepping every
assignment in `api/`, `pipeline/` and `scripts/`. **The hero moves of Phase 2 therefore survive a
restart**, which was the precondition for making them at all.

On `name_normalized` the lane did the thing this audit keeps asking for: it **measured the unscoped
version** - 80,083 rows across 28 external sources disagree, `topostext` 8,046 of 8,068 - and scoped
the repair to the curated sources because rewriting the rest would have been the §10.2
blast-radius mistake in a new place. It repaired 2 rows. The statement compares against the producer
rather than against itself, which is what made the old guard blind to a well-formed-but-stale key.

`restore_snapshot()` now carries `raw_data` in both branches (10.3), verified against all 28,322
snapshot rows carrying the key, so it cannot clear a column for a missing key. Teeth: 6 tests red
**before** the change on the HEAD blobs, 14 green after.

### T10: two real bugs found by its own tests, and a harness gap it refused to paper over

Both bugs were found by running, not by reading: an **inverted P polarity** (in-category rows went to
tier C, outside to D - backwards), and the parent-category hop asking **normalised** Commons titles
instead of raw ones (`missing: 40933` vs `missing: 351` after the fix; measured live 26/26 raw against
5/26 normalised). Signal D was also firing on generic tokens ("from", "roman", "temple") in 18,670
rows and was cut to the plan's 4,396-token size by document frequency.

It then reported a flaw in the **harness**: with `run()` sabotaged to `return []`, `run.py` reports
`errors 0 / flagged 0 / 0 findings` - the runner cannot distinguish "correctly found nothing" from
"the implementation is empty". It refused to fix that because `run.py`/`model.py` were out of scope,
and reported it instead. That is the right call, and it is a **systemic** limitation: for all ten
checks, `census.jsonl` alone cannot prove a check ever ran. The mutation teeth in each check's test
file are the only proof, which is why every one of them was mutation-proven in this audit.

### T07: the sweep ended at 22:44 and the watcher is now re-probing a 503-ing host

The original sweep process is gone and its log stopped at **22:44:40**, so `run_t07` (written 22:44,
5,071 findings over 2,806 sites) is a **complete** T07 run rather than an interrupted one. The
replacement watcher is alive and re-probing the non-final records for the same reason the cache is
resumable at all. Worth flagging for the audit that follows: `megalithic.co.uk` is answering **503**
in bulk right now, and a mass of transient 5xx from one host is a property of that host, **not** a
statement that the database's links are broken. T07 stays uncommitted until that run is audited.

## The gold standard found a hole in the census itself: the E3 scope window

The measurement's most useful output was not a rate but a **missing check**. Nothing in
T01-T10 examines the E3 cutoff, and the plan requires it in three separate places:

- **§1.3, "Definition of clean"** lists it as a condition: *"The site is in scope (E3), or flagged
  as out of scope and hidden."*
- **§1.2 E4** says how: *"Flag it AND hide it platform-wide. A new column for this is approved - but
  only during implementation."*
- **§7 gate S12** already measures it: **4,920 pass / 84 fail**.

So the census cannot certify a site clean by its own acceptance rule, and the Phase-1 acceptance
criterion ("each of the 5,004 sites has a record holding the result of all ten tests") is not
reachable without an eleventh. Two of the three blinded E3 errors are pure comparisons of stored
values and need no network at all.

The plan is candid about this class of gap elsewhere - §Phase 1 states its census "covers roughly
**18 of the 54** measured error classes" - so a large false-negative rate was expected rather than
surprising. An earlier baseline recorded **69** scope violations against the plan's **84**; that
discrepancy is itself unresolved and has been handed to the SCOPE lane to settle by running both
rules over the snapshot rather than by splitting the difference.

## Wave 3: the first real repair, the missing check, and the worklist for the expensive phase

Three lanes, all `opencode-go/deepseek-v4.1-flash`, all fresh context, `usageBudget` 6M tokens hard:

| lane | agent | product |
|---|---|---|
| **HERO** | worker | Phase 2 step 1: the mechanical hero repair, with the production write authorised (E1) |
| **SCOPE** | worker | the E3 window as census check T11, and the 69-vs-84 reconciliation |
| **FACTS** | scout | read-only: the Phase-3 worklist and a costed batching plan |

**Why these three.** HERO is the largest user-visible defect that is mechanical and costs nothing
(3,858 heroes sitting at 800 px because `HERO_WIDTH = 800` equals `THUMB_WIDTH = 800`), and it is
only now possible: wave 2 proved `is_hero` has no restart writer. SCOPE closes the hole above.
FACTS exists because Phase 3 is the expensive phase (~40,000 tokens per site) and the naive
worklist is worthless - the census "flags" 4,010 sites in T10 and all 5,004 in T09, so "has a
finding" means nearly everything. Its brief requires the factual dimensions to be counted
separately from the image and URL checks, and the split between sites a script can settle and sites
only judgement can settle, because conflating those two is how a budget doubles.

Two design decisions worth naming. HERO must **not** select candidates by `wiki_images.width` -
T09 measured that column wrong for 11,653 rows - so it selects on the cached true Commons
dimensions instead, and prefers T10's tier D ("clear": in the site's own P373 category, no off-topic
word signal, the site's name in the filename), which makes a new hero **audit-resistant** rather
than needing rework after the gallery audit. And the lanes are deliberately split so that only one
of them may touch the database, while the census lane keeps its single `run.py` edit to the very
last step because a detached sweep may invoke `run.py` at any moment.

## A third instrument bug, and the rule it confirms

T07's cache probe reported **`final records = 0` of 15,230** - i.e. the resumability was broken and
the watcher was re-probing the whole sweep. It was not. The record simply has no `final` key
(`['error','fetched_at','final_url','method','status','url']`); the real criterion is
`_is_final()` = `rec.get("status") is not None` (`t07_link_sweep.py:158`), deliberately re-probing
only **transport** failures (516 of them) so that a sweep which ran while the connection was down
heals instead of hardening. The module is right and the probe was wrong.

That is the third time in this session that an impossible-looking number was a bug in the measuring
code rather than a fact about the world (the Clopper-Pearson interval, `by_field`'s missing
annotation, and this). The rule stands and is worth keeping: **check the instrument before
believing the number** - and when the instrument was yours, say so in the record.

## The Phase-5 generator cannot fail - and would have been trusted

While an earlier note claimed the card-description workflow was "broken at step 1", checking that
claim executably produced a worse finding about the step *after* it. `scripts/merge_rewrites.py` is
the generator that Phase 5 depends on, and it **cannot fail**: `sys.exit` appears 0 times in the file
and the verifier's exit code is never read (`returncode` appears 0 times).

Proven by running it in a faithful sandbox - its paths derive from `__file__`, so a whole tree was
recreated around a copy of it, with a stub verifier that exits 3:

| scenario | exit | what it did |
|---|---|---|
| all 10 `rewrite_output_*.json` missing (**today's state**) | **0** | `WARNING: Missing batch files: [0..9]`, applied 0, **still wrote the deploy-relevant `public/data/card_descriptions.json`** |
| a batch present, every rewrite invalid | **0** | printed `Validation errors (3)`, applied 1, skipped 1 |

The second row was the surprise, and it was not what I set out to test: **validation errors are
printed and then ignored.** The apply loop's only condition is
`sid in descs and len(new_desc) <= 200` (`:78`) - it never consults the `errors` list, so a rewrite
rejected as `BAD ENDING` is written into the public file anyway. Only the >200 case is filtered, and
only because the length test was duplicated there by accident.

Why this matters beyond one script. Phase 5 regenerates the card texts, and the plan already wants
`scripts/verify_descriptions.py` retired as a gate - it too contains no `sys.exit`, which now
independently supports that decision. A generator that exits 0 after doing nothing, while silently
rewriting the file the API boots from, is the same failure shape this audit has now caught four
times: **exit 0 is a claim, not proof.** The bootstrap `cp` documented in `FIELD_CONTRACT.md` makes
this path *reachable*, so the warning travels with it: assert `Applied N rewrites` with N > 0 and
confirm the public file changed.

### Safety check after the probe

The real backups directory was intact: `2026-09-19_pre-audit` and `2026-09-20_remediation` both
still present, nothing pruned. The scratch root did its job.

---

## Wave 0 scoping fix — done, commit `96b365d`

Plan §10.2. `run_mechanical_fixes(sites)` read its argument only for `stats['total_sites']` and
then wrote table-wide: 1,759,676 rows across 28 sources where 5,004 are the curated set. The
worst of the four statements was
`UPDATE unified_sites SET site_type = :canonical WHERE site_type = :raw`, which rewrites every
row in the table sharing that raw value, in every source. `--source` filtered the candidate list
and nothing else.

Fixed: every statement carries `id = ANY(CAST(:site_ids AS uuid[]))` (the pattern already used
at `api/main.py:512-525`), and an empty candidate list returns before any statement is built —
the dangerous reading of "no filter" is "so do everything".

Verified by running the real function against a recording fake connection
(`tests/remediation/test_wave0_scoping.py`), so it asserts what reaches the database. **Teeth
proven by mutation**: dropping the id filter from the site_type UPDATE again made 2 tests fail
naming that exact statement; restoring it made all 3 pass. Without that step "3 passed" would
have been worthless.

Full gate suite after the change: 1879 passed, 3 skipped, 57 deselected — the same 3 known
skips, no regressions.

### T02 `t02_admin_country.py:354` — "Potential SQL injection sink": **FALSE POSITIVE, no change**

opengrep flagged a SQL-injection sink. Checked rather than assumed, and the file contains no
SQL at all:

- no DB driver is imported (only geopandas, httpx, shapely, pyproj)
- `grep -rn -iE "psycopg|sqlalchemy|create_engine|\.execute\(" scripts/remediation/census/tests/`
  → **no matches**; the census test tree is snapshot-only, as designed
- a case-insensitive scan for SQL keywords matches only the English word *where* inside
docstrings ("where the widening stops", "where Natural Earth marks the feature"), plus
  `sys.path.insert` and a `dict.update`

The rule is keying on the word `WHERE` in prose. Separately, the reported line number had
already moved by the time I read it (L354 was a `def` in one read and `self._tree.query(pt)` in
the next), because T02's worker is still editing the file - so the position was unreliable on
top of the match being spurious.

**Confirmed a last time now that the file is stable and its worker has finished.** L354 is
inside `containing(self, lon, lat)` and is a set comprehension over a Shapely R-tree:

```python
return sorted(
    {
        self.features[int(i)].admin
        for i in self._tree.query(pt)
        if self.features[int(i)].geom.covers(pt)
    }
)
```

There is no SQL anywhere near it - `Point(...)`, `self._tree.query(...)` and `geom.covers(...)`
are in-memory geometry. Every f-string in the file is a human-readable `FetchError` or a finding
`note`. The advisory is misclassifying a set comprehension over geometry as query construction,
exactly the class of finding this project's rules say to triage and decide on rather than obey.

## Audit of the three finished lanes (T01, T05, T08) — sound

Audited by re-running everything myself, not by reading the workers' summaries.

### Independent re-run reproduces their numbers exactly

| | worker reported | my offline re-run |
|---|---|---|
| T01 flagged / findings | 1063 / 1175 | 1063 / 1175 |
| T05 flagged / findings | 70 / 70 | 70 / 70 |
| T08 flagged / findings | 94 / 99 | 94 / 99 |

- **Determinism:** `census.jsonl` and `findings.jsonl` were **byte-identical** across two
  separate runs (sha256 prefixes `c090710384a588d5` and `34a502227ea2ccc5`). These are pure
  functions of snapshot + cache, as designed.
- **No gaps:** 15,012 rows = 5,004 sites x 3 tests, exactly.
- **Clean:** mypy and ruff clean on all six files; 57 of their pytest cases pass.

### Two modules independently reproduce numbers the plan measured by hand

This is stronger evidence than a synthetic test, because the plan's numbers were produced by a
different method at a different time:

- **T08** found 76 / 11 / 8 — the plan says "76 sites carry an evidence array with no `[N]`
  marker, 11 have a marker with no matching entry, 8 have an entry never cited". Exact match,
  plus 2,217 applicable, which is the plan's own citation-site count.
- **T05** found 27 `set` -> `'Georgia'` and 8 `set` -> `'Chile'`. The plan names exactly
  `Georgia (country)` 27 and `Chile, Easter Island` 8. The one contested value (`Baltic Sea` 1)
is proposed as `review` with no value, not as a guess.

### The 35 auto-applicable fixes carry three independent sources each

Sampled the severe `set` findings and read their evidence. Each holds:

1. `pipeline/utils/country_lookup.py` — `NAME_TO_ISO` maps both spellings to `GE`
2. `ancient-nerds-map/src/utils/countryFlags.ts:COUNTRY_CODES` — the flag **already renders**
   correctly for both, so the only defect is that the narrator reads `Georgia (country)` aloud
3. `docs/procedures/SITES_DB_REMEDIATION_2026-09.md:395` — the plan's S7

That is a genuinely minimal-risk correction with the mechanism stated, not a fuzzy match: the
render path is unaffected and only the spoken text is wrong. The worker also distinguishes what
it can prove from what needs a human — 35 findings propose `None` and go to review.

T01's 1,175 findings are **all** `review`, nothing auto-applied, which is the conservative
behaviour the plan asks for.

### Teeth check — done, the suites are not vacuous

Mutation: forced each module's `run()` to `return []` (report nothing, ever), then restored.

| module | tests failing under the mutant | after restore |
|---|---|---|
| T01 | 17 of 28 | 28 passed |
| T05 | 8 of 11 | 11 passed |
| T08 | 12 of 18 | 18 passed |

All three files were asserted byte-identical to their originals after restoration.

The tests that still pass under the mutant are the negative ones ("a canonical country produces
nothing", "a site without a QID is not applicable") — a module that reports nothing necessarily
satisfies those. That is the correct shape, not a gap.

The test names show why there is teeth to begin with: every rule has both a firing case and a
non-firing case (`test_marker_without_entry_fires` next to `test_matching_markers_and_entries_
produce_nothing`), plus fail-loud cases for bad input (`test_array_that_is_not_a_list_raises`,
`test_a_missing_entity_batch_raises_instead_of_passing_everything`) — the latter being the exact
"a failed request must never be reported as no findings" rule. T05 also carries
`test_every_proposed_value_is_a_fixed_point_and_the_same_country`, which enforces the fixed-point
rule from `docs/procedures/FIELD_CONTRACT.md`; the worker read the contract and encoded it.

## Offsite copies (started 2026-09-20) — the two remaining single points of failure

Measured before deciding, not assumed:

| Data | Size | Where it existed | Action |
|---|---|---|---|
| `public/data/images` | 20 GB | **VPS only** (locally 8 KB) | pulling to local |
| `video-assets/` | 4.6 GB | **local only** (absent on the VPS) | pushing to the VPS |
| `public/data` (JSON) | 4.4 GB | both | fine |

Each side was the only copy of one of these, so the fix is a cross-copy: local gets the images,
the VPS gets the video assets. No cloud credentials exist here, so this is real machine-level
redundancy rather than a substitute for it — **a genuine third-party offsite still needs
`rclone`/bucket credentials that are Martin's to supply**, and that gap stays open until he does.

Where the VPS copy lives: `/var/www/ancientnerds/backups/video-assets-offsite/`. Chosen after
reading the deploy script, which runs `git clean -fd ancient-nerds-map/public/data/ public/data/`
(`.github/workflows/ci.yml:298`) — **scoped to exactly those two paths**, so anything else in the
tree survives a deploy. Had I put the copy under `public/data/`, a deploy would have silently
deleted it. (`public/data/images` itself survives because `git clean -fd` without `-x` skips
ignored files.)

Both jobs verify themselves: the push asserts no `*.env` arrived on the VPS, and the pull
compares the VPS file count against the local count and prints a verdict, so a truncated transfer
cannot be mistaken for a complete one.

### A credentials file in an unbacked-up directory

`video-assets/prod-db.env` exists — production DB credentials inside a directory that is
gitignored, untracked, and (until now) had no second copy. It was deliberately excluded from the
copy (`--exclude='*.env'`), and the push asserts zero `*.env` files land on the VPS.
`git ls-files video-assets/` returns 0, so it cannot be committed by accident either.

Not acted on beyond excluding it: moving a production credentials file is Martin's call, not a
side effect of a backup job. Recorded because a secret whose only copy sits in the directory one
has just started treating as expendable backup space is worth his knowing about.

## Attention signal on T07 (2026-09-20 20:45) — judged a false alarm, deliberately not interrupted

The fleet reported "worker has had tool `bash` open for 600s". T07 is the HEAD sweep over
15,230 distinct reference URLs, which the plan itself budgets at ~45 minutes at 24 parallel — a
silent 10-minute `bash` call is the task, not a hang.

Checked rather than assumed: the cache grew from **7,800 to 7,960 files between two sequential
`find` commands**, and `t07_sweep.log` had been written seconds earlier. That is active
progress. Interrupting would have destroyed roughly ten minutes of network sweep for nothing.

Recorded here because "600s of silence" is exactly the shape of a stall, and the next reader
should see what distinguished the two in this case.

3/8 complete: **T01, T05, T08**. Still running: T02, T03, T06, T07, T09. No file owned by a
running worker is edited in this pass; findings against them are recorded here and fixed after
the wave reports.

## Wave 1 findings to fix once the wave reports

### T03 `tests/remediation/test_t03.py:208,214` — REAL, fix once T03 has finished

mypy, run directly (ground truth, not the widget):

```
test_t03.py:208:16: error: Unsupported operand types for in ("str | None" and "str")  [operator]
test_t03.py:214:20: error: Unsupported right operand type for in ("str | None")       [operator]
```

`Evidence.quote` is `Optional[str]` and the test uses `f.evidence[0].quote in text` and
`"period_name" in ev.quote` without narrowing it first. The fix is to assert the quote is not
`None` before using it — which is exactly what the test is trying to establish, so the assert
strengthens it rather than silencing the checker.

### T06 `t06_url_shape.py:226` — `UPLOAD_PATH_RE` possibly undefined: re-check after T06 finishes

The widget reports `UPLOAD_PATH_RE is not defined` at line 226, but flagged it as historical on
a file that has changed since, so it may already be resolved. T06 is still writing. Re-run ruff
and mypy on the finished file before judging; if real it is a `NameError` at scan time.
