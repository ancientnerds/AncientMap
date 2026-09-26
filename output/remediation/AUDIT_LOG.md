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

## T07 code audit: sound, and it pre-empts the objection I was forming

Read-only audit of `scripts/remediation/census/tests/t07_link_sweep.py` while its sweep still runs.
The run-level audit (offline re-run twice, byte-comparison, mutation teeth) must wait for the
watcher to stop writing the cache, but the code can be judged now, and it is the strongest module in
the set.

**Contract.** `TEST_ID`/`NAME`/`DIMENSION`, `applies_to()` (only sites whose link row actually carries
a URL - 3,575 of 5,004; 1,429 legitimately do not apply), `collect()` as the only network half,
`run()` pure over snapshot plus records. So the frozen contract holds.

**It cannot silently produce an empty answer**, which is the failure mode the whole census fears, and
it reaches that three different ways:

- `_cited_markers()` **raises** when `raw_data` is not an object or `description_citations` is not a
  list - with the reason in the message ("guessing would silently drop every citation").
- `collect()` carries two **fail-closed** guards: if every probe of a real sweep (>= `MIN_SWEEP`)
  returns no HTTP status, or if more than half do, it raises instead of writing. The comment gives the
  reason exactly: a local network outage must not be recorded as thousands of unreachable links,
  "because a cached wrong answer outlives the outage".
- `run()` **raises** when a probe record is missing ("the collector did not run for this URL"), so a
  forgotten collect cannot read as a clean sweep.

**The verdict table is honest, and it pre-empts the objection I was about to raise.** A 403 from
`www.megalithic.co.uk` (577 links) or any WAF-refused 400/405/406/501 is *refused*, **never dead** -
with the reason stated: such hosts turn away HEAD and the GET fallback while serving a browser
normally, so the only honest verdict is "could not verify". Those four "we do not know" verdicts are
reported at `Severity.COSMETIC` rather than omitted, and the docstring names why: omitting them would
mark a bot-walled site as `pass`, i.e. **"turn 'could not check' into 'checked and clean' - the
inversion this census exists to prevent"**. Severity is then split by consequence, not by colour: an
uncited dead link is `COSMETIC`/`CLEAR` (readers filter `content_url IS NOT NULL`, so clearing simply
stops rendering the dead button, and the journal keeps the old URL), while a *cited* one is
`MODERATE`/`REVIEW` because clearing the row would not touch the footnote.

**One boundary worth writing down, which is not a defect.** The test answers whether the URL *answers*
- its own title says so - not whether the page still holds the content the citation claimed. A host
that serves a 200 for a missing page is therefore `reachable`, and no HEAD sweep can tell otherwise.
Correctly out of scope here; it becomes a real question in Phase 4, where link *content* is used, so
it is recorded rather than fixed.

**Justified deviation from the plan.** The plan's "~45 min at 24 parallel" is described in the
module as "a wall-clock estimate, not a licence to hammer them"; it keeps the shared Fetcher's own
worker count because the sweep talks to 4,939 third-party hosts. Slower, and the right call.

**Still to prove (labelled unverified):** the run-level properties - that two offline runs over a
quiescent cache are byte-identical, that the mutation teeth bite, and that the reported counts
(5,071 findings over 2,806 sites) reproduce. Those are blocked on the watcher.

## Migration 0018: my own 0017 could not write a boolean column

Found by the HERO lane of wave 3, which refused to work around it and reported instead - the right
call, and the third time this session that a lane caught something I shipped.

**The defect, reproduced by me before touching anything** (production, inside `BEGIN; ... ROLLBACK;`,
so nothing could be written):

```
ERROR:  operator does not exist: boolean = text
QUERY:  UPDATE wiki_images SET is_hero = $1 WHERE id::text = $2 AND is_hero IS NOT DISTINCT FROM $3
CONTEXT:  PL/pgSQL function apply_remediation_change(...) line 24 at EXECUTE
```

`apply_remediation_change()` built its statement with text parameters. That is only valid for text
columns. It dies while *planning* - a primary key that cannot exist (`id = -1`) fails identically -
and fixing only the WHERE is not enough: the SET then fails with 42804 ("column is of type boolean but
expression is of type text"). `wiki_images.is_hero`, `is_lead` and `is_excluded` are all boolean, so
**the entire image half of the remediation was blocked by my own primitive.**

**Why it shipped:** `0017_migration_selftest.sql` exercised a TEXT column only. The self-test could
not see boolean, and neither could I, because I wrote the test around the case I already knew worked.
That is the same shape as the T07 `final`-key bug and the malformed Clopper-Pearson interval: the
instrument agreeing with itself.

**Fix: `migrations/0018_remediation_change_log_boolean.sql`** - `CREATE OR REPLACE`, forward-only,
0017 untouched. It resolves the column's type from `pg_attribute` and casts both operands, so it works
for every column type rather than for the one I happened to test.

**A second defect found while fixing it: my first truncation guard was a check that could not fail.**
I added a round-trip check so the journal cannot record a value the row does not hold (a varchar(200)
column silently truncates a longer value, and a reversal read from the journal would then write back
something that never existed). My first version compared the stored value against
`$1::<full column type>` - and a cast to `character varying(200)` truncates just as silently as the
assignment does. **Both sides were truncated, so they always matched**, and the guard accepted a
250-character value into a varchar(200) column. Observed as `C6 FAILED a 250-char value into
varchar(200) was accepted`. The check now compares in the column's base type
(`format_type(atttypid, NULL)`), which cannot truncate, and therefore catches the case while still
allowing a value-preserving coercion.

**Teeth proven, not asserted.** On a temp table, so the live function was never broken while HERO was
writing:

```
TEETH C1: old form FAILS as claimed -> operator does not exist: boolean = text
TEETH C1: new form WORKS (boolean flips)
TEETH C6: full-type comparison is BLIND to truncation (why the first guard passed)
TEETH C6: base-type comparison SEES it (this is the fix)
```

**`0018_migration_selftest.sql` now passes 10 of 10** (`selftest done: 10 ok, 0 failed`), covering
boolean, text and integer writes, NULL-clearing, the truncation guard, the wrong-old-value refusal,
the nonexistent-PK refusal, the table allowlist and the unknown-column refusal - and
`change_log_rows_must_be_0 = 0` after the rollback. C6's teeth were demonstrated by the accident
above; C1's by the temp-table probe.

**Third thing fixed in passing: 0017's refusal messages were garbled.** PostgreSQL's `RAISE` uses a
**bare `%`** placeholder - `%s`, `%I` and `%L` are not specifiers there, each prints its argument
followed by the literal letter. Measured: `RAISE NOTICE '%L', '<NULL>'` prints `<NULL>L`, and `%I`
consumes an argument (so a spec without one raises "too few parameters for RAISE"). Production was
printing `card_statsI.card_descriptionI` and `<NULL>L`. 0018 uses bare `%` throughout; the message
now reads `... for site_id=5cc613ff-... expected 1 row, matched 0 - the old value is A Roman bridge
still in use today ...`, which matters because a human has to triage these refusals during a write.

**Two of my own test bugs, both caught by running it:** `card_stats` has no `id` column (its key is
`site_id`), and `sort_order` is NOT NULL so it cannot serve the NULL-clearing case (used `thumb_width`,
which is nullable). Also: C6 initially reused a value that C3 had already overwritten in the same
transaction, so the expected old value was stale.

**Applied to production** (DDL only, `CREATE OR REPLACE`; `BEGIN / CREATE FUNCTION / COMMENT / COMMIT`).
Not recorded in `applied_migrations`, so the deploy job re-applies the identical, idempotent body.

## Wave 3 / FACTS: the Phase-3 worklist, and a 2x contradiction in the plan's own cost anchors

Read-only lane, no DB, no commits. Deliverables under `output/remediation/phase3_worklist/`:
`WORKLIST.jsonl` (1,840 records, worst-first), `WORKLIST.md`, `BATCH_PLAN.md`, `FINDER_BRIEF.md`,
`REVIEWER_BRIEF.md`, `MECHANICAL.md`, `_counts.json`, `build_worklist.py`, `build_mechanical.py`.

**I re-derived every headline number independently rather than accepting the report** (my own script
over the ten `run_t*/findings.jsonl`, not the lane's):

| test | sites (mine) | sites (lane) | findings |
|---|---|---|---|
| T01 | 1,063 | 1,063 | 1,175 |
| T02 | 117 | 117 | 117 |
| T03 | 875 | 875 | 875 |
| T04 | — (0 findings) | 0 | 0 |
| T05 | 70 | 70 | 70 |
| T06 | 3,010 | 3,010 | 13,020 |
| T07 | 2,806 | 2,806 | 5,071 |
| T08 | 94 | 94 | 99 |
| T09 | 5,004 | 5,004 | 17,315 |
| T10 | 4,010 | 4,010 | 49,691 |

**Union of the factual tests (T01/T02/T03/T05) = 1,840 exactly**, and every `run_t*` directory holds
exactly one `test_id` - so the union really was rebuilt rather than read from the top-level
`findings.jsonl`, which the lane correctly identified as holding **T03 only**. `run_t06_reverify`
duplicates T06's 13,020 rows and is not an eleventh check. Phase 3 = **1,813** sites (1,840 minus 27
mechanically settlable), severity severe 468 / moderate 1,174 / cosmetic 171.

**The lane's real finding: the plan contradicts itself about its own cost, by exactly 2x.** §13 states
"~40,000 tokens per two-stage-reviewed site" *and* "run 1 = 36 agents / 3,653,051 tokens / 37 min at
10-14 parallel" with "5 sites per agent". But 3,653,051 / 40,000 = **91 sites**, while 36 x 5 = **180**.
Both cannot hold. The consequence is the size of the Phase-3 run: **~36.8 M tokens / ~6.2 h, or
~72.5 M tokens / ~12.2 h.** The lane flagged it and refused to invent a resolution, which is right -
the plan is not its lane. Recorded here as an open decision input, not resolved by averaging.

**What that implies for the cost model, stated as an estimate with its basis.** §13's recommended
middle path is $1,100-1,400 over ~6 days, and the plan prices Phase 3 at about $350. Those figures
assume a frontier model's per-token price. On `deepseek-v4.1-flash` (input 0.15 / output 0.60 /
cache-read 0.003 per million) the same 37-73 M tokens cost on the order of **$10-40**, because the
workflow is input-dominated and cache-heavy. The 363 batches / 726 agent runs (finder + reviewer, 5
sites each) also amortise the ~31.5 k fixed per-agent overhead across five sites, which is what makes
the 40 k/site anchor plausible at all. **This is an estimate, not a measurement** - the two anchors
differ 2x, and no Phase-3 run has happened yet. The honest next step is to price ONE batch of five
sites before funding 363 of them.

**Second finding, unfixed by design:** 8 T05 sites carry both a `set` and a `review` finding
(Satsurblia Cave, Didnauri, Armazi, Tsutskhvati Cave, Tsona Cave, Kutaisi, Dmanisi, Easter Island).
They appear in the Phase-3 list for the review finding while a script settles the `set` finding - so
the same site is worked twice unless the fleet dedupes by `(site, field)` rather than by site.

**Two of the lane's own bugs, found by running it:** 4 typing errors in its first script (fixed), and
a first `WORKLIST.jsonl` built from the wrong source. Its suite run reported `1954 passed, 3 skipped,
57 deselected in 156.05s`, matching the gate result I measured independently.

## Wave 3 / SCOPE: T11 closes the census gap, and 69 vs 84 is settled - by evidence, not by splitting

**The question I left open is answered.** S12's 84 is not the plan's number disagreeing with the
project's rule. It is **two different things added together**: 69 sites strictly out of the time
window **plus 15 sites with no `period_start` at all**. Verified independently by my own recompute
over the frozen snapshot, not by reading the lane's report:

| rule | count |
|---|---|
| strict `ps > cutoff` (Americas 1500 / RoW 500) | **69** |
| period-inclusive `ps >= cutoff` | 78 (107 sites sit exactly on 500/1500) |
| `period_start IS NULL` | **15** |
| **69 + 15** | **84 = S12** |
| 78 + 15 | 93, so the boundary rule does **not** explain 84 |

The assessment says it verbatim (`_wf2_result.json`, copied to `scope_scratch/wf2_s12.txt`):
*"4.920 pass / 84 fail (69 ausserhalb, 15 ohne period_start)"*. Plan §7 kept the total and dropped the
parenthetical, which is how it came to look like a contradiction. **My first attempt at this check
reported the inclusive variant as 69, not 78** - I had made the *longitude* boundary inclusive instead
of the *period* one, which is a different rule entirely. Another instrument error, caught because the
number disagreed with a specific claim and I went looking rather than writing it down.

**T11 (`t11_scope_window.py`, 27 tests) reproduces S12 exactly: 84 flagged / 4,920 pass.** Two offline
runs byte-identical (`findings.jsonl` `be3107ddccfea39dad06937e…`). It **imports** the project's own
rule (`pipeline/normalizers/dates.py:58-88`) rather than re-typing it, and `run()` re-calls
`passes_date_cutoff()` on every site it decides, raising an `AssertionError` if the two ever disagree -
so the census cannot publish a second scope rule. Mutation proof: `run()` forced to `[]` → **19 failed /
8 passed**, then restored **byte-identically** (`9e523273676327f3…`). The 8 survivors are the contract
tests, the three "reports nothing" tests and the blind-spot pin.

**It flags, it never retires** - all findings are `Proposal.REVIEW`, because E4's column does not exist
yet and "wrong date" vs "out-of-scope row" is a factual question. 51 severe out-of-window (2 Americas /
49 RoW), 18 museum-typed out-of-window, 15 undecidable. **Documented blind spot, pinned by a test:**
Font dels Coms (fabricated `-3500`) passes, so T11 closes 2 of the gold standard's 3 E3 errors and the
third needs the Phase-3 factual audit. The pass rows must not be read as "all E3 errors found".

### T07 run-level audit: sound

Two offline runs over the now-quiescent cache are **byte-identical** (`findings.jsonl`
`957c9ccdc55996dba80a75ee…`), and both match the watcher's own `run_t07` **exactly**, so its result is
reproducible. 19 tests pass. Final numbers: **5,052 findings over 2,799 sites**, classes refused 3,767 /
server-error 617 / unreachable 405 / gone 252 / unclassified 7 / gone-permanent 4.

**The earlier 5,071 / 2,806 was the pre-healing state, and 5,052 / 2,799 is the healed one** - not a
contradiction. The cache holds 15,230 records, all readable, of which **400 are still pending** (no HTTP
status), down from 516 because the watcher re-probed them. They sit on 181 hosts (`www.megalithic.co.uk`
89, `www.ascsa.edu.gr` 24, `visitmexico.com` 16, `www.tumblr.com` 13) and are deliberately re-probed
every run rather than hardened into "unreachable": a laptop that was offline must not become a permanent
verdict about someone else's host. The 3,439 `403` and 539 `503` responses are *refused*, never dead.

### Instrument error: I could not see the cache at all

My cache probe reported `0 files` where 15,230 exist, and I nearly recorded a working sweep as a lost
cache. The cause: **the probe cache is sharded into 256 subdirectories** (`cache/t07_links/00` … `ff`),
so a flat `glob("*.json")` finds nothing. `find -type f` finds all 15,230. The module was right again;
my instrument was wrong for the fourth time this session. A near-miss on the same pattern as the `final`
key: **an empty result from my own probe is a fact about my probe.**

Also re-proved: `gold_standard/compare_fnr.py` was reformatted by pi-lens, so its earlier verification
was invalidated by the rule I set for myself. Re-running it left `fnr_result.json` **byte-unchanged** -
`fnr_unweighted = 0.6`, `fnr_weighted = 0.6243577462335628`, caught 16 of 40 wrong (per-field sums:
9+7+6+8+3+3+4 = 40 wrong, 1+3+1+8+0+3+0 = 16 caught) - so the formatter moved no number and the
verification stands.

## Wave 3 / HERO: the first production DATA write - 5,438 journalled rows, audited line by line

**This is the remediation's first authorised change to production data** (E1). Migration 0017/0018
were DDL; this moves the hero flag on real rows. 2,719 sites, each swapped from a hero the page was
serving as an 800 px `THUMB_WIDTH` derivative to an already-local 1600 px image.

### The journal (production, read after the write)

| check | result |
|---|---|
| rows | **5,438** = 2,719 `true→false` + 2,719 `false→true` |
| distinct images / distinct sites | 5,438 / **2,719** |
| sites with exactly 2 rows | **2,719** (0 with ≠2) |
| sites with ≠1 promotion / ≠1 demotion | **0 / 0** |
| NULL `site_id_ref` / `old_value` / `new_value` / `evidence` | **0 / 0 / 0 / 0** |
| rows outside `source_id='ancient_nerds'` | **0** - the scoping held |
| `run_stamp` / `test_id` / `confidence` | `2026-09-20_remediation` / `T09/hero-not-best` / `authoritative` |

Every touched site therefore got a genuine **swap** - one demotion and one promotion - not an
accidental net gain. `is_hero` carries **no restart writer** (the OVERWRITER lane proved that), so
this change survives a container restart; that is why the hero move could be made first.

### The invariant, and the accounting that closes on both sides

**0 ancient_nerds sites have more than one hero.** Hero rows stay at **3,858** - unchanged from the
baseline, because this is a swap and not an increase. `scripts/remediation/hero_repair/` code reads
**the cached true Commons dimensions** (`plan.py:28`, `:171-173` reads the wrapper's `entries` key as
warned) and keeps the stored `wiki_images.width` only as a **cross-check** - `plan.py:314` names the
column "the one T09 measured wrong", and **276 candidates were refused** because the stored size was
the sole witness and Commons contradicted it. My specific instruction held: no candidate was chosen on
that column.

The lane's own table looked wrong against my first count, and **it was my count that was narrow**:

| | |
|---|---|
| sites with ≥1 image row | **4,010** (matches T10's 4,010) |
| sites with no image row at all | **994** (matches T10's 994 n/a) |
| = 3,858 with a hero + **152** without | the lane's "152 sites-without-hero-flag", confirmed |
| of the 3,858: **2,719 repaired + 545 rejected + 594 no candidate** | sums exactly |
| repaired = **1,344 tier D + 1,375 tier C** | sums to 2,719; never a suspect tier A/B |
| plan-rule candidates = 2,719 + 545 = **3,264** | **the plan's own 3,264, reproduced** |

I had counted 134 "has a usable image but no hero" because I excluded `is_excluded` rows; the lane
counted 152 sites that have image rows at all. Both are honest, they measure different things, and
994 + 152 = 1,146 = every hero-less site. **The split I explicitly asked for is answered:** 3,264
replaceable = 2,719 repaired + 545 rejected by the stricter rule.

### ROLLBACK.sql is the exact inverse - verified, not assumed

`APPLY.sql` was regenerated at 23:48 (after the 0018 fix) while `ROLLBACK.sql` kept its 23:45
timestamp, so the rollback could have been stale. It is not: it is set-based (`CREATE TEMP TABLE
_hero_plan` + one `UPDATE … FROM`), and against the live journal

* 5,438 plan tuples, 5,438 distinct image ids,
* journal ids absent from the rollback: **0** (nothing unrecoverable),
* rollback ids absent from the journal: **0** (no phantom values),
* `site_id` disagreeing with the journal: **0**,
* rows where the rollback is **not** the exact inverse of what APPLY wrote: **0**.

It restores the pre-write state for all 5,438 rows. Each tuple also carries a **three-source evidence
chain** (`commons:imageinfo`, `snapshot:wiki_images`, `census:T10`) and a written reason, which is what
makes a later disagreement arguable rather than a matter of trust.

**Two of my own probes failed on the way to this** - both were my parse, not the artifact: I first
searched for 5,438 separate `UPDATE` statements (there are 2, it is set-based), then for 4-field
tuples (they have 7, with the reason and a JSONB evidence array). The near-miss is worth naming
because the second failure *looked* like a real finding - "5438 ids unrecoverable" - and would have
been a false alarm about a rollback that is in fact exact. Same discipline as the sharded cache: **when
my probe contradicts the artifact, suspect the probe first.**

**Gate suite, run by me rather than accepted:** `2023 passed, 3 skipped, 57 deselected, 32 warnings in
150.94s` - the 3 skips are the two known refactors plus `THEO_REGEN_TEST`.

## T10 independently re-run - and the caveat that sits underneath the hero write

Two offline runs are **byte-identical** (`findings.jsonl` `c75583da5430e3d23fe8d457…`) and both match
`run_t10` exactly. **49,691 findings over 4,010 sites**, tiers: A **3,858**, B 9,559, C 25,569,
D 10,705 - **sum 49,691**, the whole scoped gallery, with no image unclassified. Tier A's count equals
the hero count exactly, which is what makes "A = the current hero" a cross-check rather than a claim.

**The caveat, and it is material because HERO's promotions lean on it.** Every T10 run prints its own
signal fidelity:

> S faithful, F faithful, P faithful (fetched), D reconstructed from the 5,004 curated site names and cut
to the plan's 4,396-token size by corpus frequency, E partial (6 of the plan's 67 non-photo terms),
A narrow reconstruction, B unavailable: the plan's 41-city list with coordinates is not in this
repository

So **four of the eight signals are reconstructions or absent**, exactly as §6.4's loss of the curated
lists predicted. It is reported on every run rather than buried - which is the requirement I set when
I saw the lists were gone - but reporting it does not remove it.

Why that touches the write I approved: tier D is defined as *in the site's own P373 category, no
off-topic word signal, the site's name in the filename*, and HERO promoted **1,344 images from tier D
and 1,375 from tier C**. The P373 half of that is sound (**P is faithful, fetched**), and so is the
filename half. But the *off-topic word* half runs through E (6 of 67 terms) and A/B/D - the rebuilt
signals. A weakened off-topic filter makes tier D **more permissive** than the plan intended, so a
promoted hero could in principle be off-topic in a way the full signal set would have caught.

**What limits the exposure, stated as limits and not as reassurance:** HERO never promoted from the
suspect tiers A (the old hero) or B (museum-word / museum-city >150 km), the candidate's true Commons
original had to be genuinely >= 1600x900, and the whole change is journalled and reversible - I verified
`ROLLBACK.sql` restores all 5,438 rows. So the failure mode is "a wrong-but-real 1600 px image is the
hero", not data loss, and it is one statement to undo. **Residual risk, not resolved:** the 2,719 new
heroes have not been visually reviewed. The plan's own gallery-audit stage is where that happens, and
it has not run yet. I am recording this rather than calling the write fully vindicated.

### Re-proved after the formatter, and my fifth instrument error

pi-lens reformatted `hero_repair/plan.py` after the lane finished, which by my own rule invalidates
its verification until re-proved. Re-emitted from the reformatted code with `apply.py --emit`:

* **`APPLY.sql` byte-identical, sha256 `33cbab582f830378` - the same value the applied file carries.**
  So the reformat changed no behaviour and the applied statement is still the rehearsed one,
* `ROLLBACK.sql`, `PLAN.jsonl`, `SKIPPED.jsonl` byte-identical from `plan.py --write`,
* `tests/remediation/test_hero_repair.py` -> **42 passed**,
* HERO's `--verify` predicate, run verbatim by me, prints **1,139** and **1,041** - both reproduce.

That last one cost me five wrong answers. HERO reported "shorter than 900 px 3,671 -> **1,041**"; I
measured **1,033** and could not close the 8. I guessed three definitions in SQL (NULL handling,
`is_excluded`, `<=900`, `thumb_width`), then guessed that HERO had lost its source filter - and
"proved" that by measuring table-wide heroes, which are the same 3,858 because **no hero exists
outside `ancient_nerds`**. All five were wrong.

Reading the code settled it. `apply.py:107-119` counts **sites**, not rows, using the SSR's own pick
order: `ORDER BY is_hero DESC, is_lead DESC, sort_order LIMIT 1`. So a site with no hero still serves
an image, and eight of those serve one under 900 px. **HERO's number was right and mine was the wrong
unit** - my probe, for the fifth time this session (the Clopper-Pearson interval, the `by_field`
annotation, T07's missing `final` key, the sharded cache). Same lesson every time: **when my probe
contradicts the artifact, suspect the probe.** Twice today the wrong guess looked like a finding.

I also wasted one attempt on my own syntax: `plan.py` calls `relative_to(ROOT)` on `--out`, so a
relative path raises `ValueError` and **no file is written** - and my "DIFFERS" lines then reported a
missing file as a difference. A comparison that cannot distinguish "absent" from "changed" is not a
comparison.

### The split I asked for, answered in full

HERO's `PLAN.md` answers both report items I demanded. **The 3,264 is split, not refuted:**
**2,719 repaired + 545 rejected = 3,264** exactly. The 545 decomposes into **276** sites where the
stored `wiki_images.width` would have been the *sole* witness (and Commons contradicts it) + **269**
refused on T10's own suspect tier, with 594 sites having no candidate under either rule. Both rules do
read the stored column - the point is that where it stood alone, the plan **refused** rather than
trusted it, which is exactly the discipline I required given T09 measured that column wrong on 11,653
rows. The upscale guard fired on **0** rows and is documented as firing on 0 rather than quietly
dropped.

The **152** hero-less sites are explained and were left alone deliberately: `is_lead` is true for
exactly the 3,858 hero rows, so those 152 already serve their lowest-`sort_order` gallery file - a
1600 px local file - and "planting a flag there would change which image the site serves without a size
defect to justify it". That is the same fact that explains my 1,041. A refusal with a reason, not a gap.

**Atomicity, evidenced rather than asserted:** the failed first attempt raised inside the transaction
and left `journal 0 / heroes 3,858` - the one-transaction design demonstrably swallows a mid-way
failure. `--rehearse` on the identical byte-identical file reported `5438 row(s) changed and
journalled`, then rolled back to `journal 0, >1 hero 0`.

**Verdict: HERO's lane is sound.** Journal, rollback, invariant, scope, accounting and the reformat
re-proof all hold, and its two headline numbers reproduce from its own query. The residual that
remains is the one already recorded above - the tier system underneath the selection has four of eight
signals rebuilt - and it is a review gap, not a correctness failure I can demonstrate.

## Wave 4 audit — GALLERY lane, and a correction to my own offsite record

Date: 2026-09-21. Wave 4 workflow `ce8c7bcc-6148-48c2-bda5-29e43d4beb6e`.

### GALLERY — accepted, with one premise corrected

`output/remediation/gallery_design/{DESIGN.md,COST.md}`. The lane answered the question it was
actually asked, and answered it by measuring rather than assuming:

  * **A vision model IS reachable.** It live-probed `deepseek-v4-flash-vision-exp` (registry entry
    `"input": ["text","image"]`) with three real requests and got correct answers - and it found the
    non-obvious requirement that the gateway rejects the call with `MissingSessionID` unless an
    `x-opencode-session` header is sent. It also identified a second transport already in the project
    (`pipeline/lyra/minimax_shared.py:537-559`), and located the known defect there (`base_resp` is
    never checked, so quota errors are recorded as rejections).
  * **It labelled the limit of its own proof.** Capability was measured; *competence* was not, and it
    says so in the first paragraph and again as open risk 1. That is the correct distinction and the
    reason its recommendation starts with a 200-image pilot.
  * **Cost model is measured, not asserted:** 403 input tokens at 800x600 and 774 at 1280x960 (real
    probe usage), list prices from `models-store.json`. Total for G2-G4 (about 23,100 calls):
    **$4-8**, or ~$0 under the MiniMax flat plan. This independently corroborates the FACTS lane's
    finding that the plan's own cost anchors do not add up.

**The one thing I did not accept.** DESIGN.md section 2 and section 6 state that the image bytes are
only on the VPS and that the workstation "cannot reach the images without re-downloading ~50k files
from Commons". The lane read `public/data/images` and found 2 files (both `index.json`) - correct -
and concluded the corpus is not on this machine. It missed the offsite copy:

    C:/PythonProjects/AncientMap-Offsite   49,788 .webp   20.4 GB   4,017 shard dirs

I proved it is complete per shard rather than by a total, because my own earlier count was wrong (see
below). Corrected in place, since this design will drive Phase 2 work. What actually changes is
small but load-bearing: the execution site becomes a **transport** decision, not an image-availability
one - and the stated reason inverts, because the workstation has a vision transport this lane proved
works, while **VPS reachability of either model was never tested by this lane at all**. The surviving
argument for the VPS is throughput, not reachability.

### My own offsite number was wrong, in the same way HERO's was

Recorded earlier in this remediation: `vps=49790 local=49787 diff=3 ... 49,787 + 3 = 49,790`. The
conclusion (the offsite copy is complete) was right; **two of the numbers were not**:

  * `49,787` was a count of **files** in `images/`, which includes `index.json` and `index.json.gz`.
    The true image count there is **49,785**.
  * `49,790` was therefore never the VPS's image count either. The VPS holds **49,788**.

So the gap was 2 smaller than the arithmetic implied, and the arithmetic only looked closed because
a file count was standing in for an image count. This is the **sixth** time this session that a
number looked impossible or too tidy because the *measuring code* was wrong, and the second time in
exactly this shape - HERO's 1,041-vs-1,033 was also a rows-vs-sites unit error. Both times the
artifact was right and my instrument was not.

Re-measured with an instrument that cannot make that mistake: per-shard counts keyed on hex shard
names, so no cross-platform `sort` collation is involved and a single missing file would name its own
shard. Result:

    vps shards=4017  files=49788        shards only on VPS          : 0
    loc shards=4017  files=49788        shards only locally         : 0
                                        shards with differing counts: 0

The offsite copy is complete, and it is now proven bijectively rather than by a matching total.

### MECHANICAL — blockers triaged, not obeyed

Two static-analysis blockers landed on the live lane's files. The lane is running (159 turns, last
activity 3s), so under the one-writer-per-tree rule I did not touch its tree; I steered the **owner**
to fix what is real, and explicitly told it not to "fix" what is not:

  * `scripts/remediation/mechanical/plan.py:1102` - **real**: `ChangeRecord(evidence=[...])` passes a
    `list[dict[str, Any]]` where the field is declared `tuple[dict[str, Any], ...]`. A journalled
    record is the wrong place to leave a declared contract and an actual value disagreeing. Owner to
    reconcile at the source; **no `# type: ignore`**.
  * `scripts/remediation/mechanical/apply.py:95,455` - "Call without try/except" - **false positive**,
    same adjudicated rule as the seven earlier hits: CLAUDE.md's "NO FALLBACK CODE" forbids the pattern,
    and an unhandled traceback is an acceptable failure while a swallowed exception is not. Told the
    owner that leaving them unwrapped is the correct choice and needs no justification, and that if it
    does handle them the failure must be loud, non-zero and name the file - never a default, never an
    empty result, never a bare `continue`.

Also confirmed the new `scripts/merge_rewrites.py` path-traversal advisories are unreachable: the
script has **no** input surface (no `argv`, `argparse`, `os.environ` or prompt - grep returns 0), so
every path is a compile-time constant derived from `ROOT`.

## Wave 4 launched - and a lane's correct finding that my re-check nearly reversed

Wave 4 (`ce8c7bcc-6148-48c2-bda5-29e43d4beb6e`, launcher `scripts/remediation/fleet_wave4.js`) runs
three lanes, all `deepseek-v4.1-flash`, fresh context, 20 M token budget:

* **MECHANICAL** - settle the sites a deterministic script can settle, with the same journalled
  primitive the hero write used, `ROLLBACK.sql` written before `APPLY.sql` and rehearsed on the
  byte-identical file. The only lane permitted to touch production.
* **PILOT** - run **one** Phase-3 batch of five sites end to end and report what it costs, because the
  plan's own cost anchors contradict each other by exactly 2x (~40,000 tokens/site implies 91 sites;
  "36 agents x 5 sites" means 180). Averaging two contradictory anchors would be inventing a number,
  so the lane measures instead. Read-only.
* **GALLERY** - design the gallery audit (Phase 2 items 2-5) and settle whether anything reachable here
  can judge an image visually, rather than assuming a vision model exists. Read-only.

### The episode worth recording: I nearly logged a correct finding as false

Before writing the PILOT brief I checked the FACTS lane's claim that 8 T05 sites "carry both a `set`
and a `review` finding". My check found **0**, so I was about to record the lane's finding - which is
already in the audit trail - as wrong.

It was **my reading that was wrong, not the finding.** T05's 70 findings do sit on 70 distinct sites
with no site carrying two proposals; that part of my check was right. But the 8 are the sites that
carry a **set finding under T05 AND a review finding under another check** - the overlap of the
mechanical set and the review set:

| | |
|---|---|
| mechanically settlable | **35** |
| ... that also carry ≥1 review finding (both lanes would work them) | **8** |
| ... mechanically settlable only | **27** |

The 8 names are Armazi, Didnauri, Dmanisi, Easter Island, Kutaisi, Satsurblia Cave, Tsona Cave and
**Tsutskhvati Cave Natural Monument**. And **35 = 27 + 8 explains MECHANICAL.md's 27** - the clean
mechanical set is the 35 minus the 8 that Phase 3 will also touch. So the lane's number and its names
were both right; only its wording was loose, and my verification read that wording one granularity too
narrowly and manufactured a contradiction out of it.

**This is the mirror of the five earlier instrument errors.** There my probe was too *coarse* and
reported something impossible (0 files where 15,230 existed; 1,033 where the answer was 1,041). Here
my probe was too *narrow*: it answered a stricter question than the one asked, got 0, and I was one
step from overwriting a correct record with my own misreading. The rule that covers both directions:
**when my probe contradicts an artifact, suspect the probe - and check that I am asking the claim's
own question before I call it false.**

The brief now states the precise version, including that no T05 site carries two proposals, so the
next reader cannot repeat my mistake.

## scripts/merge_rewrites.py could not fail - proven before and after, and fixed

This is the Phase-5 generator, and the defect was recorded earlier from a sandbox reading. It is now
proven against both versions, same fixture, all ten batch files missing (today's real state):

| | exit | `public/data/card_descriptions.json` |
|---|---|---|
| **OLD (HEAD)** | **0** | **overwritten** - `{'site-0': ...}` replaced `{'sentinel': 'untouched'}` |
| **NEW (fixed)** | **2** | untouched; `FATAL: 10 of 10 batch file(s) missing: [0..9]. Nothing was written.` |

The old version reported success while every input was missing **and wrote the deploy-relevant file
that `api/main.py` imports at startup**. `sys.exit` appeared **0 times** in it; `verify_descriptions.py`
has **0** as well, so the re-validation it called at the end could never signal anything, and its
return code was never read. `FIELD_CONTRACT.md:220` had already recorded the rule this violates:
"Do not trust its exit code."

The rewrite fails closed with six distinct exit codes, and writes nothing to `public/data/` unless all
ten batches are present, every rewrite is valid, at least one rewrite exists, the description count is
unchanged, **and** the re-validation flags no more descriptions than before. It compares the flag
*count* rather than the exit code, precisely because that script's exit code carries no information.
On a regression it restores the working copy to its pre-run content, so the tree is never half-changed.

`tests/remediation/test_merge_rewrites_fails_closed.py` (10 tests, all green) drives the **real**
script and the **real** verifier in a throwaway tree - both resolve their paths from `__file__`, so the
sandbox is faithful and one test proves the real repository's `public/data/` is byte-unchanged.
`test_mutation_guard_is_load_bearing` disables the incomplete-batch guard's *condition* and shows the
script then walks on to the next guard (`EXIT_NOTHING`), which is what proves the incomplete-batch test
is not passing by accident. My first version of that mutation was worse than useless: it spliced the
guard out by text and landed inside the `len(missing)` parenthesis, so the mutated script would have
failed to *parse* and the assertion would have passed for the wrong reason. The mutation now compiles
the result before running it.

### Two real typing errors that the "stale" label was hiding

The plugin reported `test_t03.py` as `[stale - re-run to confirm]`, and I had earlier recorded
"Success: no issues found". **Running mypy myself found two real errors** at `:265` and `:271` - and the
plugin's own coordinates (`:208`, `:214`) did not match. Ground truth is the tool, not the label:
`Evidence.quote` is `str | None`, so both `in` tests operated on an optional. That fails **loudly**
(`TypeError: 'in <string>' requires string as left operand, not NoneType`), so it was a typing defect
and not a silent-pass path - but the test was relying on a precondition it never stated. Both now
assert the quote is present first, which strengthens the tests rather than relaxing them.

### The two dozen blockers I refused, and why

This turn the plugin raised 7 blockers of the form "Call without try/except - throws on invalid input
or missing file" against `merge_rewrites.py` (and the same shape against a scratch file I then
deleted). **Obeying that rule would be actively harmful here, and this project has already decided the
question:** `CLAUDE.md` section "NO FALLBACK CODE" says "Do NOT add fallback logic, defensive coding,
or 'graceful degradation' when fixing bugs", and this session's rule is that *"could not check" must
never turn into "checked and clean"*. Wrapping every read in `try/except` is exactly the inversion the
whole effort guards against, and it would have hidden the very defect fixed above. The expected
failures are already handled explicitly (missing batches -> `FATAL`, exit 2); unexpected ones must
raise loudly with the file name. I left all seven unwrapped, deliberately.

One plugin item I did act on: the `union-attr` error on `sys.stdout.reconfigure(...)`. I first judged
it a project-wide false positive and refused to touch it - the HEAD version of the file flags the
identical error at `:24`, ten scripts share the line, and `scripts/` is outside CI's mypy scope
(`ci.yml:129` is `mypy api/`). That reasoning was right, and then I checked the repo's own convention:
it uses targeted `# type: ignore[codes]` in 14 places, including the *same* `[union-attr]` code in
`pipeline/generate_shared_data.py:30`. So a documented ignore is this repo's established remedy for a
triaged false positive - unlike swapping T06's md5 to sha256, it breaks nothing. `merge_rewrites.py`
now carries one with the reason in the comment. The other nine scripts are left alone: they are outside
this change and editing unrelated files would be scope creep, not cleanliness.

### The fix, and the two things the blocker report was actually right about

Having refused the seven `try/except` blockers on policy grounds, I re-read what they point at and
found a real distinction I had been collapsing. The forbidden pattern is *swallowing* an error to
return a default. Converting an unexpected failure into a specific, loud, non-zero failure is a
different thing, and it is what this project asks for elsewhere ("errors are raised, recorded and
reported"). Doing so also surfaced a genuine bug the blockers were pointing near:

  * both writes now go through a temp file plus `os.replace`. Writing in place with mode `"w"`
    truncates first, so a failure part-way through the dump would have left a **truncated**
    `card_descriptions.json` - including the one `api/main.py` imports at startup, and the copy
    published to `public/data/`. An atomic replace cannot leave a half file.
  * an input that is missing or malformed is now reported as `EXIT_INPUT` **naming the file**, via a
    purpose-built `MergeInputError`. There is deliberately **no blanket `except Exception`**: a bug in
    this script must not be able to look like bad input, so unexpected exceptions still propagate.

Both were then proven to be load-bearing rather than asserted. The mutation harness deleted each
mechanism from the real file and confirmed the matching test fails, restoring the file and verifying
it byte-for-byte afterwards (`restored: True`):

    unmutated  test_malformed_batch_fails_loudly_and_names_the_file  -> PASS
    MUTATED (remove the JSONDecodeError handler)                     -> FAILS as it must
    unmutated  test_atomic_write_cannot_truncate_the_target          -> PASS
    MUTATED (remove the temp-file cleanup)                           -> FAILS as it must

One trap worth recording, because it makes a test look stronger than it is: **`EXIT_INPUT` is 1, and 1
is also what Python exits with on an unhandled exception.** So `assert returncode == 1` would pass
even if the handler did not exist. That test's real discriminating power is the message assertions
(`"rewrite_output_03.json" in res.stdout`, `"not valid JSON"`) - the mutation confirms the exit-code
assertion alone would have proved nothing. `test_malformed_batch_fails_loudly_and_names_the_file` also
cannot be satisfied by guessing: the failing file must be *named*.

### Two more plugin findings checked rather than trusted

  * **`knip: file scripts/remediation/fleet_wave4.js is unused`.** knip is a real gate - `.githooks/pre-push:162`
    and `ci.yml:76` - and I have added `fleet_wave1..4.js`, so a red gate there would have blocked
    Martin's eventual push (the hook fails closed). Ran the gate command itself:
    `npx knip --no-progress --include files,dependencies,devDependencies` -> **exit 0, no output.**
    `ancient-nerds-map/knip.json` restricts it with `"project": ["src/**/*.{ts,tsx}"]`, so the
    launcher scripts are out of scope. The advisory was wrong and the push has no blocker from them.
  * **`python-path-traversal` at `merge_rewrites.py:90` and `:104`.** The flagged sinks are
    `read_json`/`write_json_atomic`, which take a path argument - but this script has **no input
    surface at all**: no `argv`, no `argparse`, no environ, no prompts (verified by grep: 0 hits).
    Every path is a module-level constant derived from `ROOT`. Unreachable, not merely unlikely.

I also made a tooling error worth naming, because it nearly cost the verification: I sent an edit for
`scripts/merge_rewrites.py` inside a call scoped to the **test** file, so it silently did not apply.
The new fault-injection test then failed against the unmodified script - which is exactly how it was
caught. The test had teeth before the fix existed, and that is the only reason the mistake was visible.

### Safety check after the probe

Note for the record: my first attempt to compare the old and new scripts mixed Git Bash's `/tmp` with
native Windows Python's `/tmp` - two different directories - so the sandbox came up empty and the
comparison failed for a reason that had nothing to do with either script. Seventh time this session
that the instrument, not the subject, was at fault. Running the whole comparison inside one toolchain
fixed it.

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

## Phase 2 opened — migration 0019, and wave 4's production write audited

Date: 2026-09-21. Authorised by owner decision E1 (DB writes within the remediation scope).

### Migration 0019 — `wiki_images.image_kind`

Written and applied because Phase 2 item 3 needs it and GALLERY's recommendation 1 (persist the 280
verdicts that already exist) is blocked without it. Additive, idempotent, forward-only.

The vocabulary is the one the project's existing VLM prompt already emits
(`pipeline/video/shorts_select.py:51-75`): `site_photo | artifact | map_or_document |
painting_or_artwork | people | other | unknown`.

**The design decision that matters: NULL is not `unknown`.** NULL means *no verdict has ever been
recorded* (initially all 49,691 rows); `unknown` means *a vision model looked and could not decide*.
Back-filling the existing rows to `unknown` would assert a judgement that never happened - precisely
the failure this project forbids ("could not check" must never read as "checked and clean"). Only
`image_kind = 'site_photo'` may ever count as clean, so NULL and `unknown` are both not-clean.

The vocabulary is enforced by a CHECK constraint rather than by convention: a typo like `site_photos`
would otherwise read as "not site_photo" and silently drop a good image out of every downstream
query.

**No allowlist change was needed** - checked, not assumed: the allowlist in 0017 is a list of TABLE
names (`0017_remediation_change_log.sql:85`), not of table/column pairs, so `wiki_images` already
permitted any column. Confirmed against production first (`wiki_images` PK is `id`; 20 columns before,
21 after).

**Teeth, two layers.** The migration carries an inline check that writes an invalid value to a real
row inside a subtransaction; if the constraint were absent the UPDATE would succeed, the following
RAISE would escape its `check_violation` handler, and the whole migration would abort. The re-runnable
self-test (`scripts/remediation/0019_migration_selftest.sql`) then reported **15 ok, 0 failed**,
including C5 "refuses a typo (`site_photos`)" and C9 "old_value is NULL, not the text NULL". Everything
that writes ran inside BEGIN...ROLLBACK, and the post-rollback proof confirmed nothing survived:
journal unchanged, 0 non-NULL `image_kind`, 0 journal rows for the column.

**Idempotency proven by re-running it** (what CI does on every deploy, since 0019 is deliberately
absent from `applied_migrations` like 0018):

    NOTICE:  column "image_kind" of relation "wiki_images" already exists, skipping
    image_kind_columns=1   vocab_constraints=1   wiki_images_cols=21   applied_migrations_0019=0

**Two errors of my own on the way, both caught before they could matter.** The self-test's first draft
addressed the journal primary key as `pk_value`; production says the column is **`row_pk`**, so every
journal assertion would have failed spuriously - found by reading the real schema before running it.
And the migration's first "teeth" block was a check that could not fail: it wrote `WHERE false`, which
touches zero rows, so the constraint was never evaluated, and the `RAISE EXCEPTION` that followed is a
`raise_exception` the `WHEN check_violation` handler does not catch - it would have aborted the
migration every time. Writing to one real row inside a subtransaction is what gives it teeth.

(`docker exec` without `-i` silently fed psql an empty stdin again on the first attempt. My own
recorded regression, sixth occurrence of the same shape: the command "succeeded" and printed nothing.)

### Wave 4 MECHANICAL — the 35-row production write, audited

The journal went from 5,438 rows to **5,473**, i.e. exactly the 35 I authorised in the supervisor
decision. Read back from production:

| check | result |
|---|---|
| rows | **35**, on **35 distinct PKs**, 0 PKs with more than one entry |
| identity | `unified_sites.country` / `T05/country-canonical` / `authoritative` / `2026-09-21_mechanical-country` |
| the pairs | `Georgia (country)` -> `Georgia` **27**, `Chile, Easter Island` -> `Chile` **8** |
| hygiene | NULLs in old/new `0`, NULL `site_id_ref` `0`, empty evidence `0` |
| scope | rows outside `source_id='ancient_nerds'` **0** |
| landed | live values are now Georgia 27 / Chile 8; **`remaining_old_values=0`** |

**Condition (c) - the hub split - is answered and closes the question.** Before, one country had two
indexed hubs. After writing all 35: `Georgia` 30 and `Chile` 11, with **nothing left under either old
value**. That retroactively settles the 27-vs-35 decision: at 27 rows, `Georgia (country)` would have
kept 7 sites, i.e. the defect I was trying to remove would have survived. The plan itself names the
symptom at line 854 - *"Archaeological Sites in Georgia (country) (27)"* is a live hub page today.

**Restart safety, proven rather than assumed.** `pipeline/lyra/data_patches.py:54` does write
`unified_sites.country`, and it runs on every boot (`orchestrator.py:1063-1065` calls
`run_data_patches`). It is harmless here for **two independent reasons**: its WHERE carries both
`source_id = 'lyra'` and `country IS NULL`, and the 35 rows are `ancient_nerds` with non-NULL country.
Either guard alone suffices. No other boot path writes `country`.

**Canonical form checked executably.** `pipeline/utils/country_lookup.py:542` `normalize_country`
returns ISO codes *for comparison* (its docstring says so), and it maps both old and new variants to
the same key - `Georgia` and `Georgia (country)` both to `GE`, `Chile, Easter Island` to `CL` - so
consolidating them cannot change any comparison. No display canonicalizer for `country` exists, so the
plain English names are the correct stored form. `country_slug('Georgia') = 'georgia'`.

**Nothing depends on the old literals:** a repo-wide grep for `Georgia (country)` and
`Chile, Easter Island` across `.py/.ts/.tsx/.json/.sql/.md` returns no code or config hit.

### CORRECTION to the entry above, and MECHANICAL's rollback audited

**A claim I committed in `6e74238` is wrong and is corrected here.** I wrote: *"No display
canonicalizer for `country` exists, so the plain English names are the correct stored form."*
There **is** one: `pipeline/utils/country_lookup.py:572 canonicalize_country_display_name`.

What is actually true, verified executably: its map `_DISPLAY_CANONICAL` holds **only** official-rename
entries (`turkey`/`türkiye` -> `Türkiye`) and returns every other input unchanged. So it left both
`Georgia` and `Georgia (country)` untouched - it neither created the split nor could have fixed it.
That is the correct reason the write needed its own evidence chain, and it makes the write's
justification *better*, not worse: `canonicalize_country_display_name('Georgia') == 'Georgia'` and
`== 'Chile'` for `Chile`, so **the written values are fixed points of the project's own display
canonicalizer** - an additional verification of condition (b) that I had not performed when I made the
claim.

How I got it wrong is the same failure I have recorded repeatedly: I grepped for
`def normalize_country|def country_slug|COUNTRIES`, got nothing for a display canonicalizer, and
concluded from an empty result. **An empty result from my own probe is a statement about my probe.**
The function's name was simply not in my pattern.

**MECHANICAL's `ROLLBACK.sql` audited** - and it is stronger than HERO's. It contains no raw UPDATE at
all (`UPDATE` appears only in comments); the write is a loop calling `apply_remediation_change(...)`,
i.e. the journalled primitive, and it refuses to proceed unless exactly the expected number of rows
moved. It carries three scope guards and two invariants, the second of which verifies that **the
journal and the data agree row for row in both directions**.

Against the live journal (compared in Python, keyed on `row_pk`, no cross-toolchain sort):

| check | result |
|---|---|
| tuples parsed / distinct | **35 / 35** |
| journal PKs absent from the rollback | **0** |
| rollback PKs absent from the journal | **0** |
| rows that are not the exact inverse | **0** |
| reasons present | **35** |
| JSONB evidence arrays present | **35** (34 with 6 sources, 1 with 5 - a site with no Wikidata QID) |

The inverse is exact, not approximate: `rollback.old` (what is in the table now) = {Georgia 27,
Chile 8} and `rollback.new` (what would be written back) = {Georgia (country) 27, Chile, Easter
Island 8}, which is precisely `journal.old`.

**Three instrument errors of mine on this one check, all previously recorded classes, none the
artifact's fault.** An anchored `grep -c "^UPDATE"` returned 0 because the file indents its SQL (and
the command chain then aborted on grep's exit 1, hiding the tail); I wrote a temp file to `/tmp`,
which Git Bash and native Windows Python do not agree on; and `-F'	'` reached psql as the literal
letter `t`, so the "TSV" had no tabs. Each time the file was fine and my probe was not - the same
lesson as the offsite count and HERO's 1,041, now for the fourth time this session.

### Phase 2 / G0 measured: what the 280 stored verdicts actually are

GALLERY's recommendation 1 ("persist the verdicts already computed") is now unblocked by
`image_kind`. Before writing any persister I measured the artifact, and the headline number is
misleading in the usual direction.

The 16 `video-assets/shorts/<slug>/selection.json` files hold **280 entries in two different shapes**:

| bucket | count | keys | carries a kind? |
|---|---|---|---|
| `stills` | **105** | full record incl. **`id`** (the `wiki_images.id`), `filename`, `original_url`, `is_hero`, `width`, `height`, `local_path`, **`verdict`** | **yes** - all 105 are `site_photo` |
| `rejected` | **175** | **only `filename` + `reason`** | no `verdict`, no `id` |

**So G0's honest scope is 105 rows, not 280** - and every one of them is `site_photo`, i.e. the first
105 rows this project can call clean.

The `rejected` reasons are mostly *composition or quality* judgements, which are **not** image kinds and
must not be invented into one: `too small (<WxH>)` ~45, `duplicate (subject: ...)` ~35, `panorama` 15,
`text or overlay` 11, `people prominent` 2, `quality=2` 3, `relevance=1` 1, `subject lost in 9:16 crop`
1, `other site` 1.

Two exceptions worth naming, because they are decisive and they are *not* what I expected:

- **30 entries state a kind verbatim** in the reason: `kind=artifact` 17, `kind=map_or_document` 9,
  `kind=painting_or_artwork` 3, `kind=other` 1. Here the pipeline itself recorded the kind, so this is
  a real prior judgement rather than my inference.
- **32 entries say `no VLM verdict`** - the pipeline is honest about where it never judged. Those 32
  must stay NULL under 0019's rule that NULL means "never judged", and they must NOT be back-filled.

**Decision.** G0 persists the **105 id-anchored** verdicts now (no inference anywhere: `stills[].id` is
literally `wiki_images.id`, and `stills[].verdict.kind` is literally the column's vocabulary). The 30
kind-labelled rejections are recorded as an explicit follow-up, not as part of G0, because they carry
**no id** - only a filename - so persisting them needs a proven slug->site_id and filename->row match
first. Writing a kind on a filename guess would be precisely the kind of invented data this project
forbids, and a wrong row is worse than a NULL row.

### Two advisories adjudicated executably - both false positives

pi-lens flagged **29 issues in `scripts/remediation/mechanical/plan.py`** (e.g. L542/549/551/558 "`yield`
and `return` should not be used outside functions") on a file that has just performed a production
write. Ground truth, run directly: `py_compile` **OK** on both lane files, `ruff check` **All checks
passed!**, `mypy` **Success: no issues found in 4 source files**. L542-551 are ordinary
`return refuse(...)` calls inside a function; the file is 1,349 lines. The snapshot is stale.

The `mypy` success also settles a loose end from the wave-3 audit: the typing error at `plan.py:1102`
that I steered to the file's owner is **fixed** - the file is now clean rather than carrying the 93
pre-existing errors its sibling reported.

`scripts/remediation/census/tests/t02_admin_country.py` was flagged for SQL injection. Adjudicated:
`grep -c 'execute('` = **0**, `grep -c 'cursor'` = **0**, and the file reaches the network only through
`httpx.stream` for the Natural Earth archive in `collect()` - `run()` is offline and the module talks to
no database at all. There is no SQL in it to inject into.

**The pattern, now roughly the twentieth occurrence:** the pi-lens snapshot produces alarming counts
that do not survive one direct tool run. Ground truth is `py_compile`/`ruff`/`mypy`/`pytest`, never the
widget. I record it again because the failure mode is persuasive - 29 syntax errors in a file that
just wrote to production is exactly the kind of claim that deserves to be checked rather than
believed.

## Phase 2 opened on DATA: G0 persists the already-computed verdicts (105 rows)

Wave 4 closed, and with it GALLERY's G0 became executable. This is the first *data* write of the
remediation that is not a repair of a known error - it records verdicts the shorts pipeline had
already made and thrown away.

**The write, read back from production after it committed:**

| fact | value |
|---|---|
| journal rows for `2026-09-21_gallery-verdicts-persist` | **105** |
| journal total | **5,578** (5,473 + 105) |
| distinct `row_pk` | **105** (0 duplicated) |
| table / column | `wiki_images` / `image_kind` only (0 rows elsewhere in this run) |
| test id / confidence | `G0/vlm-kind` / `authoritative` |
| `old_value IS NULL` | **105** - and `old_value = 'NULL'` returned NULL, not false, which is the proof it is a real NULL rather than the text |
| `new_value` | `site_photo` for all 105 |
| `site_id_ref` set | 105 / empty evidence **0** |
| rows outside `source_id='ancient_nerds'` | **0** |
| distinct `applied_at` instants | **1** (one transaction) |
| landed `image_kind = 'site_photo'` | **105** |
| curated rows still NULL | **49,586** |
| rows with a kind outside the vocabulary | **0** |
| **non-curated rows carrying a kind** | **0** |
| `is_hero` true among the 105 | 7 |

**Bijection proven, not assumed:** the 105 journal ids, the 105 plan rows and the union of
`id` fields across the 16 `selection.json` files are the same set (`plan == selection ids: True`).
So the write is exactly the set GALLERY measured - no row was invented, none was dropped.

**The undo is committed with the code** (`output/remediation/gallery_audit/ROLLBACK.sql`, 105 rows
back to NULL, each tuple carrying a three-source evidence chain), following the same versioning
rule as the hero lane: the file describing an action not yet taken is versioned, the regenerable
files describing the action already taken are ignored.

**Four of my own instrument errors on the way, all caught before they mattered:**

1. **A wrong `# type: ignore` code.** I wrote `# type: ignore[arg-type]` where the real error is
   `call-overload`. The project sets `warn_unused_ignores = false`, so mypy stayed silent and the
   plugin caught it. Credit where it is due: this is a case where the widget found something the
   project's own config would have missed. Fixed at the source with a checked conversion
   (`_as_int`), not by correcting the ignore code.
2. **A success reported as failure.** `--check-primitive` ran the *apply script's* in-transaction
   verification, which references a temp table the probe never creates; a probe that had printed
   `probe OK: NULL old value accepted, exactly one row moved, value landed` exited 3.
3. **The same defect in its twin call site, missed.** I fixed the probe but left the identical
   dependency in the post-hoc verify path, so a successful `--apply` exited **4**. `_kind_plan` is
   `ON COMMIT DROP`; after the commit it no longer exists. The write itself was correct and its
   in-transaction numbers were all right. Fixed by splitting the queries: the in-transaction
   checks read `_kind_plan`, the post-hoc ones may only read facts that outlive the transaction.
   Lesson recorded: when a defect has two call sites, fix both - I fixed one and the other fired.
4. **`RAISE NOTICE` arrives on stderr, not stdout**, so my assertion on the probe's own
   confirmation initially found nothing. Both streams are searched now.

Two further defects were found by the checks rather than by review, which is the point of having
them: the rehearsal caught a **real SQL syntax error** (`RAISE EXCEPTION '... source_id='ancient_nerds''`
- an embedded literal terminated the message string; the source name is now passed as a `%`
argument and a regression test pins it), and my own new test asserted against its own explanatory
comment **for the third time this session** (`"image_kind = NULL" not in sql` matched the comment
saying `= NULL` is wrong). Both are the same failure mode as the earlier entries: a probe that
cannot ask the claim's own question.

**What this does NOT establish**, carried forward rather than tucked away: GALLERY proved the
vision model is *reachable* and correctly labels colour, but its semantic **competence** on
archaeological imagery is unverified. These 105 rows are a first reviewable batch, not a validated
classifier, and only `site_photo` is treated as clean - the other 49,586 curated images are still
NULL, i.e. never judged. The 30 kind-labelled rejections remain a recorded follow-up.

## Wave 4 closed: the two production writes and the pilot, plus a formatter sweep with re-proof

All three wave-4 lanes finished. Their reports are lane self-reports, which this project does not
treat as reviews; the review is wave 5 (five read-only lenses, each with one question, plus a
`gegenpruefer` that measures).

**Mechanical lane, re-proven after I reformatted its files.** `ruff format --check` flagged all
three mechanical files. My own rule is that a formatter touching already-verified files invalidates
their verification, so the claim was re-established rather than assumed:

| check | result |
|---|---|
| `apply.py --emit` with the reformatted code | `APPLY.sql` sha256 `0e2cb32716c0c2a1…`, `ROLLBACK.sql` sha256 `df1bf7b0c18e73b2…` |
| published values from the lane's own `evidence/11_fingerprints.txt` | the same two hashes -> **byte-identical** |
| `tests/remediation/test_mechanical.py` | 63 passed |
| `ruff check`, `ruff format --check`, `mypy` on the lane and its tests | clean; mypy "Success: no issues found in 5 source files" |
| the lane's own mutation sweep | 30 cases, 30 fired, 0 survived |

Two honesty notes on that table. First, the sweep's attribution is weaker than its headline:
**13** of the 30 mutations were caught by the *named* test, **17** only as a suite-level failure
(the suite went red but not through the test the sweep names), and 1 was skipped because its needle
appears twice. So the sweep proves the *suite* has teeth for 30 mutations, and proves the *named
test* has teeth for 13. The sharper question - which assertions would survive the deletion of the
behaviour they guard - is asked of the wave-5 TESTS lens independently. Second, `git diff` was a
useless instrument for the re-proof: `APPLY.sql` is gitignored by design, so it is untracked and
`git diff` can say nothing about it. The sha256 comparison is what carries the claim;
`ROLLBACK.sql`, which is tracked, was confirmed by both.

**Also measured this stretch, both by running the real tool rather than trusting a snapshot:**

* `scripts/remediation/mechanical/plan.py` **parses cleanly** (`ast.parse` OK, `py_compile` OK,
  `ruff check` clean, `mypy` clean, 1,353 lines) - so the plugin's 73 findings against it,
  including "return outside function" at L585-592, are a stale false positive, now confirmed
  executably rather than waved away.
* **The plugin was right about a real bug of mine.** `scripts/remediation/fleet_wave5.js` did not
  parse: I had put backticks around `apply_remediation_change` *inside* a backtick template, which
  terminated the template. `new AsyncFunction('runs','emit', src)` reproduced it exactly
  (`Unexpected identifier 'apply_remediation_change'`). Note the backtick count in the file was
  even, so a parity check would have missed it - only the real parser found it. That is the second
  genuine defect the plugin caught in this session that my own tools did not, and it is why a
  finding gets adjudicated by running the tool rather than by pattern.

## Closed: the `b9e48fab7` gate run with two failures (undiagnosed, and now shown to be unrecoverable)

A background gate run exited 0 while its verdict text read `2 failed, 2093 passed`. I never captured
those two names, so the record said "undiagnosed". Its output file has now arrived, and it settles the
question the other way: the file is **2,353 bytes / 25 lines** and contains only the tail - the PyJWT
warnings, the three `-rs` skips and the summary line. The `FAILED` lines and the short summary sat
*above* the trim point, so the names are **unrecoverable from this artefact**. That is the recorded
bounded-`bg_run` trap, confirmed on the very case that motivated the rule: a failing gate must be
captured to a file, which is why the next one (`b46d66773`) was and read green at
`2097 passed, 3 skipped, 57 deselected`.

What the tail does still establish, and it is worth having:

* The three skips are **named**, and they are the three known pre-existing ones:
  `test_article_verifier_citations.py:13` and `test_article_writer_citations.py:12` (both refactored
  out of `article_generator`) and `test_shining_ones_regen.py:50` (needs `THEO_REGEN_TEST=1`). So the
  skip count was never hiding a fourth.
* The **32 warnings** are all `InsecureKeyLengthWarning` from PyJWT, raised on **test-local** keys of
  8, 11, 16 and 30 bytes. Test-only, not a production secret defect - recorded because a future reader
  seeing "HMAC key below the recommended length" in a security-adjacent log should know it is the test
  fixtures, not a live key.
* The pass count rose by exactly 4 between the two runs (2093 -> 2097), which is the size of the
  `tests/remediation/` files a live lane was writing at the time. That is consistent with the transient
  failures, but it remains a **hypothesis, not a finding**: the mechanism was never observed directly.

## The exit-0 family, now with its mechanism measured: the task log held 7 bytes

Same run, two artefacts, and the difference is the whole lesson:

| artefact | size | content |
|---|---|---|
| `.pi/tasks/.../b46d66773.output` (what `bg_run` kept) | **7 bytes, 1 line** | `EXIT=0` |
| `output/remediation/logs/gate_after_0019.txt` (the redirect) | 21,221 bytes, 257 lines | the full pytest output, `= 2097 passed, 3 skipped, 57 deselected, 32 warnings =`, 0 FAILED, 0 ERROR |

So the bounded log did not merely truncate the run - it contained **nothing about the run at all**.
`EXIT=0` was the entire claim, and on the earlier gate run (`b9e48fab7`) that exact artefact shape
accompanied a verdict reading `2 failed`. Two conclusions, both now measured rather than argued:

1. **A task log reading `EXIT=0` proves nothing about pass/fail, and may not even be evidence that the
   suite ran.** The verdict must come from a captured artefact. This is why the gate runs redirect to
   `output/remediation/logs/`.
2. **The redirect is not an optimisation, it is the instrument.** Where a fleet lane's deliverable is
   the output rather than a file it wrote, that output does not survive; the lanes in this remediation
   are therefore required to write deliverables to disk, and are audited from those files - never from
   a task-log preview.

## Final adjudication: the t02 "SQL injection" advisory is a spatial-index false positive

Third appearance, so it gets a named mechanism rather than another re-check. The advisory points at
`scripts/remediation/census/tests/t02_admin_country.py:354`, which is not an import and not SQL:

```python
def containing(self, lon: float, lat: float) -> list[str]:
    pt = Point(lon, lat)
    return sorted({self.features[int(i)].admin for i in self._tree.query(pt) ...})
```

`self._tree` is a **Shapely `STRtree`** - an R-tree spatial index - so `.query(pt)` is a geometry
lookup. The scanner's SQL-sink pattern matched the token `.query(`. The decisive check (a file with
no database surface cannot inject into one): `execute(` **0**, `executemany` **0**, `cursor` **0**,
`psycopg` **0**, `sqlalchemy` **0**, `sql.SQL` **0**, `conn.` **0**, `session` **0**, `subprocess`
**0**, `eval(` **0**, `os.system` **0**. The file reaches the network only through its `collect()`
(`httpx`); `run()` is offline.

That is the third distinct instrument-mismatch family in this session, and worth naming as a family:
(1) a probe matching the file's own explanatory **comment**; (2) a probe matching a legitimate SQL
**literal** in a `WHERE` clause; (3) a scanner matching `.query(` on a **spatial index**. Each looked
like a finding and each was the question being asked of the wrong object.

## Wave 5 review, first half: 3 of 6 lenses in (DEPLOY, SECURITY, TESTS) - triage with my own re-checks

The reviews are correct in substance more often than not, and two of the DEPLOY lens's own findings
are refuted by the database. Both directions are recorded, because a checker's output is a trace, not
a verdict.

### Verified by me and REAL (each re-checked independently)

**P0-A - the CI `tests` job cannot collect `tests/remediation/test_mechanical.py`, so nothing deploys.**
The chain is forced and each link was read: `test_mechanical.py:34-35` imports `mechanical.plan` at
module level; `plan.py:124-126` imports `census.tests.t02_admin_country` at module level;
`t02_admin_country.py:137,140` imports `geopandas` and `pyproj` at module level; and
`.github/workflows/ci.yml:184` installs only `-r requirements-api.txt -r requirements.lyra.txt`, in
which geopandas and pyproj occur **0** times each. So collection raises ModuleNotFoundError, `tests`
is red, and `deploy` is skipped. It is invisible locally because the project venv has geopandas -
exactly the hole the working-tree check does not close.

**P0-B - a test ERRORS (not skips) in a clean checkout.** `test_gallery_audit.py:145`
(`test_load_verdicts_on_the_real_input_finds_105_rows`) calls `load_verdicts()` against
`video-assets/shorts`, which `.gitignore` excludes, and `load_verdicts` *raises* when the directory is
absent. Same deploy-blocking consequence as P0-A, and unlike the other two data dependencies in these
files it carries no guard.

**P0-C - third-party live keys are in my committed history, and gitleaks scans the full history.**
Found all three patterns in `output/remediation/phase3_pilot/evidence/`: a Google Maps key
(`AIzaSy...`, 39 chars = gitleaks' default `gcp-api-key` shape) in `Satsurblia%2Fnationalparks.txt:792`,
a Mapbox token (`pk.eyJ...`) in `Didnauri%2Fmapcarto.txt:40`... (path: `Didnauri%2Fmapcarta.txt:40`),
and a Carto key (`cb1_...`) in `Satsurblia%2Fgeorgia_to.txt:1451`. **76 of those evidence files are
git-tracked**, so they are in the commits, not merely on disk. `sast` runs on every push and must
succeed, so this blocks the deploy as well - and it is the single strongest argument for having not
pushed: these bytes would be on GitHub.

### Refuted by me - the DEPLOY lens's findings 6 and 7 are not real

Its premises were reasonable and its reasoning sound, but the database says otherwise. Read-only on
the VPS, `SELECT filename FROM applied_migrations`:

* **`restore_ancient_nerds.sql` IS recorded** (last row), so its 5,005 `INSERT ... ON CONFLICT DO
  NOTHING` lines do not re-run each deploy. Finding 6 is not a finding.
* **`0017_remediation_change_log.sql` IS recorded** too. The deploy loop skips a recorded file, so the
  broken pre-0018 function body is never re-set - the "one-sided recording" window the lens feared
  cannot open. Finding 7 is not a finding.
* `0018` and `0019` are indeed absent from the table, so `0019` does re-run every deploy: finding 3
  stands, including the lens's observation that its writing self-test takes a row lock on a real row.

### The rest of the real list (from all three lenses)

| # | where | what | why it matters |
|---|---|---|---|
| D | `persist_verdicts.py:416-419` | `v.slug` is the only external value not `!r`-ed; a slug with a newline could reach a line-initial `\` in a script piped to psql | asymmetry, proven; exploit unproven - fix the asymmetry, do not claim the exploit |
| E | `mechanical/apply.py:227` | `{source}` interpolated raw into a single-quoted RAISE message | the same defect G0 measured and fixed; the TESTS lens independently noticed the rendered text and read it as correct SQL, which is how it stays latent |
| F | `0018:123-126` | a caller can journal a "change" where `p_old = p_new` | the journal may not lie - same class as 0018's own truncation refusal |
| G | `0019:97-118` | re-run takes ACCESS EXCLUSIVE and writes a real row; and `LIMIT 1` + "must be NULL" can abort spuriously | a deploy that fails for a reason unrelated to the change; the TESTS lens found the same trap independently |
| H | `ci.yml:198` | the CI pytest call has no `-rs` | this project's own rule: a silent skip must never read as green |
| I | `apply.py` / `persist_verdicts.py` | `APPLY.sql` is sent to production with no integrity link to the plan it renders | no privilege gain, but the undo a reviewer checks is unverified |
| J | `test_gallery_audit.py:359,367` | two tests re-implement the rehearsal transform inline, so the module's guard and transform are untested | if the COMMIT strip breaks, `--rehearse` runs the real statement to COMMIT and prints REHEARSAL OK |
| K | `test_mechanical.py:604` | the reconciliation assertion is satisfied by `POST_COMMIT_READS`/the header | deleting invariant 2 keeps all 63 tests green |
| L | `test_mechanical.py:744,751`; `test_gallery_audit.py:215,255` | counts and value-presence asserted, never per-site identity | a plan of 35 right values on 35 wrong sites validates |
| M | `persist_verdicts.py:verify_sql` | the documented `_kind_plan` failure has no regression test | one assertion kills the class |
| N | `ci.yml:36-51` | `migrations/**` and `scripts/**` are in no change filter | a migration-only push skips every code gate yet still deploys |
| O | `phase3_pilot/http_get.py:34` | the `# noqa: S310 - https only` claim is not enforced | a claim without a check, which this project does not allow |
| P | `test_mechanical.py:47-49`; `REHEARSAL_READS` | skip reason names a command that raises; the "left-behind temp table" read filters `nspname='public'` against a `pg_temp_N` object | a message that cannot be acted on, and a metric that cannot fail |

Lens #4 of the TESTS review is the **fifth** instance in this session of an assertion satisfied by
the file's own comment or by a vacuous predicate - the family that keeps producing false assurance.

**Sequencing, deliberately:** SQL, BACKEND and GEGENPRUEFER are still reading these trees, so no file
under review is touched until they finish. The `-rs` gap (H) is itself the reason to trust the skip
counts I have been reading by hand.

## Wave 6a landed (brief amendment), and an honest producer gap it found

The brief worker folded the twelve ratified decisions into both Phase-3 briefs, corrected the
superseded figures in BATCH_PLAN.md and MECHANICAL.md, and wrote the five new false-alarm families as
items 7-11 of the plan's own section 4.3. Gate after its work: **2137 passed, 3 skipped, 57
deselected** - up from 2097, the difference being the lanes' new tests. It changed documentation
only: no code, no database, no commit.

Two corrections it forced on me, both upheld:

* My instruction named the wrong file for section 4.3. `ENRICHMENT_AUDIT.md` has no section 4.3 and no
  false-alarm list at all; the list is `SITES_DB_REMEDIATION_2026-09.md:191`. BRIEF_GAPS.md mislabelled
  it, I repeated the mislabel, and the worker refused to create a second, unreferenced copy.
* Decision 5 was over-broad. The rule stands - no `set` on either prose field in Phase 3 - but
  `card_description` is reverted by the boot import while `unified_sites.description` has **no** boot
  overwriter (I verified this myself: its only writers are two call sites in api/routes/sites.py and
  `restore_snapshot`). The briefs now give the two reasons separately and ground the prose-field rule
  in the Phase-5 split rather than a restart.

**Producer gap, recorded because it must not be lost.** Decisions 2 and 11 introduce a required
`defect` flag and a `true_but_no_correction` verdict. Neither has a producer: grep finds no `defect`
key and no such verdict value anywhere in `scripts/remediation/`, and `census/model.py`'s
`Proposal` enum has exactly SET, CLEAR and REVIEW. They are therefore words in two briefs, not
machine fields - **whoever builds the Phase-3 runner must emit both**, or the two decisions are
decoration. This is the same failure class as the vacuous assertions: a stated guarantee with nothing
behind it.

Also re-proved after the fact: `scripts/merge_rewrites.py` and its fails-closed test had an
uncommitted `ruff format` pass in the tree (quote style plus three line-wraps, no semantic change).
Per the standing rule a formatter invalidates prior verification, so it was re-proved rather than
committed on inspection: ruff format --check clean, ruff check clean, mypy clean, 13 tests passed.

## The credential finding, measured by the real tool - and why I did NOT allowlist it

The DEPLOY lens predicted three keys from a static read. The actual scanner disagrees, which is the
point of running it: `gitleaks git . --config .gitleaks.toml --gitleaks-ignore-path .gitleaksignore`
scanned **3,468 commits / 4.89 GB in 2m44s** and reported **7 findings, not 3**, every one of them
`generic-api-key`, and every one of them in `output/remediation/phase3_pilot/evidence/`:

| file | line | what it is |
|---|---|---|
| `Didnauri%2Fmapcarta.txt` | 40 | Mapbox public token (`pk.eyJ...`) |
| `Petroglyph%2Fasp_guess2.txt` | 120 | `B522BF96E81C10...` |
| `Petroglyph%2Fak_state_parks.txt` | 120 | `B522BF96E81C10...` |
| `Petroglyph%2Fak_state_parks_wrang.txt` | 81 | `B522BF96E81C10...` |
| `Satsurblia%2Fnationalparks.txt` | 853 | `6CjuR6EIMWDdRq...` |
| `Satsurblia%2Fnationalparks.txt` | 1022 | `6CjuR6EIMWDdRq...` |
| `Satsurblia%2Fgeorgia_to.txt` | 1451 | Carto key (`cb1_...`) |

Two lessons from the difference. First, the Google Maps key the lens highlighted did **not** fire - a
careful static read is still not the tool. Second, three of the seven hits are a key neither the lens
nor my own grep had named, because I searched for the patterns I expected rather than letting the
scanner tell me. And every one of the seven comes from a single commit: **`b2dc450e9af7fed5d1ff1cc46bfb2dcb6bc546fc`**,
my own G0 commit that staged the pilot tree - so this is my mistake, in one place, and still unpushed.

**I did not add `.gitleaksignore` entries, and that is the substantive decision.** The file states its
own rule in its header: *"Format: commit:file:rule:line - never add an entry for a live credential."*
These seven are third-party **live** keys in verbatim public HTML. We cannot rotate them because they
are not ours; they are also not expired and not dead, unlike every existing entry in that file, which
records a rotated or expired key. Allowlisting them would turn the gate green by teaching it to ignore
live credentials - the one thing that file forbids, and one of the stop conditions: a check that is
green only because it was weakened.

**The remedy its own rule implies is removal, not exemption.** Plan, to execute only when the fleet is
quiescent and after a `git bundle` backup, because a live VLM lane is still reading that tree:

1. Stop versioning raw third-party response bodies at all. `fetch_log.jsonl` keeps url plus sha256 plus
   retrieval time; the *extracted* evidence already lives in `PILOT.jsonl`, which the SQL lens confirms
   is the artefact actually consumed. The bodies are third-party copyright and a credential carrier
   both, so they should never have been committed.
2. Rewrite the single unpushed commit that introduced them so the blobs leave history, then re-run
   gitleaks to prove the count is 0 - the only way this gate goes green honestly.
3. Record the old-to-new commit hash mapping here, because the audit log cites commit hashes and a
   rewrite would otherwise leave the whole evidence trail dangling.

**This is a Martin decision point, and it is on his open list:** the keys are in history but unpushed,
so nothing has been published. Either the rewrite happens before the first push, or the first push
publishes seven live third-party keys to GitHub and the deploy stays blocked by the sast gate. Both
are defensible; choosing between them is his, because a push is the outward action.

## Wave 5 complete - the measuring lens refutes two of my own decisions

All six lenses are in. The gegenpruefer (the only reviewer with a shell, whose job is to refute its own
recommendation) measured rather than read, and it confirmed the load-bearing numbers with raw output:
1,813 phase3 records / 2,210 findings / **8 `set` = 0.36 %**; 285 coords-only = 15.72 %; PILOT 40 rows =
28 CORRECT / 11 WRONG / 1 UNVERIFIABLE, proposal 28 none / 6 set / 6 review, 110 evidence items of which
**15 carry no HTTP status** (local code and snapshot citations - so "110 evidence items" is not "110
fetches"); COST refuses to average and labels its token figures derived, not measured. It also proved
the pilot's independence rather than asserting it: **14 reviewer fetches, 0 sharing a URL with a finder
fetch**. And it confirmed my "35 = 27 + 8" split precisely: the 27 `set` findings outside Phase 3 sit on
the 27 records whose `phase3` flag is false.

**P1 - the single UNVERIFIABLE verdict does not hold, and this makes the pilot look worse, not better.**
The OSM evidence line for that row quotes a coordinate that belongs to a different node: the node
carrying the name `საწურბლიას მღვიმე` is at 42.3886354, 42.6060480, **1.331 km** from the stored point,
while the quoted 42.3964749, 42.5890186 is an untagged, self-closing node of a `highway=unclassified`
way - and it lies **outside the query's own bounds** (`<bounds maxlat=42.395>` versus lat 42.3965), so it
was never a member of the fetched candidate set at all. The published 2.35 km is exactly the distance to
that road node. The three real candidates sit 60-90 m from each other and ~1.3 km from the stored value,
which is the same shape as rows the pilot itself called WRONG (Karpasia, 3.5 km). So the justification
"three candidates, none authoritative enough" collapses, and the honest verdict is WRONG -> review. The
batch headline becomes **28 / 10 / 2**, and the already-serious false-negative rate becomes 25/40 = 62.5 %,
not 24/40 = 60 %. The direction matters: the pilot was lenient in a second, independent way, and it is
the reviewer who caught it, which is the entire argument for the fleet's division of labour.

**Two decisions of mine are refuted, and I am correcting them rather than defending them.**

1. *"The 285 coords-only sites can never produce a write."* Unbacked in that strong form. Both cited rules
   (FIELD_CONTRACT section 4 item 6 and ENRICHMENT_AUDIT anti-pattern 4) speak only about the *coordinate*
   findings; the census says nothing about those sites' other fields, and the pilot itself wrote findings
   for field classes that "only T01/coords" does not exclude. What is supported is the weaker claim: no
   *census finding* of those 285 is writable. Consequence: they stay in Phase 3 - the scope is **1,813**,
   not 1,528 - because prose and other-field findings are exactly what the pilot found by hand.
2. *"invisible to T02 because T02 only asks about the country."* Refuted by the pilot's own citation:
   `output/remediation/run_t02/findings.jsonl` line 31 names the coordinate as a suspect explicitly. The
   defect is real and unnamed; the reason attached to it was wrong.

**P2 - a systematic error class, not seven accidents.** Seven claims are wrong for one shared reason:
the wrong geometric reference point was used, or a number was published as measured when its provenance
does not support it. Bounding-box centre quoted as the geometry (Danube: 82.7 km, actually **74.18 km** -
an 8.5 km error in three documents marked "measured"; polygon "centre" 73 m, actually the bbox centre,
the centroid is 254 m); a non-existent Satsurblia named-feature query cited as evidence (both 287-byte
responses are Petroglyph queries); a "six largest pages = 70 %" figure that only reproduces by counting
one page in the numerator and not the denominator; a division wrong in the third digit (3,653,051/180 is
20,294.7, not 20,293); and a 102 km distance whose coordinate appears in none of the 76 evidence files,
which contradicts the pilot's own traceability claim section 7 even though the number is right. The rule
this earns, and which I am adding to the briefs: **name the reference point whenever a distance is
published, and never label a value "measured" when what was measured was a bounding box.**

Everything it verified is listed in its report as verified, which is what makes the rest credible: the
Grave Street ranges reproduce exactly with the point 5 m from the nearest way, Juneau 0.396 km, the
Didnauri wikidata ways, the PLOS 25,535-24,408 cal. BP quotation verbatim, the fetch_log totals (76 rows,
57x200, 19 non-200, 2,399,608 bytes), all six COST aggregates, and a 239-token citation audit that found
no invented source. The FIELD_CONTRACT and ENRICHMENT_AUDIT citations all exist verbatim.

## Live state and what remains (written before a context compaction, as a recovery anchor)

**Four lanes are running as this is written.** Wave 6: FIX-1 owns
`scripts/remediation/mechanical/` plus `tests/remediation/test_mechanical.py`, `migrations/0018` and
`.github/workflows/ci.yml`; FIX-2 owns `scripts/remediation/gallery_audit/` plus
`tests/remediation/test_gallery_audit.py`, `migrations/0019`. Both were confirmed writing to disjoint
files. Wave 7 owns the pilot and worklist documents. The VLM pilot worker owns
`scripts/remediation/vlm_pilot/`. Nothing else may be edited until they finish - one writer per tree.

**The complete verified fix list they are working from** (each verified by me directly, not taken from a
report): DEPLOY P0-A the CI collection break, where `test_mechanical.py` imports `mechanical.plan`, which
imports the census T02 module, which imports geopandas and pyproj at module level while ci.yml installs
neither - so the tests job is red, the deploy job is skipped, and migrations 0018/0019 never reach
production. SECURITY 2 the raw `{source}` interpolation in `mechanical/apply.py`. BACKEND B3 the
unchecked post-write read-back that was already blind once. SQL 6 a guard that cannot fire. SQL 7 and
BACKEND B8 the rollback journalling under the apply's own change_key, found independently by two lenses.
SQL 8 a NULL-silent `<>` where `IS DISTINCT FROM` is required. SQL 5 and BACKEND B4 a skipped mutation
counted as fired. SECURITY 4 the `0018` not-a-change guard. CI hygiene: `-rs` missing from the pytest
job, and `migrations/**`/`scripts/**` missing from the backend change filter. BACKEND B5 a claim the code
does not cover. DEPLOY 4b versioning `PLAN.jsonl`/`APPLY.sql`, whose "regenerable" premise is false.
TESTS 1, 3, 4, 6, 7, 8, 9, 10, 12 in `test_mechanical.py` and `test_gallery_audit.py`. And the whole
gallery-audit group: B1 the `--plan` that destroys the rollback artefact, SQL 1/B2 the verify that
compares a run-local count with a table-wide one, SQL 2 the rollback with no executable path, three
fewer guards and never parsed by psql, SQL 3 its single 86.7 KB line, SECURITY 1 the un-repr-ed slug,
SQL 9 a print where a raise belongs, BACKEND B6 a third hardcoded vocabulary, SECURITY 3/B7 the missing
plan-to-apply integrity link and the timeout that cannot say whether it committed, DEPLOY 3/TESTS the
`0019` re-run that is not a no-op.

**Deliberately NOT done, with the reason.** The credential fix's second half - a targeted rewrite of the
single unpushed commit `b2dc450e` so the seven third-party keys leave history - waits for the fleet to be
quiescent, because a rewrite rebases all 42 commits and four lanes are editing the working tree. Before
it: a `git bundle` backup, and after it: the old-to-new commit hash mapping recorded here, since this
log cites hashes throughout.

**Next, in order.** When the fixers land: triage, re-run the gate, re-emit and re-pin the delivered
SQL artefacts where a guard changed. When the VLM pilot lands: label the four contact sheets by eye and
compute the confusion matrix against `VLM.jsonl` - its semantic competence is still unverified. When
wave 7 lands: verify the re-adjudication is visible rather than substituted, and that no stale figure
survives. Then the history rewrite. Then build the Phase-3 runner, which must emit the `defect` flag and
the `true_but_no_correction` verdict that currently exist only as words in two briefs, and which should
run one instrumented batch of 15 sites with real token accounting before scaling to 1,813.

## The t02 SQL-injection advisory, refuted a fourth time - and closed as an instrument mismatch

The linter flagged `scripts/remediation/census/tests/t02_admin_country.py:354` as a SQL injection sink
again, marked stale, claiming the file had changed. It had not: `git status` shows the file untouched,
while `mechanical/plan.py` - which imports it - is being edited by a live lane, which is presumably why
the advisory re-fired. The finding is a false positive and the mechanism is nameable in one line: line 354
is `sorted({self.features[int(i)].admin for i in self._tree.query(pt)})`, and `self._tree` is a **Shapely
STRtree**, an R-tree spatial index (`shapely.strtree` imported at line 145, constructed at line 313) - not
a database, not a session, not a cursor. `query(` occurs exactly once in the whole file, on that object.

The whole-file sink census is zero: `execute(` 0, `executemany` 0, `cursor` 0, `psycopg` 0, `sqlalchemy` 0,
`sql.SQL` 0, `conn.` 0, `session.` 0, `subprocess` 0, `eval(` 0, `os.system` 0. The only network reach is
`httpx` inside `collect()`, which is the contract's designated network phase.

Two instrument slips of my own, recorded because this is how most of this session's false alarms began.
First, three of my grep patterns had an unescaped `(`, so `grep -E` printed a syntax error where a count
belonged - an errored probe says nothing about the file. Re-run with fixed strings, the counts are the
ones above. Second, `text(` counted 11 and I could not explain it, so I did not report it as clean: the 11
are nine calls to this module's own `_text()` helper plus pathlib's `read_text`/`write_text`. There is no
SQLAlchemy `text()` construct in the file at all. My first classifier missed that because it looked for
`context(`-style prefixes and did not anticipate the `_text` boundary - too narrow, the same failure
direction as the probe that concluded a function did not exist because the name pattern was too tight.

Verdict: no code change. A false positive with receipts is not repaired by a suppression, and adding one
would hide the next, real finding in the same place. The advisory is now adjudicated in this log and will
be ignored on later firings for this file.

## The VLM competence caveat, measured and narrowed (and one lane recovered from a stall)

**The VLM pilot did not fail - it finished its measurement and then ran out of wall clock.** The worker
was killed at the 30-minute ceiling, which is why it reported as a timeout, but `VLM.jsonl` had already
been written complete: 200 of 200 verdicts parsed, 0 errors, `finish_reason` stop for all 200, 195 first
attempt, median 11.2 s per tile, 735 s and $0.35088 in total. The timeout fell on the write-up, not the
measurement. My first probe reported the file as missing because I looked for `VLM.partial.jsonl` - the
instrument again: the worker had renamed the partial to the final name on success.

One belief dies here: the gateway is not broken. A previous measurement recorded 664 failures in 733
calls; this run had 0 failures in 200. Whatever that earlier figure described, it was not this endpoint
with this client.

**What was measured.** 200 real rows from the 49,691-image snapshot, seed 20260921, stratified 50 per T10
tier (A hero, B suspect, C grey, D clear), tiles deliberately blinded so the verdict cannot be read off
metadata. Ground truth is my own eye-labelling of all 100 tiles in tiers A and B against the contact
sheets, tile by tile. Result: `site_photo` share is 74 % (A), 40 % (B), 72 % (C), 76 % (D). So the model
reacts to something real in the suspect tier, but does **not** reproduce the boundary between grey and
clear - not necessarily a failure, since tier C's only signal is a weak metadata property (the site name
absent from the filename) that need not be visible in a picture.

**The competence is asymmetric, and that is the finding.** In tier B, agreement is about nine in ten, and
in three disagreements the model was right and I was wrong: a football stadium I read as a colonnade, a
museum ivory I read as in-situ rock art, a basilica mosaic I read as a line drawing. In tier A it
degrades: of the 37 `site_photo` verdicts I accept about 20. The excess is generic landscape - empty
fields, hillsides, a pond, a coastline, a road through fields - and one hard error: `#66405` is a
19th-century engraving returned as `site_photo`. An engraving is not a photograph of a site under any
definition this plan uses. Rejecting documents, objects and people, by contrast, looked reliable
throughout.

So `site_photo` must be read as "an outdoor photograph", not "a photograph of the archaeology". For the
§7 shorts gate and any gallery cleanliness number, treat it as an upper bound on clean images and re-check
the hero tier specifically, where the over-call concentrates.

**Intervention, recorded because it was a stall and not a slow task.** FIX-1 issued a bare recursive
`grep` at the repo root and its shell had been open 600 s. I inspected rather than interrupting: the
process was `grep.exe` at 1 GB resident, and `.git` alone is 35 GB (LFS objects), so the search was
reading tens of gigabytes. That is the trap this project already paid for twice. I killed that one search
process - freeing the child's shell while leaving its 169k tokens of work intact - and steered it to
`git grep` or a scoped `--include` search. Not an interrupt: the child was not progressing on that call,
but it was not lost either.

Limitations, stated in `COMPETENCE.md` as well: the ground truth is one thumbnail pass by me, not an
independent panel; tiers C and D were not eye-checked; no repeat-call stability test was run; the sample
is stratified by tier, so these rates describe the tiers, not the corpus.

## Wave 6 (the post-review fix wave): both lanes timed out, and what that cost

**Both fixers hit the 30-minute ceiling and both artifacts are empty fragments** - one caught the single
line "Now the `--render-rollback` CLI mode in `plan.py`:", the other "Now extract `journalled_ids_sql` in
the module:". So nothing about the work could be taken from the lanes themselves. This is the second and
third timeout of the session (the VLM pilot was the first), and the pattern is now clear: **the brief was
larger than the ceiling allows**, not that the work was hard. The fix is smaller briefs, not more time.

**The receipt's file list is unusable, and provably so.** Both children reported the identical,
alphabetically-sorted list of every changed file - including files in each other's scope. With
`isolation: none` the "changed tracked files" summary is the whole working-tree diff, never per-child
attribution; it also named `scripts/merge_rewrites.py`, `tests/remediation/test_merge_rewrites_fails_closed.py`
and `docs/procedures/SITES_DB_REMEDIATION_2026-09.md`, all three of which have **no diff at all**. So the
list is not merely unattributed, it is false, and nothing may be concluded from it. Everything below was
therefore established by executing the tree, not by reading a summary.

### Verified, by execution

- **Tests: 136 passed** across `tests/remediation/test_mechanical.py` and `test_gallery_audit.py`.
- **One genuine regression, adjudicated rather than papered over.** FIX-1's rework of the scope guard in
  `apply.py` broke `test_the_scope_guard_names_the_curated_source`, which asserted the phrase
  "are not ancient_nerds sites". The guard now raises
  `'country repair: % planned row(s) are not % sites', bad, _literal(source)` - the name reaches the
  operator as a RAISE **argument** instead of text spliced into the message, which is exactly the rule
  three lenses asked for. The old phrase was assertable only *because* the name was spliced in, so
  re-asserting it would have re-asserted the defect. I rewrote the test to ask for both halves - the
  placeholder present in the message, the name absent from it - which is strictly stronger than the old
  expectation, since the old one could not tell the two apart. **Teeth proven:** mutating the render back
  to the spliced form makes the test fail; the file was then restored byte-identically (sha256
  `8b0c9b32e13431a5...`, checked before and after).
- **Both landed writes' undos are exact inverses**, checked with my own tuple parser rather than the
  generator's own logic: mechanical 35/35 and gallery 105/105 on key set, old/new swap, `site_id`
  agreement and distinct `change_key`. The values make sense: country restored to "Chile, Easter Island"
  and "Georgia (country)"; image_kind restored to NULL.
- **The integrity digest is real, and recomputed independently.** `plan_digest` is sha256 over sorted
  canonical JSON lines, order-independent; recomputing it myself from `PLAN.jsonl` gives
  `b39d38cdad3ff0e3...`, matching the header on both APPLY and ROLLBACK.
- **The re-rendered apply still describes production.** FIX-1 re-rendered both mechanical scripts, so
  their hashes changed (APPLY `71ad097ac794133a`, ROLLBACK `83ccdfb3035d2d2a`) and a re-render can
  silently divorce an artifact from the journalled write. Checked against the **live production journal**,
  read-only: the pinned APPLY matches the 35 journalled rows 35/35 on site set, `change_key` and
  old+new values. The claim survived the re-render.
- **Only the undo had been versioned for the mechanical write**, while the gallery pair was versioned
  whole. `APPLY.sql` and `PLAN.jsonl` are now pinned too: the generator cannot reproduce them, and
  APPLY.sql is the statement set that wrote rows already journalled in production. Versioning the undo
  while ignoring the apply is half an audit trail.

### Fixed in this wave, and what remains

`ci.yml` now runs the DB-less subset with **`-rs`** (a silent skip was indistinguishable from a pass) and
counts **`migrations/**` and `scripts/**`** as backend changes - the same hole the file already documents
for a test-only commit that skipped Backend Tests and deployed over a red predecessor. Still undone from
the wave-6 brief, and now the only outstanding item: **FIX-1 `[H]`**, the 0018 refusal guard and its
self-test cases.

### Two more instrument slips of mine, recorded because the instrument was ours

1. My new tuple parser cut the `VALUES` body at the **first semicolon**, which occurs inside the evidence
   JSON, and so reported **0 tuples for both files** - including the gallery file where an earlier regex
   had found 105. An empty result from my own probe is a statement about my probe. Fixed to stop at the
   semicolon that closes the statement.
2. My YAML probe verified `-rs` by taking the first step whose text contains "pytest" - which is the
   **install** step (`pip install ... pytest ...`), not the test step. It reported `has -rs: False` for a
   file that had it. Re-asked by selecting the step that runs `pytest -q`.

### Adjudicated, no action (the checker is wrong, not the code)

- `mechanical/apply.py:111, 415, 599` - "call without try/except". L111 is guarded four lines above by
  `raise PlanError(f"{path} is missing - build the plan first")`; L415 refuses an empty plan and raises on
  a read-back that disagrees, by design; L599 is a read-only measurement SELECT. Wrapping these in
  try/except is the fallback code this project forbids, so the finding is a named instrument mismatch,
  the same class as the earlier `apply.py:95` advisory.
- `ci.yml` line-length (76 hits, 4 of them mine) - an 80-column prose rule applied to a YAML workflow
  that already violates it in 60-odd pre-existing lines. No project gate lints YAML line length; I
  shortened my own comment and left the rest alone rather than churn the file.
- `logs/ledger_probe/child_append.py:62` and `race_probe2.py:25` - "open() called with invalid mode
  `\"r+b\"`" and "call without try/except". The mode in the source is `with open(lock_path, "r+b")`,
  which is valid (read/write binary, no truncate); the checker read the source's own quotation marks
  as part of the mode. Both files are throwaway concurrency probes under the ignored
  `output/remediation/logs/` tree (`.gitignore:216`), and both must fail loudly: a probe that falls
  back on a missing argument reports a run it never made, and its earlier green run proved only that
  it was too gentle. Adjudicated at the bytes, left visible.
- `gold_standard/measure_reviewer.py:110, 113` and `review_stage.py:153, 187, 420` - "identity
  operators with literal values". The value arrives from JSON with three states, so `is True` /
  `is False` is the load-bearing distinction and not a slip for `==`. Measured: `refuted is True ->
  applies=False`, `refuted is False -> applies=True`, `refuted is None -> applies=False`. A truthiness
  check would count `None` as applied and inflate the measured rate, and `if refuted:` in the writer
  would let a refuted finding through the only write gate Phase 3 has.

## The raw third-party response bodies leave the repository history (2026-09-21)

**gitleaks, pointed at the same target where it found 7 live `generic-api-key` findings, now reports
"no leaks found"** - 3,475 commits, ~4.89 GB, 2m22s, exit 0. The removal is at the level the finding
lived at (history), not just at the level it was noticed (the index).

The fix, in order. All 76 raw bodies were taken out of the index earlier (`git rm -r --cached`, keeping
the bytes on disk) and re-ignored, but that alone leaves the blobs reachable from the commit that
introduced them, so the first push would have published the keys and the sast gate would have stayed
red. `.gitleaksignore`'s own header forbids allowlisting a live credential, so exemption was never an
option. So `git filter-branch --index-filter` over `b2dc450^..main` removed
`output/remediation/phase3_pilot/evidence/` from every commit in that range: 15 commits rewritten,
everything before them untouched. The reference tree is provably unaffected - `git diff --stat` between
the old and the new HEAD is empty, because the path had already been unversioned and was absent from
HEAD beforehand. The files are still on disk and still the fetch evidence; they are simply not versioned.

Verified rather than assumed, at each step: 47 unpushed commits before and after, 0 commits on `main`
holding the path, 0 files at HEAD under it, 0 modified files in the working tree, and the identical HEAD
tree. The old refs (`refs/original`) and the reflogs were then dropped so the objects are truly
unreachable, which is what makes the scan meaningful - and the same command was re-run to prove it, not
a different smoke test.

Backup, because a rewrite without one is a guess: `/c/PythonProjects/ancientmap-pre-rewrite-20260921-0211.bundle`
(2,113,204 bytes) from `origin/main..HEAD`. Nothing has been pushed, so no remote ever saw the old
hashes and no force-push or coordination is needed.

**Warning for anyone reading older entries here: the hashes recorded before this one are stale.** The 15
rewritten commits have new ids - the old `b2dc450` is now `98ce0c3`, `f96d4c3` is now `835653d`,
`c10f582` is now `000bd1e`, `4a7e000` is now `cabed98`, `6cf4802` is now `a9585f5`. The full old-to-new
table, with each subject, is in `output/remediation/HISTORY_REWRITE_2026-09-21.md`; the old ids resolve
only through the backup bundle.

## Item [H]: the journal could record a change that never happened (fixed, and reproduced first)

SECURITY 4 was right, and the reproduction is the proof. Before the fix, `apply_remediation_change`
accepted `p_old = p_new`: the conditional UPDATE matched, the round-trip check passed, and a journal row
was written whose `old_value` equals its `new_value` - a correction the journal claims and the data never
received. Run against production, the two new cases failed exactly there: **C11 "p_old = p_new was
accepted as a change"** and **C12 "journal rows = 1 (want 0)"**. So the defect was not theoretical and
the cases are not decorative; the mutation run is the evidence for both halves at once.

The guard is `IF p_old IS NOT DISTINCT FROM p_new THEN RAISE` near the top of the function, `IS NOT
DISTINCT FROM` rather than `=` so that NULL -> NULL is refused too - "set this NULL field to NULL" is
precisely the no-op worth catching, and `= NULL` is never true. `COMMENT ON FUNCTION` now records the
refusal, so the documented contract matches the code rather than lagging it (the comment had claimed
only truncation and coercion).

**Applied to production** with `-v ON_ERROR_STOP=1`. Without it psql continues past a failed `CREATE`
and `COMMIT`s an empty transaction, which would have looked exactly like success. Verified by read-back
rather than by the script's exit: `pg_get_functiondef` now contains the guard. Re-run afterwards:
**12 ok, 0 failed**, and `remediation_change_log` held 5,578 rows before, during and after.

One smaller real defect found on the way, in the same family as everything else here: the selftest's
closing line was labelled `change_log_rows_must_be_0`, a question that number can never answer on
production - it printed 5,578. A reader would have taken a correct run for a failed one, or trained
themselves to ignore the line. Relabelled `journal_rows_after_rollback`, with the actual invariant
spelled out: it must equal the count taken before the run.

## Phase-3 runner piece 1 - the missing component, and a reformat that had to be re-proved

The Phase-3 review of 1,813 sites needs a runner that did not exist. Piece 1 landed the finding
schema, a measured cost ledger and an offline deterministic plan: 28 tests, ruff and mypy clean.

`Verdict` is exactly `defect | true_but_no_correction | unverifiable`, and that first pair is the
point - neither value had any producer in this repository, which is why the census can flag a site
and still leave "is the stored value actually wrong?" unanswered. `Finding.defect` is derived from the
verdict, so the flag can never contradict it. The ledger records token counts per call and never
estimates them, and it deliberately carries **no dollar figure**: a price table is an assumption, and
an assumed cost is the invention this runner exists to prevent.

**A formatter had rewritten an already-verified file.** `scripts/remediation/mechanical/apply.py`
came back from the lane reformatted by `ruff format` - the lane reported it as pre-existing, but the
tree was clean before the lane started. By this project's rule that invalidates the file's
verification, so it was re-proved rather than waved through. My first instrument was token-stream
equality and it is the **wrong instrument**: it reports a difference, because ruff inserts trailing
commas when it explodes a tuple, and those are inert. The right instrument is the syntax tree -
`ast.dump` of both versions is identical, 88,735 characters each - which proves the change cannot
alter behaviour, and the 552-test remediation suite is green. A render comparison was attempted twice
and **not obtained** (`emit` requires `ROLLBACK.sql` to exist first, and `--render-rollback` reads
`PLAN.jsonl` from the output directory); the AST proof is stronger than that comparison would have
been, so it was not chased further.

**Instrument slips of my own, four in this stretch.** One: a `&&` chain aborted after a probe crashed,
and a later `;`-separated command printed anyway, so the output *looked* like a complete run while the
render check had been skipped entirely - the fix is newline-separated commands. Two: `echo $?` after a
pipeline reports the **pipeline's** exit, not the command's, so two lines reading `exit: 0` were
worthless while argparse had in fact rejected the flag. Three: I guessed the JSON key names
(`site_ids`) and the CLI flag name (`--rollback`) instead of reading them, and mistook each failure
for a defect in the artifact. Four: I computed 1,815 sites by multiplying 121 batches by 15 instead of
summing them; the true count is 1,813 (120 full batches plus 13), which is exactly the scope.

The determinism claim was reproduced here rather than taken from the lane's summary: three independent
runs give `96704b808ae1b29d69480693...`, and the plan's 1,813 site ids are exactly the
`WORKLIST.jsonl` `phase3=true` set with no duplicates.

## Phase-3 runner piece 2 - the evidence-fetch stage, and two interpretation calls ratified

The fetch stage collects per-site evidence before any model call. 47 tests across the two runner
files, ruff and mypy clean. The cap **stops the stream** rather than slicing a buffered body, and
decision 12's named-feature rule is enforced twice: at the URL builders and again in `get` before a
socket opens, so the expensive URL shape cannot be reached by another route.

The one permitted live fetch was corroborated rather than believed: it returned 200 and **4,356 bytes**
for Satsurblia Cave, and the *pilot's own* evidence file for that page is exactly 4,356 bytes. Two
independent fetches, same byte count.

**Ratified, call 1:** a fetch line carries `kind="fetch"` with `stage=finder/reviewer`.
`LedgerKind.FETCH` is a first-class shape from piece 1, and `stage` preserves the finder/reviewer
split that `COST.md` measures its 76 fetches by. Collapsing `stage` to `"fetch"` would destroy the only
dimension that split carries.

**Ratified, call 2:** a body of exactly 61,440 bytes reports `truncated=True` and cannot be told from a
cut one. Left deliberately, not overlooked. Disambiguating means reading past the cap, and the cap
exists so that a 598 KB dump is not pulled over the wire only to be discarded. The skew is toward
"this evidence may be incomplete", which is the safe direction for an audit: it can cost a verdict, it
cannot manufacture one. The consequence is now written at the function, so the next reader does not
have to rediscover it.

The ambiguity was **measured, not argued**: exactly-at-cap reports `True`, under-cap `False`, over-cap
yields exactly 61,440 bytes. My first reading of the code claimed the opposite - the grep excerpt I was
reading had cut off the two lines that decide it. That is the third time this session a probe of mine
was the thing at fault, and measuring took ten seconds.

## Phase-3 runner piece 3 - the measured model call, and two measurements that changed the design

The runner can now make a call and record what it cost. 590 tests in the remediation suite, ruff and
mypy clean, and **zero live calls in the tests**: they run against two captured transcripts, and both
fixtures were verified byte-identical (sha256) to the probe files they were copied from.

**The dollar figure is measured, not assumed.** Pi's JSON stream carries the settled usage in the
`message_end` event - tokens *and* the provider's own `cost.total` - so the ledger records what was
actually charged. Piece 1 deliberately carried no price figure, because a price table is an
assumption, and an assumed cost is the invention this runner exists to prevent.

**Two measurements changed the design, and neither was a preference:**

- **`-ne` is not optional.** Identical prompt, same model: with extensions loaded, 2,271 input tokens,
  14,013 ms, $0.000341 per call; with `-ne`, **437 tokens, 2,698 ms, $0.000066**. Extensions inject
  roughly 1,830 tokens into every call for a model that only ever judges text the runner already
  fetched - 5.2x the money and 5x the time. The four numbers sit in the comment beside `PI_FLAGS`.
- **`pi` is a POSIX sh script on Windows** and cannot be exec'd by `subprocess` without a shell:
  `FileNotFoundError [WinError 2]`. `pi.cmd` reports 0.86.1 and execs the same bundle with the same
  argv. **Found by the lane, not by me**, and it would otherwise have failed at batch runtime -
  recorded here because a finding that arrives from a worker still has to be right, and this one was.

**What this still does not establish.** Cheap calls are not correct calls. The 60% false-negative rate
belongs to the census-with-tools design; the argument that this design is better is an argument, not a
measurement. The instrumented batch is what converts it, and it is also what turns the two extrapolated
cost anchors into one measured number.

**Slip of my own:** I ran `judge` without running `prepare` first and got a `FileNotFoundError` on the
batch's `input.json` - the third time this session I guessed a CLI's contract instead of reading it.
The sequence is documented in the CLI's own docstring: plan -> prepare -> fetch -> judge. The stale
opening paragraph that still described this file as "piece 1" and said the runner "does not exist yet"
was corrected with this commit, since a docstring that misdescribes the file is exactly the kind of
false claim this record is supposed to catch.

## Phase-3 runner piece 4 - the batch-killer the first live run exposed, and three claims of mine it corrected

The first live batch was worth its zero model spend: it found that **one flaky Overpass request ended a
whole 15-site batch**, and that the request which timed out left **no ledger line at all**, so the cost
record undercounted exactly the attempts the pilot counted. My own brief caused it - I wrote that a
transport failure must RAISE. The distinction it missed: raising protects a single site's evidence,
killing the batch protects nothing.

Now: a transport failure and a retryable status (408/429/5xx) are recorded outcomes, retried at most
twice, with **one ledger line per attempt**, so the attempts are countable and a retry cannot hide. The
guard that worked - refusing to judge evidence that is not on disk - is untouched and mutation-proven.
Partial evidence is now named in the prompt so the model can answer `unverifiable` instead of implying
there is no defect, a site with no evidence at all buys no model call yet still yields a recorded
`unverifiable`, and `status` reports an absent ledger as a fact instead of raising on a fresh run.

**Three claims of mine were wrong, and the lane corrected all three. I verified each against the raw
files before accepting it.**

1. I said the runner was probably failing Overpass for lack of a User-Agent, quoting the 89-byte body
   "Please include a meaningful User-Agent string with your requests". The fetch log says that body came
   with **HTTP 429 from `overpass.kumi.systems`** - a *different host*, one the pilot had rotated to -
   and the runner already sends the project's identifying agent. I inferred a cause from an error
   message without checking which client sent it or who answered. No defect existed; the header is now
   pinned by a wire-level test instead of being "fixed".
2. I said `Karpasia%2Foverpass_site.txt` was an empty result. It is **a hit**: 1 element,
   `historic=archaeological_site`, `name='Ayios Philon Roman harbor'`. The truly empty ones are
   `Petroglyph%2Foverpass.txt` and `_bbox.txt` (287 bytes, `"elements": []`).
3. My framing that Overpass was "largely useless" is **unsupported by the same files**: on
   `overpass-api.de` the pilot got 61, 27, 14, 8 and 1 real named features. The failures were
   host-specific (`kumi.systems`) and status-specific (504), not systematic. Overpass stays, as a
   second opinion whose yield the next live batch measures rather than assumes.

The pattern in all three: I read an error *body* and reasoned about its *cause* without checking the
transport that carried it. That is the same class of mistake this project keeps finding in its own
checks - a number that looked impossible was a bug in the measuring code - and it is mine here.

## The 1,813-site worklist does not cover the errors - measured, not argued

While the instrumented batch re-ran, I put a number on the doubt that has been in this file since the
60% false-negative rate was first computed. It is worse than "the census misses some errors".

The blinded gold-standard check examined **36 sites**. Of those, **11 (31%) are inside the planned
1,813 and 25 (69%) are outside it**. And of the **17 distinct sites that actually held a verified
missed error**, only **3 are in the worklist** - the other 14 are not planned at all. Taken together
with `fnr_result.json` (40 blinded errors, 16 caught, 24 missed, FNR 0.60, CI 43-75%), this says the
worklist's flags correlate poorly with where the errors are.

So fixing only the 1,813 would produce a database in which **14 of the 17 known-error sites are still
untouched** - the exact "looks audited" outcome this file warned about, now with a number attached
rather than a worry. The per-field pattern shows why: the missed errors sit in `description` (8),
`card_description` (5), `period_start` (4), `scope` (3) and `site_type` (4), while the census's flags
are dominated by the hero-image, URL-shape and link checks (T09 alone flags 5,004, T10 4,010, T06
3,010, T07 2,806).

Limits, stated plainly: 36 sites is a small sample, so the true share is uncertain - the direction is
not. The 3-of-17 figure is about sites the blinded check happened to draw, which was a random draw,
not a sample of error-bearing sites.

**The consequence for scope.** Covering all 5,004 sites costs about ten dollars at the measured token
rate, so the choice is no longer expensive - it is between a database that is one-third audited and
one that is whole. I recommend all 5,004. That is Martin's call, and the next measurement is the one
that should precede it: run the new finder over the 17 truth-set sites, whose correct values are
recorded in `fnr_result.json`, and see how many of the 24 missed errors it actually catches. That
measures recall directly rather than arguing it, for about five cents.

## The evidence bound was set below the real distribution - measured, then raised

The second live batch got past the fetch stage (61 requests, 22 successful, 13 failed, 4 non-2xx) and
stopped at the judge with the refusal it was built to make:

    the evidence is 23947 characters, over the 9200-character bound (the design point is
    ~2,300 input tokens per call). Truncating silently would judge a page the model never saw;
    narrow the evidence or raise the bound deliberately.

The refusal was right and the number was wrong. `MAX_EVIDENCE_CHARS = 2300 * 4` came from my own
misreading: "~2,300 input tokens" was a design point about a *whole call*, and a bare call measures
437 input tokens, so the phrase never described the evidence at all. The batch's own files give the
real distribution: 23 evidence files, **median 469 bytes**, with a long tail - 23,947 characters for
Siega Verde, 13,649 for Hattusas, then 8,194 and 8,071. The bound sat below the middle of that tail
and refused 2 of 15 sites.

Raised to 32,000 characters: the observed maximum plus about a third, still far under the 61,440-byte
per-page cap the fetch stage enforces, and about $0.0013 per call at the worst case. I chose to raise
it rather than narrow the evidence on purpose - the sentence that decides a verdict is exactly what
narrowing deletes. The refusal stays as the sensor: raising this number again happens from a later
batch's figures, not from another guess.

Two things this batch measured that outlast the bug:

- **Every recorded non-2xx is Overpass** (429 x3, 504 x1, all `overpass-api.de`). The retry fix was
  not defensive coding; it was the difference between a batch that finishes and one that does not.
- Evidence is **cheap and mostly small**: 61,616 bytes for 22 successful fetches, median 469 bytes a
  site. The expensive tail is a handful of long Wikipedia articles, and those are the sites where
  there is something to judge.

## 2026-09-21 - the live batch's second failure: the prompt was in argv (measured)

`judge` made **zero** model calls and exited 2 with:

```text
31860bc4-476a-49bc-9f97-e25220063d19/finder: pi.cmd exited 1; stderr tail: 'Die Befehlszeile ist zu lang.'
```

The defect was mine, and it was in the transport, not in the model. The runner handed the prompt to
`subprocess.run` as the **last argv element**. `pi.cmd` is a batch file, so Windows executes it
through `cmd.exe`, whose command line stops near 8,191 characters - and a real prompt (one site
record plus its evidence) measures about 24,000. The same run's `fetch` stage succeeded
(`FETCH_EXIT=0`), so the failure looked like a model problem; it was a Windows problem. A design that
says "argv as a list, never a command line" is still bounded by the operating system's command-line
length, and nothing in the earlier measurements had exposed that because every probe prompt was tiny.

Fixed by moving the prompt to **stdin**, UTF-8 encoded, leaving argv at 13 short elements:

* measured before believing: `pi -p` reads the prompt from stdin - a one-word question answered
  445 input tokens, $0.00006735, exit 0, 15 JSON lines.
* `pi_argv()` no longer takes a prompt at all, so a later edit cannot put it back by accident.
* the test that pins it builds a **20,000+ character** prompt and asserts (a) the prompt is in no
  argv element, (b) the whole argv stays under 200 characters, (c) the child receives the exact
  UTF-8 bytes including the non-ASCII site name. Mutation-proven: with the prompt put back into
  argv it fails on `assert prompt not in argv`, and the file restores byte-identically.
* two older tests asserted the superseded contract (`argv[-1] == prompt`). They are rewritten, not
  deleted, and they failed first - which is how I know they still ask a question.

**Carried forward, measured, not mine to fix here:** `mypy api/` - a CI gate (`ci.yml:136`, no
`continue-on-error`) - reports **93 errors in 14 files** locally (mypy 1.19.1, Python 3.13): 35 in
`api/cardgame/discord_commands.py`, 18 in `api/routes/public_v1.py`, 16 in
`api/services/discord_bot.py`. Those files are **byte-identical to `origin/main`**
(`git diff --stat origin/main..HEAD -- <paths>` is empty), so this is pre-existing type debt and not
the work of any unpushed commit. Whether CI is actually red is **unverified**: `gh` is not
authenticated here, and CI type-checks on Python 3.11 with an unpinned mypy, so a version-dependent
difference is possible. It matters because a push that touches `api/` runs that job and would block
the deploy.

## 2026-09-21 - the first measured live batch: judgement is cheap, fetching was the whole cost

The batch that finally ran made **15 model calls, 15 sites, 0 skipped, 0 unverifiable findings**:

| measured | value |
| --- | --- |
| provider-reported cost, summed verbatim from the ledger | **$0.007285** for 15 calls |
| per call | **$0.000486** |
| input / output tokens | 43,431 / 1,284 (mean 2,895 in, 86 out per call) |
| cache reads | 0 |
| extrapolated, one stage | **1,813 sites -> $0.88**; **5,004 sites -> $2.43** |
| fetch stage wall clock | **38 minutes** (06:17:36 -> 06:55:21) |
| judge stage wall clock, all 15 calls | **39 seconds** (06:55:25 -> 06:56:04) |

The plan's Phase-3 cost model ("two-stage factual audit, reduced, ~2,217 sites, ~$350") is therefore
**two orders of magnitude off, in the safe direction**, and for a reason worth naming: it prices
agentic loops at ~40,000 tokens per site, while this runner fetches the evidence itself and asks one
bounded question. The money was never the blocker. I said so earlier from arithmetic; now it is
measured. Even a second stage (finder + reviewer) leaves all 5,004 sites near **$5**.

The blocker was the wall clock, and it was one host.

**Every single fetch failure is `overpass-api.de`.** Grouped from the ledger by host and by the last
attempt's outcome: `overpass-api.de` 113 `transport_failure` + 4 `http_error`; `en.wikipedia.org` 14
`ok`; `www.wikidata.org` 8 `ok`. The 117 Overpass failures are 39 distinct targets x `MAX_ATTEMPTS=3`,
each burning `OVERPASS_TIMEOUT=20.0` seconds - which is exactly the 38 minutes. **98 % of the batch's
run time was spent retrying a host that never answers, to buy 39 seconds of real work.** At that rate
the 1,813-site worklist is ~77 hours and all 5,004 sites ~211 hours.

Why the host never answers, measured rather than guessed (same User-Agent the runner sends):

```text
overpass-api.de         http=000 time=0.077s   curl: (35) Recv failure: Connection was reset
overpass-api.de  (root) http=000 time=0.076s   same, so it is not the query
overpass.kumi.systems   http=000 time=25.02s   curl: (28) timed out
overpass.osm.ch         http=400 time=0.41s    an HTTP answer - this host IS reachable
en.wikipedia.org        http=301 time=0.16s    control: the network is otherwise fine
VPS -> overpass-api.de  http=400 time=0.35s    the VPS reaches it fine
```

A TLS-level reset with **0 bytes** in 0.077 s is not a rate limit and not a refusal - both of those
answer with a status code. My first hypothesis was a broken IPv6 path, and **it was wrong**: the name
resolves to IPv4 only here (162.55.144.139, 65.109.112.52, no AAAA record) and `curl -4` is reset just
the same. So it is this workstation's network path, not Overpass and not the address family. The VPS
answers the same host in 0.35 s, which means coordinate evidence *is* obtainable in this project - on
the VPS, exactly as the plan already rules for the VLM work. It is not on the critical path: the
contract makes coordinates a human call (285 coords-only sites, 117 T02 sites).

Decision, taken from the measurement: **probe a host once per run instead of hammering it.** If a host
does not answer a probe, its targets are recorded as *not attempted*, with the reason, one ledger line
each, and the batch continues on the hosts that do answer. The distinction is the one this log keeps
insisting on: *"this host did not answer, so the target was not attempted"* and *"this target was
attempted and failed"* are different facts, and both must be readable. See `PIECE4b_BRIEF.md`. No host
rotation, no fallback endpoint: which endpoint to ask stays the operator's decision.

**One thing this batch does not yet prove.** Fifteen sites were judged, zero were unverifiable, and
**not one of them carries a known truth**: `batch-0001` and the 17 truth-set sites do not intersect
(`input.json` against `fnr_result.json`). A cheap pass that quietly misses defects produces exactly the
"looks audited" database this whole remediation exists to prevent, so the finder's *recall* is still
unmeasured. That measurement is the next piece, and it is why the plan builder must learn to be driven
by an explicit site-id list.

## 2026-09-21 - piece 4b landed: 38 minutes became 1.45 seconds, and the two facts stayed apart

The fix is one reachability probe per host per run, taken lazily immediately before that host's first
*pending* target. A host that does not answer leaves every pending target on it recorded as
`host_unreachable` - one line each, `attempt=0` because nothing was attempted, the probe's own reason
as the error, `given_up=False`, and **no request to their URLs** - while the other hosts are fetched as
they always were. No host rotation, no fallback endpoint.

**What I measured myself, from the artefact, not from the report:**

| check | before | after |
| --- | --- | --- |
| ledger lines | 155 (140 fetch + 15 model_call) | **169** (154 fetch + 15 model_call) |
| the run's own new rows | - | 1 probe + 13 `host_unreachable` |
| `fetch.json` totals.requests | 39 | **1** |
| `...totals.not_attempted` / `.probes` | absent | **13 / 1** |
| `...totals.bytes` / `.fetches` | 0 / 0 | **0 / 0** (nothing written, nothing overwritten) |
| live fetch wall clock | **~38 min** | **1.45 s** |

The 15 `model_call` rows from the cost measurement are still there - the proof this piece was supposed
to preserve. Every one of the 13 not-attempted rows carries `attempt=0`, `given_up=False`, no
`http_status` and the probe's own reason, and their 13 URLs are the *target* URLs, not the probe URL.
One request at 1.45 s is itself the proof that no target was asked: 13 targets x 3 attempts x 20 s
cannot fit in 1.45 s.

The distinction this log keeps insisting on is now proven end to end, through the real collector, the
real report, the real reader and the real prompt builder: the built prompt says `not attempted`, names
the `host probe` and its `ConnectError`, says `0 request(s) recorded`, and does **not** contain the
sentence used for a target that was asked and failed - while the evidence that did arrive is still
there and is the only thing called present.

**Gates, run by me:** `tests/remediation/` **610 passed** (83.53 s, was 603); `ruff check` clean;
`mypy scripts/remediation/phase3/` clean on 6 files; the full DB-less suite **2258 passed, 3 skipped,
57 deselected** (145.44 s).

**One red gate, and it is not this piece's.** `ruff format --check tests/remediation/` is red for 14 of
27 files, and it was already red at HEAD - measured by piping every committed file through
`ruff format --check --stdin-filename` so the project config still applied. For the two files this piece
touched, HEAD's version has **14** format hunks and the working tree has **14**: the same hunks on the
same pre-existing tests, none inside the new code. The lane added **zero** formatting debt and correctly
refused to reformat unrelated lines. It stays red on purpose: `ruff format --check` is a CI gate for
`api/ pipeline/` only (`ci.yml:124`), reformatting 12 unrelated test files would bury a real change in
noise, and a reviewer who wants it green can have it green in one command.

**Not proved by me:** the lane's eleven mutation proofs (I verified the artefacts, the gates, the code
and the *substance* of the tests, not the mutation sweep itself), and the judge stage's live behaviour
with a real model - this fix was verified through the prompt text, not through a paid call.


## 2026-09-21 - piece 5: the report was true and the tree was broken, and a mutation sweep inside a lane is the reason

**The lane died at the 30-minute ceiling, and its report was accurate anyway.** Piece 5 (the
snapshot-driven discover plan) was delivered by `75e09c31`, killed mid-flight. Its ledger claim ("no
`--live` call") holds: the ledger was still 169 lines with all 15 `model_call` rows, so the paid recall
experiment stayed mine. Its plan figures hold too - reproduced here byte for byte: **85 calls / 40,096 B
/ `ad32d26f...`** for the 17-site truth list, **25,020 calls / 12,042,556 B / `a5786f10...`** across all
5,004, and the piece-1 anchor unmoved at **`96704b80...`** on both the committed artefact and a fresh
run.

**But the tree it left behind did not work.** Five tests failed on the delivered files, contradicting
its own "gates green" - which was true when written and false afterwards. Cause, found by comparing the
five file hashes it says it restored against the files on disk: four matched, `snapshot_plan.py` did
not (`9257da45...` claimed, `66f94870...` on disk). Its `DISCOVER_FIELDS` was missing `country` while
`FIELD_STORED_IN`, `FIELD_QUESTION` and the tests all still demanded it - i.e. **mutation #3 of its own
sweep was still applied**. The lane re-ran the sweep after writing its report, and the ceiling killed
it between applying that mutation and restoring it.

**Detection technique worth keeping:** a lane's report is verifiable in one command, because a
mutation-proof table that names the sha256 it restored is a *testable claim* - hash the files and
compare. That is what turned "probably fine" into a five-failure tree in under a minute.

**Restore proved, not asserted.** Re-adding `country` in the frozen order reproduced the report's
restored hash exactly (`9257da451c6ada58`) *and* both plan hashes and byte counts above, through an
independent path. Gates re-run here: **640 passed** in `tests/remediation/` (610 before, 30 new), `ruff
check` clean, `mypy` clean on 8 files, and the mutation sweep **run by me, not read**: **17/17 caught,
all five file hashes identical before and after** - which also proves the sweep restores cleanly when
it is allowed to finish.

**Process lesson (the one that will recur):** a mutation sweep run inside a subagent lane is unsafe,
because the ceiling can kill it mid-restore and leave a mutant in the working tree that looks like
finished work. Sweeps belong in the parent process, or must restore on signal. This is the second lane
this session the ceiling killed mid-sweep.

**Corrected: the brief that pointed at a dead column.** `PIECE5_BRIEF.md` told the piece to route
Wikidata by `card_stats.wikidata_qid`. Measured: that column is present in all 5,004 exported rows and
**NULL in every one**; nothing in the repository writes it, it is created only by `api/main.py:126`, and
the only writer of a Q-id is `pipeline/lyra/prospector/external_ids.py:55`, into `site_external_ids`
(**4,618** rows). Following the brief literally would have routed **no site at all** to Wikidata, and it
would have looked like thin evidence rather than like a bug. The lane found it, deviated with the
evidence and reported it as an open question. Corrected in the brief (`15898c5`). This is the second
piece in a row where the lane corrected me from the artefact, and both times it was right.

**The discover pass's first real evidence, and its first measured coverage cost.** Fetching the 17 truth
sites cost 33 targets (17 `enwiki` + 16 `wikidata_entity`; `Font dels Coms` has no Q-id), **0 failures,
0 non-2xx**, both hosts probed HTTP 200, 226,668 + 8,694 bytes. The pilot's "8.8 s per fetch" was
Overpass timeouts; against Wikipedia and Wikidata the whole thing finishes in seconds.

Then the bound bit, and the measurement is uncomfortable: `plan_site` puts a site's *entire* evidence
into all five field prompts and checks `MAX_EVIDENCE_CHARS = 32_000` **once per site**, so one large
site loses all five fields at once. **2 of the 17 truth sites are refused** (Priene Ruins 37,339 chars,
Pyramid of Caius Cestius 49,952). Those two sites hold **2 of the 24 known-wrong fields**, which are
therefore unmeasurable by construction - and the 3 `scope` entries no column holds are unreachable too,
so the value pass can reach **at most 19 of 24**. Extrapolated to the full run that is roughly 12 % of
sites recorded unverifiable without a question being asked; on a 17-site sample that is a direction, not
a rate.

**Not proved here:** what the model actually answers. The recall number is the next measurement and the
only one that decides whether this design works at all.


## 2026-09-21 - the discover pass measured for the first time: 5 of 19, and the misses were the question's fault

**The number.** 75 calls - one per (site, field) over the 17 truth sites - caught **5 of the 19** known-wrong
fields the pass can actually ask about (5/24 against all 24). That is **26.3 % recall on the errors the
census missed**, where the census's own recall on those is 0 % by construction. Cost: **$0.054226**, i.e.
**$0.000723 per call**, 49 % dearer than the census-driven finder's $0.000486 because this prompt carries
the site's whole evidence. Projected across all 5,004 sites: **~$18 per stage** - money is still not the
constraint, which is why a 26 % recall is the problem and not the price.

**Three ceilings, and they are not the same thing.** Of the 24 ground-truth entries: **2** sit on sites the
evidence bound refused outright (`Priene Ruins`, `Pyramid of Caius Cestius`), and **3** are `scope`
decisions that no column holds, so no per-field value question can reach them. **19** were therefore asked.
Reporting 5/22, as the first version of my own scoring script did, would have counted the `scope` entries as
reached merely because their site was judged - an inflated denominator built out of questions that were
never asked. The script now defines `asked` as "a call was made and answered for this exact (site, field)",
which is the only definition that cannot flatter the result.

**What actually failed, read from the answers rather than inferred.** Of 14 misses, 11 were confident
`CORRECT` and 3 `UNVERIFIABLE`. The `CORRECT` ones cluster into three causes:

* **Silence read as agreement (8 of 11).** `Ahu Tongariki`: *"the only discrepancy being an unsourced
  construction date absent from the evidence but not contradicted"* -> `CORRECT`, though the stored date
  (1-500 AD) is wrong (c. 1250-1500 AD). The question said `CORRECT` = "the evidence agrees", and "does not
  contradict" was read as agreement.
* **The finder's own sentence contradicting its own verdict.** `The Merry Maidens / period_start` wrote that
  the evidence *"places its construction within the -3000 to -1500 bucket"* while the stored `-4000` is
  *"a bucket lower bound for the preceding -4500 to -3000 range"* - the prompt's own "different bucket is
  `WRONG`" rule firing in the model's own words - and then answered `CORRECT`.
* **The model's subject knowledge upholding a wrong value.** *"the dating (4500-3000 BC) is a standard
  attribution for the site"* kept a wrong date alive; *"the Neolithic in Britain begins c. 4000 BC"* did the
  same for `The Gop`.

**Two of the misses cannot be caught from this evidence at all.** `Arc de Berà`: the enwiki extract itself
says the arch was built through the will of Lucius Licinius Sura, while the truth is that it was *restored*
under that will - the evidence repeats the stored error, and no finder can see through it. `Font dels Coms`:
the enwiki lookup returns *missing* (no English article), so the field is unanswerable by this route; a site
with no enwiki article needs another evidence route, and that is a routing gap, not a model failure.

**And it is not merely conservative.** 7 `WRONG` verdicts are not ground-truth entries; several are
plausible catches the blinded check did not record (`Bulls of Guisando / period_start`, `Midford Castle /
card_description`, `Ocriticum / period_start`, `Hebbariyeh Roman Temple / description`). They are listed
with their reasons in `recall_result_gold.json` for adjudication rather than counted as false positives -
the ground truth is what the blinded check could see, not every error that exists.

**The response (`42fb917`).** The question now asks for the evidence statement **before** the verdict line
(the verdict was written first, and the sentence then contradicted it), says `CORRECT` requires the evidence
to *state* the value, says silence is never `CORRECT`, forbids citing the finder's own knowledge, and says a
sentence that puts the real value elsewhere makes the verdict `WRONG`. Three new tests pin those three guards
separately so each mutation reddens its own test, and the sweep - moved out of gitignored scratch into
`scripts/remediation/phase3/mutation_sweep.py` - is **20/20 caught** with every restore byte-identical.

**Still unproven:** whether the rewrite moves the number. Round 2 runs the identical experiment, same sites,
same evidence, into `runs/gold2`; the only difference is the question. Until it lands, the 26.3 % stands as
the measured performance of the design as it was.


### The routing measurement behind two of the round-1 misses (measured from the snapshot, 2026-09-21)

Round 1 could not reach `Font dels Coms` at all: the enwiki lookup returns *missing*, and the pass has no
other prose route. Measured over the snapshot, that is not a corner case:

| route | sites | share |
|---|---|---|
| `enwiki_title` (the prose route the pass uses) | 4,619 | 92.3 % |
| `wikidata_qid` (claims: `country`, `site_type`) | 4,618 | 92.3 % |
| `unified_sites.source_url` | **4,962** | **99.2 %** |
| a `site_content_links` row carrying a URL | 3,575 | 71.4 % |
| neither enwiki nor a Q-id | 385 | 7.7 % |

**385 sites have no English article**, so `description` and `card_description` have no prose route for them
as the pass is built. Of those, **368 are reachable through `source_url` or a content link** and only
**17 sites (0.3 %) have no prose route at all today**. `Font dels Coms` itself carries
`source_url = https://visitandorra.com/en/culture/font-dels-coms-spring/` and five content links - the prose
was reachable, the pass had no route to it.

So the "unverifiable" answers on those fields are partly a **routing gap, not a model failure**, and the
cheapest next recall gain is a third route rather than a better question. Not adopted yet: whether a
`source_url` page *settles* a field is a separate question, and it gets measured before it is believed -
this is recorded as a measured input, not as a design change.

---

## The recall re-run: 5 of 19 -> 8 of 19, and the three defects the answers exposed

`runs/gold2`, 2026-09-21, commit `42fb917` (the rewritten question), same plan, same fixture, same
evidence - **the evidence is byte-identical between the two rounds** (33 files, 0 differing bytes,
verified after the fact), so the question was the only variable.

| | round 1 | round 2 |
|---|---|---|
| caught | 5 of 19 reachable (26.3 %) | **8 of 19 (42.1 %)** |
| against the 24-entry ceiling | 5 of 24 (20.8 %) | 8 of 24 (33.3 %) |
| `WRONG` verdicts | 12 | 25 |
| `UNVERIFIABLE` | 16 | 27 |
| cost | $0.054226 / 75 calls | $0.056514 / 75 calls |

Five entries became catches (`Arc de Bera` description, `Ahu Tongariki` description, `The Gop`
site_type and description, `The Merry Maidens` description); two were lost (`The Gop`
card_description, `Overstone Anglo-Saxon Cemetery` card_description). The rewrite works, and it also
made the pass **less** willing to call a value correct - `UNVERIFIABLE` rose from 16 to 27.

**The number that mattered was not the recall.** Round 2 produced 17 `WRONG` verdicts that are **not**
in the gold standard. Adjudicated by reading the 17 full answers, they separate into three defects of
*mine* and the model's own errors - and all three of mine were **missing information**, not prompt
polish:

1. **The prompt contradicted itself.** The rewrite said `Only the evidence in this message decides`,
   and the model then flagged `England` as `WRONG` because the evidence wrote `United Kingdom` -
   citing the clause that permits exactly that and overriding it in the same sentence: *"under the
   allowed design England is acceptable, yet ... so the stored value differs"*. Four false positives
   (`Midford Castle`, `Aubrey Holes`, `Overstone`, `Amyntas`), all `country`. An absolute-sounding rule
   had demoted the per-field clause to a subordinate paragraph.
2. **`site_type` was judged without the catalogue's vocabulary.** All four `site_type` flags were
   wrong, each by reading the evidence's own phrase as the target value: "triumphal arch" against
   `Gate/archway/bridge`, "folly castle" against `Castle/palace`, "hill fort" against
   `Fortress/citadel`, "ahu" against `Megalithic statues`. One answer states its own doubt: *"if the
   catalogue's grouping places 'triumphal arch' under a 'Gate/archway/bridge' class, the stored value
   would instead be CORRECT"*. The catalogue uses **70** distinct values and the question named none.
3. **`period_start` gave lower bounds, not spans.** `Bulls of Guisando` was flagged on arithmetic the
   model got wrong *after* its verdict: *"Wait - both -200/-100 and -500 fall in the same bucket...
   Let me correct."* They are both `500 BC - 1 AD`, so the flag was false.

Fixed in `0f542d7`: the clause now says it defines `matches` for its field and beats the general rules;
the `site_type` question carries the catalogue's own list, read from the snapshot the plan was built
from, and **refuses to be built without it**; the `period_start` spans are read off the site's own
`categorizePeriod` (`ancient-nerds-map/src/data/sites.ts:60-70`) rather than derived. Five new tests,
mutation sweep **20 -> 24, all 24 caught**, every restore byte-identical. Record:
`output/remediation/phase3_runner/PIECE5B.md`.

**A defect this exposed in the suite itself:** the tests that read the production snapshot read an
artefact that is not in the repository (`.gitignore:216`), so a CI checkout never has it and those
tests would fail there. They now skip with a reason when it is absent - the shape `test_t11.py:56`
already uses - proved by hiding the artefact rather than assuming: **31 passed, 7 skipped, 0 failed**,
snapshot restored byte-identically. Two tests that only needed the catalogue's value list pin it
instead, so they stay hermetic and can still catch a mutation in CI.

**What is not established here:** whether the three fixes move the recall number. That is the third
run (`runs/gold3`), same plan, same fixture, same question otherwise.

### Judge-checker adjudication, kept (2026-09-21)

The lint pass re-reports a fixed set of findings on every edit that touches `run.py` or
`fetch_stage.py`. They are **false positives of one class** (`call without try/except`), they sit on
lines this work never touched, and each is checked here rather than asserted. Re-checking them is
cheaper than a comment that suppresses them:

| line | what it is | why the finding does not hold |
|---|---|---|
| `run.py:121` | `if record["phase3"] is True:` | The plan-format guard. A JSON `true` is a Python `bool`; `is True` is the strictest correct spelling. The suggested `== True` would *weaken* it - `1 == True` is also true. |
| the three `payload = json.loads(report.to_json())` sites in `run.py` (fetch, judge, judge-discover) | `payload = json.loads(report.to_json())` | `to_json()` (`model_stage.py:917-924`) is `json.dumps` of a dict built from the object's own fields. **There is no file and no foreign input**, so "missing file" cannot arise; a `try/except` here would hide a serialisation bug rather than handle one. Cited by expression, not by line: every inserted line in `run.py` moves the number, and this is re-reported every turn. |
| the `return int(args.func(args))` at the end of `run.py` | `return int(args.func(args))` | The argparse dispatch. `args.func` is set by `set_defaults(func=cmd_*)` for every subparser, and an unknown verb is refused by argparse **before** dispatch: `run.py not-a-subcommand` exits `2` with `invalid choice`. Executed, not assumed. |
| `list_other_flags.py:52` | a reader of `model.json` and the answer files | `call without try/except` again - and here the `try/except` would be the defect. This script exists to surface flags the fixture does not list; a reader that swallows a missing file or unparsable JSON reports "no flags" for a run it never read, which is the one outcome it must never produce. Raising loudly **is** the check. |
| `verify_sources.py:48` | a reader of `fetch.json` (the page map for the citation check) | Same class, same reason, and one step stronger: this file decides whether a correction is writable, so a swallowed error would silently make a fabricated citation look verified. |
| `fetch_stage.py:682` (x2) | `return float(value[0]), float(value[1])` | Not unguarded - the three lines above it require the value to be a 2-sequence and every element to be `isinstance(v, (int, float))` and not a `bool`. `float()` on an `int`/`float` cannot raise; the `raise InputError` for everything else is one line below. |
| `fetch_stage.py:1307` | `result.truncated += int(outcome.truncated)` | `outcome.truncated` is this module's own dataclass field, computed by `one_attempt` from the transport's `truncated` flag. There is no foreign input to validate. |
| `fetch_stage.py:392` | `def __exit__(self, *exc: object) -> None:` | The exit protocol calls this with `(exc_type, exc_value, traceback)`, and a variadic parameter accepts all three - the contract is met, and the line predates the pacer work. The suggested named signature would be equivalent, not a fix, so it is not applied. |
| `mass_run.py:190-191` | `if isinstance(cost, (int, float)) and not isinstance(cost, bool):` then `spend.cost_usd += float(cost)` | `float` of an `int` or `float` cannot raise. The guard exists because a *fetch* ledger line carries `"cost_usd": null`, and null must not be summed as zero silently. |
| `mutation_sweep.py` | `sys.exit(main())` | The instrument's own entry point. `main` returns an `int`, and a crash inside the sweep **must** reach the exit code: the one failure mode this instrument was rebuilt to prevent (2026-09-21) is a sweep that dies mid-loop and reports nothing, leaving a mutant in the tree. A `try/except` here would turn a dead sweep into a green one. |
| `review_stage.py`, four sites | `refuted is True` / `refuted is False` | The same three-state rule as `model_stage.py`, now in the reviewer: `REFUTED` is `YES` / `NO` / **`UNRESOLVED`**, and the value is `True` / `False` / `None`. Measured, all three states: `True -> applies=False`, `False -> applies=True`, `None -> applies=False`, while the naive `if refuted:` spells them `True -> True`, `False -> False`, `None -> False`. So the naive form would have written a finding the reviewer **refuted** - the one outcome the pass exists to prevent. `== True` is not equivalent for `1` either. The suite pins all three states (`test_unresolved_is_neither_refuted_nor_not_refuted`). |
| `test_phase3_discover.py:1001` (line moves with every insert; cited by expression) | the `.encode("utf-8")` on the body handed to `EvidenceStore.write` | **Not** unnecessary: the parameter is `body: bytes` (`fetch_stage.py:831`) and the store writes it with `write_bytes`. Executed rather than assumed - passing the `str` raises `TypeError: memoryview: a bytes-like object is required, not 'str'`. The encode is what makes the call correct, and the suggested removal would break it. |

| `model_stage.py` (line numbers move; cited by expression) | the two `Usage` guards (`reported in (float("inf"), float("-inf"))`, `float(reported)`) and `[json.loads(f.to_json()) for f in self.findings]` | Both `float` sites stand under a guard that has already refused everything but a non-`bool` `int`/`float`, and both **raise `ModelCallFailed`** two lines above - a `try/except` there would swap a loud refusal of a nonsense cost for a silent default, which is the one thing that guard exists to prevent. The `json.loads` site parses this module's own `to_json()`, with no file and no foreign input, exactly like the three `run.py` sites above. Re-reported here because the reviewer question's rewrite moved these lines. |

No change is the correct outcome: the only edits that would silence these are a `try/except` around the
dispatch, an `== True`, and dropping an `encode` the callee's own signature requires - all three would
make the code check less. Nothing here is suppressed with a `# type: ignore` or a `nosemgrep`, so the
findings stay visible on every run.

## The third recall round: 7 of 19, and the boundary the question itself got wrong

Run: `bash output/remediation/logs/gold3_run.sh` -> `runs/gold3/`. The plan's sha256 is
`ad32d26fccb3913b2656d70df5485f9185bbe956a343f4476668e6e00dcbb9c0` (identical to rounds 1 and 2), and
the 33 fetched evidence files are **byte-identical to round 1's** (0 differing bytes over 17 enwiki +
16 wikidata_entity files), so the only variable between the rounds is the question. Every stage exit
was checked against its artefact rather than believed: `plan`, `prepare`, both `fetch`, both `judge`.

| round | question | CORRECT | WRONG | UNVERIFIABLE | caught / 19 | cost |
|---|---|---|---|---|---|---|
| 1 | first live question | 47 | 12 | 16 | 5 (26.3 %) | $0.054226 |
| 2 | + silence-is-not-agreement, evidence-first | 23 | 25 | 27 | 8 (42.1 %) | $0.056514 |
| 3 | + clause precedence, `site_type` vocabulary, bucket spans | 29 | 17 | 29 | **7 (36.8 %)** | $0.058108 |
| 4 | + the spans stated inclusive-first/exclusive-second (the boundary fix) | 32 | 13 | 30 | **5 (26.3 %)** | $0.058388 |

Cost is read from the frozen per-run `model.json` (75 calls, 364,945 in / 5,611 out for round 3), never
from `LEDGER.jsonl`, which a live run is appending to. The input rise of ~12k tokens across rounds is
consistent with the 70-value `site_type` list being carried in 75 calls.

**The two information fixes did what they were for, on precision.** `WRONG` fell 25 -> 17, and the
eight that disappeared are exactly the ones named in the round-2 entry: **0 `country`** and **0
`site_type`** false positives remain. Per entry, round 3 gained `The Gop/period_start`,
`Ocriticum/description` and `The Gop/card_description`, and lost `Arc de Berà/description`,
`The Merry Maidens/description`, `Temple of Dedun/description` and `Hebbariyeh Roman Temple/site_type`
- each of those four lost to `UNVERIFIABLE` on evidence that states no value.

### The defect: the clause stated a bucket boundary that the code does not have

The question taught the model a false fact. As delivered in round 3, the `period_start` clause read:

> `-3000 to -1500 is 3000 - 1500 BC; -1500 to -500 is 1500 - 500 BC; -500 to 1 is 500 BC - 1 AD`

`categorizePeriod` (`ancient-nerds-map/src/data/sites.ts:58-70`) compares with `<`, so each bucket is
inclusive of its first year and **exclusive of its second**: `-1500` belongs to `1500 - 500 BC` and
`-500` to `500 BC - 1 AD`. Both values land one bucket late, not one bucket early, and the two
surviving `period_start` false positives sat on exactly those two values - a stored `-1500`
(`Beacon Hill`) and three stored `-500` (`Arc de Berà`, `Bulls of Guisando`, `Ocriticum`). The Beacon
Hill answer states the cause in its own words: *"Stored value -1500 falls in the span `3000 - 1500 BC`
(upper bound inclusive, i.e. -3000 to -1500)"*. The model applied the rule it was given.

Fixed by stating every span as inclusive-first/exclusive-second and naming the two boundaries a reader
gets wrong, and the test that guards it no longer restates the spans - it **derives** them from
`sites.ts` (`re.findall(r"if \(start < (-?\d+)\) return '([^']+)'", ...)`) and asserts each one appears
in the question, so the question cannot drift from the code again. Sweep: **25/25 mutations caught**,
the restored file byte-identical (`discover_stage.py` `3368c12a29f3d534`); the sweep now carries a
"bucket boundaries stated as closed ranges" case, and the older "spans dropped" case was re-anchored to
the new text.

### What the flags outside the fixture are

The fixture is *"the 24 errors the census did not flag"*, not the complete error set, so a `WRONG`
verdict on a pair the fixture does not list is undecided evidence. Adjudicated one by one for round 3
(10 such flags), with the stored value in hand:

| class | n | which |
|---|---|---|
| the question's boundary bug | 4 | `Bulls of Guisando`, `Arc de Berà`, `Beacon Hill`, `Ocriticum` - all `period_start`, stored exactly `-500`/`-1500` |
| model error | 2 | `Beacon Hill/description` calls 1000 BC "outside" 1500-500 BC (it is inside); `Overstone/description` reads thin evidence as a *different* value |
| rubric-boundary call | 3 | `Midford Castle` and `Bulls of Guisando` `card_description` flagging "Legend says ..." / "among the most famous"; `Arc de Berà/card_description` flags an overstated generalisation |
| **a real error the fixture lacks** | **1** | `The Merry Maidens/card_description`: stored "the two Pipers stones reach 4.6 metres", evidence "two 3-metre-high standing stones" |

The honest reading: the finder's true-flag rate in round 3 is 8 of 17, and **4 of the 9 false ones
were the question's fault, not the model's**.

### An instrument bug found while doing this, in my own tooling

`output/remediation/gold_standard/list_other_flags.py` (new, and the reason the table above exists)
first reported round 2 as 21 `WRONG` where the committed scorer says 25. Both read the same answers.
The cause: the new script required the verdict at the *start of a line*, while 5 answers write it
inline (`2. VERDICT: UNVERIFIABLE`). The scorer's whole-text regex is correct, and the new script now
imports the same rule instead of re-deriving it; both instruments reproduce
`{CORRECT 29, WRONG 17, UNVERIFIABLE 29}` for round 3 exactly. Two instruments disagreeing on the same
artefacts was the finding - not either number.

### Round 4, and the claim it refuted

I predicted before the run that the boundary fix "cannot lose a catch": it stops flagging pairs
`categorizePeriod` puts in the same bucket and can only add a flag where the code puts them in
different ones. **The measurement says otherwise, and the mechanism is worth recording.** Round 4
caught **5 of 19** - back to round 1's level - and two catches went `WRONG` -> `UNVERIFIABLE`:

* `The Gop/period_start` (stored -5000, truth -4000 to -3000). Round 3 answered "the evidence states
a different value (Neolithic, i.e. within 4500-3000 BC)". Round 4 answers: *"The evidence states the
site is a Neolithic monument but gives no numeric year for `period_start`; on this field it is
silent."* The clause is read by a model, and a clause that insists on numeric spans makes a model
refuse to bucket an era name. The arithmetic is unchanged; the **behaviour** changed.
* `Ocriticum/description`. A prose field, untouched by the period clause: this one is variance.

**The series is 5, 8, 7, 5.** With one model and 19 reachable entries, that is a noise band, not a
trend - and the honest reading is that prompt editing on this fixture does **not** measurably raise
recall. What it does move, monotonically and in the right direction, is the number of flags: `WRONG`
went 12 -> 25 -> 17 -> 13, and the clause went from containing a false statement about the code (round
3) to containing none (round 4). The delivered question is therefore chosen for **being correct**, not
for scoring best, and the recall estimate reported for it must carry the band: any of 5-8 of 19 is
consistent with these runs. Further rounds on this fixture would be fitting noise.

### Round 4's flags outside the fixture, adjudicated

8 flags, against round 3's 10:

| class | n | which |
|---|---|---|
| **real, and absent from the fixture** | **2** | `The Merry Maidens/card_description` (Pipers 4.6 m vs the evidence's 3 m), `Ksar el Barka/card_description` (stored "founded in 1690 by the Kounta"; the evidence has the Kounta arriving to an existing town called Laaci-Wendu) |
| century arithmetic | 2 | `Bulls of Guisando/period_start` ("2nd century BCE") and `Ocriticum/period_start` ("4th century BC") both placed in `1500 - 500 BC`; both centuries are inside `500 BC - 1 AD`, since -200 and -400 are greater than -500 |
| rubric-boundary call | 4 | the "Legend says ..." and "Vettones as the *Celtic* Vettones" flags, plus two fine-grained prose mismatches |

The two arithmetic flags are a **new** defect class, not the boundary one: the model converts a
century phrase to the wrong span. That conversion is convention, not subject knowledge, so the fix is
the same kind as the span table itself: the clause now works both examples ("the 2nd century BC is
-200 up to but not including -101, and the 4th century BC is -400 up to but not including -301, so
both of those centuries fall in `500 BC - 1 AD`"), and the test checks the sentence against
`categorizePeriod` for every year it covers rather than checking that the words are present.

### Round 5, and the freeze

Command: `bash output/remediation/logs/gold5_run.sh` -> `runs/gold5/`. Plan sha256 unchanged
(`ad32d26fccb3913b...`), 33/33 evidence files byte-identical to round 1, all six stage exits checked
against artefacts. **7 of 19 caught, 15 `WRONG`, 33 `CORRECT`, 27 `UNVERIFIABLE`**, 75 calls,
367,345 in / 5,760 out, **$0.058558**.

The century sentence did what it was for, on half its targets. `Ocriticum/period_start` (the "4th
century BC" case) is gone from the out-of-fixture flags; `Bulls of Guisando/period_start` (the "2nd
century BCE" case, stored -500) is still flagged, even though the clause now says in words that the
2nd century BC is -200 to -101 and therefore falls in `500 BC - 1 AD`. That remaining flag is a
**model arithmetic failure with the correct fact in front of it**, not a question defect, and it is
recorded that way rather than repaired with another sentence.

Per entry against round 4: gained `Temple of Dedun/description`, `Hebbariyeh Roman Temple/site_type`
and `Ocriticum/description` (all three were round-3/4 losses returning); lost `Beacon Hill/
card_description`. The `Hebbariyeh site_type` return is instructive - the `site_type` clause did not
change between rounds 4 and 5, so that flip is variance by construction.

| round | caught / 19 | WRONG | CORRECT | UNVERIFIABLE | cost |
|---|---|---|---|---|---|
| 1 | 5 | 12 | 47 | 16 | $0.054226 |
| 2 | 8 | 25 | 23 | 27 | $0.056514 |
| 3 | 7 | 17 | 29 | 29 | $0.058108 |
| 4 | 5 | 13 | 32 | 30 | $0.058388 |
| 5 | 7 | 15 | 33 | 27 | $0.058558 |

### Owner decision, 2026-09-21: all 5,004, and corrections with sources

Martin decided three things in one message, and they change the remaining work:

1. **Scope is all 5,004 sites**, not the 1,813-site census worklist. That matches the coverage
   finding (`5815e64`: the worklist holds 4 of the 17 sites carrying the 24 missed errors) and it is
   the answer to the question the plan left open. Cost is not the reason to hesitate - the discover
   stage over all 5,004 is 25,020 calls, measured at $0.000781 per call = **~$19.5**; wall clock is
   the constraint, which is what the mass-run driver addresses.
2. **The model must correct, not only flag.** The delivered question says the opposite today, in
   writing: `Never guess a replacement value.` and `You propose; you do not write.` Under the new
   requirement a `WRONG` verdict must carry the value the site should store.
3. **Every correction must carry evidence and a source.** So the answer gains `PROPOSED:` and
   `SOURCE:` lines, and - this is the part that keeps the project's own rule intact - **a cited source
   must be a URL the run actually fetched, with a verbatim quote that occurs in the bytes we stored**.
   A model may not cite a page nobody pulled; the quote is machine-checkable against our own evidence
   files, so "with sources" becomes a verified property rather than a claim in prose.

Consequence for the pipeline: the discover answer format is extended (parse into
`evidence`, `verdict`, `proposed`, `sources` plus a `problems` list), the source claim is verified
against the fetched bytes, and the writer refuses any finding that is incomplete or whose quote does
not occur in the stored page. `HUMAN_ONLY.md` lists what stays a human decision (push/deploy, a search
provider key, the 285 name/coordinate cases, the 117 T02 cases, the 17 sites with no prose route, the
42 without `source_url`, image spot-check, style calls).

**No search route exists in this codebase** (checked: no `*SEARCH*`/`SERP`/`TAVILY`/`EXA` accessor
anywhere in `api/`, `pipeline/`, `scripts/`). *[Corrected 2026-09-22: wrong -
`pipeline/lyra/minimax_shared.minimax_search` exists and serves Lyra, the tweet verifier and Theo; the
true statement is that the phase-3 pipeline has no search route. See the 2026-09-22 corrections at
the end of this log.]* "Research online" therefore means, until a provider is
named: more and independent *fetched* routes, not a model with a browser.

#### The trap inside "with sources": the evidence is API JSON

The first version of the citation check would have failed every honest quote, and the failure would
have looked like a model that fabricates citations. `model_stage.evidence_block:558` puts
`EvidenceExcerpt.text` into the prompt **verbatim**, and for `enwiki`/`wikidata_entity` that text is
the API's **JSON response** - so the page carries `\u00c1vila` and `\n` exactly where the model reads
`Ávila` and a line break. A byte comparison of a normally-transcribed quote against the stored file
therefore reports "does not occur" for a quote that is perfectly genuine, and the metric would have
measured JSON escaping rather than citation honesty.

Both sides are unescaped (`\uXXXX`, `\n`, `\"`, `\/`), whitespace-folded and case-folded before they
are compared. That fold is the only relaxation and it is deliberately narrow - the words and their
order are still required - but it is also the honest description of the instrument: this check proves
a sentence was **in the page we fetched**, not that it was byte-identical to it. Recorded here because
the next person to tighten this check would otherwise re-introduce the false negative.


The question is frozen at round 5's wording. Three reasons, all measured:

1. **The catch count is noise.** 5, 8, 7, 5, 7 over five rounds with one model and 19 reachable
   entries. Two of the five rounds differ by three entries (`The Gop period_start`,
   `Ocriticum description`) with no clause between them touching those fields. Any further edit would
   be fitted to 19 data points.
2. **The question no longer states anything false.** Round 3's clause mislabelled two bucket
   boundaries; round 5's derives every span from `categorizePeriod` and states the century
   convention. What remains disagreeing is the model's arithmetic and its judgement calls on prose -
   not facts the question asserts.
3. **The remaining false flags cannot be removed by prompt text without changing the rubric.** The
   residual classes are century arithmetic (model-side, with the fact supplied), and "the stored claim
   is unsupported / too general / a legend" - which is the evidence-only rule working as designed.
   Softening it to reduce those flags would trade a known, inspectable false-alarm rate for an
   unknown one, and the pass exists to raise **leads**, which a human then reviews.

Delivered numbers, for the mass-run decision: **recall 7/19 (band 5-8)**, **8 of 15 flags lie
outside the fixture** and were adjudicated by hand (2 real errors it does not list, 1-2 century
arithmetic, the rest rubric calls), **$0.000781 per call**, so the discover stage over all 5,004 sites
is 25,020 calls ≈ **$19.5** - against the earlier wall-clock figure of ~211 h, which remains the
binding constraint and is unaffected by any of this.
* Three of the four lost catches went to `UNVERIFIABLE` on evidence that states no value. The
delivered rule is "Only the evidence in this message decides", so that answer is *correct under the
delivered rubric*; the fixture expects a solver that also uses its own subject knowledge. That is a
design decision (own knowledge may refute and never uphold?) and it is deliberately **not** folded
into this fix.

## Round 6: the correction contract, and zero fabricated citations (2026-09-21)

Martin's direction changed the deliverable: **all 5,004 sites, the model corrects instead of only
reporting, and every correction carries evidence and a source.** The delivered question said the
opposite - `Never guess a replacement value.` / `You propose; you do not write.` - so this is a design
change, and it is measured like the five rounds before it.

The contract: a `WRONG` verdict now owes `PROPOSED: <the value the field should hold>` and up to three
`SOURCE:` lines, each `<url from the evidence> - "<a sentence copied from that page>"`. Five places
decide whether such a finding may be written, and each was proved to have teeth by mutation: the
question asks for it, `parse_answer` parses it (inline verdicts included), `source_problems` requires
a source, refuses a url **this run never fetched**, and `quote_occurs` requires the sentence to be in
that page. `verify_sources.py` reports the rate over a whole run; the writer (piece 6) will call
`source_problems` and drop what fails.

**The trap that would have made this look like the model's fault.** The `enwiki`/`wikidata_entity`
evidence files are the APIs' JSON responses and `model_stage.evidence_block:558` puts them into the
prompt verbatim, so the page says `\u00c1vila` and `\n` where the model reads `Ávila` and a break. A
raw-byte comparison reports every honest quote as missing, and the metric would have measured JSON
escaping while reading as a model that invents citations. Both sides are unescaped, whitespace- and
case-folded first; words, order, punctuation and digits are still required.

Round 6, controlled like the others - plan sha256 `ad32d26fccb3913b...`, all six stage exits verified
against their artefacts, **33/33 evidence files byte-identical to round 1**:

| | round 6 |
|---|---|
| recall | **7 of 19 asked = 36.8 %** (of 24: 29.2 %) |
| verdicts | CORRECT 31 / WRONG 13 / UNVERIFIABLE 31 |
| WRONG carrying a proposed value | **13 of 13** |
| WRONG carrying a source | **13 of 13** |
| quoted sentences | 14 |
| **citation problems** | **0** - every quote occurs in the page it cites |
| cost (frozen `model.json`) | 75 calls, 382,930 in / 7,439 out, `$0.061903` = **`$0.000825`/call** |

Two readings. Recall sits inside the noise band the five earlier rounds established (5, 8, 7, 5, 7):
the contract costs nothing in catches. The citation rate is **not** a noise band - 14 of 14 verified
against our own bytes - and that was the risk worth $0.06 before 25,020 calls: a model that
paraphrases would make the design unusable at scale, and it does not paraphrase. Cost per call rose
from `$0.000781` to `$0.000825` (longer answers), so the discover stage over all 5,004 sites projects
to **~$20.6**; wall clock remains the binding constraint. Out-of-fixture flags fell 8 -> 6.

What this obliges: a finding whose source cannot be verified must never reach the journal, and the
mass run should record the citation rate per batch - it is the one number that says the running model
is still the measured one.

`output/remediation/HUMAN_ONLY.md` now carries the table Martin asked for: what only he can decide
(the push, the mass-write deploy, a search-provider key, cron mail, offsite, the `mypy api/` debt) and
what only a human should judge per site (285 name/coordinate calls, 117 T02 countries, 17 sites with
no prose route, 42 without `source_url`, deletions). Its counts come from the snapshot and from
`output/remediation/phase3_pilot/COST.md:141`, not from memory.

Also decided here, because it was the same defect class twice: `score_recall.py` no longer carries its
own verdict regex but imports `discover_stage.VERDICT_RE`, and the five committed
`recall_result_*.json` files were re-derived with the shared rule and came back **byte-identical**
(5/19, 8/19, 7/19, 5/19, 7/19).

---

## Piece 7: the mass-run driver, and the host pacer under it (2026-09-21)

`scripts/remediation/phase3/mass_run.py` walks a plan and drives every batch through `prepare`, `fetch`
and `judge`. Nothing in it touches the database: this piece produces findings, piece 6 turns confirmed
findings into guarded writes, and keeping those apart is what makes findings safe to produce in bulk.

**A script, not a subagent lane, and that is a measured decision.** The 30-minute ceiling binds lanes,
not `bg_run` scripts. Two lanes this session were killed at that ceiling and their workflow receipts
reported files they had not written - one of them left a mutant in the tree. A script writing to files
it owns cannot lose its evidence that way, and an interrupted batch is simply not done.

**The prerequisite, built first: the host pacer.** `HostPacer` + `PacedFetcher` in `fetch_stage.py`.
One lock file per host (created `O_CREAT|O_EXCL`, stamped with its own acquisition time, stale takeover
after 30 s), a minimum interval of 0.2 s between two requests to the same host, and a fail-closed
`PacerTimeout` instead of an unbounded wait. It decorates the `Fetcher.get` seam, so probes, retries
and targets are paced alike. It is a **cross-process** handshake on **one machine**; it is not a global
rate limiter and not a distributed one, and that sentence stays true if the mass run ever moves to the
VPS.

**The guards, each with a test that has been proved able to fail by mutation:**

| guard | protects against |
|---|---|
| `batch_state` says `done` only when both artefacts parse and every recorded answer is on disk | a truncated `model.json` from a kill mid-write reading as success |
| the ledger is read before each batch is started | spending past a ceiling because nobody looked |
| N consecutive failures stop the run; a success clears the count | 300 batches burned against one broken assumption, or a breaker that is only a counter |
| the phase-3 sources are hashed at start and compared before every batch | two batches executing two versions of the code |
| the progress file is written to a temp file and swapped in | a reader seeing half a progress report |
| the dry run writes no ledger line | a "harmless" dry run that quietly bought something |
| every stage exiting 0 is *not* enough; the artefacts decide | `exit 0` taken as a claim, again |
| a stage past its wall clock is recorded, not fatal | one hung batch killing a 40-hour run |

**The budget is checked between batches**, so with `--jobs N` up to `N` batches are in flight when a
ceiling is reached. That is written down rather than discovered: the driver stops naming what it did not
reach, and the overshoot is bounded by the batch wave. **Resumption** is by construction: `fetch` skips a
target whose evidence file exists and `judge` re-uses an answer it already has (`wrote=False`), which is
what makes "a half-written batch is redone rather than trusted" cheap enough to be the default.

**Numbers.** `PLAN.snapshot.jsonl` over the whole table was generated and its sha256 is
**`a5786f102c8352bbfe94eb9ecfd9dc7d0b8b15625f4ac94b6753a245572716bb`** - identical to the piece-5
figure, 12,042,556 bytes, 334 batches, 5,004 sites, ordinals 1..334, last batch 9 sites - while the
worklist plan stayed byte-identical at `96704b808ae1b29d…`. 25,020 calls at the measured $0.000825
(round 6) is **~$20.6** for the discover stage; a reviewer stage would roughly double it and is **not
built**. Serial wall clock is ~76,000 fetches at 8.8 s plus ~25,000 calls at 2.6 s, so **~200 h and
up**; `--jobs 4` is a first measurement, not a promise, because the pacer keeps two processes out of one
host without making the host faster, and every batch wants the same hosts.

**One decision belongs to Martin before this starts** (`HUMAN_ONLY.md` (h)): `overpass-api.de` is
unreachable from this workstation while the VPS can reach it. A mass run started here therefore
collects **no overpass evidence at all**, and the discover pass would answer with strictly less
evidence than it was measured with - the six recall rounds all share the same 33 evidence files, which
is exactly what makes them comparable to each other. Either run it on the VPS or accept the reduced
evidence and say so in the findings.

**Defects of my own, found while writing, recorded because the classes recur:** two identical branches
(`live` / not `live`) doing the same thing were dead duplicated logic and were collapsed; an unclosed
backtick left a mangled sentence in a docstring, which no tool reported; and the first atomicity test
could not distinguish `os.replace` from a plain write - asserting "no `.tmp` is left behind" is
satisfied by both - so it was replaced by one that dies between the write and the swap, and the new
mutation then proved it has teeth. The `BatchRunner` protocol replaces what would have been a
`# type: ignore` in the tests, following the repo's own `Fetcher` protocol. And `read_plan`'s bare field
access became a `PlanError` naming file and line: here the checker was right, unlike the five `run.py`
lines, and the difference is that a **plan is input** - unknown fields and a non-numeric ordinal are
things that happen to input.

**Verified.** The gate after the pacer: **2316 passed, 3 skipped, 57 deselected in 181.94 s** (2309 +
7 pacer tests). The driver's own file: **29 tests** green. Mutation sweep **43/43 caught, `missed: []`**,
restore proved byte-identical for all six files it touches (`mass_run.py` `ba511951644ce0b1`,
`fetch_stage.py` `126396c218747869`, `discover_stage.py` `cd2a3edb3eb104d2`, `snapshot_plan.py`
`983b5ea8e8c42798`, `model_stage.py` `2810315bc048a1ef`, `run.py` `1f51e01aa3f75d21`). The full report is
`output/remediation/phase3_runner/PIECE7.md`.

**Not in this piece:** no database writes, no reviewer stage (so still no path from a discover finding
to the writer, which needs `refuted=false`), no per-field evidence selection (an oversized site is still
refused as a whole), and no search provider - the answer contract requires a source the run itself
fetched, which is the only kind of source it can check.

## Piece 7, the part the stubs could not see (2026-09-21)

The driver and the pacer were committed green - 29 driver tests, 43/43 mutations, 2316 in the gate -
and the first attempt to actually *use* it found two defects in it. Both were in the seam between the
driver and `run.py`, and neither was reachable by a test that stubs that seam.

### `prepare` was sent flags it does not have, and never the plan

The driver built one argv shape for all three stages. Checked against the real parser instead of a stub:

    $ run.py prepare ... --ledger L.jsonl --live
    EXIT 2: unrecognized arguments: --ledger L.jsonl --live

and, once that was visible, the defect behind it: `prepare` was **never** passed `--plan`. It would have
prepared the default worklist plan under a batch id that exists in *both* plans, so the run would have
fetched and judged the wrong fifteen sites - silently, because nothing about that raises.

That is not hypothetical: the smoke plan and the worklist both have a `batch-0001`.

    input.json      batch_id=batch-0001  sites=['a5d9e9a7-9fd2-4a0f-a3ae-7dd78fba429b']
    worklist        batch_id=batch-0001  sites=['31860bc4-476a-49bc-9f97-e25220063d19', ...]

**The lesson is the shape of the test, not the bug.** 29 tests were green while the driver could not
have prepared a single batch: `_StubRunner` stood in for `StageRunner`, so the argv was only ever
inspected, never parsed. A seam that is stubbed must *also* be checked against the real thing -
`test_every_stage_argv_is_accepted_by_the_real_cli` feeds every stage's argv to `run.build_parser()`,
and `test_prepare_is_given_the_plan_and_neither_the_ledger_nor_live` asserts on the namespace it parses
into (`not hasattr(ns, "ledger")`), which is the only way "prepare does not take a ledger" can be stated
once and stay true.

### The ceiling counted the ledger's whole history

Found while preparing the smoke run: `Budget.stop_reason` compared `spend.calls` - the **total** in the
shared ledger - against `--max-calls`. The ledger is shared with the pilot and the six recall rounds,
which held 465 model calls at that moment, so `--max-calls 25020` would have stopped 465 calls early and
meant something other than what it says.

The ceilings now count from the ledger as it stood when the run started, and both numbers are named:
`call ceiling reached: 80 >= 75 calls this run (the ledger holds 80)`. The start-up line reads
`already spent 465 calls, $0.354982 (the ceilings count from here)`.

This one required rewriting a test of mine: `test_the_call_ceiling_stops_...` seeded the ledger with 75
calls and asserted a stop, i.e. it *encoded the absolute reading*. A seeded ledger is a baseline now, so
that test asserted the superseded defect. It was rewritten so the stub buys calls the way `judge` does
(`calls_per_batch`, `cost_per_call`), and the test a mutation now has to break is
`test_a_ceiling_means_this_run_and_not_the_ledgers_whole_history`: five hundred calls of history, a
ceiling of 75, forty calls bought per batch, two batches - the run finishes, and the ledger total ends at
580, well past the ceiling.

### Two smaller ones, both mine, both caught by something already built

- A replacement block I wrote renamed `queue` to `queues` in `run_mass` while the rest of the function
  still used `queue`. The checker reported seven `queue is not defined` errors in the same call that
  introduced it. Credit where it is due: that is the second time this session a checker caught a defect
  of mine before it reached a commit.
- My first version of the dollar-ceiling test bought $0.16 of calls against a $0.25 ceiling and asserted
  a stop. The test failed, loudly, which is what it is for. The arithmetic is now 3 batches x 20 calls x
  $0.01 = $0.40, and the assertion names the batch that was not reached.

The projection line also read `projected $0.00` for a five-call run (`.2f` of 0.004125). Now `.4f`:
`projected $0.0041`.

### The first end-to-end run: one site, 19 seconds, and a real correction

`mass_run.py --live --limit 1` over a one-site plan (`PLAN.smoke.jsonl`), run dir `runs/smoke1`.

| | |
|---|---|
| stages | `batch-0001: done (5 answers on disk)`, exit 0, nothing not reached |
| ledger | 465 -> 470 calls, $0.354982 -> $0.358588 (**+$0.003606**, $0.000721/call) |
| fetch | 2 probes + 2 targets = 4 requests, 7,367 bytes, 0 failures, 0 truncations |
| evidence | `enwiki` 1,533 B + `wikidata_entity` 5,834 B - **byte-identical to the recall round** |
| model | 5 calls, 21,255 in / 695 out, 0 calls skipped |
| wall clock | 10:22:17 -> 10:22:36 (19 s); four fetches inside one second, calls ~2.5 s apart |

And the run produced a finding, not just an exit code. `card_description` came back:

    VERDICT: WRONG - the sources say the Kounta arrived in 1690 to an already-existing community
    (Laaci-Wendu existed earlier as the Jaawbe capital), not that the town was founded by them then.
    PROPOSED: Ruined town in Mauritania, later Ksar el Barka, on the shores of Lake Gabou; ...
    SOURCE: https://en.wikipedia.org/w/api.php?... - "In 1690 the Kounta, who were from Ouadane and
    fleeing increasingly desertification, came to the area. There was still a Black African farming
    community there ..."

The stored value claims a founding in 1690; the cited sentence says they *came* to a community that was
already there. That is the round-6 answer contract - a correction with a source - working in production
rather than in a measurement.

**Wall clock, corrected by measurement - and the old estimate stands until the mass run says
otherwise.** One site of the enwiki+wikidata shape takes 19 s. The truth-plan sites took ~120 s each (up
to 15 targets each, including the unreachable `overpass-api.de`). Which of the two the 5,004 sites
resemble is not yet measured; the first mass batches will say. Nothing here is a projection from n=1.

### The pace belongs to the driver, not to a default in `run.py`

Wiring the pacer into `cmd_fetch` was one `if`, and it was wrong in the way that matters: the new
`--pacing-dir` **defaulted to the repository's own directory**. The first command after that edit failed
to delete a lock it had left behind:

    rm: cannot remove '.../output/remediation/logs/pacing/en.wikipedia.org.lock': Device or resource busy

The lock came from a *test*. The existing live-fetch tests call `R.main(["fetch", ..., "--live"])`
without `--pacing-dir`, so they took the default and wrote real lock and stamp files into the working
tree. Two consequences, both real: a test run can hold a host's lock while a live run waits up to
`HOST_LOCK_WAIT_SECONDS` and then fails closed, and every test run quietly rewrites the machine's pace
state.

The scope was the defect, not the value. **Concurrency is what the driver creates, so the driver is what
names the pace:**

- `run.py fetch --pacing-dir` defaults to **empty**: one `fetch` process has nobody to pace against, and
  a machine-wide default is a shared resource a test can grab.
- `mass_run.StageRunner` passes `--pacing-dir <DEFAULT_PACING_DIR>` for the `fetch` stage only (nothing
  else opens a connection), and the run banner prints it. `run.DEFAULT_PACING_DIR` and
  `M.DEFAULT_PACING_DIR` are the same path, and a test asserts they agree.

Proved at the CLI, not in the abstract - the stage log of the `--jobs 2` run carries the flag:

    $ ...\python.exe ...\run.py fetch --run-dir ...runs\smoke4 --batch-id batch-0001 \
        --ledger ...\LEDGER.jsonl --live --pacing-dir C:\...\output\remediation\logs\pacing

and afterwards both hosts those two batches touched have a stamp file in that directory.

### The guard caught my prose

The same edit broke `test_the_skeleton_touches_no_network_and_no_model_client`, which bans
`httpx|requests|urllib|socket|aiohttp|openai|anthropic|subprocess` in the source of `model.py`,
`ledger.py` and `run.py`. The hit was `socket` - in a **comment of mine** ("not a second owner of the
socket"). The guard is blunt and its intent is exact: those three modules do not even *name* a network
or model client. So the comment was reworded, not the guard. That is the third time this session that
something already built caught something I wrote.

Also mine, and caught by reading my own diff inside the same edit: while adding `pacing_dir` to
`StageRunner.__init__` I renamed `stage_timeout` to `step_timeout` in the signature and left
`self.stage_timeout = stage_timeout` below it - a `NameError` at every construction, i.e. no batch could
have started. Reverted before any test ran.

### The sweep died and left a mutant in the tree (2026-09-21)

This is the worst failure mode this project has, and it happened: the sweep that proves every guard has
one aborted mid-mutation and left the mutated file behind. The receipt is
`output/remediation/logs/phase3_mutations/sweep_after_pacing_wiring.txt`, 24 lines, `SWEEP_EXIT=1`:

    Exception in thread Thread-61 (_readerthread):
      File ".../subprocess.py", line 1615, in _readerthread
        buffer.append(fh.read())
    UnicodeDecodeError: 'charmap' codec can't decode byte 0x81 in position 489
    ...
      File ".../mutation_sweep.py", line 553, in main
        detail = first_failure(proc.stdout + proc.stderr) if caught else "NOT CAUGHT"
    TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'

**Two causes, and the second one is mine.** `subprocess.run(..., text=True)` decodes the child's output
with the **locale's** codec - cp1252 here - so one UTF-8 byte outside cp1252 killed subprocess's reader
thread and `stdout` came back `None`. And the restore (`shutil.copy2(backup, path)`) sat *after* the line
that raised, so nothing put the file back.

**What was left behind.** `discover_stage.py` carried
`unescaped = text` instead of `unescaped = _ESCAPE_RE.sub(_unescape_match, text)` - the JSON-escape
decoding silently switched off, in a file that otherwise looked like finished work. Found, not stumbled
on, by asking the mutations themselves: for each one, is its **original** text still in the file? The
anchor question is the decisive one, because a mutation *replaces* its anchor - and one mutation
(`over-bound evidence no longer becomes the site's own outcome`) duly reported both texts present,
because its replacement text also occurs legitimately elsewhere. Both facts are in the log of that
check; only one of them was a mutant. `git checkout --` restored the file to its committed bytes, and
the 51 discover tests pass.

**The repair.** Not `(proc.stdout or "")` - that tolerates an unreadable capture and quietly loses the
failure detail. The child is read as UTF-8 explicitly (`encoding="utf-8", errors="replace"`), and the
child is told to write UTF-8 (`PYTHONIOENCODING`), which is what `StageRunner.call` already does for the
judge's non-ASCII prompts. The locale is not the child's encoding, and assuming it is was the bug.

**The instrument now has its own tests** (`tests/remediation/test_phase3_sweep.py`, 2 tests, each with
its own mutation): `main()` takes `repo` and `backup_dir` so a test can sweep a throwaway tree - a sweep
test that touched the real tree could leave exactly the mutant it exists to prevent. One test feeds it
the unreachable output (`stdout=None`), the other a mutation the test *did not* catch; both assert the
file is byte-identical afterwards, and the first also pins the encoding the child is read with.

**The rule this earns, and it is not a metaphor:** a sweep whose failure mode is "the tree is now wrong"
is worse than no sweep, because a mutant in the tree looks exactly like work already done.

**Two smaller things from the same hour, both mine.** Running `ruff format` on the whole of
`phase3/` rewrote a line in `discover_stage.py` that no change of mine had touched; that was reverted to
the committed bytes, and the rule is to format the files being changed and not the directory. And a
multi-block `edit` of mine deleted the path element from one mutation tuple, leaving it with five
instead of six - caught by `mypy` before any test ran, which is the argument for keeping the mutation
list typed.

### The evidence bound was raised from the fixture's own figures (2026-09-21)

`MAX_EVIDENCE_CHARS` was 32,000, and a site whose combined evidence exceeded it was refused **whole**:
`check_evidence_bound` raised, and the discover pass turned that into all five of the site's fields
being unverifiable. Across the recall fixture's 24 truth sites that hit two - Priene Ruins (37,339
characters) and the Pyramid of Caius Cestius (49,952) - and it hit them inclusively: the fields whose
decisive sentence sits in the part that *would* have fitted were refused along with the rest.

The comment on that constant already said what to do about it - "if a later batch trips it, this
number gets raised from that batch's own figures rather than from another guess" - and the fixture is
those figures, so it was raised to **64,000**: the observed maximum plus about a third, the same
headroom the earlier figure was aiming at, and still well inside the fetch stage's 61,440-byte page cap.

**The alternative was rejected, and the reason matters more than the decision.** Truncating each page
to a share of the budget and *naming the cut* would refuse no site at all, and `PARTIAL_EVIDENCE_NOTE`
already shows the shape for saying that honestly. What stops it is who would catch the error it can
cause: a finding justified by the visible part of a page but contradicted by the hidden part would be
seen by the finder and by the reviewer **through the same truncation** - and refuting the finder is the
reviewer's entire job. The quote requirement narrows that hole (a `SOURCE:` quote has to occur in the
evidence the run fetched) but it does not close it. Refusing leaves the pipeline unable to make that
mistake at all; a larger bound buys back the coverage the refusal was costing without buying the risk.
So the refusal stays, and it stays a sensor for the next batch's own figures.

A test now pins the floor: `test_the_evidence_bound_is_above_every_site_the_recall_fixture_measured`
asserts the bound is at least 49,952 and names both figures, so lowering the number past the
measurement fails instead of quietly re-refusing a site the fixture had already paid for.

### Two more checker findings, adjudicated (2026-09-21)

`model_stage.py`'s `float(reported)` (three sites) and `json.loads(f.to_json())` join the table above.
The first is the fail-closed path and says so one line later (`reported != reported or reported in
(float("inf"), float("-inf")) or reported < 0`): a provider that reports a cost this code cannot
believe must stop the call, not be coaxed into a number. The second parses our own in-process
dataclass - the same class as the three sites in `run.py`. Neither is a defect; both stay visible and
neither takes an action.

### An appended log is not evidence about the latest attempt (2026-09-21)

After the pacer fix, the restarted run was inspected two minutes in. Two stage logs had **fresh
mtimes** and contained `PacerTimeout` / `WinError 32`:

```
13:37:03  batch-0001.fetch.log   Treffer=2
13:39:40  batch-0005.fetch.log   Treffer=1
```

The conclusion drawn from that was "the repair did not remove the wedge" - and it was wrong. Stage
logs are **appended**, so an mtime dates the *last* write, not the content above it: the traceback sat
**above** the new attempt's own `$ ... run.py fetch ...` line and belonged to the run that had been
stopped an hour earlier. The new attempt's payload was a complete report with `skipped_existing: 27`,
and the driver itself said `batch-0001: done (55 answers on disk)` with `0` FAILED.

The rule, which is the same one as "check the instrument before believing the number":

* the identity of a *line* in an appended log comes from the text around it (`$ <command>` starts an
  attempt), never from the file's timestamp;
* the driver's own verdict (`done`, `FAILED`) is the measurement; a pattern count in a stage log is
  not one.

And the cheap confirmation that it is the *new* run: `output/remediation/logs/mass_run_driver.log`
carries `0` FAILED and the ledger's `at` timestamps move forward, while every traceback in those logs
predates the launch.

### The first mass run died on the pacer's lock, and the lock was wrong (2026-09-21)

Four batches in, every fetch ended `exit 1`; the tracebacks all ended the same way:

```
phase3.fetch_stage.PacerTimeout: ...\pacing\en.wikipedia.org.lock was held for 60s
  - the holder is stuck, not busy
```

The run was stopped by hand (it is resumable, so stopping cost nothing but the probe requests).

**Reproduced, then explained.** The first probe - four processes, twelve waits each, against a fresh
directory - passed, and that green was a statement about the probe, not about the pacer: the race is
hit when processes start *simultaneously* on one host. With **eight** processes and the real
constants, four died with

```
PermissionError: [WinError 32] Der Prozess kann nicht auf die Datei zugreifen,
  da sie von einem anderen Prozess verwendet wird ... en.wikipedia.org.lock
```

and four gave up waiting. Three defects, each with a measured consequence:

1. **An empty lock was called a leftover.** The lock is created by `os.open(O_CREAT|O_EXCL)` and
   filled by the next statement, so for that instant the file exists and says nothing. `_is_stale`
   read "no readable timestamp" as "a killed process's lock" and stole it from a **live** holder.
2. **The thief and the victim then both held it.** The victim's `finally` deleted a file that was no
   longer its own, and the mutex stopped being a mutex: several processes were inside the critical
   section at once, which is the impoliteness the pacer exists to prevent.
3. **On Windows that delete fails.** A file another process holds open cannot be removed - WinError
   32 - and that `PermissionError` escaped `wait()`, so the failure was not a slow fetch but a dead
   batch. The stale-takeover path had the same exposure.

The rules that replace them, each pinned by its own test and its own mutation:

* **Age, not readability.** A lock's mtime is set at creation, so it has no empty window. The
  content is still used when it parses (it carries the injected clock's time, which is what makes
  the interval testable), and the file's age is the fallback. Both directions are pinned: young and
  unreadable is *held*; old and unreadable is *taken over*.
* **A lock is deleted only while its content is still ours.** The content is now `<time> <token>`;
  a lock somebody else owns is not ours to destroy.
* **A lock that cannot be deleted is waited out, never spun on**, and a failed delete is a return
  value, not an exception. Losing this race costs one batch's time; it must not cost the batch.

**The earlier smoke runs proved the wiring, not the race.** `smoke2` and `smoke4` ran `--jobs 2`
with two batches - and the collapse needs several processes probing the same host at the same
instant. What they proved (the flag reaches `fetch`, the pacer wraps the `Fetcher` seam, the stamps
land in the machine-local directory) still stands; what they did not prove is now stated as not
proven.

**What made this cheap to find:** the failure was loud - a traceback per batch, `exit 1`, no silent
empty result - and the pacer's own error message named the file and the duration. A guard that fails
by *waiting quietly* would have burned the two days before anyone read a log.

### pi-lens deleted a tuple element and called it a reformat (2026-09-21)

While a mutation sweep was running, pi-lens reported two autofixes. The first was **false**: it named
`fetch_stage.py`, and that file was byte-identical to HEAD with an mtime from four hours earlier -
verified by `git diff` and sha256, not by the message. The second was real, twice over:

* `discover_stage.py` was reformatted at 13:02:32, **while the sweep was running**: one
  `problems.append(...)` collapsed onto a single line. Harmless as text - and still enough to
  invalidate the sweep, because mutations target that file and the per-mutation comparison only ever
  compares bytes it captured itself.
* `snapshot_plan.py` was "reformatted" afterwards, and that diff is **not** a reformat:

```diff
     "site_type",
-    "country",
     "card_description",
```

`DISCOVER_FIELDS` lost an element. That tuple decides which fields the discover pass judges, so every
plan built from it would have carried four fields instead of five - silently, and with a plan digest
nobody had a previous value to compare against. It is the same defect class as the multi-block `edit`
of mine that dropped `mass_run.py` from a mutation tuple earlier the same day, and the second time a
hash comparison against a known-good revision was the only thing between it and the pipeline.

Both files were reverted to HEAD (`discover_stage.py` back to `cd2a3edb3eb104d2`, `snapshot_plan.py`
to its blob) and the sweep was re-run on the frozen bytes.

**Two rules, one of them now an instrument.** Never carry a plugin's autofix on trust: read the diff
against HEAD and compare hashes, whatever the message claims was fixed. And because "compare the
hashes by hand after every sweep" is exactly the discipline that fails at hour eleven,
`mutation_sweep.py` now captures every touched file's digest *before* its loop and reports
`DRIFT <file>: <before> -> <after>`, exiting non-zero - a statement about the **tree**, which the
per-mutation comparison cannot make, since that one only ever ran earlier. `final_drift` is a plain
function with its own test and its own mutation.

**Consequence for the mass run, decided here:** it runs in a **git worktree pinned to one commit**,
not in the working tree. Its digest guard hashes `phase3/*.py` per batch and stops the run when they
change, so a plugin writing into the working tree would kill a multi-day run that is otherwise
resumable and correct. Outside the working tree, no formatter can reach it.

## Piece 6a: the reviewer, and what its own tests found (2026-09-21)

The discover batch is deliberately **finder-only**, and that makes the finder's precision the
pipeline's precision. Nothing inside that batch can tell a wrong finding from a right one: the same
question, asked twice, would answer itself. What a second pass can add is a **different question**
about the same evidence, and that is what the reviewer asks - not "is this value wrong", but "can
this finding be refuted". The pilot answered it 61 % of the time with a refutation, which is the
reason the pass is worth its calls at all.

The module carries four decisions worth naming, because each one is a way the pass could quietly
become useless:

* **Only a complete `WRONG` finding that proposes a change is reviewed.** A finding that says
  `CORRECT` proposes nothing, and there is nothing to refute. Those fields are written into the same
  report as `unreviewable` **with the finder's own reason**, never silently skipped - "nothing to
  review" and "not reviewed yet" must not look alike in a receipt.
* **`UNRESOLVED` is a third state.** `if refuted:` would fold a recorded "I could not settle this"
  into "not refuted", and the writer applies only `refuted is False`. The identity comparisons
  (`is True` / `is False`) are load-bearing here for the same reason they are in `model_stage.py`.
* **The citation check is the finder's own code.** `discover_stage.source_problems` now delegates to
  a new `claim_problems(sources, pages)`, and the reviewer calls that. An invented citation is the
  same defect in both roles; two spellings of the check would have been two chances to drift apart.
* **A refutation must cite a page this run fetched.** The reviewer's sources are checked against the
  same excerpt set the finder saw, so "the page says otherwise" cannot be a claim about a page
  nobody opened.

**Its own tests caught two real defects of mine before anything else could.** The first was dead
code: an edit of mine nested the `if refuted is not True and sources:` check *inside* the
`if refuted is True and not sources:` block, so the "a source on a non-refutation is a problem" rule
could never fire. The second was the fixture's own honesty: it cited
`https://en.wikipedia.org/wiki/Cave`, a pretty URL the run never fetches - the honest citations are
the API URLs the fetch bought. The fixture now derives its URL from `F.targets_for_site(site)`, so
the test cannot cite a page the pipeline never opened. A test that invents its own evidence would
have passed against a reviewer that invented its own citations.

**The routing: a refusal became a condition.** `run._judge_discover` used to refuse
`--stage reviewer` outright. It now allows it **when the batch carries the finding the reviewer is
about**, and `_has_answers` asks about the *answers*, not about the directory: a killed run leaves an
empty `answers/` behind, and a reviewer that trusted the directory would buy nothing and write a
report of five empty verdicts - a receipt that says a review happened. The refusal message names the
directory that is empty and the pass to run first, because "not allowed" leaves the caller guessing.

**One refusal is unreachable, and that is now stated rather than mutated.** `--stage` is declared
with `choices=[s.value for s in Stage]` and `Stage` has exactly two members, so `args.stage !=
Stage.FINDER.value` cannot be reached from `R.main` once the reviewer branch returns. The mutation
that used to disable it was therefore replaced by three reachable ones (no answers, an empty answers
folder, an unrouted reviewer stage), and the `--stage` help text - which still claimed the pass was
"finder-only" - was corrected. A mutation no test can catch is noise, not evidence.

**A mutation that would have been caught for the wrong reason, found before the sweep ran.** A
partial `edit` of mine left `REVIEWER` assigned **twice**: the new line at the top of the constants,
and the old line 12 lines below it. The later assignment wins in Python, so the mutation carried the
name of the test I had just deleted - pytest would have collected nothing, exited with a collection
error, and the sweep would have counted that as "caught". The pre-sweep check (each anchor must occur
exactly once, each named test must exist, no mutation may be a no-op) found it. That check itself
first printed `Mutationen: 0 | Probleme: 0`, because it walked `ast.Assign` while the list is
annotated (`MUTATIONS: list[...] = [...]`, an `AnnAssign`). **An empty loop is not a clean result**;
the check now asserts a floor on the number of mutations it read.

## The ledger lost lines silently, and an append is not an append (2026-09-21)

The relaunched mass run stopped after `batch-0017: done`, with `DRIVER_EXIT=1` and
`LedgerDamage: LEDGER.jsonl:2735: a ledger line inside the file does not parse`. The line was 99
bytes long and read `?action=wbgetentities&ids=Q12339802&props=claims%7Clabels%7Cdescriptions&
languages=en&format=json"}` - the **tail** of a fetch line whose head was gone. Its neighbours give
the arithmetic: a 438-byte model-call line sits where the head should be, a 537-byte fetch line is
the shape of the damaged one, and **537 - 438 = 99**, the fragment's exact length. That is not a torn
write, which loses its tail; it is a **clobber**: two writers computed the same end-of-file position,
the shorter write landed on the longer one's head, and the leftover tail stayed behind as a line of
its own.

**The instrument, before any repair.** Four processes appending 250 lines each through the real
`Ledger.append`: **880 lines in the file, 0 unparsable, 0 duplicates** - the missing 120 are not
damaged, they are gone, because the line that overwrote them is a valid line. Repeated: 888 of 1000.
Control with one process: 250 of 250. The raw route is no better: `os.open(...,
O_APPEND|O_CREAT|O_WRONLY)` plus `os.write` lost **257** of 1000. So `_O_APPEND` on this platform is
emulated as seek-to-end-then-write, not as an atomic append, and `os.fsync` flushes - it does not
serialise.

**Why the guard could not see it.** `Spend.from_ledger` parses every line, so it catches a *damaged*
line - and it caught exactly one. The silently lost lines were never damaged; there was nothing to
catch. The ledger's own numbers were simply low, and the driver's budget check reads the ledger.

**What it cost this run, measured rather than feared.** Not the 12 % the tight-loop probe suggests:
the run's window in the ledger holds **1429** model-call lines and the twenty batches' `model.json`
report **1430** calls (the one in flight when the driver died), with no label appearing twice. Model
calls are seconds apart, so writers rarely collide; the probe writes back to back. The damage was not
the count but the **parse**: one clobbered line was enough to stop a 46-hour run.

**The fix, validated before it was written.** The same four processes behind an OS byte-range lock
(`msvcrt.locking` with a retry, `fcntl.flock` on POSIX): **1000 of 1000, nothing lost, nothing
unparsable**, 2.2 s against 1.1 s. A region lock and not a create-exclusive lock file: the first
attempt of this probe died with `PermissionError` on Windows while another process was removing the
lock - a lock whose identity can be taken away is not a lock. The OS frees a region lock when the
holder dies, so a killed batch cannot leave one behind.

**The damaged line is quarantined, not deleted.** Its bytes and its two neighbours on either side are
in `output/remediation/logs/ledger_damage_2026-09-21.txt`; the line was then removed from the ledger
and the file parses again (2938 lines, 0 unreadable). Deleting a record whose meaning is
unrecoverable is how an audit trail turns into a story.

### The fix, and what its own receipts show (2026-09-21)

`Ledger.append` now holds an operating-system region lock around the write: `msvcrt.locking` with a
sleep between attempts on Windows, `fcntl.flock` on POSIX, released by the OS when the writer dies.

**The platform narrowing came from mypy, not from a hunch.** The first version tested `os.name ==
"nt"`, and `mypy scripts/remediation/phase3/ledger.py` printed three errors - `Module has no attribute
"flock" / "LOCK_EX" / "LOCK_UN"` at line 319. The finding is correct and the cause is visible in the
stub: typeshed's `fcntl.pyi` declares `flock` and those constants **inside `if sys.platform !=
"win32"`**, so on Windows my POSIX branch is dead code a checker can only see through if the code
narrows on `sys.platform`. Rewriting the guard as `if sys.platform == "win32"` cleared all three
errors (mypy: no output) with no `# type: ignore`. The branch stays, because the run this protects may
move to the VPS, which is Linux.

**The delivered code, measured by the probe and not by a model of it.** The same four-process probe
that lost 120 of 1000 entries before now reports **0 lost, 0 unparsable, 1000 of 1000** - it runs the
real `Ledger.append`, so this is a statement about the shipped writer.

**The test has teeth, and they were proven before the sweep saw them.**
`test_a_second_writer_never_costs_a_ledger_line` starts four processes that append 150 entries each
through `Ledger.append` and asserts 600 lines, all distinct. With the lock: `1 passed in 1.63s`. With
the lock replaced by `if True:` - the same mutation now in the inventory: `assert 543 == 600`, 57
entries lost, tree restored byte-identically (sha256 unchanged). Writing the test found a guard of the
project's own first: `LedgerError: 0-0000: a model call needs the model it called`, so the child builds
a complete model call rather than the guard being relaxed.

**The instruments were fixed too, because both had lied.** The anchor checker - which had only ever run
inline - is now a file, and it no longer walks the AST: `MUTATIONS: list[...] = [...]` holds **names**
like `REVIEW_TEST`, so `ast.literal_eval` raises and my first version had reported `Mutationen: 0 |
Probleme: 0` for a list it never read. It imports the sweep and reads the list the sweep will read: `70
| 0`.

**Two of my own instruments were wrong on the way, in the same direction.** The first check for the
repair compared `len(raw)` with `sum(len(line) + 1)`, which is off by one for every file that ends
with a newline - it refused a file that was fine. And the first damage count compared the **cumulative
ledger of the whole session** against the reports of **one run's twenty batches**, which is why it
reported "-499 model calls missing": a cumulative file is not a per-run report, and a number that
large should have sent me to the instrument before the code.

## The bytes that were verified, and the bytes that were committed (2026-09-21)

The commit `d899af3` landed and the run's worktree was moved onto it, and then the question that
belongs after every commit came up: *does the run execute the bytes that were tested?* It did not, in
a way `git status` cannot show.

`git status` in both trees called the phase3 sources clean - and it called them clean *after* two of
them had been rewritten from CRLF to LF. Measured on `discover_stage.py`:

| quantity | value |
| --- | --- |
| `git rev-parse d899af3:scripts/remediation/phase3/discover_stage.py` | `6f66d0ad...` |
| `git ls-files -s` (index blob) | `6f66d0ad...` |
| `git hash-object --path=... <file>` (worktree, filters applied) | `6f66d0ad...` |
| `git hash-object --no-filters <file>` | `6f66d0ad...` |
| `git diff --numstat` | empty |

So the file *was* the commit, and the ` M` in `git status --short` was a stat-cache artefact. That is
the uncomfortable half: the same command that said "clean" a minute earlier had told me nothing.
**`git status` is not a hash check**, in either direction - an earlier lesson was a `checkout` writing
CRLF where the blob had LF while status said unmodified; this one is status saying modified while every
hash agrees.

The real finding was elsewhere. The main tree's working copies of `discover_stage.py` (716 lines) and
`snapshot_plan.py` (331 lines) carried CRLF, because a tool had rewritten them, while the committed
blobs are LF throughout. Gate `b75f86946` therefore tested bytes that the commit does not contain - and
for `discover_stage.py` that includes the multi-line `QUESTION_TEMPLATE`, whose literal line endings
differ between the two variants. The semantics survived (2382 passed either way), but "the gate tested
the tree that gets committed" was, for those two files, a claim I had not earned. Both were normalised
to LF, the anchor checker and the affected suites re-run, and the gate was run again on exactly the
committed bytes: `output/remediation/logs/gate_on_committed_bytes.txt`.

The run executes the **worktree**, so its bytes were checked the same way, file by file, for all eleven
phase3 modules - every `hash-object --path` equals the blob of `d899af3`. Finally, the digest the run
prints is a *within-run* guard (`mass_run.py:481` - computed at start, re-checked between batches), so
it never was a statement about an earlier run, and moving the worktree onto a new commit cannot block
the resume. That question was worth asking before the relaunch rather than after it.

## The parser demanded a marker the question never asked for (2026-09-21)

**Found by measuring the reviewer on the gold fixture before trusting it** — the step the plan asks
for, and it found a defect in the reviewer instead of a number.

The dry run planned **0 calls** for both gold6 batches, against 85 (site, field) pairs. A reviewer
that reviews nothing writes nothing, and the writer applies only findings the reviewer did not
refute: the whole remediation would have produced **zero corrections** while every gate stayed green.

The cause was a single line, and it was mine. `discover_stage.parse_answer` required a literal
`EVIDENCE:` line — `git log -S 'EVIDENCE: <a sentence' -- scripts/remediation/phase3/discover_stage.py`
is **empty**: the frozen question never asked for a marker. It asks for

> *One sentence saying what the evidence in this message gives for this field - the value it states,
> or the word `silent` if it states nothing about this field.*

and then for the verdict line. The `EVIDENCE:` requirement came in with `f042e85`, my own round-6
commit, which added the correction-and-source guards.

Measured on the real corpus, not on the fixtures:

| | answers | carry the marker | the old rule called them unusable |
| --- | --- | --- | --- |
| gold6 (round-6 contract) | 75 | **0** | all of them |
| first 20 mass-run batches | 1777 | 3 | 1774 |

**The fix reads the question instead of a marker:** the reason is the first line that is neither
empty nor a marker line (`VERDICT:`, `PROPOSED:`, `SOURCE:`), and the `EVIDENCE:` spelling is read as
the same sentence — 3 of 1777 answers wrote it that way, so it is tolerated rather than thrown away.
With it, the reviewer plans 12 + 1 calls on gold6, and on the mass corpus so far:

| | answers | `WRONG` verdicts | reviewable (no problem at all) |
| --- | --- | --- | --- |
| the new rule | 2440 | 475 | **462** |
| the old rule | 2440 | 475 | ~3 |

The 19 answers that still carry a problem carry a **real** one — 5 `WRONG` with no `SOURCE:` page, 5
with two `PROPOSED:` lines, 4 `SOURCE:` lines with no url and quote, 4 `CORRECT` verdicts carrying a
correction, 2 with no `VERDICT:` line. An instrument that flags 19 real deviations out of 2440 is
doing its job; one that flags 2437 is not an instrument.

Paid for with three tests and mutation 71: `test_the_reason_is_the_sentence_the_question_asks_for`
uses the gold run's own answer shape and asserts `problems == ()`,
`test_an_answer_without_a_reason_sentence_is_a_problem` is the one that fails when the reason is
taken from the verdict line, and `test_an_evidence_marker_is_read_as_the_same_sentence` pins the
tolerated spelling. The fixtures that wrote `EVIDENCE:` were rewritten to the shape the question
actually produces — a fixture is a statement about the code, and this one was stating the wrong
thing.

**The lesson is not "the marker was wrong".** It is that a parser is a *second* statement of the
question, written by hand, and when the two drift the parser wins silently: the question keeps being
asked, the answers keep being bought and paid for, and the parser discards them one by one while
every count, every ledger line and every gate still reports success.

## The reviewer forbade nothing, because it was never asked in a shape we could read (2026-09-21)

**The second zero-write defect of the same afternoon, found the same way — by measuring the stage
instead of trusting it.**

The measurement was the small one the plan asks for before a stage is used at scale: 17 blinded
truth sites, their findings handed to the reviewer, the verdicts scored against the gold standard.
What came back:

| | |
| --- | --- |
| findings the reviewer was asked about | 13 |
| `refuted` | **0** |
| `unresolved` | **12** |
| `with_problems` | 12 |
| `applies` | **0** |

Every one of the twelve answers ended with a line like

```
**VERDICT: none refuted** — the finding overstates a wording preference as a contradiction.
```

and `"REFUTED" in text` was **false** for all of them. The model had done the work — that answer
reasons its way to exactly the right conclusion, that the finder's claim of a contradiction is not
made out — and then wrote its verdict in a shape of its own invention.

**The cause was the question, and it is the exact mirror of the finder's defect reported above.**
`REVIEWER_QUESTION` (`model_stage.py`) asked the question in prose:

> *Can the finder's finding for this site be refuted against the evidence in this message? Name the
> single claim that fails, or say that none did. Try to break every finding.*

It never named an answer shape. The parser (`review_stage.parse_review`) demands exactly one line
matching `^\s*REFUTED:\s*(YES|NO|UNRESOLVED)\s*$` plus a `WHY:` sentence — and no answer ever carried
one. The frozen finder question, by contrast, spells its shape out line by line.

**The two directions are not symmetric, and the asymmetry is the point.** For the finder, the
question was frozen at round 5 after seven measured rounds and the parser was mine and wrong, so the
parser was fixed. For the reviewer, the parser is right and the question was wrong: the plan applies
**only** `refuted = false`, so an unreadable verdict must never be read as "not refuted". That is
what `review_stage.py` says in as many words — *"unreadable" and "not refuted" must not be the same
value* — and it is why the failure mode was UNRESOLVED rather than a write. A pipeline that silently
treated a malformed verdict as permission would have been worse.

**The consequence, had it shipped:** every finding read as unresolved, `applies` false everywhere,
the writer applying nothing — and every gate, every ledger line and every count still green. That is
twice in one afternoon that the pipeline's output was zero and only a measurement said so. The first
was the finder's discarded answers, the second the reviewer's discarded verdicts; both were format
drift between a question and the parser that reads it.

**The fix** writes the shape into the question the way the finder's question learned to: the three
values named with what each one means, `YES` as the only verdict that carries a citation, `WHY:` as
the sentence that names the claim, the reason-sentence-before-the-verdict order that the finder's
first live run had to learn the hard way, and one rule the reviewer needs in mirror image of the
finder's — **own knowledge may not refute a finding.** A refutation removes a correction from the
write path, so a reviewer that refutes from memory rather than from a page this run fetched throws
away corrections the evidence supports.

**Paid for with two tests and two mutations (72, 73):**

* `test_the_reviewer_question_asks_for_the_verdict_line_the_parser_wants` builds the shape from
  `REFUTED_VALUES` itself, so the question and the parser cannot drift apart without one of them
  failing here;
* `test_the_reviewer_question_forbids_refuting_from_the_referees_own_knowledge` pins the clause that
  keeps a refutation on the evidence.

**The lesson, and it is the general one:** a parser is a *second* statement of its question, written
by hand in another file, and the two only stay in step if something tests them **against each other**.
A literal in the question and a literal in the parser agree today and are two independent things;
the assertion above derives the one from the other's vocabulary. Where a question and its parser are
literally two literals, the honest form is one test that ties them — otherwise the next drift is
found the same way this one was, by noticing that a stage which spent real money produced nothing.

## The reviewer measured, and the leniency cost less than the arithmetic said (2026-09-21)

The reviewer had to be measured before the writer exists, because the plan's Phase 3 rule makes it
the last gate before a database write: **only `refuted = false` is applied**. If the reviewer is
lenient, a doubtful correction gets written; if it is harsh, a real correction is thrown away. Both
numbers are needed, and the first pass over them was wrong in two ways - one in the instrument, one
in my reading of it.

### What the number was, and the instrument defect behind it

`output/remediation/gold_standard/measure_reviewer.py <run-dir>`, against the 17 blinded truth sites
of `runs/gold6`:

| | first pass | after fixing the instrument |
|---|---|---|
| blinded truth errors (field level) | 39 | **43** |
| of those, the finder proposed a correction | 6 | **7** |
| - left standing (would be written) | 4 | **5** |
| - thrown away by the reviewer | 1 | 1 |
| - left undecided (`UNRESOLVED`) | 1 | 1 |
| reviewed on a field the blinded check called **correct** | 6 | 6 |
| - the reviewer rejected the finding | 2 | 2 |
| - the reviewer let it through | 4 | 4 |
| counted as `unexamined` | 1 | **0** |

The defect was in `truth()`: the blinded check writes **compound field labels** when one error sits
in two fields at once (`"period_start + description"`, `"hero_image + gallery_images"`) and one label
that is not a field at all (`"source coverage"`). Keying on the raw string silently lost the first
and invented a phantom key for the second. Measured consequence: **7 of the 24 missed errors in
`truth_fields.json` looked absent from `errors_found`**, and **three real error fields**
(`590d3dff/description`, `9ed175c7/card_description`, `b6af84c5/description`) were counted as
`unexamined` - i.e. the instrument was quietly discarding exactly the truth it was measuring against.
Splitting the label on `+` reconstructs all 24.

**The 43 and the FNR's 40 are different denominators, not a disagreement.** `fnr_result.json`'s
`blinded_errors: 40` is `16 caught + the 24 the census missed` - errors scoped to what the census
could be scored against. `43` is every field the blinded check named as an error, including the ones
the census did catch, with compound labels split into their two fields. Neither number belongs in the
other's place.

### The semantics are not inverted - and I thought they were, twice, from truncated text

The dangerous hypothesis was that the reviewer's `YES`/`NO` might be inverted, which with
`applies = refuted is False` would have written exactly the refuted findings. The evidence says no:
**in 10 of the 13 reviewed findings the `WHY:` sentence and the `REFUTED:` value agree** - where the
reason says the finder's claim *fails* it wrote `YES` (`a5d9e9a7 card_description`, `e7ee7c00
description`), and where the reason says the finding *survives* it wrote `NO`. Two cases are
ambiguous in their wording, and **one case (`9ed175c7 site_type`) carries no `REFUTED:` line at all**
- its `WHY:` says the evidence "corroborates" the finding, i.e. the verdict should have been `NO`,
and the parser read the absence as `UNRESOLVED`. That is a format slip in the safe direction: no
write follows from it.

**The mistake was mine and it was made twice in this one measurement.** I read a 200-character
excerpt of each `WHY:` sentence, concluded two verdicts contradicted their reasons, and nearly
recorded a "possibly inverted semantics" defect. The full sentences say something else. This is the
third time in this session that a truncated read produced a false conclusion - after the mutation
names truncated to 52 characters and the appended log treated as evidence about the latest attempt.
**An excerpt is a different artefact from the artefact.** Print the whole line before judging the
line.

### The four writes the arithmetic called unjustified, and what they actually are

The instrument's own label was wrong - it printed `refuted (false positive)` for the case where the
reviewer **rejects** a finding on a correct field, which is the reviewer doing its job. Corrected. The
expensive direction is the other one, and there are four specimens. All four, stored value against
proposed value, read by hand:

| field | stored | proposed |
|---|---|---|
| `0529af31 card_description` | "associated with the **Celtic** Vettones people" | "associated with the territory of the **pre-Roman peoples known as the Vettones**" |
| `32429f3c card_description` | "**Legend says** the owner chose the design after winning the fortune in a card game" | "**It has been suggested** ... **but this is unlikely**" |
| `590d3dff card_description` | "A 1960 tsunami **swept them all inland** before restoration re-erected them" | "**toppled in civil wars** before the 1960 tsunami **swept the ahu inland**" |
| `e7ee7c00 card_description` | "a shrine to Ceres and Venus" | "a **sacellum** of Ceres, Venus **and Proserpina**" |

**Not one of them is a corruption.** Each is closer to the cited page than the stored text: the third
corrects a causal claim (the tsunami swept the ahu inland after civil wars had toppled the moai, as
the reviewer itself argued), the second replaces an unsourced legend with the page's own hedge, the
fourth adds a deity the page names in a later section. So the honest reading of the number is:

* **Sensitivity 5/7**: of the blinded errors the finder proposed a correction for, five survive the
  reviewer. One real repair is thrown away and one is left undecided.
* The four "upheld on a correct field" findings are **unjustified rather than wrong** - and the
  blinded check's `CORRECT` verdict means "this value is not false", not "this value may not be
  touched". That softens the denominator, and it is written down here rather than left to be
  discovered by whoever reads the number next.

Both readings are at n=7 and n=6. At n=19 this project already had to treat a 5-8 spread as noise;
these rates are preliminary and the sample cannot settle the reviewer's quality either way.

---

## The reviewer's referent, five measurements, and the plan's own briefing (2026-09-21)

The reviewer is the only write gate Phase 3 has: `applies = asked and refuted is False and not
problems`, and the plan says plainly that "Only `refuted = false` is applied". So the question the
reviewer is asked is not prompt polish - it decides what reaches the database. It had never been
measured before this session, and measuring it five times found a logical defect, not a rate
problem.

### The defect was the referent, not the rubric

The question said "name the claim it rests on" without saying what "it" was. The finder complains
about the stored value in *every* finding it issues, so the reading "the stored value" makes every
finding refutable; the reading "the proposal" makes almost none. The model resolved the ambiguity
per call, and hand-reading all thirteen findings of the blinded truth set shows it resolving it both
ways in adjacent calls.

Five rounds, thirteen live calls each, same evidence, same model (`deepseek-v4.1-flash`,
`--thinking off`), only the question changed:

| round | question | refuted | real repairs kept | suspect findings rejected |
|---|---|---|---|---|
| A | evidence only, own knowledge forbidden | 3 | 5 / 7 | 2 / 6 |
| B | own knowledge allowed, referent ambiguous | 8 | 2 / 7 | 4 / 6 |
| C | referent pinned to the proposal alone | 1 | 7 / 7 | 1 / 3 |
| D | both halves + the plan's 4.3 briefing | 6 | 3 / 7 | 2 / 4 |
| E | D + parser tolerance + unnumbered answer | 5 | 3 / 7 | 2 / 6 |

Round B's count looked best and was the worst answer: of its thirteen `WHY:` sentences, **three name
evidence that supports the finder's correction while the verdict kills it, and one names evidence
that defeats the correction while the verdict keeps it**. No rate exposes that; only reading the
sentences does. Round C fixed the direction and destroyed the instrument - one refutation in
thirteen means the only write gate in Phase 3 waves everything through.

### The plan named the missing ingredient, and I had not implemented it

Phase 3, verbatim: stage 2 "attempts to refute every error claim using **its own** research - not by
re-reading stage 1's evidence. **Must be briefed on the false-alarm patterns in 4.3.**" Section 4.3
lists eleven patterns "correctly refuted" in the pilot, and they are exactly the shapes in which a
value looks wrong without being wrong. The question carried none of them until round D.

They are now data, not prose: `MS.FALSE_ALARMS` with a parallel `MS.FALSE_ALARM_SOURCES` naming the
plan item each line paraphrases, and a test that reads the plan file and asserts the two lists cover
the same items. The numbers are deliberately *not* in the prompt - the model has never read the
plan, and a citation index in an instruction is noise.

The effect is visible in the specimen: both truth-set errors the reviewer refuted in D and E are
refuted **with the pattern, named**, e.g. `758dd394%2Fsite_type` - "Wikidata's P31 is the generic
'monument' (Q188040), while 'Timber circle' is a plausible finer type not contradicted here, so the
first half fails and the proposed 'Monument' is merely less specific" (4.3.5, *never downgrade
specificity*). The plan asks the reviewer to be conservative in exactly this way.

Also decided, on the plan's own text rather than on a rate: **own knowledge may refute, never
uphold.** The plan's stage 2 refutes "using its own research", and `refuted = false` is the only
write gate - so a rule that forbade refuting from knowledge would have disabled the stage the plan
describes. The `SOURCE:`-on-`YES` requirement was dropped with it: a refuter with no fetch step
cannot cite a page it never fetched.

### A parser is a second statement of the question

Two of thirteen answers in round D came back with `problems`, and neither was a model error:

```
a5d9e9a7%2Fcard_description:   "1. The first half fails: ... 2. REFUTED: YES"
                               -> 0 `REFUTED:` line(s); a `SOURCE:` page belongs to `REFUTED: YES`
b6af84c5%2Fcard_description:   "REFUTED: YES" ... "REFUTED: YES"
                               -> 2 `REFUTED:` line(s)
```

The question numbered its answer steps ("1. One sentence ... 2. Then the verdict line.") and the
model mirrored the numbering into the verdict line. `REFUTED_RE` anchored on `^\s*REFUTED:`, so a
literal `2. ` before it read as **no verdict at all** - a grounded refutation silently downgraded to
`UNRESOLVED`, and its source line then tripped the wrong-verdict check. Both problems, one cause,
and the cause was mine. The pattern now accepts an optional list marker; the guards are untouched
(exactly one hit, value from `REFUTED_VALUES`). The question no longer numbers its answer steps and
says to write nothing after the verdict line. Measured after the fix: both cases are `problems == ()`
and one of them is `applies=True`, i.e. a repair that had been silently dropped is written again.

### Measured, and honest: the reviewer is not deterministic here

`a5d9e9a7%2Fcard_description` and `b6af84c5%2Fcard_description` received **opposite verdicts in
rounds D and E on identical input** - same question, same evidence, same model, `--thinking off`.
Two of thirteen. This bounds what any single run can be claimed to show, and it is the reason the
decisions above rest on mechanisms (referent, false-alarm patterns, parser shape) rather than on
round-to-round counts.

### The residual, named

Three of seven real repairs kept; three real errors refuted, each with an explicit 4.3-based
justification; one honestly `UNRESOLVED`. The error is in the **conservative** direction - the
reviewer under-corrects rather than corrupting - which is what a gate whose only action is
`refuted = false` is for.

### Three instrument bugs of mine, caught by their own receipts

* `sorted()` on strings is lexicographic, so a complete 4.3 coverage printed as incomplete:
  `['1','10','11','2',...] != ['1','2',...,'11']`. The data was whole; the check was not.
* `p.count("4.3.1")` also matches inside `4.3.10` and `4.3.11`, so my duplicate check reported
  duplicates that do not exist.
* An `edit` whose `oldText` appended a `\n` the closing paragraph does not have - the third
  occurrence of this session's recurring form, *a truncated or remembered read is a different
  artefact from the artefact*. The tool's "content-drift" message was right about the mismatch and
  wrong about the cause: nothing else had written the file.

And one real defect in my own change, caught by `mypy` before any test ran: a `+` ended the implicit
string concatenation and a trailing comma turned `REVIEWER_QUESTION` into a 2-tuple
(`Dict entry 1 has incompatible type "Stage": "tuple[str, str]"`). The constant is a `str`; the
check is `isinstance(q, str)` plus `mypy` on the module.

## The pre-push gate does not test the phase-3 sources, and five more holes (2026-09-21)

Measured against the tree at `7ad305d`, 81 commits ahead of `origin/main`, unpushed. Six things, each
with the command that shows it. They are recorded as **open**, because they are.

**1. The gate the push actually runs does not exercise `scripts/remediation/phase3/`.**
`.githooks/pre-push` names, in its own gates, only the paths the project's CI names:

```
$ grep -n "phase3\|scripts/remediation" .githooks/pre-push
(no output)
$ grep -n "git diff --name-only" .githooks/pre-push
109:    echo "pre-push: tracked files that were pushed: $(git diff --name-only "$MAIN_LOCAL_SHA" -- . | wc -l)" >&2
```
No per-test or per-path section exists (`grep -cE '^AKTUELLER_TEST=' .githooks/pre-push` → 0). So a push
today would run the DB-less pytest subset — which *does* import and exercise `phase3` through
`tests/remediation/` — but **no** phase-3-specific check is a gate in its own right. The evidence that
this matters: `f72141e` fixed a parser that demanded a marker the frozen question never asked for, and
`7ad305d` fixed the reviewer's referent; both were found by reading the artefacts, not by the gate.

**2. `run.py` has no `report` subcommand, so the mass run's outcome is only in `LEDGER.jsonl` and the
log.** `grep -n '"report"' scripts/remediation/phase3/run.py` → no match. A resume, an abort, and a
completion therefore look alike from outside except for the driver's own lines. `mass_run.py` writes a
progress file, but nothing turns the ledger into the run's result.

**3. The reviewer has never run against the mass run.** `ls output/remediation/phase3_runner/runs/mass/batch-0001/reviews/`
→ *No such file or directory*. The 13-call measurement on `gold6` established that the question is
answerable (`reviewer_result_gold6.json`: 13 reviewed, 5 refuted, 1 unresolved, 2 refuted on
blinded-correct fields, 3 real errors left standing) — but no verdict exists for any of the 138 finished
batches. `refuted is False` is the only key to the writer, so the writer currently has nothing to open.

**4. `pacing_scope` does not exist in the code.** `grep -rn "pacing_scope\|pacing-scope" scripts/ tests/`
→ no match. `run.py:396` constructs `PacedFetcher(http, HostPacer(args.pacing_dir))` whenever
`--pacing-dir` is given, so `--jobs N` batches pace *each other* on the same host. Measured from the
ledger: the last 1,200 fetches are **620 `en.wikipedia.org` + 580 `www.wikidata.org`, exactly two hosts**.
A design that wanted to raise concurrency without raising the per-host rate has no switch for it.

**5. The mutation sweep is the instrument every guard is measured with, and it has never been run on
the mass run's own corpus.** All 77 mutations run the unit tests in `tests/remediation/`. They have
never been pointed at the 138 finished batches' answers or at a real reviewer verdict. That is the same
gap class as the reviewer measurement: a guard proven against fixtures, unproven against the artefacts.

**6. `bash output/remediation/logs/mass_run.sh` can report `exit=0` while the driver died.** Measured
twice in this session (`DRIVER_EXIT=1` inside the log, `exit=0` from the wrapper). The exit code of a
pipeline is the last command's, and the script ends on a `date`. The fix is one line (capture
`DRIVER_EXIT` and `exit "$DRIVER_EXIT"`), and it is not made, because the run is live and the script is
its launcher.

**Not a finding, verified so it stops being re-litigated:** the four lint classes reported on every
edit are false positives, re-checked at the byte today — `list_other_flags.py:52` and
`race_probe2.py:25` are readers of the run's **own** artefacts, where raising *is* the check (a
`try/except` would turn a loud abort into an empty answer, which `CLAUDE.md` forbids);
`child_append.py:62` reads `with open(lock_path, "r+b") as handle:` — the checker quotes the source's own
quotation marks as part of the mode string; `measure_reviewer.py:110/113` use `is True` on JSON tri-state
values, where `== True` would also accept `1`. `ruff` is clean on all of them.

## The fetcher never read `Retry-After`, and the ledger is why the fix looks like that (2026-09-21)

**The finding.** `git grep -n "Retry-After\|retry_after" -- scripts/remediation/phase3/` returned **no
hits**, and `FetchedPage` carried only `status, final_url, body, truncated` - the response headers were
never read at all. So on a 429 a host saying *wait 30 s* was re-asked after this module's own 0.2 s
pacer interval and its own `RETRY_BACKOFF_SECONDS = (1.0, 3.0)`. That is precisely the impoliteness
the pacer exists to prevent: our clock deciding, against the provider's own instruction.

**What was verified before the comment was written.** RFC 9110 section 10.2.3 was fetched from
`rfc-editor.org` and the comment cites only what that text contains:
`Retry-After = HTTP-date / delay-seconds`, `delay-seconds = 1*DIGIT`, the 503 sentence and the 3xx
sentence. No "MUST ignore an invalid value" claim is made, because the fetched text does not contain
one.

**The design, and where the ledger forced it.** The first version carried the refusal reason on the
**ledger line's** `error` (`error=attempt.error or refusal`). That is a real defect, not a style
choice: `L.Entry._check_fetch_attempt` (`ledger.py:214-218`) **raises**
`LedgerError("... a response that arrived is recorded by its status, not by an error string")` for any
answered attempt that carries an `error`. A 429 **is** an answered attempt, so the first version would
have thrown on the exact path it was written for.

So the reason lives on `TargetOutcome.given_up_reason` instead - a field of our own, next to
`not_attempted`, which already exists for the neighbouring sentence ("never asked" versus "asked and
failed"). `failure` reads it back (`elif self.given_up_reason:`), which is the sentence the judge stage
consumes when it decides whether a missing evidence file is an explained failure or a hole in the
record. The ledger line keeps saying what it is: a status, and `given_up`.

**Three consequences worth stating, because each is a decision and not an accident:**

1. **The host's number outranks ours** (`if asked is not None and asked > wait: wait = asked`), and
   **our backoff is a floor the host cannot lower** - `Retry-After: 0` does not shorten the 1 s/3 s we
   already chose. Both are asserted.
2. **A host asking for longer than we will block on one host is not disobeyed.**
   `RETRY_AFTER_CAP_SECONDS = 60.0`, the same bound as `HOST_LOCK_WAIT_SECONDS`: the target is given up
   on **with the asked-for delay named**, not re-asked sooner. Waiting less and asking again would be
   the very thing this fix exists to stop.
3. **A value that is not in the RFC's grammar is treated as absent, not as zero**
   (`delay-seconds = 1*DIGIT` -> `text.isascii() and text.isdigit()` first, because Python's
   `str.isdigit()` is also true for `"\u0663"` and `"\uff11"`; `"7.5"` is absent too).

**The five `STOP` claims pi-lens raised on the new code are false positives, each checked at the byte.**

The rule this project already paid for holds: a checker gives a trace, not truth, and adjudicating is
not the same as silencing. None of these was "fixed" by adding a `try/except` or an ignore - several of
them are load-bearing guards that a `try/except` would destroy.

| claim | the byte it points at | verdict |
|---|---|---|
| `L292` `return float(text)` "throws on invalid input" | `if text.isascii() and text.isdigit():` on the line above | **false** - measured: `float()` on a non-empty ASCII-digit string raises for no input, including `"9"*400` -> `inf` and `"0"*10**6` -> `0.0` |
| `L785` `return float(value[0]), float(value[1])` | `all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)` on the line above | **false** - `float()` of an `int`/`float` cannot fail; same class as the already-adjudicated `model_stage.py` `float(reported)` site |
| `L1432` `result.truncated += int(outcome.truncated)` | `truncated` is a dataclass field set from `page.truncated`, a `bool` | **false** - measured: `int(True) -> 1`, `int(False) -> 0`, no exception |
| `L516` `except FileExistsError:` "boolean expressions should not be used in except" | `handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` above it | **false** - `FileExistsError` is an exception class (`issubclass(FileExistsError, OSError)` is `True`), not a boolean expression; this is the canonical way to catch "the lock file already exists" |
| (repeat) the four long-standing classes | `list_other_flags.py:52`, `race_probe2.py:25`, `child_append.py:62`, `measure_reviewer.py:110/113` | **false, re-checked at the byte today** - raising *is* the check in the first two; `"r+b"` in the third is a valid mode (the checker quotes the source's own quotation marks); the fourth is the tri-state test where `None` must not count as applied |

**One of those was re-checked with a measurement, not with an assertion.** pi-lens repeated
`child_append.py:62: open() called with invalid mode '"r+b"'` and offered a suggested "safer, explicit
form" as the fix. Read at the byte, the line is `with open(lock_path, "r+b") as handle:` - the mode is
the three-character string `r+b`, and the checker read the source's own quotation marks as part of the
literal. The distinction is measurable, so it was measured: `open(p, 'r+b')` opens;
`open(p, '"r+b"')` raises `ValueError: invalid mode: '"r+b"'`. The checker's *reading* would make the
probe broken, and the probe is not broken. The finding was already stale (`Historical finding;
workspace changed since capture`), and the file is a throwaway probe under the gitignored
`logs/ledger_probe/`. Applying the suggested "fix" would have been a change made to quiet a display on
code that is correct - which is the one thing this project does not do.

`ruff check scripts/remediation/phase3/fetch_stage.py` -> `All checks passed!`, exit 0;
`mypy` -> `Success: no issues found in 1 source file`; `tests/remediation/test_phase3_fetch.py` ->
**44 passed**. The `Retry-After` guards are mutation-proven (8 entries, 77 -> 85).

### Provenance note, because the working tree moved under the summary

`HEAD` (`7ad305d`) has `error=attempt.error,` at `fetch_stage.py:1215` and a two-branch `failure`;
the working tree has `given_up_reason`. So that improvement is **uncommitted and newer than `HEAD`**,
while the handover summary describes the ledger line as `error=attempt.error or refusal`. **The summary
is a lossy artefact and it is wrong on this detail; the bytes are not.** Checked at the time: no
subagent fleet active (`subagent({action:"status",view:"fleet"})` -> "No active subagent fleet"), and
only one session log for this project had been written recently. Recorded here instead of quietly
repaired, because "the file is not what the handover says" is exactly the class of fact this log
exists for. The content is **not** accepted on trust: `anchor_check.py` finds all 8 new mutation
anchors and all 6 new test names **in these bytes**, and the suite is green on them.

Two instruments were wrong before the number was right, both recorded because the mistake is
generic: filtering the session log on `name`/`tool_use` when the records carry `toolName` (the filter
found nothing and I nearly read that as evidence), and `run.py` sitting at `pass_name=None` in
`git diff` while **the mutation sweep held that mutant in the tree** - a live sweep is not an editor,
and `git diff` during one is not a statement about the repository.

## One empty model answer discards a whole batch - measured on the live run (2026-09-21)

**The observation.** The driver log carried five lines of the same shape:

```
batch-0100: FAILED - judge exited 2 (1 in a row)
batch-0118: FAILED - judge exited 2 (1 in a row)
batch-0124: FAILED - judge exited 2 (1 in a row)
batch-0143: FAILED - judge exited 2 (1 in a row)
batch-0146: FAILED - judge exited 2 (1 in a row)
```

`progress.json` agreed: `batches_done: 121, batches_failed: 5, batches_skipped: 20, stopped: None,
not_reached: []`. `"(1 in a row)"` every time - so the breaker (`DEFAULT_FAILURES_BEFORE_STOP = 3`)
never trips, and the run continues past all five.

**The cause, from the stage's own log** (`output/remediation/logs/mass/batch-0143.judge.log`, quoted
verbatim):

```
"error": "0294d74b-0e97-4509-913a-475e3c21e1a7/site_type stdout:9 assistant message_end:
          the assistant message carries no text - an empty answer is not a result"
```

So it is **not** a transport failure and **not** a 429. The model returned an empty assistant message for
one field of one site, `model_stage` refused it - correctly, an empty answer is not a result and must not
be silently read as "no findings" - and the refusal propagated out of `run.py judge` as **exit 2**.

**Why that costs more than one field.** The measure is the answer count per batch dir: a healthy batch
holds **75** answers (`answers/<site_id>%2F<field>.txt`), the five failed ones hold **62, 50, 33, 22
and 12**. A partially written answer set is not a partial result; it is a batch that stopped mid-way,
and the run moves to the next batch. Five batches x up to 5 sites is up to 25 sites that would be
quietly absent from the deliverable.

**The remedy is built in - verified in the code, not assumed.** `batch_state`
(`mass_run.py:255-277`) returns `done` **only** when the artefacts parse *and* `len(judgements) ==
calls`, with the comment "a truncated artefact is not evidence: the batch is redone, and a re-run is
cheap because fetch and judge both skip what is already on disk". And `run_mass` keeps
`progress.failed[batch_id] = detail` and returns 1 if anything failed. So **re-invoking the same
command is the top-up**: finished batches are skipped (`batches_skipped`), the five incomplete ones are
redone. No code change, no data loss - but it has to be done, and `batches_failed` has to reach 0 before
the run counts as finished.

**Ordered follow-up, with the reason attached:** the top-up pass also brings the `Retry-After` fix to
the batches that run in it - the live run reads the worktree pinned at `d899af3`, i.e. **before**
`8d0b7ef`, so politeness towards a 429 is not yet in force for anything already fetched.

**A measurement gap this exposed, recorded because it is the kind that makes a green number lie.**
The ledger's model rows carry `error` on **all 11,023** of them as `None`, and `outcome` also as `None` -
so the ledger does **not** record how a model call ended. "No errors in the ledger" therefore says
nothing about model calls; the failing signal lives in the stage log and in `progress.json`. Anyone
reading model health from the ledger today is reading an empty column.

**Two instruments were wrong before the numbers were right, both the same mistake.**
(a) My first count filtered the ledger on `kind == "model"` and printed an empty counter - the value is
`model_call`, and the empty result was not "zero failures", it was "matched nothing". (b) My first
session-log probe filtered on `name`/`tool_use` and found zero write calls on `fetch_stage.py`, which I
almost read as exculpatory; the records carry `toolName`, and a re-run with that field found that the
log does not record tool **inputs** at all - so it cannot answer the question either way. An empty
result is a statement about the filter, not about the world.

**The top-up recipe, with its evidence.** The run lives in the worktree at `d899af3`, which is
*before* `8d0b7ef` - so the polite `Retry-After` path is not in force for anything it fetches. Read at
the byte, the digest guard does **not** forbid resuming with newer code: `mass_run.py:578` computes
`digest = None if args.no_digest_guard else package_digest()` **fresh on every invocation**, and
`:481` compares that value against `digest_of()`, which is the same function - `run_mass`'s
`plan_digest` parameter receives exactly the fresh digest at `:629`. The check is therefore a
comparison of the live digest with itself, always equal on a fresh start, and it has teeth only
**within one process**, where it re-runs between batches and catches a source edit made while the run
is going ("the phase-3 sources changed while the run was going"). So:

1. let the current run end, or stop it - the `phase3/` bytes must not change under a live process;
2. advance the worktree to the new commit;
3. re-invoke the same command with the same plan, the same run dir and the same ledger.

Step 3 skips what `batch_state` calls `done` (`mass_run.py:255-277`) and redoes exactly the
incomplete batches: the five above, plus anything that fails later. `batches_failed` must reach 0
before the run counts as finished.

## Correction: it is TWO unusable-stream modes, not one empty answer (2026-09-21, run 2 ended)

The heading above is too narrow and the measurement corrects it. Run 2 ended on its own terms:
`DRIVER_EXIT=1`, `stopped: circuit breaker: 3 consecutive batch failures`, `batches_done: 130`,
`batches_skipped: 20`, `batches_failed: 8`, and **175 batches never reached** (`batch-0161` to
`batch-0334`); 11,866 calls, $11.375892. Eight failed batches, and the eight stage-log error strings
split **4 / 4** into two different causes:

**Mode A - the stream ended with no text** (4 of 8, verbatim):

```
<site>/<field> stdout:9 assistant message_end: the assistant message carries no text -
                       an empty answer is not a result
```

**Mode B - two billed calls in one stream** (4 of 8, verbatim):

```
<site>/<field> stdout: 2 settled assistant usages in one stream;
                       this runner will not guess which call was billed
```

Mode B is the interesting one, and the runner's refusal is correct: it must not invent a billing
attribution for a call it cannot identify. What is *not* correct is the consequence of that refusal -
the whole batch is abandoned, with 62, 50, 33, 22 and 12 of 75 answers already on disk. **The
refusal is right about the call and wrong about the blast radius.** The two batches differ only in
which numbered stdout record carried the anomaly: `stdout:9` for A, `stdout: 2` for B.

**Both modes are sporadic, not systematic.** The eight failures are eight *distinct* `(site, field)`
pairs on eight *distinct* sites - no site appears twice, and there is no field clustering (5
`site_type`, 1 `country`, 1 `description`, 1 `card_description`). This is a transport/protocol flake,
not a property of any site.

**This contradicts a decision this project already made.** "A transport failure is recorded data, not
a batch-killer" is the recorded rule for the fetch path, and `TargetOutcome.given_up_reason` (with
`not_attempted` beside it) is the machinery that implements it - a missing evidence file is an
*explained* failure, not a hole in the record. In the judge path the same class of anomaly propagates
out of `run.py judge` as **exit 2** and takes the batch with it.

**Consequence, stated plainly because it decides the rest of the work:** 8 failures in 138 attempted
batches is 5.8 %, and the breaker trips at 3 *consecutive*. With 175 batches unrun, a restart alone
cannot finish the deliverable - it will stop again at the next cluster. The transport anomaly has to
be turned into a per-field recorded failure before the remaining 175 batches can complete. That is a
change in `model_stage.py`/the judge path, which the piece-6 build holds locked; it is therefore the
first task after that build lands, and until then a restart is only partial progress. Restarting is
still worth it, and run 3 does exactly that: `batch_state` skips the 150 and redoes the 8.

**A third instrument of mine was wrong, same class as the other two.** The classifier that produced
"4 with the empty-answer wording, 4 other" used the pattern `'[^"\\]'` inside a non-raw Python
string, which Python folds to `[^"\]` - an unterminated character class, so the probe raised
`re.PatternError` rather than reporting. Printing the `"error"` values without a regex gave the four
verbatim strings above. The lesson of this section and of the two before it is one lesson: the probe
is part of the evidence, and a probe that fails loudly is worth more than one that returns something
plausible.

**The remedy, decided before it is built, with the reason it is cheap.** The anomaly is per call and
sporadic (measured above: eight distinct sites), and the expensive part of a batch - fetch and the
calls already answered - is **on disk** and reused: `batch_state`'s own comment says "a re-run is
cheap because fetch and judge both skip what is already on disk". So the batch is retried **in place**,
a bounded number of times, inside `mass_run.batch()`, instead of being abandoned to a manual top-up.
The retry re-buys only the calls that never landed - one or two of seventy-five - and a failed attempt
is still recorded as an attempt, not erased.

Why the retry rather than letting an unusable stream become a per-field finding: turning it into a
finding would put a model-call failure into the same record as a *judgement*, and a hole that looks
like a verdict is the one thing this pipeline must not produce (`model.py`'s third verdict exists
precisely to keep "cannot be settled" apart from "settled"). A retry leaves the record's meaning
alone: either the batch completes and every answer is a real answer, or it fails and says so.

What must be true for this to be honest, and is therefore part of the change: the attempt count is
recorded per batch (not just the final outcome), each attempt appears in the batch's log with its
reason, and `batches_failed` still counts a batch whose *last* attempt failed. A retry that hides a
systematic failure behind a green total would be worse than the defect.

### That remedy was wrong, and a re-run proved it (2026-09-21, run 3, ninety seconds long)

Two sentences above are corrected by the measurement that followed them, and both are left standing so
the correction is checkable: "**Both modes are sporadic, not systematic**" and "Restarting is still
worth it". Run 3 was launched as a plain restart and ended after about ninety seconds - `DRIVER_EXIT=1`
at 17:16:30, the same breaker, the *same* failures at the *same* `(site, field)` with the *same*
messages: `batch-0155` again on `355d25f2-.../site_type`, `batch-0146` again on
`7e5a3822-.../description`.

So the anomaly is sporadic **across sites** and **deterministic for a given question**. Re-asking
reproduces it. A bounded retry cannot fix these eight; it would spend its attempts arriving at what one
re-run already showed. The reasoning that made the retry look right is worth naming, because it is the
kind that reads as obviously true: "the answers are on disk and reused" is a true statement about the
**batch**, and it says nothing about the one call that never landed.

Two measurements pin it down:

* **No answer file exists** for the failing field of either batch - `runs/mass/batch-0155/answers/`
  holds 62 files and `batch-0146` holds 50, and neither contains `355d25f2-...%2Fsite_type` or
  `7e5a3822-...%2Fdescription`. The call is genuinely unanswered, not a stale bad file re-read.
* **The retry produces nothing**: eight batches attempted, three consecutive failures, breaker, stop -
  and not one new answer for any of them.

**A fourth instrument of mine was wrong, and this one was load-bearing.** My first read of run 3's spend
filtered the ledger on timestamps beginning `2026-09-21T17:1` and printed **zero calls**, which I very
nearly recorded as "the judge failed without paying for anything" - a claim that would have inverted
the diagnosis. The ledger stores `at` as **UTC with an offset** (`2026-09-21T15:16:25+00:00`), so local
17:16 is `T15:16` and the filter matched nothing. The last rows at `15:16:25`, `15:16:26` and
`15:16:29` line up second-for-second with the fresh judge logs at 17:16:25/26/29 local. An empty result
was, for the fourth time in this section, a statement about the filter.

**The remedy that follows from the measurement.** The call must be allowed to fail **as a recorded
per-field outcome** while the batch continues - the rule this project already applies on the fetch side
("a transport failure is recorded data, not a batch-killer", implemented as
`TargetOutcome.given_up_reason` beside `not_attempted`). The shape exists: `model.json`'s `judgements`
already carry a `wrote` flag, so a failed call is a judgement with `wrote: False` and its reason, and
`batch_state`'s `len(judgements) == calls` still holds, because a failed call is still a call.

The objection recorded above - that this "would put a model-call failure into the same record as a
judgement" - is answered by the field, not by the shape: the judgement is marked `wrote: False` with the
reason, which is exactly how a fetch failure is already recorded, and it is **not** a `Verdict`. Nothing
in the record then says the field was judged; it says the question could not be asked. The consequence
for the deliverable is honest and small: of roughly 2,500 questions, eight stay unanswered with the
reason named and **no value written for them** - which is the safe default, since a field nobody could
ask about must never become a field somebody guessed at.

This is a change in `model_stage.py`'s judge path, which the piece-6 build currently holds locked, so it
is the first task after that build lands. Until then, a restart of the mass run is not partial progress:
it is no progress, and it costs a minute of model calls each time.

### The module had already refused the retry, for a better reason than my measurement (same day)

Reading `model_stage.py`'s own docstring - in the worktree, i.e. the bytes the run actually used -
settles two questions this section got wrong, and both are before the raise sites rather than after
them:

> Three things this module refuses to do, because each of them is an invisible cost or an invented
> number: 1. **It never computes a cost.** ... 2. **It never writes an unmeasured call.** A non-zero
> exit, a timeout, a stream that does not parse, a missing `message_end` usage block or an empty
> assistant text all raise. Usage is never defaulted to zero and an empty answer is never returned as
> a result. A call that fails *after* the provider billed it is therefore not in the ledger - the ledger
> refuses a line it cannot total - which is stated here rather than papered over. 3. **It never retries.**
> A retry doubles the charge invisibly.

**The "ledger gap" I was about to record as a defect is refusal 2, and it is the right call.** I had
measured that `355d25f2-.../site_type` has no `model_call` row while its neighbours `description` and
`period_start` do, and read that as an attempt going unrecorded. The bytes say the opposite: a failed
call is deliberately kept out of the ledger because **the ledger refuses a line it cannot total**, and
the alternative - a line with usage defaulted to zero - would be an invented number in the one artefact
whose whole purpose is to be a measurement. The ledger's model rows carry `outcome: None` and
`error: None` on all 11,872 of them, so the failing signal lives in the stage log and in
`progress.json`, and it is **not** supposed to be reconstructed from the ledger.

**And the batch retry I proposed above contradicts refusal 3.** The reason is stronger than my
measurement was: a batch retry skips the answered calls, so it re-buys **exactly** the calls that were
billed and never journalled - the one charge that is invisible by construction. My measurement (the
same question fails again, twice, in ninety seconds) reached the right conclusion - do not retry - from
weaker evidence. Both are kept, because the measurement is what would have to be redone if the design
reason were ever dropped.

**What survives both refusals.** The per-field recorded failure: no retry (no second charge) and no
invented cost (the ledger stays empty for that call, as designed), with the reason written where it
belongs - beside the other calls of the batch - so that every call is either answered or **named** as
unanswerable. `BatchModelReport.calls` should count an unmeasurable call because it genuinely was one,
while the completeness check that `batch_state` performs must count the named hole as accounted for, not
as a missing answer. Nothing in that change tells a lie about usage, and nothing re-buys a call.

**The lesson, which this section has now produced four times in one afternoon: read the artefact
before claiming a defect.** A missing row looked like a gap in an invariant; it was a documented
refusal in the same module, four lines above the `raise`.

## Piece 6 landed, and was verified against its own bytes (2026-09-21)

Commit `7b87f6e`: four files, 3298 insertions and 1 deletion -
`scripts/remediation/phase3/write_stage.py` (new, 1746 lines),
`tests/remediation/test_phase3_write.py` (new, 1099 lines), `scripts/remediation/phase3/mutation_sweep.py`
(+237, appended only) and `output/remediation/phase3_runner/PIECE6.md` (new, 217 lines).
`LEDGER.jsonl` is **not** in it, and the working tree equals the commit for all four files (sha256 of
`git show HEAD:<path>` against the file).

**Reproduced by me rather than taken on report:** `ruff check` -> `All checks passed!` (exit 0);
`ruff format --check` -> `2 files already formatted`; `mypy` -> `Success: no issues found in 1 source
file`; `anchor_check.py` -> `Mutationen: 106 | Probleme: 0`; and
`pytest tests/remediation/test_phase3_write.py -q` -> **50 passed in 0.38 s**.

**The owner's 100-step rule is implemented word for word.** `--chunk-size` defaults to **100** with the
owner's date in the comment ("in 100er schritten updaten, nach jedem 100 immer die Pruefung");
`APPLY.sql` is one transaction opening with `\\set ON_ERROR_STOP on` and `BEGIN;`; every applied row is
re-read and compared against the intended value *for the same named sites*; `ROLLBACK.sql` is run as-is
and the invariant inside it asserts the rows are back at the old value; and the module states the
consequence in its own words: "A chunk whose read-back or inverse disagrees **raises** and chunk *n+1*
is never sent: that is the STOP". A mismatch is a STOP, not a warning.

**The data rules are honoured at the byte where it matters.** The conditional `WHERE` is
`IS NOT DISTINCT FROM $3::<column type>` - the NULL-safe form, so a NULL old value is compared
correctly and `=` would not be - taken from the primitive's own conditional in `0018`; each row's
`change_key` is recomputed and a mismatch **raises** (`{site}: change_key ... is not the digest of the
row`); and the reversal uses `mechanical.apply.rollback_change_key`, a *different* name, so the apply
and the rollback of one row cannot collide in the journal. `PSQL` carries `-v ON_ERROR_STOP=1` and
`-t -A` (the read-backs are parsed).

### And what it plans on real data: no row at all, for two reasons that are decisions, not defects

My own dry run on `runs/gold6/batch-0001`, exit 0:

```
"not_cleared_by_the_reviewer": 68, "rows_planned": 0, "chunk_size": 100, "dry_run": true,
"refused_by_rule": {"report-only-field": 7, "reviewer-did-not-clear": 68}
```

Seventy-five verdicts, seven cleared by the reviewer, and **all seven on a field that can never be
written**, so the writer plans nothing. The two reasons, both read from source:

* `model.REPORT_ONLY_FIELDS = frozenset({"description", "card_description"})` - brief decision 5, with
the brief's own reasons: a boot overwriter for `card_description`, the phase split for `description`.
  The mass run asks five fields per site, so **three can ever be written**: `period_start`, `site_type`,
  `country`.
* In this sample the reviewer cleared 7 of 75 (9.3 %).

**The consequence has to be said plainly, because it bounds the owner's own instruction.** Martin asked
that the model *correct* the content rather than only flag it, and research and cite as it does. With the
brief as it stands, phase 3 can correct at most three of the five fields it judges, and the field most
associated with "the content" - `description` - is deferred by another phase on purpose. On the gold
sample, one real batch, the write path would change **no row**. That is the writer behaving correctly on
this data; it is not evidence that the pipeline is broken, and it is also not a result anybody should
describe as "sites fixed".

### What is verified, and what is not

* **Verified against the bytes:** every number in the two lists above, plus the digest binding, the
  NULL-safe conditional, the distinct rollback key and the `ON_ERROR_STOP` flags.
* **Not verified, and not verifiable here: anything that needs Postgres.** No database was contacted -
  none exists locally and nothing was sent to the VPS. The PL/pgSQL block, the 12-argument
  `apply_remediation_change` call, the read-back against real `to_jsonb` output and the journal
  invariants all rest on a **fake psql seam** in every test. The first `--apply` must therefore be a
  single chunk, read by hand, against a freshly snapshotted database.
* **Unreachable by design, and recorded instead of coded:** `unified_sites.name_normalized`. Its refusal
  is `no-table-mapping`, derived from the plan's own field map, so a branch keyed on `unaccent` would be
  code no test could reach; the module says so in its guard table ("If that mapping ever grows the
  column, this table has to grow with it").
* **One standing rule was deviated from inside the lane:** the mutation sweep ran there, against the
  rule that it runs from a parent process (piece 5's incident). The lane reports every mutation
  restored, per-file sha256 equal and the final tree byte-identical. That claim is worth exactly as much
  as its independent reproduction, which is running now in the parent process; until its `SWEEP_EXIT`
  line is read, the 106/106 is **unconfirmed** and this entry says so.

**Outcome of both open checks, same day.** The parent-process re-run finished:
`106/106 mutations caught; missed: []`, `SWEEP_EXIT=0` (read from the sweep's own trailing line, not
the wrapper's exit code), and **"the tree is byte-identical to the sweep's start for 10 file(s)"**.
The lane's claim therefore stands as independently reproduced, not merely asserted - and the same run
also demonstrated the restore path that matters: `review_stage.py` was visibly modified while the sweep
held its mutant and its sha256 equals `HEAD` afterwards, which is the `finally` doing its job.

The DB-less suite on the committed bytes: **`2448 passed, 3 skipped, 57 deselected, 32 warnings in
114.96s`**, `PYTEST_EXIT=0` - 2398 + exactly the 50 tests piece 6 added, and the same three known skips.
Every number the lane reported is now reproduced by a second process on the same bytes.

One housekeeping consequence: a **formatter reflowed `tests/remediation/test_t10.py`** - a file no lane
authored this turn and not a sweep target (`grep -c test_t10` over `mutation_sweep.py` = 0), numstat
`2 2`, `f(x), (list(y))` becoming `f(x), list(y)`. It is committed (`777d37f`) rather than reverted:
reverting invites the formatter to redo it, and `.githooks/pre-push:105` compares the working tree with
the commit being pushed, so one uncommitted cosmetic diff is enough to block every future `main` push.
The proof for that commit is the suite above, which ran on exactly those bytes.

## A mutant survived the kill, and the sweep's own `assert` was what found it (2026-09-21)

The acceptance of the judge path was launched, wrote a zero-byte sweep log and stopped. Its task file
says why: `"status": "killed"`, `"error": "Killed during Pi session shutdown/reload"`,
`"notified": false`. A background task is killed with the session that owns it, so the absence of a
completion notice is **not** evidence that a run is still going - the task record is. The same run was
re-launched verbatim; the second attempt finished, and its own trailing lines are the reason this
section exists:

```
SWEEP_EXIT=1
= 2 failed, 2456 passed, 3 skipped, 57 deselected in 122.52s =
PYTEST_EXIT=1
Nachher unveraendert: 8 von 8 | abweichend: []
SNAPSHOT_OK=0
```

Two tests red, and the sweep refusing to run: `mutation_sweep.py:1235`
`assert original.count(old) >= 1, f"{name}: anchor not found in {rel}"` fired with
*"the ceiling counts the ledger's whole history: anchor not found in mass_run.py"*. Both symptoms have
one cause. `mass_run.py:226` held **a mutant left in the tree**:

```
 bough = spend.calls  # mutated                                <- what stood there
 bought = spend.calls - (baseline.calls if baseline is not None else 0)  <- what belongs there
```

The 30-minute lane that was killed had been running this sweep; the kill landed between the mutation
and its restore, and the mutant stayed. The two red tests are the mutation's own catchers
(`test_a_ceiling_means_this_run_and_not_the_ledgers_whole_history`, `..._that_is_not_reached_lets_the_batches_run`, both `assert code == 0` -> `1`), i.e. **the tests were right and the tree was wrong**.
The sweep's guard had predicted exactly this: `mutation_sweep.py:1241` carries the comment about a
mutated file in the tree and a TypeError in that very loop, dated the same day.

**A before/after hash snapshot cannot see this.** `SNAPSHOT_OK=0` reported 8 of 8 files unchanged and
that statement is true - the sweep had changed nothing, because it refused to start. The snapshot
measures *drift during the run*, not *health of the tree*. What found the mutant was the opposite of a
consistency check: an instrument (the sweep's anchor assertion) that refuses to measure a tree it
describes incorrectly. Repair was surgical and double-sourced - `git show HEAD:` has the line at 225
and the mutation table has the identical original string at `mutation_sweep.py:633` - so the mutant's
absence is not restored from memory but from two independent statements of what the line is. After the
repair: `38 passed` in `test_phase3_massrun.py` (was 36 passed, 2 failed).

**Rule this buys:** any instrument that mutates the sources it proves must be preceded by a hash
snapshot *outside* the instrument's own scope, and a kill during a sweep has to be treated as "the tree
may be mutated" until an anchor assertion has run. A green suite and a clean tree are two claims, and
the suite is the one that can be green for the wrong reason.

## `mass_run.py:198`: a real gap, one line to the left of where the checker pointed (2026-09-21)

pi-lens raised `unchecked-throwing-call-python` on `spend.cost_usd += float(cost)`. The reading is
wrong at that line and right at its neighbour. The call is guarded by
`if isinstance(cost, (int, float)) and not isinstance(cost, bool):`, so `float()` cannot raise for the
values it receives; a `try/except` around it would be precisely the silent swallow `CLAUDE.md` forbids.
The actual defect is the `else` branch that does not exist: **a `cost_usd` that is not a number is
skipped silently and counted as 0**, and this number is the one the money ceiling is measured against.
A ledger row with a stringified cost would therefore under-count the spend and let a run past its
ceiling. The repair is to stop loudly, as the neighbouring cases already do (`LedgerDamage` for an
inner unparsable line, `torn_lines` for a trailing one), plus a range check so a huge integer cannot
become `inf`. It is recorded here as a **scheduled wave with its own mutation and gate**, not smuggled
into the judge-path commit, and the finding is marked `flagged` (a fix is expected; the disposition
stays until the fix is observed) rather than `false-positive` - the symptom is a false alarm, the
finding is not.

This is the third variant of one lesson, and it is worth stating once in its general form: **a checker
can point at the right file and the wrong line, and its recommended remedy can be weaker than the code
it criticises.** Fixed `float()` in a `try` would have turned a loud-stop candidate into a silent zero;
the finding belongs one statement to the left.

**Fixed the same day, as promised - and the shape is the file's own.** The `if isinstance(...)` filter
became a guard with an `else` that stops: a `cost_usd` that is present and is neither `None` nor a
non-bool number raises `LedgerDamage` naming the line and the type it found; a value that is negative
or not finite raises the same, and a literal integer too large for a float is caught as `OverflowError`
and raised as the same damage rather than crashing as an arithmetic accident. `None` - the normal case
for a row that carries no charge - still counts as zero, and the test asserts that case explicitly
before it asserts the six that must stop. Two new mutations hold the two guards in place
(`a cost that is not a number is counted as zero`, `a negative or infinite cost is counted`), because a
guard nobody mutates is a guard that has silently stopped guarding. The property being repaired is not
robustness for its own sake: this sum is the number the money ceiling is measured against, so a cost
counted as zero is a run that spends past a ceiling it believes it has not reached.

**Its outcome, measured.** `118/118 mutations caught; missed: []` (`SWEEP_EXIT=0`) - the two new
mutations among them, so both guards have teeth - and `2459 passed, 3 skipped, 57 deselected`
(`PYTEST_EXIT=0`), one more than the judge-path gate's 2458 and exactly the new test. The same run's
snapshot reported this file as drifting, and the cause is this file: the edit that wrote the paragraph
above and the acceptance that hashes it were issued in one tool block, so the snapshot captured the
earlier bytes. The three executable files were byte-identical, which is the claim that gate had to
make. The rule it buys is small and sharp: **a file is never written in the same block as the run that
hashes it** - an instrument whose input and whose subject are written in the same breath measures
neither.

## 2026-09-21 - the finder's description proposals would replace a passage with a stub, and the phase split already refuses them

**The reviewer stage ran for the first time, over the batches that already exist.**
`run.py judge --stage reviewer` (`run.py:545`, `_judge_discover_reviewer`) over `batch-0001`: 8 calls,
23.6 s, 5 findings cleared, 3 refuted, 67 recorded as unreviewable with the finder's own reason. The
dry run over all 160 batch directories puts the whole pass at **2,165 calls** and 9,835 unreviewable
records, so the reviewer's unit is the finding, not the site. The verdict mix of the 11,367 finder
answers, counted from the answer texts themselves (`CORRECT` 5,431 = 47.8 %, `UNVERIFIABLE` 3,708 =
32.6 %, `WRONG` **2,209** = 19.4 %, 19 answers with no verdict line):

**1,341 of those 2,209 findings cannot be written by this stage at all** - `description` 459 and
`card_description` 882, both report-only (`phase3/model.py:49`, `write_stage.py:206-223`). The writable
ones are `site_type` 475, `period_start` 371 and `country` 22. The review pass the writer needs is
therefore 868 findings, not 2,165; the other 1,341 reviews are reviews of a field no Phase-3 statement
can reach (recorded for Phase 5, not wasted, but not Phase 3's bill either).

**Then the measurement that makes that split load-bearing.**
`output/remediation/logs/proposal_shape.py` compares every proposal with the stored value it would
replace, read from `PLAN.snapshot.jsonl`, and of the 456 `description` proposals **136 are under half
the stored length and 73 under a quarter**. The specimens are not marginal: Troy `0576c316` proposes
113 characters where the row holds 505 (Wikidata's one-liner "ancient Homeric-era city in northwest
Asia Minor ..."), Duloe Stone Circle `4a42b149` proposes 62 where the row holds 742 ("Small stone
circle at Duloe, 150m south east of Stonetown Farm"), Dun Fiadhairt `b4666064` 45 against 98.

**The mechanism is a field confusion, and the finder states it itself.** Its evidence line for Troy
reads "The evidence gives a **Wikidata English description** for Q22647" - the short string that
belongs to `card_description` - and it concludes `VERDICT: WRONG` because "the evidence states a
different value for this field (a short one-line description rather than the stored multi-sentence
account)". The same answer shows why the evidence was thin: the enwiki extract for that title "returned
no page", which left Wikidata's short string as the only witness. The reviewer then cleared it, because
its contract is `applies = not refuted` and not-refuted is not the claim "better than what it
replaces" - its own reason text records that the stored text is the richer one and applies the change
anyway.

**No guard was added, and that is the finding.** The obvious repair is a floor - a long-form field is
not replaced by a value under half its length - and it was written and then **reverted**: `description`
never reaches `_row_for`'s checks, it is refused as report-only three statements earlier, so the rule
would have been dead code with a passing unit test. `git diff` was empty afterwards and the file is
byte-identical to `7b87f6e`. The floor belongs to **Phase 5**, in the writer that first makes
`description` writable, and it must be there before that writer runs: 136 of the 456 proposals measured
here are exactly the rows it would otherwise write. Threshold and evidence: 50 % of the stored length,
as measured here.

**The `period_start` proposals are not the same case, and were read rather than counted.** A year has
no length, so the three specimens were read verbatim: Dun Telve `52258395` `-2000 -> 1` (the source
says the broch is "Iron Age, approximately 2000 years ago", so the stored value is a probable import
artefact that read an age as a year), Schwarzenacker `4fbef8ee` `-500 -> 1` ("existed from the time of
the birth of Christ until 275 A.D.") and Castro of Monte Castelo `6d04a9ad` `-1000 -> -5`, where the
source names "5 B.C. and the 5th century" *and* "the oldest artefacts from 900 B.C." and the finder
took the later phase. Two of the three correct a real legacy error; one picks the wrong number out of
the same sentence. That is a reviewer-question matter, not a length matter.

## 2026-09-21 - the boundaries the project already ships answer the country question, and 83 rows contradict them

The `country` verdicts are the weakest of the five fields because the finder matches a *name*, and a
name collides across continents: two of the ten clearances are 5,000 and 10,000 km from the coordinates
of the row they claim to describe. The project, however, already ships
`data/boundaries/countries.geojson` (258 polygons, 96 spellings in the database) and `shapely` is a
declared dependency (`requirements.txt:32`), so "which country is this place in" is a point-in-polygon
test rather than a judgement. Measured over all 5,004 curated rows on 2026-09-21 with one read-only
`SELECT id, name, country, lat, lon` (`output/remediation/logs/country_census.py`):

- **4,713 agree** with their own coordinates
- **83 contradict** them (`output/remediation/logs/_country_mismatches.txt`)
- **208 fall in no polygon** - coastal, island and offshore points. The test is inconclusive there and
  must never be read as agreement.

The contradictions are not one kind of thing, and that is the finding that matters:

- **~30 are political lines the boundary file draws differently**: `Cyprus -> Northern Cyprus` (7),
  `Cyprus -> Akrotiri Sovereign Base Area` (6), `Cyprus -> Cyprus No Mans Area` (1),
  `Ukraine -> Russia` (9, all Crimea), `Serbia -> Kosovo` (2), `Syria -> Israel` (2, Nimrod Fortress in
  the Golan), `Israel -> Palestine` (2). The stored value is the internationally recognised state in
  each case and the file holds the de-facto line. Nothing here is ours to decide: an automatic rule that
  "corrected" these would write a political judgement into the database.
- **~25 straddle a border**: `France -> Germany` (Bliesbruck-Reinheim is a cross-border park),
  `Slovakia -> Hungary` (Celemantia, on the Danube), `Spain -> Portugal` (the Coa valley property spans
  both countries), `Belgium -> Netherlands` (Veldwezelt-Hezerwater), `Bulgaria -> Romania` (Silistra),
  `Belize -> Guatemala` (Pusilha). `Greece -> Italy` is Selinunte, a Greek colony *in* Italy, and is a
  genuine stored error rather than a border case.
- **22 are one and the same genuine error**: `Ireland -> United Kingdom`, every one of them in Northern
  Ireland (Boa Island 54.5168/-7.8333, Moylehid, Goward Dolmen, Ballylumford Dolmen, Annaghmare Court
  Tomb, Annadorn Dolmen and 16 more). The finder proposed three of them, because it saw 2,280 of the
  5,004 sites; the census needs no model for any of the 22.
- **A handful are outright inconsistencies** that deserve their own look: `Saudi Arabia -> France`,
  `Pakistan -> Peru`, `Bolivia -> Peru`, `Azerbaijan -> Armenia`, `Germany -> Switzerland`,
  `Croatia -> Republic of Serbia`, `Sweden -> Switzerland` (the last is Aquae Helveticae, which is
  Baden in Switzerland, stored as "Sweden" - a real legacy error).

The ten `country` rows the reviewer cleared were then verified one by one against the polygons
(`output/remediation/logs/country_probe.py`): **six are right** (Selinunte -> Italy, Annadorn Dolmen /
Dooey's Cairn / Giant's Ring -> United Kingdom, Aquae Helveticae -> Switzerland, Ahin Posh Tape ->
Pakistan, stored as "Afghanistan" while the coordinates are in Pakistan), **three are name collisions**
(Lamay in the Yucatan proposed as Peru, San Claudio in Chiapas as Spain, Soura in Lycia as India) and
**one is a political line** (Jaffa Gate, Israel/Palestine). The gate for the writer is therefore "the
proposed country must contain the site's own coordinates", with the alias map derived from the
database's own 96 spellings rather than from imagination: `England`, `Wales`, `Scotland` and `Northern
Ireland` are *more* specific than `United Kingdom`, not contradictions, and neither are the boundary
file's `Northern Cyprus` / `Akrotiri Sovereign Base Area` / `Cyprus No Mans Area` subdivisions.

That alias map then produced a second finding, and it is a spelling one. The database holds
**1,052 `England` + 118 `Wales` + 83 `Scotland` + 4 `Northern Ireland` against exactly one
`United Kingdom`** - the dataset's convention is the constituent country. The reviewer's three Northern
Irish clearances propose `United Kingdom`, which is geographically right and still the wrong value:
written, they would put a second spelling on the same place and split the filter list. The correction
value for those 26 rows (22 from the census, 3 from the reviewer, and one more the census places in
Northern Ireland) is `Northern Ireland`. That is a spelling decision and it is recorded here rather
than taken by a model: the gate lets the reviewer's three through, because the coordinates prove the
country and a wrong spelling still beats the wrong country, and the split stays visible in the filter
list until the owner picks one convention for the other 23.

## 2026-09-21 - the write path is proven on production, and 72 of 481 rows are held back

**The first write happened, and it is the smallest one that could prove anything.** One chunk, read by
hand, against a database snapshotted minutes earlier - the owner's own precondition. The backup is
`backups/2026-09-21_pre-write/` (655,369,826 bytes, stamp outside the prune pattern, so it can never be
deleted) and its `DRILL_REPORT.txt` is the proof rather than the log line: `unified_sites` 1,759,676 =
1,759,676 restored, `VERDICT: dump is restorable and matches production row-for-row`.

| check | result |
|---|---|
| writer report | `batch-0001 zeilen=2 sites=1 matched_0=0 journal=2`, `batch-0002 zeilen=2 sites=6 matched_0=0 journal=2` |
| summary | `4 Zeilen fuer 7 Sites geschrieben, 4 Journaleintraege, matched_0=0, Abweichungen beim Nachlesen: 0` |
| independent read-back (the database, not the writer) | Aguada Fenix `-1000` + `Archaeological site`; Annadorn Dolmen `United Kingdom`; Appolonia Temple Ruins `Settlement` |
| the journal's own rows | `phase3:batch-0001:chunk-0001`, `phase3:batch-0002:chunk-0001/0002`, old and new value per row |
| the hold mechanism | Monte Lazzu is in an applied batch and its `site_type` still reads `Settlement` - the row was refused, not written |

`Annadorn Dolmen Ireland -> United Kingdom` is one of the 22 Northern-Irish rows the country census
found; the boundary file's own words are what let it through, and the spelling question stays open
above.

**Two defects were found by running the driver, not by reading it.** (1) `write_batch` passed
`rows[0]["plan_dir"]` to the writer, and a planned row has no such key - the batch directory is
`RUN / batch_id` (`write_dry_all.py:23,46`). (2) The child needs `PYTHONPATH` to import
`pipeline.normalizers`; the dry run had only ever succeeded because the calling shell exported it. The
gate now carries its own environment, so it behaves the same from a bare prompt. Both failures happened
**before** any writer call, which is why the database was untouched and no partial row exists.

**The row-level apply is `--chunk-size 1 --chunk K`, and K counts the writable rows, not the plan's
rows.** `build_plan` appends only `WriteRow`s to `plan.rows` and puts the refusals in `plan.refusals`,
so `chunks_for` slices the writable list; `PLAN.jsonl` is that list in order, and `ALL_ROWS.jsonl` is
built by concatenating each batch's `PLAN.jsonl` (`write_dry_all.py:106`). That is why this driver can
write one row of a batch where another row was withheld, and why the read-back after the first chunk
proves the alignment rather than assuming it.

**72 of the 481 writable rows are held back**, and the criterion is not "the model may be wrong" but
"this row's own reviewer reason does not carry both halves of its claim": the stored value is shown
wrong **and** the proposed value is supported by the evidence. The reason a row is held is therefore
always quotable from the row itself, and the 72 are listed with those quotes in
`logs/_write_apply/HOLDS.md`.

| class | example (row number) |
|---|---|
| the reason says the stored value is *not* shown wrong | 22 Hattusas, 125 Cochabamba, 148 Pagans Hill, 217 Paanamarca, 282 Wanakawri, 324, 382 Alte Burg |
| the reason says the stored value is the *finer* one and the proposal is coarser | 244, 318, 373, 441, 454, 353 Xultun, 104 Inka Murata |
| the reason says the evidence *supports the stored* value | 171 Tulum, 375, 425 Stones of Stenness, 437, 470 Salona |
| both halves fail in the reviewer's own words | 71 Upper Plym Valley, 193, 268 Kahu-Jo-Darro, 391 Devil's Lair (its BP arithmetic refutes its own conclusion, `48,000 BP` is `-46,050`, so the proposal is right and the reason is not) |
| a bucket-boundary nudge with no date behind it | 39 (`-3000 -> -2999`), 176, 200, 202, 206, 338, 347 |
| the evidence quote shows no value at all (`P571` alone, or raw JSON) | 12, 70, 131, 192, 430 |
| the stored value is right and the proposal is not | 303 Goebekli Tepe, 421 Stoa Basileios, 441 Tan Hill, 454 Braughing |

**The filter that finds these is a reading aid, and its recall was measured rather than assumed.**
Within the first hundred rows - read by hand, ten of them holds - the two marker passes plus the
not-a-sentence test flagged all ten. The first run of the extended filter printed into a truncated
view, so it was re-run to completion: **245 hits, 60 already decided, 185 open** - and reading those 185
found **12 more holds** the truncated view had hidden. Two of those twelve use the exact sentence shape
that the better-known holds use ("the stored value is not contradicted", "a coarser type does not
invalidate the finer stored one"), which is the honest limit of this method: a filter is not the
verdict.

**The country gate refused four of the ten cleared `country` rows** - Lamay (`Mexico -> Peru`), San
Claudio (`Mexico -> Spain`) and Soura (`Turkiye -> India`) because the site's own coordinates lie
thousands of kilometres from the place the name matched, and Jaffa Gate (`Israel -> Palestine`) because
its coordinates lie in Israel and the row is a political line rather than a correction. Ahin Posh Tape
(`Afghanistan -> Pakistan`) passed: the boundary file puts its coordinates in Pakistan, which is a
stored error the census had already found.

**The steps are the owner's rule of 2026-09-21**: `--step 100` stops every hundred *sites*, reads the
rows it wrote back out of the database itself and prints what it found, then continues; `--limit` counts
sites; a finished batch is marked with `_write_apply/<batch>/APPLIED.json` so a second run resumes
instead of re-applying rows whose old value is no longer there to match.

**The first attempt at the full run was stopped after eleven batches, and the reason is worth keeping.**
Twelve further holds had been written into `make_holds.py` - but the gate reads `HOLDS.jsonl`, and that
file is only rewritten when `make_holds.py` *runs*. The edit was verified and the artefact was not, so
the run started with `zurueckgehalten: 60` and would have written those twelve rows; it was stopped
while batch 11 of 160 was in flight, and the check that mattered was the intersection of the new holds
with the rows already written, which was **empty**. The count that counts is the one the gate prints
from the file, never the one the script's source suggests, and the file is regenerated before the
reader starts. The eleven finished batches were resumed, not re-applied.

### The wave is finished: 410 rows at 396 sites, nothing deviating

The run wrote in eight checks of a hundred sites, and each check read its rows back out of the database:
at 100/200/315/400/507/622/701/800 sites, 36/80/114/168/223/267/312/360 rows written - **zero deviations
every time**. `matched_0=3` is the batch that was in flight when the first attempt was stopped: its three
rows already held the new value, so resuming wrote nothing twice. That is the idempotence the conditional
`WHERE` promises, measured instead of argued.

| | count | |
|---|---|---|
| planned rows | 485 | the writer's dry run, unchanged by the reading |
| refused by the boundary rule | 3 | Lamay, San Claudio, Soura - the name matched a place thousands of kilometres from the coordinates |
| withheld after the hand-read | 72 | their own reviewer reason does not carry both halves of the claim |
| **written** | **410** | 485 - 3 - 72 |
| journal rows for this wave | 410 | `run_stamp LIKE 'phase3:batch-%'`, one per written row |
| sites in the plan | 462 | the writer's own dry-run figure, so no site slipped out |
| **sites actually changed** | **396** | `count(DISTINCT row_pk)` over this wave's journal rows |
| planned rows still at their old value | 75 | the 72 withheld plus the 3 refused |

The acceptance is `output/remediation/logs/verify_writes.py`, and it asks production rather than the
writer: every journal row of this wave must find its new value in `unified_sites`, **and every planned row
without a journal row must still hold its old value** - which is what tests the 75. `ERGEBNIS: 0
Abweichungen`, `ABNAHME_EXIT=0`.

Its first version was wrong, and how it was wrong is why it is now written in both directions: it excluded
only the withheld rows, so the boundary-refused rows whose batches were applied counted as written, and it
reported two deviations that were the refusal *working*. A control that cannot fail is not a check.

### The mass run's real blocker: the judge asked a question whose answer was already on disk

Rounds 2 and 3 of the mass run ended at 130 of 334 batches on the circuit breaker, "3 consecutive batch
failures". Those failures are not the fetch stage and not the overpass endpoint - each one is `judge exited
1`, and the traceback names the cause exactly:

```
phase3.fetch_stage.EvidenceConflict: ...\answers\<site>%2Fdescription.txt holds different bytes
than the answer just received; refusing to overwrite a recorded fetch
```

The guard is right: a recorded answer is never overwritten with different bytes. What was wrong is that the
question was asked at all. `EvidenceStore` documents its own rule - *"Existence is the record: a target
whose file is already on disk is not fetched again, so a re-run costs nothing"* - and the fetch stage
honours it, but `judge_site` called the model **before** it looked: `runner.run(call)` first,
`answers.write(...)` after. A re-run therefore paid for a second answer to a settled question and then died
on the second bytes.

`judge_site` now returns the stored answer without a call. Three consequences, all deliberate:

- **No money.** No ledger line is appended, because a ledger line is the record of *asking* and nothing was
  asked. The judgement carries the stored answer's own length with zero usage, so a reuse reads as
  `wrote=False` and a cost of 0 in `model.json`.
- **The guard is untouched.** The refusal to overwrite is not weakened; the collision is avoided.
- **The escape hatch stays the store's own.** Deleting the answer file (with the evidence file it was judged
  against) is how a human asks that one question again.

That last point is also the one way this rule can mislead, and it is written down here rather than left to
be discovered: a *changed* question written to the same key reuses the recorded answer silently. Within one
run directory the question is frozen, so a re-review with new wording needs the file deleted - otherwise the
measurement is not a measurement. The zero cost is the sign that nothing was asked.

The guard has teeth, measured rather than asserted: mutation 119 replaces `if answers.exists(...)` with
`if False`, and the new test then fails with the mass run's own error
(`EvidenceConflict: ...answers\site-1%2Ffinder.txt`) - `1/1 mutations caught`, the tree byte-identical
afterwards. Full gate: **2460 passed, 3 skipped**.

### Round 4 died twice on a host hiccup, not on the work

Round 4 finished ten batches, and they cost **509 calls ($0.43)** - the judge fix worked: not one batch
ended on the `EvidenceConflict` any more. Then the circuit breaker stopped the run after four failures in
a row, and the failure was a different one:

```
"error": "...\/period_start: 'pi.cmd' could not be started: [WinError 2] ..."
```

No model error, no network, no evidence: **the tool itself could not be started for about three seconds.**
Measured, not guessed:

| measurement | value |
|---|---|
| the two failure times (local) | 21:47:00 and 21:47:03 |
| a **successful** call after them | 21:47:12 (batch-0167) |
| `pi-node/current` last written | 21:47:27 |
| the same command, now | `rc=0`, version 0.87.0 |

It was not the environment: in exactly the same background environment `shutil.which('pi.cmd')` resolves
the program and `subprocess.run(['pi.cmd','--version'])` returns `rc=0` from both trees. And it was not the
working directory either - `ModelRunner(cwd=None)` inherits it, and the same call succeeds from every
directory tried. The run starts thousands of `pi` children, and one of them touched the Pi tree: a mass run
is its own disturber here. **The mechanism inside Pi is not established** and is not claimed here.

The circuit breaker behaved correctly: four failures in a row on the same tool are a reason to stop, not to
keep going. And because the run is resumable, stopping cost **nothing** - the ten finished batches were
recognised as `already done` on the second attempt, free of charge, and the four failed ones are retried.
What is *not* done about it is a retry: a retry would hide exactly the failure class that wants to be seen,
which is the same reason the module refuses to retry a model call.

The second attempt died the same way, and it widened the picture: this time `prepare` itself failed with
`3221225794` (`0xC0000142`, `STATUS_DLL_INIT_FAILED`), so **`python.exe` could not start either**, and the
"the Pi tree was being rewritten" reading was too narrow. Measured afterwards - every one of these is a
refutation, not a hypothesis:

| measurement | value |
|---|---|
| 80 starts, one at a time | **0 failures** |
| 100 starts, 4 at a time, cwd = the worktree | **0 failures** |
| RAM free / page file in use | 7.4 GB of 31.3 GB / 177 MB of 11,278 MB |
| orphaned `pi`/`node` children | none |
| error or warning entries in the System/Application logs in the window | none |

So the cause is a few-second window in which **no process can start at all** - not the environment, not the
working directory, not the concurrency, not memory - and its host-side mechanism stays unestablished. That
leaves one honest place to act: not the model stage, but the driver, and only for a *start* failure. The
retry is bounded (`MAX_SPAWN_ATTEMPTS = 3`), loud (one line per retry in the stage's own log, the count in
`progress.json`), and blind to everything else: a failed call, a timeout and a parse error come back on
their **first** exit, because a retry that hides real breakage is worse than the stop it replaces.
`spawn_retries` in `progress.json` is how a human sees whether the protection was ever needed.

### The owner's decisions, 2026-09-21 and 2026-09-22

Asked as an interactive multiple-choice list - Pi ships the tool as an example, installed unchanged as
`~/.pi/agent/extensions/60-questionnaire.ts`. Each answer is recorded with what it *changes*, because a
decision that changes nothing is not a decision.

| # | question | answer | what it changes |
|---|---|---|---|
| 1 | the 72 held rows | **leave them, write nothing** | nothing: `HOLDS.jsonl` already carries all 72 |
| 2 | the Northern-Irish spelling | **`Northern Ireland`** | the two open plan rows and the one already written row are re-spelled, and the discover prompt gets the dataset's convention as a note |
| 3 | the 4 refused rows | **write none of them** | nothing: the writer already refuses all four (boundary and fixed point) |
| 4 | the 29 geopolitical census rows | **leave them as they are** | nothing: they are census findings, not planned rows |
| 5 | when to deploy | **only after all 5,004 are through** | nothing today: the commits stay local until the run is complete |
| 6 | the missing search route (A3) | **solve it with MiniMax** | the 5,569 "unverifiable" answers *[corrected 2026-09-22: 7,761 by the answer files; 5,569 has no derivation]* get a search service; only structured hits (title, url, snippet) are taken and the reasoning stays on `deepseek-v4.1-flash` |

**B9 was asked twice, and the first answer was worthless because my framing was wrong.** The first version
called `United Kingdom` "one spelling for the whole country - like England, Scotland, Wales". Measured on
production afterwards: `England` 1052, `Wales` 118, `Scotland` 83 - those **are** country parts, so the
argument pointed at `Northern Ireland`, not away from it. The question was put again with the measurement
inside it, and the owner then chose `Northern Ireland`. The wrong answer was not quietly kept, and the
wrong recommendation is written down here rather than edited out.

Measured while answering: the plan holds **485** rows, **10** of them `country`, **72** held; exactly **3**
planned rows come from `Ireland` (Annadorn Dolmen, Dooey's Cairn, Giant's Ring), and the wave already wrote
the first of them - so that one now needs a follow-up correction to match the decided spelling.

### The spawn protection worked, and its window was still too short

The fourth attempt is the first one that ran with the protection, and it paid for itself: `spawn_retries:
6` in `progress.json` - six start failures were retried and **recovered**, and the attempt got 28 batches
further than the one before (`batches_done` 27 -> 55, 254 of 334 batches, about 3,810 sites, $20.46). It
still stopped on the circuit breaker, because four batches exhausted their three attempts: the hiccup
outlasted 3 x 5 s = 10 s. So the window was widened to `MAX_SPAWN_ATTEMPTS = 6` and
`SPAWN_RETRY_WAIT_SECONDS = 15.0` - 75 s of coverage - which is still bounded, still loud, and still blind
to every real failure. The number that matters is not the constant but `spawn_retries`: it says whether
the protection was needed, and how often.

### What the finder has said, counted from its own answers

The finder pass over the plan is **complete**: 334 of 334 batches are done - 333 of them in the run, and
`batch-0272` retried on its own after a single `judge exited 2` (a real failure, not a start failure, which
is why the spawn protection stayed out of it) and finished too. Read straight out of the answer files -
24,255 fields over 4,852 sites - measured 2026-09-22:

| verdict | fields | share |
|---|---|---|
| CORRECT | 11,747 | 48 % |
| UNVERIFIABLE | 7,761 | 32 % |
| WRONG | 4,708 *[corrected 2026-09-22: 4,710 by `parse_answer`; this row made the table sum to 24,253]* | 19 % |
| no readable verdict | 37 | 0.2 % |

Proposals by field: `card_description` 1,881, `site_type` 1,037, `description` 947, `period_start` 808,
`country` 43 - and only **1,888** of them sit in a writable column, because `description` and
`card_description` are report-only (`model.py:49`).

An earlier count of this, taken when 256 of the batches were through, read 3,595 wrong over 3,840 sites -
the same distribution. It stays here rather than being replaced, because a reader who saw the earlier number
has to be able to find it again.

**The first count of this reported 668 answers "without a verdict", and that number was my instrument, not
the data.** The pattern demanded `VERDICT:` at the start of a line, while the answers put it inside a
numbered list (`2. VERDICT: CORRECT`). Counted again unanchored: 37. The wrong number is written down here
instead of quietly dropped, because a number that reached a reader has to be corrected where it was read.

### The write wave was killed by a print, not by the database

The first attempt at the second write wave ended with `WRITE_EXIT=1` and **nothing written**. The
traceback is a `UnicodeEncodeError` on `\u0259` in a site name, raised while the gate printed its
refusal list - which it does *before* it writes the first row, so the wave aborted with the database
untouched.

The cause was mine and it was an environment variable: the background launch set `PYTHONPATH` and
`PI_SKIP_VERSION_CHECK` but not `PYTHONIOENCODING=utf-8`, so Python encoded stdout with the console's
cp1252. The same command in an interactive shell - where that variable is set - had run cleanly minutes
earlier, and that difference is the whole bug.

Two things followed. The immediate one: the untouched state is *proved*, not assumed. A fresh dry run
after the crash still reports `168 offene Stapel | 584 Zeilen`, the same numbers as before it, and the
`APPLIED.json` count is unchanged at 149 - all of them from the first wave - so no row and no marker
was written. The lasting one: `write_gate.py` now reconfigures its own stdout and stderr to UTF-8 with
`errors="replace"` at import time, because a tool that writes to production must not be killable by the
encoding of whichever console it was started from.

### The second write wave: 584 rows, checked at six points, 0 deviations

The gate wrote **584 rows at 601 sites** in six steps of a hundred, and the writer's own check after each
step found **0 deviations** every time. `matched_0=0` is the load-bearing number: not one planned row
failed to match the old value the plan had assumed, so nothing was written on a stale premise.

The independent acceptance (`logs/verify_writes.py`) asks production in both directions instead of
trusting the writer, and it puts the whole action at **994 journal rows** - both waves together - of which
**994 carry the new value** and **80 planned rows still carry the old one unchanged**: the 72 held by hand
plus the 8 the boundary check stopped. 994 + 80 = 1074, exactly the plan, so no row was changed silently.
Read back: 1022 of 1022 sites, **0 deviations**. By field: `site_type` 596, `period_start` 389,
`country` 9.

The 8 boundary refusals are worth naming as a class, because they are the check working: in each of them
the evidence had matched a *different place of the same name* - the Temple of Artemis proposal would have
moved a point in Greece to Turkey, Flevum's a point in Germany to the Netherlands. A wrong coordinate
there looks exactly like a wrong country, and the boundary test is what tells them apart. Those eight are
among the 8 `(site, field)` questions in `HUMAN_ONLY.md` for their own reasons.

## 2026-09-22 - the mechanical lane's mutation proof proved 12 of its 30 cases, not 30

`mechanical/APPLIED.md` section 8 reports `cases: 30  fired: 30  survived: 0` and says every guard of
the country lane has a test that fails when the guard is removed. The table behind it
(`mechanical/evidence/10_mutation_sweep.txt`) does not show that, for three reasons found while
extending the lane:

1. **A skipped case printed as fired.** A needle that occurs more than once was reported `SKIPPED`,
   but `fired` was computed as `len(rows) - len(survived)` and the exit code looked at survivors only.
   `statement must commit` (`    if not sep:`, twice in `apply.py`) was skipped in the recorded run,
   next to `fired: 30`.
2. **17 mutants did not compile.** The `if False:` replacement dropped the guard's indentation, so
   17 of the 30 mutants were `IndentationError`s. pytest then failed at *collection* (exit 2), the
   named test never ran, and any non-zero exit counted as fired. The recorded table shows exactly
   those 17 as `fired: ` with no test name after the colon. Measured by compiling each delivered
   mutant against the LF sources in `HEAD`: 17 do not compile, 1 needle is not unique, 12 are real.
3. **On a CRLF checkout** (`core.autocrlf=true`, as in any fresh worktree of this repo) the three
   two-line needles match nothing, and the run still exits 0 with `fired: 30`.

The corrected sweep (`scripts/remediation/mechanical/mutation_sweep.py`) fires a case only when the
mutant compiles, the named test passed (not skipped) on the original, and pytest reports that test
FAILED by name on the mutant; a skipped, invalid, unproven, errored or surviving case fails the run.
It keeps the guard's indentation, matches needles in the file's own line endings, and runs the tests
with the interpreter that runs it. `tests/remediation/test_mechanical_sweep.py` pins each of those
rules, and checks every real case statically in the normal test run (needle unique, mutant compiles,
test exists). The `statement must commit` needle is unique now, and the second COMMIT guard
(`ROLLBACK.sql has no COMMIT`), which had no test at all, has one.

Result on 2026-09-22: **`cases: 31  fired: 31  skipped: 0  survived: 0`**. So the guards *were*
covered - every one of the 17 fires once its mutant compiles - but the delivered run did not show it.
All three runs are in `mechanical/evidence/13_mutation_sweep_audit.txt`; the published
`10_mutation_sweep.txt` is left as it was recorded.

## 2026-09-22 - `[H] SECURITY 3 / BACKEND B7` closed in the mechanical lane

The mechanical `--apply` sent whatever `APPLY.sql` held, and it re-emitted the file right before
sending it, so the statement a reviewer had read and rehearsed was not provably the one that ran.
A psql timeout escaped as a `subprocess.TimeoutExpired` traceback, and a non-zero exit as a plain
error - neither said whether the COMMIT had reached the database.

Now (`scripts/remediation/mechanical/apply.py`, helpers in `plan.py`):

* `APPLY.sql` and `ROLLBACK.sql` carry `-- plan sha256 <digest>` as their first line - the sha256 of
  the `PLAN.jsonl` they were rendered from, taken over the text with LF endings, because this
  repository checks committed files out with CRLF (`core.autocrlf=true`; measured on the delivered
  T05 plan: `da4201ef..` as bytes in a worktree, `cc2e885f..` as text on both checkouts).
* `--rehearse`, `--rehearse-rollback` and `--apply` never re-emit. Each sends the file on disk only if
  its pin is the plan's digest *now* and its body is exactly what the plan renders; a stale plan, a
  hand edit, a second pin or a file from another plan is refused before any psql call. `--emit`
  refuses unless `ROLLBACK.sql` is this plan's pinned reversal.
* `--apply` refuses a run stamp that already journals rows. After a timeout or a failed exit it reads
  the journal for its stamp: all planned rows means **COMMITTED** (then the read-back is asserted,
  exit 4), none means **NOT COMMITTED** (exit 3), anything else - or a journal that cannot be read -
  is **OUTCOME UNKNOWN** (exit 5) with the exact count query to run before any retry.
* The transport, the timeout rule and the pin format live in one place,
  `scripts/remediation/prod_write.py`, moved there from the gallery lane (which now imports them),
  instead of a second copy in the mechanical lane. The mechanical transport gains the gallery's ssh
  `ConnectTimeout`/keepalive options on the way.

The delivered T05 `ROLLBACK.sql` (the undo, an action not yet taken) was re-rendered with its pin
(`plan.py --render-rollback`); its body is the current rendering, sha256 `832b7b6a..`, which differs
from the delivered file only by that pin and the one comment the lane had already reworded. The
delivered T05 `APPLY.sql` is kept as it ran, without a pin - which `--apply` now refuses, as it must
for a lane that has been applied. Checked read-only against production the same day: the 35 journal
rows of `2026-09-21_mechanical-country` are exactly the 35 `(site, old, new)` of the delivered plan,
with their `country-canonical:` keys and `T05/country-canonical` test id
(`mechanical/evidence/14_repin.txt`).

Tests: `TestThePin`, `TestTheDeliveredT05Pin` and `TestTheCommitState` in
`tests/remediation/test_mechanical.py` (the commit-state tests drive `cmd_apply` against a fake that
answers only the statements the real path sends) and `tests/remediation/test_prod_write.py`. Every
new guard has a mutation case: sweep `cases: 140  fired: 140  skipped: 0  survived: 0`.

## 2026-09-22 - the phase-3 acceptance follows the journal chain

`tools/verify_writes.py` compared every phase-3 journal row's `new_value` with the live value. The
B9 lane rewrites five of those rows (`United Kingdom` -> `Northern Ireland`) and the site_type shape
lane three more, so after those writes the documented **0 deviations** would have become **8
`NICHT NEU`** - for writes that are journalled and correct. It now reads every planned field's whole
journal chain, across all stamps: each link must start where the one before ended, the chain must
end at the live value, and a planned field phase 3 did not write must start from its planned old
value. A replaced phase-3 value is reported as *superseded by <stamp>*, never counted and never
silently passed. NULL is kept apart from `''` with a marker, which the per-row version could not.

Read-only run against production the same day, before any of the new lanes: `994 phase-3 field(s)
journalled, 80 planned field(s) phase 3 did not write, 1022 sites read - RESULT: 0 deviation(s)`, the
same numbers as the documented acceptance. Predicted after the UK and site_type lanes apply (from their
plans against `ALL_ROWS.jsonl`): still 0 deviations, with 5 fields superseded by
`2026-09-22_mechanical-uk-parts` and 3 by `2026-09-22_mechanical-site-type-shape`; the period lane
writes `period_name`, which this acceptance does not judge. DB-less tests in
`tests/remediation/test_verify_writes.py`; every new check has a mutation case.

## 2026-09-23 - review of the mechanical lanes: ten findings, each checked, each closed

A review of `wip/mech-lane` (the three new lanes, the B7 commit state and the chain-aware acceptance)
reported sixteen findings through three lenses (correctness, rules, tests). After removing
duplicates, ten distinct defects remain. Each was checked against the code before it was fixed,
the first by running `judge()`; the VPS measurement in item 4 is the reviewer's. Every fix has a
test that fails without it and a mutation case that proves it. Nothing below touched production;
the only production access was read-only.

1. **The acceptance passed a reverted phase-3 write silently.** `tools/verify_writes.py` treated
   every stamp that starts with `phase3:batch-` as a phase-3 write. That prefix also matches the
   writer's reversal stamp `<stamp>-rollback` (`phase3/write_stage.py:rollback_stamp`). So a write
   followed by its reversal counted as "journalled", was not superseded and gave 0 deviations. The
   per-row check it replaced excluded `%-rollback` and reported this case as `NICHT NEU`. Reproduced
   with `judge()`: deviations `[]`, written 1. The judge also accepted a phase-3 row outside the plan.
2. **The acceptance never saw a phase-3 write outside the plan.** `main()` read the journal only for
   `row_pk IN (<planned ids>)`. The old tool read every phase-3 row and reported one outside the plan
   as `FEHLT`. Both gaps were latent. A read-only check on production today found 994 phase-3 rows
   in the three columns, 994 distinct fields, every one a planned `(column, pk)` of `ALL_ROWS.jsonl`,
   and no phase-3 rollback stamp. The fixed tool reads every phase-3 row of any table, loads the
   chain of every planned or phase-3 field, and reports four kinds of deviation: `REVERTED`,
   `OUTSIDE PLAN`, `OUTSIDE TABLE`, and a phase-3 rollback on a field phase 3 never wrote. Rerun
   read-only on production: `994 phase-3 field(s) journalled, 80 planned field(s) phase 3 did not
   write, 1022 sites read - RESULT: 0 deviation(s)`, unchanged.
3. **The acceptance copied the planners' chain rule.** Its `broken()` repeated the loop in
   `plan.journal_break`. Both now call `scripts/remediation/journal_chain.py:first_break`. The same
   module names the reversal suffix, and a test pins that it matches `write_stage` and every lane.
4. **`--apply` declared NOT COMMITTED while the server could still commit.** After a client timeout
   or ssh's 255, `settle()` read the journal once and treated 0 rows as "nothing was written". The
   reviewer measured on the VPS that the remote psql still ran the next statement of its stdin 17 s
   after the client ssh was killed. Its uncommitted journal rows are invisible to the count, so an
   empty journal only settles the outcome after psql's own exit 3: ON_ERROR_STOP has then ended the
   script and the session. Every other failure with an empty journal is now `OUTCOME UNKNOWN`
   (exit 5). The report names `OPEN_SESSIONS_SQL` (psql sessions still in a transaction) and the
   count query to run before any retry. A full journal is still COMMITTED, because a committed row
   cannot vanish. The three new lanes also bound their transaction on the server:
   `SET LOCAL lock_timeout = '10s'` and `statement_timeout = '120s'`. A lock wait now ends as
   exit 3 and NOT COMMITTED within seconds, where it used to hang until the 900 s client timeout
   and end as UNKNOWN. Both values were validated read-only on production (PostgreSQL 16.4:
   `set_config` accepts them). T05's statement is unchanged byte for byte (its sha256 pin holds).
   The committed `APPLY.sql`/`ROLLBACK.sql` of the three lanes were re-rendered from their
   unchanged plans. Each file gains six lines, and the plan pins stay as they were: uk-parts
   `c2b22916..`, period-name `82bc62b7..`, site-type-shape `7557dad8..`. The orchestrator's
   rehearsal will be the first run of this text on production.
5. **A committed write whose read-back failed was reported as REFUSED.** After psql exited 0 (the
   COMMIT), a failing "after" read escaped as `PlanError`, printed `REFUSED` and exited 1. The
   runbook reads that code as "nothing was sent". A timeout at that point exited 5. Both cases, and
   a read-back that disagrees with the plan, now report `COMMITTED BUT NOT CONFIRMED` with exit 6.
   `settle()`'s COMMITTED path does the same instead of exiting 4 or 1.
6. **`--probe-guards` accepted any ERROR as proof.** On the new lanes guard 4 refuses a 101-character
   value too, and the primitive refuses a foreign old value. Guard 2's and guard 3's probes would
   therefore raise even with their own guard removed. The guards' RAISE texts are now constants
   (`GUARD1_SAYS`..`GUARD5_SAYS`), shared by the renderer and the probes. A probe counts only when
   psql stopped the script (exit 3) with its own guard's text, `<label>: <n> <text>`, and left no
   journal row. A test checks that each probe's text matches exactly one RAISE of its statement.
   Also fixed: the number of failed probes was returned as the exit code, so three failures read as
   exit 3, "NOT COMMITTED". It is now exit 7. The output reads `refused by its own guard=True`
   instead of `raised=True`.
7. **The lane read-backs had no order.** `journal_readback` ended in a `UNION ALL` without
   `ORDER BY`, and the reviewer's production run came back scrambled. They now end in `ORDER BY 1`,
   like T05's `VERIFY_SQL`. The three texts were run read-only on production today and came back
   sorted: uk-parts Ireland 63, Northern Ireland 4, United Kingdom 6, card_stats divergence 44;
   period-name mismatch 220; site-type-shape residual 4, outside the list 8; every journal count 0.
8. **The commit-state fake answered any stamp.** `FakeProduction` returned the next queued count for
   any `run_stamp = ...`. Reading the rollback stamp in `commit_state` or in the "never apply twice"
   check therefore stayed green. On production that mutant would report a landed write as NOT
   COMMITTED. The fake now accepts only the lane's own stamp, and the landed read-back only with the
   lane's stamp, column and every planned row. The commit-state tests run for all four lanes.
9. **`assert_the_write_landed` and the four loaders had no test.** The loaders are `load_journal`,
   `uk_parts.load_candidates`, `period_name.load_rows` and `site_type_shape.load_rows`. New tests
   cover every read-back disagreement, the loaders against a fake reader that applies the SQL's own
   predicates and refuses unknown ones (`tests/remediation/test_mechanical_loaders.py`), and the
   site_type lane's two-link chain, which restores what the last write replaced.
10. **The UK decision was tested only where the map-units cache exists.** In CI and in the main tree
    that cache is absent, so 38 of the 44 UK tests skipped and the sweep's 27 UK cases would have
    been UNPROVEN.
    Part of the finding was wrong: CI installs geopandas and pyproj (`ci.yml`, since `771243b`), so
    moving code out of the geopandas module was not needed. Every decision guard is now also decided
    on a schematic map of lon/lat boxes (`TestClassifyUkOnASchematicMap`). Northern Ireland has a bay
    on that map, so the 1000 m tolerance is tested inside a unit's envelope, as on a real coastline.
    A GEOUNIT-vs-NAME test writes its own shapefile. Without the cache, 39 UK tests run where 6 did
    before (37 real-data tests still skip, by design). The sweep's UK cases name the schematic tests.

Sweep, run without the map-units cache (the main tree's condition): **`cases: 187  fired: 187
skipped: 0  survived: 0  invalid: 0  unproven: 0  errored: 0`**, exit 0
(`mechanical/evidence/16_mutation_sweep_review.txt`). The first run, with the cache, found one
survivor: the schematic sea point lay outside every unit's envelope, so the 1000 m tolerance was
never measured there. The bay fixed that.
## 2026-09-22 (late) - the gap, the writer's citation check, the lanes and the id repair

Branch `wip/tools-gap`. Every number here was re-derived from the run's own files with the pipeline's
own parser (`discover_stage.parse_answer`) or read from production with `SELECT`s; nothing was written to
production, and no model was called.

### Corrections to numbers this log and HANDOVER carried

The wrong figures stay where they were read, marked as corrected, as this log does elsewhere:

* **WRONG is 4,710, not 4,708.** `parse_answer` over the 24,255 answer files: CORRECT 11,747, WRONG
  4,710, UNVERIFIABLE 7,761, no verdict 37 - sum 24,255. The table above summed to 24,253.
* **The fields add up to 25,020 only with the two classes nobody counted:** 24,255 answered + 760 never
  asked (152 sites whose evidence was over the 64,000-character bound; the reason is only in
  `model.json` `skipped`) + 5 empty model streams (`model.json` `failures`). `ALL_REFUSED.jsonl` names
  the 760 as "the finder bought no call for this field (... not on disk)" and never names the bound.
* **42 answers carry two different `VERDICT:` values** (the first one counts): 21 WRONG then CORRECT, 10
  WRONG then UNVERIFIABLE, 7 CORRECT then WRONG, 4 CORRECT then UNVERIFIABLE (count from the remaining
  map, re-measured: 42). None of them reached the write plan.
* **27 judged sites were shown an evidence page cut at the 61,440-byte cap with nothing saying so**
  (23 `wikidata_entity`, 4 `enwiki` pages). The fetch stage now appends `TRUNCATION_MARKER` to such a
  page (new runs; `runs/mass` is unchanged).
* **The reviewer**: 4,579 asked (4,569 calls + 10 resumed), 2,108 cleared (`applies`), 2,202 refuted,
  173 unresolved, 161 with problems (`review.json` totals). HANDOVER's "confirmed 2,204" is asked minus
  refuted minus unresolved and counts 96 answers with problems as confirmed.
* **994 rows at 952 sites**, not "at 1,022 sites": 1,022 is the planned site count
  (`SELECT count(DISTINCT row_pk) ... LIKE 'phase3:batch-%'` = 952).
* **Spend ~$27, not ~$31**: finder $22.51 over 24,260 calls (`model.json` totals), reviewer $4.63 over
  4,569 calls (`review.json`); the ledger holds $23.72 for every finder call including the gold rounds,
  and $4.65 reviewer. HANDOVER's "finder 25.87" has no derivation in the run's files.
* **Decision 6's "5,569 unverifiable answers"** has no derivation; the answer files give 7,761.
* HANDOVER also said batches of five sites (they hold 15; 333 x 15 + 1 x 9) and 38,456 answer files
  (24,255 answers; 38,456 is answers + 4,579 reviews + 9,622 evidence files).

### The writer never ran the finder's citation check - 44 rows in production fail it

`write_stage` now builds the pages exactly as the finder's prompt was built (`model_stage.evidence_excerpts`
over the batch's `evidence/` and `fetch.json`, then `discover_stage.pages_from_excerpts`) and refuses a
row whose citation `discover_stage.source_problems` rejects (`RULE_CITATION`,
`finder-citation-not-in-evidence`). The dry plan over the whole mass run with that rule (read-only,
into a scratch directory): **1,028 rows instead of 1,074**, refused by rule
`{'reviewer-did-not-clear': 22912, 'report-only-field': 1031, 'finder-citation-not-in-evidence': 46,
'not-a-change': 2, 'not-writable-in-the-columns-shape': 1}`. The 46 are exactly the old plan minus the
new one: **44 are in production** (22 `site_type`, 22 `period_start`) and 2 are among the 80 unwritten.
By kind, over the 46 (my classifier; the remaining map split the non-ellipsis quotes differently, 12 JSON / 19
other): 12 quotes with an ellipsis, 9 quotes of re-typed Wikidata JSON, 24 other quotes not found in
the stored page, 1 cited URL that was never fetched. The rows stay as they are - changing or holding
them reopens HANDOVER section 5 and is the owner's decision:

| # | site | site_id | field | old -> new | stamp | written |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Acrocorinth | `f6d1da2a-f957-47fb-9ccf-58f2197eacc8` | period_start | `-1500` -> `-700` | `phase3:batch-0169:chunk-0001` | yes |
| 2 | Adulis | `0349db41-4fca-4804-b614-e075164512b3` | period_start | `-2000` -> `-1450` | `phase3:batch-0033:chunk-0001` | yes |
| 3 | Alba Fucens | `13120650-2e61-45af-976c-b2e0665c49af` | period_start | `-3000` -> `-303` | `phase3:batch-0151:chunk-0001` | yes |
| 4 | Asclepieion of Athens | `629670bb-a4ec-4a5a-97a5-7623f86f46d8` | period_start | `-1500` -> `-419` | `phase3:batch-0306:chunk-0001` | yes |
| 5 | Brauroneion | `44354857-115b-44d3-b155-cae373565602` | period_start | `-1500` -> `-430` | `phase3:batch-0171:chunk-0001` | yes |
| 6 | Carteia | `504bf30a-c4a0-48e7-8bbc-378b585b59b5` | period_start | `-3000` -> `-940` | `phase3:batch-0309:chunk-0001` | yes |
| 7 | Castlestrange Stone | `6848b0cc-552a-4e7d-b767-281d3658a5ac` | period_start | `-500` -> `-300` | `phase3:batch-0199:chunk-0001` | yes |
| 8 | Chagres and Fort San Lorenzo | `6991377d-fbb5-4c0b-9e24-6dc294033fda` | period_start | `1000` -> `1590` | `phase3:batch-0266:chunk-0001` | yes |
| 9 | Combe Hill, East Sussex | `9ae31b41-d78d-44da-824d-43487ec611f0` | period_start | `-4500` -> `-3001` | `phase3:batch-0244:chunk-0001` | yes |
| 10 | Dykyi Sad Archaeological Site | `86c101ad-fcdb-413a-8aec-6aad2d1574e7` | period_start | `-1500` -> `-1250` | `phase3:batch-0300:chunk-0001` | yes |
| 11 | Er-Grah Tumulus | `c2628a93-7c87-4a98-8d13-8301f7063403` | period_start | `-4500` -> `-5000` | `phase3:batch-0246:chunk-0004` | yes |
| 12 | Foso e Interior Citadelle De Victoria | `fad5c73f-8725-47d0-b13c-372fefba62ea` | period_start | `-3000` -> `1500` | `phase3:batch-0029:chunk-0001` | yes |
| 13 | Madjedbebe | `e3df9803-11c3-47ca-8cd2-39265d32470b` | period_start | `-500` -> `-63000` | `phase3:batch-0091:chunk-0005` | yes |
| 14 | Nokalakevi | `a621b66e-1fda-41b4-9c34-d1a3e7486bd5` | period_start | `-500` -> `-1000` | `phase3:batch-0133:chunk-0001` | yes |
| 15 | Phanagoria | `3e9107fa-e54c-407c-aaa7-a6f198e48c0f` | period_start | `-1500` -> `-543` | `phase3:batch-0150:chunk-0001` | yes |
| 16 | Porte Noire | `9b4f553e-24bf-4860-9790-4f8184426360` | period_start | `1` -> `176` | `phase3:batch-0095:chunk-0001` | yes |
| 17 | Prince of the Lilies | `e4631001-b923-4f36-be7f-c961f9e287ba` | period_start | `-3000` -> `-1550` | `phase3:batch-0102:chunk-0001` | yes |
| 18 | Quoyness Chambered Cairn | `657dbfe1-7b3f-4548-93c6-99be8674a6ff` | period_start | `-4500` -> `-3000` | `phase3:batch-0135:chunk-0001` | yes |
| 19 | Skara Brae | `2cbc1c11-5750-4b96-973b-7f1f8c847003` | period_start | `-4000` -> `-3180` | `phase3:batch-0136:chunk-0002` | yes |
| 20 | Skopje Aqueduct | `d570a6d4-f4a9-4a82-856f-e66c4b55d056` | period_start | `1` -> `1600` | `phase3:batch-0140:chunk-0002` | yes |
| 21 | Temple of Hera, Olympia | `4c7f6521-241f-48c0-93da-f8d7893f5446` | period_start | `-3000` -> `-600` | `phase3:batch-0259:chunk-0001` | yes |
| 22 | Tomb of Leonidas | `f80ffef9-a3c9-472f-a429-dd591ce7372b` | period_start | `-1500` -> `-430` | `phase3:batch-0053:chunk-0005` | yes |
| 23 | Amantia | `c720b595-63d5-4f41-ba14-47ebf79c6098` | site_type | `Temple complex` -> `City/town/settlement` | `phase3:batch-0033:chunk-0004` | yes |
| 24 | Ashley, Northamptonshire | `c8370b05-1d32-491a-a735-344f6534b4d8` | site_type | `Residence/villa/farmhouse` -> `City/town/settlement` | `phase3:batch-0111:chunk-0001` | yes |
| 25 | Barclodiad y Gawres | `643b79ca-d609-475e-839e-28c9858fa00a` | site_type | `Necropolis/tombs complex` -> `Tomb` | `phase3:batch-0121:chunk-0007` | yes |
| 26 | Butrint | `17c94d52-2df2-44ba-83f1-41c26ee6eea3` | site_type | `Temple complex` -> `City/town/settlement` | `phase3:batch-0266:chunk-0001` | yes |
| 27 | Dougga | `867e1487-3a96-4974-ae74-eaf5448927b9` | site_type | `Temple complex` -> `City/town/settlement` | `phase3:batch-0024:chunk-0001` | yes |
| 28 | El Kab | `a71d8ba8-3ca0-4845-a519-609b286b4eb3` | site_type | `Temple complex` -> `Archaeological site` | `phase3:batch-0060:chunk-0004` | yes |
| 29 | Hammam Essalihine | `9212f10a-d866-4d70-bb38-0cbffc49a2c5` | site_type | `Megalithic structures` -> `Bath` | `phase3:batch-0061:chunk-0001` | yes |
| 30 | Huilai Monument Archaeology Park | `316b3d27-1295-41ce-a5c0-3b9c8251647e` | site_type | `City/town/settlement` -> `Archaeological site` | `phase3:batch-0315:chunk-0001` | yes |
| 31 | Jubail Church | `b7319c81-70e7-4c3b-9b06-b39bf9cc7dd0` | site_type | `Temple complex` -> `Church/cathedral` | `phase3:batch-0129:chunk-0002` | yes |
| 32 | Lohum Jo Daro | `8718faea-a442-445c-b369-c8572ec0be7e` | site_type | `City/town/settlement` -> `Archaeological site` | `phase3:batch-0233:chunk-0001` | yes |
| 33 | Manikyala Stupa | `dd425ddf-0128-45e2-84dd-c442978149e3` | site_type | `Temple complex` -> `Monument` | `phase3:batch-0281:chunk-0001` | yes |
| 34 | Menelaion | `041bcb70-5676-4ef5-bab2-07f2153098c0` | site_type | `City/town/settlement` -> `Archaeological site` | `phase3:batch-0099:chunk-0001` | yes |
| 35 | Mulinuyuq | `c8855169-8cd1-40ae-9f2a-cfc8be715d8b` | site_type | `City/town/settlement` -> `Archaeological site` | `phase3:batch-0013:chunk-0005` | yes |
| 36 | Preah Palilay | `41705e94-8ffd-45f3-943e-df6fac317144` | site_type | `Temple complex` -> `Temple` | `phase3:batch-0106:chunk-0003` | yes |
| 37 | Pukara, Coporaque | `64137ead-762b-4621-a59c-5c7395ef4826` | site_type | `City/town/settlement` -> `Archaeological site` | `phase3:batch-0015:chunk-0001` | yes |
| 38 | Sidrón Cave | `a4ac2a6f-0159-447e-a6d2-7300fbc986ef` | site_type | `Megalithic structures` -> `Cave Structures` | `phase3:batch-0191:chunk-0001` | yes |
| 39 | Sudheran-Jo-Thul | `6fa3017d-6545-48c6-b54b-c041b9f860b8` | site_type | `Temple complex` -> `Monument` | `phase3:batch-0098:chunk-0001` | yes |
| 40 | Takht-i-Bahi | `49037cfb-5c88-4863-aa23-c317502fc6d8` | site_type | `Temple complex` -> `Monastery` | `phase3:batch-0218:chunk-0001` | yes |
| 41 | Thul Hairo Khan | `16419886-7d47-4007-86ae-2fef6dd1fa38` | site_type | `Temple complex` -> `Sacred site` | `phase3:batch-0167:chunk-0001` | yes |
| 42 | Ugarit | `4a1c0e1a-7ef6-4e1f-bbdb-6334304bcf52` | site_type | `Megalithic structures` -> `City/town/settlement` | `phase3:batch-0288:chunk-0001` | yes |
| 43 | Wayna Q'inti | `660397b7-a480-4ae7-9742-5ff0970c8e31` | site_type | `City/town/settlement` -> `Archaeological site` | `phase3:batch-0238:chunk-0001` | yes |
| 44 | Xpuhil | `27c3bfef-7374-4231-9c14-3c1c09ee6ec2` | site_type | `City/town/settlement` -> `Archaeological site` | `phase3:batch-0219:chunk-0001` | yes |
| 45 | Uruk | `d0b9e72f-73a8-4671-a01f-5cafa6e53bf8` | period_start | `-4500` -> `-3200` | - | no (held / boundary) |
| 46 | Adulis | `0349db41-4fca-4804-b614-e075164512b3` | site_type | `Temple complex` -> `City/town/settlement` | - | no (held / boundary) |

### The tools are lanes, and three defects came out of giving them tests

`output/remediation/tools/` now names a *lane* (`lanes.py`: run dir, dry plan, apply root, holds,
reviewer logs and journal stamp pattern at once; `--lane mass` is the old default). Defects found and
fixed on the way, each with a test that fails without the fix:

* `review_all.py`'s $8 ceiling never stopped anything: it broke out of `pool.map`, which had already
  queued every batch, and the pool then ran them all (a fake batch: 10 of 10 ran after a STOP at the
  third). It also compared the whole ledger's reviewer spend (already $4.65) with the ceiling.
* `write_gate.py` writes rows by their *position* in the writer's plan (`--chunk K`). A rows file built
  before the writer gained a rule would shift every later position onto another row; the gate now
  re-plans each open batch dry and refuses unless the change keys match in order.
* `make_holds.py` keys its 72 holds by line number of `ALL_ROWS.jsonl`; it now refuses a rows file whose
  change-key sequence is not the one those numbers were read against (sha256 `0b7ad95d...`).

**The acceptance follows the journal chain** (`verify_writes.py`): for every row the lane touched or
planned it reads every journal row of every stamp in `id` order, demands a continuous chain ending at
the live value, and reports a lane row a later lane re-wrote as *superseded by that stamp* instead of as
a deviation. Run read-only against production on 2026-09-22 with the mass lane's own `ALL_ROWS.jsonl`:
**994 carried, 0 superseded, 80 unchanged, 0 moved, 1,022 of 1,022 sites read, ERGEBNIS: 0
Abweichungen** - the 994/80/0 of the write wave, reproduced.

### WDQS rewrites dates - measured, and why the narrowed route does not read dates there

Q37200 P571 is `-2560-00-00T00:00:00Z` (precision year, Julian) through `wbgetclaims`, and
`-2559-01-01T00:00:00Z` through WDQS (XSD 1.1 counts a year 0). Q12506's Julian `+0537-12-27` is
`0537-12-29` through WDQS (converted to Gregorian). Century- and decade-precision dates came back
unchanged (Q10288 `-0500`, Q5690 `-0900`). So the narrowed Wikidata route reads P571, P580, P582 and
P1619 through `wbgetclaims` and only the item-valued properties and the coordinate through WDQS.

### The gap plan, and its measurement

`output/remediation/gap/GAP_PLAN.md` is the record: 802 questions over 194 sites, 13 batches `gap-NNNN`,
from a fresh production export (2026-09-22T21:46:19Z). Measured with a scratch fetch (1,152 read-only requests over
a first pass and one re-fetch) and the discover stage's own evidence selection: **all 152 over-bound sites now fit under
64,000** (median 78,134 -> 29,763, max 63,279), so the bound stays and the 14 sites with an English
extract cut at the page cap are judged on it with the truncation marker. WDQS answered seven `429`
(`Retry-After: 120`) and six timeouts with the first query form; the explicit form and a one-second
WDQS pace left 0 failed targets after one re-fetch.

### Twenty curated sites point at the wrong Wikidata item

Q309 "history" (7 sites), Q23498 "archaeology" (2), Q11635 "theatre" (3), a rock band for Stabiae,
Persepolis for the Tomb of Artaxerxes III, the World Heritage parent for five Gyeongju belts, Mundo
Perdido for Tikal. What the data shows about the cause: `external_ids.py` resolved each id from the
curated `source_url`, and for the 13 generic ids that URL itself names the generic article
(`/wiki/History`, `/wiki/Archaeology`, `/wiki/Theatre`, `/wiki/Temples_(band)`). For two of them the
stored name redirects to exactly that section of another article (`Estipeon` -> `Štip#History`,
`Castellum Onagrinum` -> `Begeč#Archaeology`), which looks like a section fragment taken as a title;
the other eleven show no such trace, so how their URLs were made is not established. Each site was
re-resolved one at a time; the reviewed repair (26 row changes at 19 sites, Tikal unresolved) is rendered with evidence,
statement, rehearsal and undo in `output/remediation/qid_repair/`, pre-flight-checked read-only
(26 rows, 0 deviations), **not applied**.

### Mutation proofs

`mutation_sweep.GAP_MUTATIONS`, run through the sweep's own `main`: **19/19 caught**, the tree
byte-identical to the sweep's start for 8 files - the writer's citation and rerun checks, the cut-page
marker and its UTF-8 trim, the dates-not-through-WDQS rule, the WDQS pace and query form, the route and
sitelink guards, the gate's lane and stale-plan guards, the reviewer ceiling, the chain acceptance,
the hold pin, the repair statement's one-row guard and the gap plan's withheld ids.

## 2026-09-23 - review round on the gap tools: what was found, what was fixed

Two reviewers read the gap-tools branch. Every finding was re-checked before anything was changed;
all of them held. What changed, with the measurement behind each:

**The write gate walked past three things it had seen.** `write_stage.apply_chunk` writes none of a
chunk whose pre-flight finds a moved row and exits 0; the gate then still wrote `APPLIED.json`, so a
resume never looked again, and the acceptance counted the unwritten rows as withheld. A step read-back
with deviations went on to the next hundred, and a hold whose change key names no planned row held
nothing while the count said it held one. Now every writer report is checked against the rows the call
was handed (written, journalled, matched_0, skipped chunks); a mismatch writes `STOPPED.json`, never
`APPLIED.json`, and ends the wave; a later run refuses a stopped batch; a read-back deviation ends the
wave; a stray hold is refused before anything is planned. The gate also stops over-counting sites in
row-by-row mode (each call's report counts the whole batch's sites; the gate now counts the rows it
wrote).

**The acceptance was too forgiving.** It accepted a lane write of a value nobody planned, a lane that
wrote one row twice, a planned row changed by *any* other stamp, and - with a wrong `--stamp-like` -
every row as "moved". It now requires, per row: a lane journal row carries exactly the planned old and
new value, is the lane's only write of the row, and is not a withheld row; a planned row without a lane
journal row must be withheld (a hand-read hold or a boundary refusal, computed with the gate's own
`withheld()`), else it is `NOT WRITTEN`; a later stamp may supersede or move a row only if the operator
names it (`--allow-stamp`, for the UK lane `2026-09-22_mechanical-uk-parts`). Re-run read-only against
production on 2026-09-23 with the mass lane's own rows and holds: **994 carried, 80 withheld and
unchanged (72 held + 8 refused at the boundary - exactly the 80 of the wave), 0 moved, 0 superseded,
1,022 of 1,022 sites read, RESULT: 0 deviation(s).** The docstring no longer claims "strictly
stronger" for the two cases it accepts by design.

**The plan a lane was written from is now pinned.** `write_dry_all.py` without flags overwrote the
mass lane's 1,074-row plan with a 1,028-row re-plan, after which the acceptance read 44 correct
production writes as 44 deviations (both reproduced). `write_dry_all.py` now refuses to write into the
dry root of a lane that has an `APPLIED.json`; `verify_writes.py`, `write_gate.py` and `make_holds.py`
refuse a rows file that is not a written lane's pinned plan (`lanes.REVIEWED_PLAN_KEYS_SHA256`, the
mass lane's `0b7ad95d...`). The builder's regenerated 1,028-row file is now refused by name instead of
producing 44 deviations.

**One way to the database.** `lanes.psql`, `lanes.json_rows`, `qid_repair._text` and
`write_gate.psql_json_rows` were copies of the writer's `run_sql`, `_json_rows` and `_sql_text` (the
`json_rows` copy without the is-an-object check). The tools now use the writer's, re-exported through
`lanes.py`; `gap_plan.batches` is `run.assign_batches` with a new `prefix` keyword (its size guard
included).

**A sitelink badged as a redirect is refused.** Verified with the project User-Agent: Q4810863 (the
item the repair gives Estipeon, a gap site) links enwiki `Astibo` with badge `Q70893996` ("sitelink to
redirect"), and `Astibo` redirects to `Štip#History` - after the repair, the sitelink step would have
routed Estipeon to the whole article of the modern town, the failure the repair corrects. The five
sitelinks the gap plan resolves today carry no badge. `Q70894304` ("intentional sitelink to redirect")
is refused the same way; a sitelink without its `badges` list is refused, not read as unbadged.

**The truthy page is cited by a short address.** The narrowed route's WDQS GET address is 1,951
characters for Q10288, and the citation check matches URLs byte for byte. The mass run's URL fidelity,
measured over its answer files: enwiki 4,672 exact / 9 miss (0.19 %), wikidata_entity 865 / 2
(0.23 %), at 130-220 characters - no data exists for 2 KB. The target now shows and is cited as
`https://www.wikidata.org/wiki/<qid>#wikidata_truthy` (`Target.url`) and still asks WDQS
(`Target.query_url`); the ledger and the fetch report record the address actually requested. The
prompt texts are untouched.

**Smaller ones.** `gap_plan.enwiki_missing` read any answer without `query.pages` as "the article
exists"; it now refuses an error body, `{}` and an `invalid` title (all 5,004 enwiki files of the mass
run: 3,699 articles or cut pages, 1,305 missing, 0 of another shape). The fetch stage's docstring no
longer claims `runs/mass` stores as before: the truncation marker applies to every page stored from
now on. `vlm_pilot/rejected_kinds.py` resolves images through the exact-case tree listings again
(the ruff fix had deleted them; the exact-case lookup reproduces all 30 versioned `resolved_path`
values). `qid_repair.py check`/`verify` compare APPLY, REHEARSAL and ROLLBACK byte for byte with the
rendered statements instead of trusting the digest header; the renderer still reproduces the versioned
`APPLY.sql` and `ROLLBACK.sql` byte for byte. New output and comments are English; the acceptance
prints `RESULT: N deviation(s)` (the token the mechanical lane's branch uses).

**Mutation proofs.** `mutation_sweep.GAP_MUTATIONS` (19) and the new `REVIEW_MUTATIONS` (37), run
through the sweep's own `main` with the main venv: **56/56 caught**, the tree byte-identical to the
sweep's start for 11 files. Every guard above has its own entry, including the ones the reviewers'
mutants survived: the gate's stale-plan call in `main`, the replan's run directory, the chain-missing
link, the sitelinks answer that omits an id, the census's duplicate question, the record-vs-sitelink
qid check, the repair's curated-site guard and invariant 1, and the rerun list's type check.

One older entry had stopped landing: the narrowed-route change rewrote `if feature ==
FEATURE_WIKIDATA_ENTITY and not qid:` as `if slot == ...`, so "no qid, no qid skip" pointed at nothing
and a full sweep would have died on its anchor assert (the gap branch ran only its own 19 entries).
The anchor is corrected (1/1 caught), and `test_phase3_sweep.py` now reads every entry's anchor and
test name against the tree in the gate suite, so the next such drift is red before anyone runs a
sweep: 176 entries, 0 stale.


### 2026-09-23 - applied today, and the search pilot that failed

**Applied to production, each with rehearsal, guard probes on production, journal and a rehearsed
reversal** (evidence under each lane's `evidence/`):

| lane | rows | stamp | read-back |
|---|---|---|---|
| site_type shape repair | 3 | `2026-09-22_mechanical-site-type-shape` | APPLY OK; 5/5 guards refused |
| migration 0022 (key lookup) | - | deploy `c3564e3` | function body replaced; 0018 selftest 12 ok / 0 failed against it |
| period_name derivation | 220 | `2026-09-22_mechanical-period-name` | APPLY OK; 0 of 5,004 off their bucket; 6/6 guards |
| UK country parts (B9) | 23 | `2026-09-22_mechanical-uk-parts` | APPLY OK; NI 4 -> 26, UK 6 -> 0; 6/6 guards |
| external-id repair | 26 at 19 sites | `2026-09-22_external-id-repair` | `verify: 26 rows, 0 deviation(s)` |

The phase-3 acceptance after them: 994 journalled, 80 not written, 1,022 sites, **0 deviations**, with 5
fields superseded by the UK lane and 3 by the site_type lane.

**Why 0022 exists.** `apply_remediation_change()` located its row with `WHERE %I::text = $2`, which
casts the key column and makes the primary-key index unusable: EXPLAIN on production, Seq Scan cost
232,500 against an Index Scan at 8.45, twice per call. The period_name lane's 220-row rehearsal hit
its 120 s statement timeout; after 0022 the same statement ran in 116 ms.

**The gap run.** 13 batches, 194 sites, 802 questions (152 over-bound sites x 5, 5 empty streams, 37
unreadable verdicts), built from a fresh export after the external-id repair: all 194 fit the evidence
bound with the narrowed Wikidata claims (0 before), 802 answers, 0 failures. Its reviewer and writes
wait for the fixes below.

**The search pilot failed** (thresholds sealed beforehand in `phase3_runner/SEARCH_PILOT.md`, sha256
`fa0287afde951b7d1e12901954ac444dd51c7e79b30c439d048dbfaf3b64d2e5`; scorer
`output/remediation/tools/score_search_pilot.py`; result `phase3_runner/SEARCH_PILOT_RESULT_1.txt`).
59 fields the mass finder called UNVERIFIABLE on 26 gold sites, 48 MiniMax searches, 59 finder calls:
the search moved 20 of 59 to a decision, and three of the four thresholds failed - 1 answer cites a
quote that is not in its evidence (Font dels Coms), 3 decided WRONG where the human says CORRECT
(Las Labradas and Aubrey Holes period_start, Odeon card_description), agreement 14/20 = 70 %.
Transport passed (0 unaccounted slots). Quota: about 1,900 weekly tokens per search (per-batch
median; 19,230 as an upper bound that charges Lyra's concurrent use to the search).

The thresholds stay as sealed; the definitions are not loosened after the fact. What the cases show:

1. **Bucket arithmetic at the boundary.** The finder wrote "-4500 falls in `< 4500 BC`" and "500 falls
   in `1 - 500 AD`"; by `categorize_period` (lower bound inclusive) both are in the bucket the
   proposal is in or next to. Aubrey Holes' -4500 -> -4000 is a same-bucket change, which the gold
   standard and the reviewer's own brief say is not an error - and the reviewer cleared it.
2. **A snippet is not a page.** Las Labradas' "1000 B.C. - 300 A.D." came from a travel page about
   another site (Toro Muerto); the Font dels Coms quote is not in the Zenodo snippet and its other
   citation was never fetched.
3. **The reviewer's flag contradicts its own WHY line.** Lake Mungo: "Neither half holds ..." with
   `REFUTED: NO`; Odeon: "the stored text is not shown wrong" with `REFUTED: NO`. The mass lane met
   the same class by hand (the 72 held rows).

Under the writer's own rule (`applies`: asked, refuted is False, no problems) Las Labradas would not
have been written and the Odeon card text is report-only; Aubrey Holes would have been. No search-lane
row is written until (a) a deterministic period-bucket gate in the writer, (b) a search hit counts only
when its quote occurs on the fetched page, and (c) a reviewer whose WHY line names a failing half
while `REFUTED: NO` holds the row - and a new pilot in a new run directory passes.


### 2026-09-23 - the three writer fixes the failed pilot asked for

Branch `wip/search-fixes`. All three apply to every phase-3 write lane (mass, gap, search); the frozen
prompts (`QUESTION_TEMPLATE`, `FIELD_CLAUSE`, `REVIEWER_QUESTION`, `PARTIAL_EVIDENCE_NOTE`) are
byte-identical (`test_phase3_frozen.py`), and the sealed pilot thresholds are unchanged.

**(a) The period-bucket gate** (`write_stage.RULE_SAME_BUCKET`, `period-start-inside-the-stored-bucket`).
A `period_start` row whose proposed value lies in the stored value's bucket - `pipeline.utils.text.
categorize_period`, the card's own function, lower bound inclusive - is refused. Re-measured read-only
from the production journal (`remediation_change_log`, `run_stamp LIKE 'phase3:batch-%'`,
`column_name = 'period_start'`): **170 of the 389 `period_start` rows the mass lane wrote are
same-bucket moves** - the critic's 170, key for key the same rows as the pinned plan gives. They are
not changed. 19 of the 35 held `period_start` rows are same-bucket too.

**(b) A search hit counts only through its fetched page** (`phase3/hit_stage.py`, `run.py verify-hits`,
the fourth stage of a search plan: `prepare,search,judge,verify-hits`). After the finder, the page
behind every hit a finder answer cites is fetched (per-site cap 8, per-host pace, one ledger line per
attempt, write-once under `hitpage.<sha1(url)[:12]>`, failures in `hitpages.json` in `fetch.json`'s
shape). The reviewer is shown it (bounded: 6,000 characters per page within the room the evidence
bound leaves, with a cut marker), and a citation of a hit is checked against the whole fetched page,
never the snippet (`discover_stage.pages_from_excerpts`). A hit page that could not be fetched or is
not text refuses the row (`RULE_HIT_UNVERIFIED`, `search-hit-page-not-verified`); a cited hit nobody
tried to fetch raises in the reviewer and the writer. The page reader is Lyra's own, moved unchanged
from `pipeline/lyra/handlers/content_fetch.py` to `pipeline.utils.text.extract_text_from_html`, plus
`html.unescape`. Measured on a copy of `runs/search-gold`, the stage run live with the project
User-Agent: 20 cited hits in 25 citations, 20 requests, 13 HTML, 2 PDFs (unreadable), 5 x 403 (four
Cloudflare, one CloudFront); 8 of the 25 quotes occur on the fetched page, 24 in the snippet the
finder was shown (17 in the snippet only). *Corrected by the fixer's review:* the page cap governs
nearly every result, not only the three Wikipedia articles - **14 of the 15 stored pages were cut at
the 60 KB cap** (only comusantjulia.ad came back whole), and **all 9 citations whose readable page
does not carry the quote are on cut pages** (pathere.org x2, nilecruisetrips.com, travelshelper.com
x2, andbeyond.com, and the Wikipedia articles on Lake Mungo, the Odeon and Ahu Tongariki, each
2,400-4,100 characters of mostly navigation). Such a row was refused as
`finder-citation-not-in-evidence`, which reads like a fabricated quote; it is now refused as
`search-hit-page-not-verified` with a reason naming the cut (`write_stage._hit_page_refusal`). The
cap binds and is not raised.

**(c) The reviewer contradiction hold** (`write_stage.RULE_REVIEW_CONTRADICTS`,
`reviewer-why-names-a-failing-half`; the phrases are `review_stage.FAILING_HALF_PHRASES`, 18 of them,
each bound to its subject). Measured with `output/remediation/tools/measure_review_holds.py` on the
mass lane's pinned plan: **recall 51 of the 72 hand holds**; **77 of the 994 written and accepted rows
would have been held**. Read one by one, 10 of those 77 use the phrase against their own content (a
false hold), 5 say both, and 62 do say the stored value is not shown wrong or the proposal is
contradicted - the class the hand-read held 72 of and missed there. They stay as they are (and are
listed for Martin: `HUMAN_ONLY.md` B11). The bucket gate and the hold together catch 57 of the 72
hand holds; what neither names is the finer-type and the unverifiable-quote class, which stays the
hand-read's. *Added by the fixer's review:* the false holds are not spread evenly. Per phrase, on the
written rows: **"neither half holds" 4 of 7** (Presa-Tusiu, Annaghmare, Chacamarca, La Almoloya -
each goes on to say the stored value is wrong or the proposal supported), **"the stored value is not
contradicted" 4 of 9** (Apollonia, Ashley, Court Hill, Erebuni), "the reason fails" 1 of 4 (Pen
Dinas), "does not show the stored value wrong" 1 of 10 (Asclepieion of Athens); the other fourteen
phrases hold no written row falsely. A row one of those four holds goes to the hand-read
(`review_stage.HAND_READ_PHRASES`, `HUMAN_ONLY.md` B12) rather than counting as a settled refusal.

**The first pilot under the new writer** (*corrected by the fixer's review*; the first version named two
lost human-WRONG fields where there are three, and counted Lake Mungo `period_start` as a catch).
`score_search_pilot.py` prints the sealed block exactly as sealed (it reproduces
`SEARCH_PILOT_RESULT_1.txt` byte for byte, threshold 1 over what the finder was shown:
`discover_stage.finder_pages`), beside it what the writer itself would write, and - since the review -
what each rule refuses on its own (`rule_cost`: each rule switched off alone at its one entry point).
On the verified copy of `runs/search-gold`: **0 rows written, 0 harmful**. The writer *before* the
three rules (`git archive 59f21bb`, run read-only over the real `runs/search-gold`; `rule_cost`'s
all-off line gives the same rows) writes **5 rows: 3 agree** with a human WRONG (Lake Mungo
`period_start` -500 -> -50000, Ahu Tongariki `period_start` 1 -> 1000, Cueva de los Murcielagos
`period_start` 1 -> -6000), **1 is unsupported** (Lake Mungo `site_type` Geological interest ->
Archaeological site, human UNVERIFIABLE) and **1 harmful** (Aubrey Holes `period_start` -4500 ->
-4000, human CORRECT). What each rule changes on its own:

| rule switched off alone | rows it alone refuses | human verdict |
|---|---|---|
| (a) period-bucket gate | none (Aubrey Holes falls to (b): its hit is a cut PDF; (a) refuses it only with (b) off) | - |
| (b) hit page | Ahu Tongariki `period_start` (its scispace hit answered 403) | WRONG |
| (c) contradiction hold | Lake Mungo `period_start` ("Both halves fail: the evidence actually supports a value around -500"), Cueva `period_start` ("The stored value 1 is not shown wrong") | WRONG, WRONG |

Lake Mungo `site_type` is refused by both (c) and (b) (its Britannica hit answered 403), so no single
switch releases it. The Odeon card text is report-only and was never writable; Las Labradas
`period_start` is not cleared (the reviewer's `SOURCE:` on a `NO`). **Net: all 3 agreeing writes are
lost, to stop 1 harmful and 1 unsupported write.** Lake Mungo `period_start` is not a catch by (c):
the gold standard calls the stored -500 WRONG, the finder was right and the reviewer's sentence was
not. On this pilot (c) blocks no write that (b) or the older rules would not already block, and costs
two correct ones - the rules' price, measured, and the next pilot's `rule_cost` prints its own.

**Mutation proofs.** `mutation_sweep.PILOT_FIX_MUTATIONS` (38 new) plus the two entries whose anchors
moved, through the sweep's own `main` with the main venv: **40/40 caught**, the tree byte-identical for
11 files. Gate: 3349 passed, 98 skipped (data a worktree does not carry), 57 deselected.


### 2026-09-23 - the review of the three writer fixes, and what it changed

Branch `wip/search-fixes`. Eleven findings of an independent review, each checked against the code and
the real data before anything was changed - read-only: the main tree's `runs/mass`, `runs/search-gold`
and gold standard, and the review's own copy of `runs/search-gold` after a live `verify-hits` (project
User-Agent). No production query, no model call, no new fetch. **All eleven held; none was rejected.**
The corrections to the section above are marked in place; what changed:

1. **The first pilot's cost** (the one major finding) - three human-WRONG writes are lost, not two, and
   Lake Mungo `period_start` is a cost of (c), not a catch. Reproduced both ways: `git archive 59f21bb`
   over the real run writes the 5 rows named above, the new writer 0, and switching each rule off
   alone gives the table above. `score_search_pilot.py` now prints that table itself (`rule_cost`,
   each rule off at its one entry point, inside the scorer only - the writer has no switch); its
   sealed block still reproduces `SEARCH_PILOT_RESULT_1.txt` byte for byte.
2. **"the proposed value is contradicted" matched sentences that say the value half holds** - "neither
   the finding's reason nor its proposed value is contradicted" (batch-0237), "contradicted neither by
   Wikipedia nor Wikidata" (batch-0053), "contradicted by the evidence? No" (batch-0151), and a
   conditional, "contradicted only if" (batch-0171). Narrowed by five `nor <owner>` lookbehinds and
   three lookaheads; a half's name in quotes (`the "reason" half fails`, the sentence batch-0053's hand
   hold really turns on) is read now. Recall stays **51 of 72**, written holds **77 of 994**; the `NO`
   answers whose first phrase it is fall from 38 to 35.
3. **Per-phrase false holds** - recorded in the phrase block and above; the four phrases that held
   written rows falsely route their holds to the hand-read (`review_stage.HAND_READ_PHRASES`, the
   refusal carries `write_stage.HAND_READ_NOTE`; `HUMAN_ONLY.md` B12). The hold itself is unchanged.
4. **The page cap** - see (b) above: 14 of 15 pages cut, all 9 missing quotes on cut pages. A readable
   hit page that was cut and does not carry the quote is refused as `search-hit-page-not-verified`
   naming the cap (`write_stage._hit_page_refusal`); the excerpt knows it was cut
   (`EvidenceExcerpt.truncated`, read off `fetch_stage.TRUNCATION_MARKER`, which `gap_plan.py` now reads
   too instead of its own check).
5. **An interrupted `verify-hits` re-ran every stage** - the judge would re-buy each named failure (an
   unreadable stream leaves no answer file). `mass_run.judged_state` is the judge's part of
   `batch_state`, and `StageRunner.stages_for` resumes such a batch at `verify-hits` alone.
6. **The finder could be shown hit pages** - once they were on disk, every caller of
   `evidence_excerpts` got them, the discover stage included. `hit_pages` is now a required keyword:
   `False` for the finder and everything that stands for what it was shown (discover, search and gap
   plans, the sealed threshold, the hit stage's own url lookup), `True` for the reviewer and the writer.
7. **A search hit could point into the workstation's tunnels** - `verify-hits` fetched search-result
   urls with redirects followed and no address check (psql 15432 and the API on 18000 sit on localhost
   here). Lyra's check moved unchanged to `pipeline.utils.http.is_public_http_url`, used by Lyra, by
   `fetch_stage.assert_public_address` (in `HttpFetcher.get` and before the hit stage's request: 0
   requests, `not fetched: ...`) and by a request hook that refuses a redirect hop into a non-public
   address before it is asked. It reads the url as written and resolves no name, like Lyra's: a public
   name that resolves to a private address is not caught.
8. **Guards without a test or a sweep case** - the empty-bucket branch and the `period_start`-only check
   of the bucket gate got writer tests; every exclusion of the phrase set got a negative sentence (real
   where the run has one). Two of them needed more than the review named: "nothing in the evidence
   supports the stored" and "nor evidence supports the stored" were protected by no test at all - the
   Cadbury Hill negative names a bare year, which that phrase never reads.
9. **The rows Martin decides on** - `measure_review_holds.py --out-dir` writes the 77 written rows the
   hold would hold and the 170 written same-bucket `period_start` rows, with key, values and `WHY:`
   line (`HUMAN_ONLY.md` B11). My reading of the 77: 60 name a failing half, 10 are false holds, 7 say
   both.

**Mutation proofs.** `mutation_sweep.REVIEW_FIX_MUTATIONS` (51 new) and the four entries whose anchors
moved, through the sweep's own `main` with the main venv: **55/55 caught**; the builder's 38
`PILOT_FIX_MUTATIONS` again: **38/38 caught**; the tree byte-identical afterwards (10 and 11 files).
A consistency check at import time (every hand-read phrase is a failing-half phrase) was moved into a
test, because it made the module unimportable under the sweep's phrase deletions and the sweep then
proves nothing (pytest exit 4). Gate: **3397 passed, 98 skipped** (data a worktree does not carry),
**57 deselected**; `ruff check`, `ruff format --check api/ pipeline/`, `lint-imports`, `vulture` clean.
## 2026-09-23 - the owner cases B1/B2: decided from data, planned, not applied

The owner's instruction for HUMAN_ONLY section B was "implement the recommendations" of the
remaining-work map (`logs/remaining_map_2026-09-22.json`, block "B - owner cases"). Delivered: the
classifier `scripts/remediation/bcases/` (collect, classify, qid_research, coord_plan, run), its
per-site verdicts in `output/remediation/bcases/`, wave 2 of `tools/qid_repair.py` and the German
section in HUMAN_ONLY. **Nothing was written to production.** Every production contact was a read:
one export `SELECT` of the 5,004 curated rows, three schema/journal counts, `bcases/run.py check`
(51 rows, 0 deviations), `qid_repair.py check --wave 2` (13 rows, 0 deviations) and
`qid_repair.py verify` of wave 1 (26 rows, 0 deviations).

**Superseded in part the same day** by the review below ("the owner cases, reviewed"): the independence
rule, the coordinate plan (17 moves became 9), the B2 class of the Côa Valley row, the duplicate list
(20 losers became 19 plus one held pair) and the wave-2 wording. The numbers in this section are the
first version's.

### What production held when this started

* Wave 1 of the external-id repair had been applied at 03:25 UTC (`2026-09-22_external-id-repair`,
  26 journal rows). Its plan, statements and rules are unchanged; wave 1 still renders its versioned
  `APPLY.sql`, `ROLLBACK.sql`, `PLAN.jsonl` and `PLAN.md` byte for byte, and `verify` reads 0 deviations.
* `unified_sites.scope_status` exists (migration 0020); 0 curated rows carry a value.
* `geom`: 5,003 of 5,004 curated rows hold exactly `ST_SetSRID(ST_MakePoint(lon, lat), 4326)`, one holds
  NULL; `h3_index` is NULL on all of them. There is no trigger, so a coordinate write writes `geom`
  as a third journalled change next to `lat` and `lon`.

### Measured

* **B1 names** (631 T01 name findings, classified against the links the census compared - the
  snapshot's `site_external_ids` - with fresh Wikidata names of all 4,515 linked items): 508 keep
  (354 exact name, 50 same without generic words, 67 descriptive subset, 37 transliteration), 77 wrong
  link (21 generic concept, 43 shared parent or sibling, 8 no coordinate, 5 more than 5 km), 46 to read.
  The remaining-work map's 508/77/46 is reproduced exactly. 18 of the 77 are wave-1 sites.
* **Wave 2**: the other 59 researched one at a time (`bcases/qid_research.jsonl`: the exact-title
  article, every item within 1 km by `list=geosearch`, ten `wbsearchentities` hits). 13 research
  suggestions; 12 taken (1 rule A, 11 rule B: 13 row changes), 1 refused by hand (Ramesses III Temple:
  name and point Karnak, description and source Medinet Habu). 47 stay as they are, each with its
  reason - 24 have no item of their own, 11 have a candidate that cannot prove the 1 km gate, 5 are
  right links shared with a second curated row of the same site, 3 are type records, 2 are right links
  on a wrong point, 2 contradict themselves.
* **Coordinates** (477 T01 findings + 11 B2 rows = 488): 17 move (51 journalled changes; 11 of them
  among the 285 coordinate-only sites), 98 where the stored point is the English article's point,
  210 whose item cannot speak for the point (115 container, 33 linear/areal, 30 shared, 32 other name),
  163 open (102 one witness, 45 two witnesses that are one, 8 disagreeing, 7 none, 1 split). One move
  (Temple of Atargatis, 459 km) lands outside its stored country, Lebanon: a country follow-up.
* **B2** (117): 25 political (B10), 44 coastline/island/border, 4 `Northern Ireland` right, 22 Ireland
  in Northern Ireland (all written since by the UK lane), 6 wrong country (3 written, 3 open), 3 wrong
  coordinate, 12 need a witness, 1 not a country. Identical to the map's classification.
* **Duplicates**: 20 DUP pairs (the plan estimated about 8; plan rule 1 - the measurement is recorded,
  not the estimate overwritten), 20 losers in `DUPLICATES.jsonl`, 0 unresolved groups; 13 stacked
  points carrying 36 sites. PART-OF 59, NEITHER 83, WRONG-ID 19 differ from the map's 65/93/44 because
  wave 1 has since replaced the shared generic anchors.
* Two full re-runs of the classifier with different hash seeds produce byte-identical files.

### Traps found on the way

* en.wikipedia `prop=coordinates` returns at most ten coordinates per request unless `colimit` is set:
  131 of 614 pages came back without coordinates and with a `continue`. The fetch now asks for
  `colimit=max` and refuses any answer that carries `continue`.
* Wikidata answered "cirrussearch-too-busy-error" inside an HTTP 200, and `census.fetch.Fetcher` caches
  every 2xx - the refusal would have been read back from the cache forever. `collect.api_json` asks
  again, bounded, with the cache bypassed; any other API error raises.
* Overpass (`overpass-api.de`) answered five queries from this workstation and then reset every
  connection (`WinError 10054` six times, `curl` exit 35 on `/api/status`). OpenStreetMap is therefore
  not a witness in this run; asking it from the VPS would use production for more than a read.
* The map's K classes matched class words as substrings ("hill" in "hillfort", "city" in "ancient
  city"). Whole-word matching with a site-word exemption gives, on the 285: container 60 (map 88),
  linear/areal 20 (26), shared 7 (7), 1-10 km 135 (105), over 10 km 63 (59). The K classes are a report;
  a write is decided by the witness rule and the name identity. The N7 split moves the same way
  (27 site / 19 locality, map 22/24).
* A first version of the plan rendered the evidence in dict order and its own `check` refused it after
  the round trip through `PLAN.jsonl` (sorted keys). The statement now renders sorted keys; a mutation
  case keeps it that way.

### Decisions taken under "implement the recommendations"

* Coordinates are written as three journalled changes (`lat`, `lon`, `geom`), not two: `geom` has no
  trigger and the prospector's dedup measures on it.
* Two witnesses count once when `P625` is referenced to English Wikipedia (`P143` Q328 or an import
  URL) or when the points are the same within max(5 m, the P625 precision) - anti-pattern 9.
* Name identity (N1/N2) gates a move: a part-of name ("Temple of Apollo, Delphi" on Delphi) would
  otherwise move a temple to its sanctuary's centre.
* Museum objects move to the `P189` find-spot only when stored at the holding museum.
* Survivor rule as the task stated it (content links, sources, older `created_at`) plus the lower id
  as a tie-break, reported as such: the 5,004 curated rows carry only three distinct `created_at`
  values, and the tie-break decides 7 of the 20 pairs.
* The external-id repair's wave 2 keeps rules A/B and adds the map's gate (1 km, a site kind, the
  article's coordinates as rule A's position proof); a research lead is never taken unread.
* `gap_plan.py` still withholds wave-1 links only; the gap lane's plan is built, so wave 2 is named for
  its next re-plan rather than changing a plan in flight.

### Mutation proof

`scripts/remediation/phase3/mutation_sweep.py bcases`: **32/32 caught**, the tree byte-identical to
the sweep's start for 5 files. The older repair and gap-plan entries, re-run after the wave-2 change:
8/8 caught.

## 2026-09-23 - the owner cases, reviewed: 12 findings, what they changed

Two reviews of `wip/bcases` raised 12 findings. Each was checked against the data before anything was
changed; nothing was written to production (every production contact below is a read).

### The cache had to be rebuilt first

The builder's derived cache (`cache/bcases/`, 46 MB) lived only in its worktree, and that worktree had
been removed before the fix started - the re-classification the findings ask for had no input. It was
rebuilt: `bcases/run.py export` (one read-only `SELECT`, 5,004 rows) and `collect` (Wikidata and
Wikipedia with the project `USER_AGENT`, 90 s). With the **unchanged** code the rebuilt cache
reproduces every delivered file (`names`, `coords`, `b2`, `dup_pairs`, `stacked`, `DUPLICATES`,
`COUNTS`) exactly, so the changes below are the code's, not the day's data drifting. The rebuilt cache
sits in the fixer's worktree (`output/remediation/cache/bcases/`, gitignored); the main checkout still
has none, so `test_a_full_reclassification_reproduces_the_delivered_verdicts` skips there until it is
copied or rebuilt. That test could never have passed: it compared `write_all`'s counts, whose
`b2_state` keys were booleans, with `COUNTS.json`, where JSON had turned them into `"false"`/`"true"`.
The keys are now `"open"` / `"written since the census"` (`classify.summarise`, with a test that
needs no cache); the same comparison, run by hand against the main checkout's census data, passes for
the counts and all seven files.

### Findings confirmed and fixed

* **Rounded copies counted as two witnesses (two findings, major).** Confirmed: Castro of Santa Trega's
  article value is its P625 cut to four decimals (5.6 m), Khao Sam Kaeo's likewise (10.7 m), Taq
  Kasra's article is the P625 rounded to whole arcseconds (16.1 m); the 5 m `COPY_M` called all three
  independent and PLAN.md journalled them "(independent)". The Wikipedia witness had no precision at
  all. Now (`classify.independent`): two witnesses are one when either says it was imported from the
  other; when one is the other rounded, truncated, floored or ceiled to the grid its own digits are
  written on (`grid_of`: whole degrees, tenths, arcminutes, hundredths, thousandths, arcseconds,
  4-8 decimals; a value lies on a grid within a thousandth of a step, never more than 1e-8 degrees);
  or when they lie within one arcsecond (30.9 m), one step of either grid, or the P625's declared
  precision. Result: **8 of the 17 moves are open again** - El Kab (its P625 is the article's point
  cut to whole arcminutes, 333 m), Bülövqaya (14 m), Khao Sam Kaeo, Eridu (27 m), Taq Kasra, Temple of
  Atargatis (8 m), Sialkot Fort (P625 = the article truncated to whole arcseconds), Castro of Santa
  Trega. **9 moves, 27 journalled changes** remain; the closest is Yenikale at 34 m (no rounding of
  either, just over one arcsecond). The Temple of Atargatis country follow-up is gone with its move.
  The reviewer's 35 m experiment also caught Yenikale; the principled floor (one arcsecond) does not,
  and El Kab - 333 m apart, caught only by the rounding rule - shows why a distance alone is not the
  rule. On the real data the rounding rule changes wording only (every rounded pair is also within the
  distance), except El Kab; a constructed equator case (a 0.9" truncation on both axes, 39 m) is the
  test that only the rounding rule catches.
* **Guards without a failing test (two findings, major).** Confirmed with a harness that applied each
  mutation and ran both test files whole: 32 of 34 guard mutations survived (97 passed, 1 skipped each
  time; the two SQL-line mutations failed one test each). Every one now has a test that goes red
  without it:
  the linear/areal gate (Via Egnatia), an article of another item / a missing article / a point on
  another globe, a P625 on another globe, a museum object with two find-spots, the tolerance floor
  (precision 0.1 degrees; 0.01 degrees would not widen it - its half is 556 m), the P4656 import URL,
  Q3, the UUID / planned-twice / whole-site / read-UUID checks of the plan, `compare`'s lat, old-geom
  and geom-is-point checks, the statement's `statement_timeout`, every clause of guard 3 and of
  invariant 1, the `entities` / answered-id / JSON / `query` / answered-title checks of the fetch, the
  cache and census-link checks of `inputs`, rule A's redirect / missing / same-item conditions, rule
  B's old-item / N1-N2 / Wikimedia-page conditions, and both research list checks.
* **A matching name hid a wrong link (major).** Confirmed: 72 of the 508 kept names meet Q1 (4), Q2
  (36) or Q4 (35). Every name record now carries `link_suspect` (the tests the link meets on its own,
  with their evidence); `COUNTS.names_keep_link_suspect` = Q1 4, Q2 36, Q4 35, any 72. They are not in
  wave 2 and nothing is written; the class-item links (milecastle, dolmen, nuraghe), Asklepion Kos on
  the shared Asclepeion and The Temple of Artemis (stored in Greece, linked and described as Ephesus,
  388 km) are named for the owner; "Themistoclean Wall" is the lower-case test's false positive.
  HUMAN_ONLY, the qid_repair wave-2 docstring and its PLAN.md now say wave 2 is the rows whose *name*
  did not match.
* **Côa Valley and Siega Verde classed "wrong country" (minor).** Confirmed: its description spans
  Portugal and Spain. In `classify_b2`, a row whose point and P625 agree on the neighbour is
  transboundary (c2, leave) when its own description names both countries; only this row changes
  (b 6 -> 5, c2 44 -> 45). The wider rule "any description naming both" was measured and rejected: it
  would have made Glubochek (51 km inside Moldova, described as in Ukraine) a border straddle.
* **Banias / Caesarea Philippi retired a Golan row (minor).** Confirmed: the only DUP pair whose rows
  name different countries (Syria / Israel). A group whose rows name different countries is now held
  (`DUPLICATES_HELD.jsonl`, with the lines the survivor rule would have written) instead of listed for
  the scope lane: 19 losers, 1 held group.
* **The first P625 instead of the preferred one (minor).** Confirmed on the rebuilt cache: Charax
  Spasinu (Q1063054) holds a preferred P625 1.07 km from the first; Demetrias (Q1150349) likewise.
  `collect.claims_record` now takes the truthy statements (preferred when any, else non-deprecated) and
  records the rank and the count; the witness quote names the rank when there are several. Charax
  Spasinu's reason changes from "the same point" to "disagree, 1.07 km"; no verdict changes. The
  wave-2 research was re-run with the fixed record: one candidate distance moves (Milecastles'
  Q4916035, 102.8 -> 106.6 m), no suggestion changes, and wave 2's statements are byte-identical
  (`qid_repair.py check --wave 2`, read-only: 13 rows, 0 deviations).
* **SQL clauses pinned only by a byte comparison, wave 2 not pinned at all (minor).** The statement
  test now asserts the `statement_timeout` line and every clause of guard 3 and invariant 1; a new test
  compares `qid_repair/wave2/PLAN.jsonl`, `APPLY.sql` and `ROLLBACK.sql` with the renderer and asserts
  the evidence source is wave 2's research.
* **`gate_m` not tied to the research (minor).** A test recomputes each of the 12 settled distances
  from `qid_research.jsonl` (rule B: the candidate's P625; rule A: the P625, or the article's point
  where the P625 is beyond the gate - Harzhorn) and compares to 0.05 m. All 12 match.
* **Duplicated utilities (minor).** `coord_plan` imports `phase3.write_stage.plan_digest` (same
  bytes, so the pin is unchanged); `collect` imports `mechanical.plan._claims`; `classify.fold` is
  built on `pipeline.utils.text.normalize_name` (square brackets kept, as the verdicts were measured -
  the re-classification is identical).

### Measured after the fixes

* Coordinates: move 9 (5 of the 285), stored-agrees 98, not-comparable 210, review 171 (one witness
  102, two that are one 52, disagreeing 9, none 7, split 1). `bcases/run.py check`, read-only against
  production: **27 rows, 0 deviations**.
* Names 508 / 77 / 46 unchanged; B2 c2 45, b 5; duplicates 19 + 1 held; stacked 13 / 36.
* Mutation proof: `mutation_sweep.py bcases` **86/86 caught** (the builder's 32, one anchor moved to
  the new independence line, and 54 new), the tree byte-identical to the sweep's start for 7 files;
  the repair and gap-plan entries re-run after the wave-2 wording change: 8/8.

## 2026-09-23 - external-id repair, wave 3: the kept names on a suspect link (planned, not applied)

Waves 1 (26 rows) and 2 (13 rows at 12 sites, stamp `2026-09-23_external-id-repair-wave2`) are
applied. Wave 3 took the 39 B1 name findings whose name matched (`group` keep) while their link met
Q1 (generic concept) or Q2 (item shared with other curated rows) on its own - `link_suspect` in
`bcases/names.jsonl`: Q2 33, Q1 3, Q1+Q2 1, Q2+Q4 2. The 33 with Q4 alone (item only far away) are a
coordinate question first and stay out. **Nothing was written to production.** Production contacts,
all reads: one `site_external_ids` read of who links each of the 33 linked items today (after wave 2)
and the 3 candidate items (Q22681531, Q2717874 and Q22987223 are linked by no row), and
`qid_repair.py check --wave 3`.

### Research

`bcases/run.py research --suspects` (new flag; same `qid_research.research` and `suggest`, rule for
rule, same 1 km gate) wrote `bcases/qid_research_suspects.jsonl`: per site the exact-title article,
every item within 1 km (`list=geosearch`), ten `wbsearchentities` hits, plus `link_suspect`,
`shared_with` (the export's other curated rows on the same item, with distances), country and
description. Suggestions: rule A 0, rule B 4, unresolved 35. Every record was read by hand; two ad-hoc
`wbsearchentities` lookups (cached, project user agent) were added as evidence: "milefortlet" and four
Thasos-Artemis queries.

### Outcomes (`qid_repair.py --wave 3`, `output/remediation/qid_repair/wave3/`)

| outcome | sites | what it means |
| --- | --- | --- |
| replace | 2 | rule B under the gate: Ancient Theatre of Megalopolis `Q823721` (the modern town) -> `Q22681531` (the theatre, 31 m); Siega Verde `Q552106` (the Côa Valley, Portugal, 53.5 km) -> `Q2717874` (Siega Verde, 16 m). Titles unchanged (no own English article; `Siega_Verde` redirects to the joint Côa article). 2 row changes |
| keep-type | 3 | Dolmens of Sardinia, Nuraghes of Sardinia, Milefortlet - Hadrians Wall: the record is the type. Wikidata has no milefortlet class - its milefortlets are instances of Q1568283 and `Milefortlet` redirects to `Milecastle` - so the task's "different type" does not hold |
| duplicate-candidate | 23 | the link is right and another curated row is the same site: 12 pairs already in `DUPLICATES.jsonl`, Caesarea Philippi is the held Golan pair, the rest (Twin Gates/Porta Gemina, Birdoswald, Biniai Nou, Killarumiyoq, Obelisk of Ark, Madain Saleh/Hegra, Enkomi/Engomi, Amyntas) are named in the plan |
| link-right | 5 | Themistoclean Wall (Q1 misread a specific wall without P625), Psychro Cave and Locmariaquer Megaliths (their other row's link was replaced by wave 2 - production holds each item on one row now), Pandavleni Caves (the other row is one of its caves), The Temple of Artemis-Selçuk (the other row is the Thasos record) |
| unresolved | 6 | The Temple of Artemis, Asklepion Kos, Asklepieion - Pathos, Caunos Tombs of The Kings, Bosnian Pyramid of the Sun, Bosnian Pyramid of Love |

* **Two rule-B leads refused by hand:** Madain Saleh's Q12239409 is the Hejaz railway station named
  after the site; Caesarea Philippi's Q2484244 would split the held Banias/Caesarea Philippi pair by
  link and settle what the owner holds by country (B10).
* **The Temple of Artemis (a939e800):** point and country are Limenas on Thasos (40.7802, 24.7156),
  description and link are the Ephesus temple (Q43018, 388 km), which the Selçuk row carries too. No
  Thasos Artemis item passes rule B: none of the 15 items within 1 km names Artemis, and
  `wbsearchentities` finds nothing for "Artemision Thasos", "Sanctuary of Artemis Thasos", "Temple of
  Artemis Thasos" or "Artemision (Thasos)". Unresolved: Ephesus makes it a duplicate of e60fc487,
  Thasos leaves it with no item to link - the owner's decision.
* **The two Asklepieia** stay on the class Q731841 although each has an obvious item (Q2655433 at Kos,
  258 m; Q82073722 at Paphos, 20 m): the names match only descriptively ("Asklepion (Kos)", N3) or not
  at all ("Pathos" for Paphos), and wave 2 refused the same kind of spelling lead (Sun Temple of
  Niuserre). They are the strongest leads for the owner.
* **Enkomi / Engomi:** both rows describe the one Bronze Age city and link the village item Q1343280.
  The site's own item Q22987223 holds two normal-rank P625 1.9 km apart; the one the research reads is
  2.07 km from "Enkomi" (beyond the gate) and 93 m from "Engomi Ancient City Ruins", for which
  Wikidata's geosearch (indexing the other point) returned no candidate at all.

### Check, render, proofs

* `qid_repair.py check --wave 3`, read-only against production: **2 rows, 0 deviations**.
* Waves 1 and 2 render byte for byte what is committed (`PLAN.jsonl`, `PLAN.md`, `APPLY.sql`,
  `ROLLBACK.sql`; a new test compares all four, CRLF of this checkout normalised).
* Tests: 6 new in `test_bcases.py` (selection, sharers, the suspect record with a scripted fetcher,
  the `--suspects` file and flag, the delivered research re-judged by `suggest`), 9 new in
  `test_remediation_tools.py` (wave-3 sites vs research, gates vs research, delivered files, the plan's
  outcome table, kept rules carry no value, the gate, the stamp, check/verify).
* `mutation_sweep.py "qid wave3"`: **22/22 caught**, the tree byte-identical to the sweep's start for
  3 files; the older `bcases` and repair entries re-run after the change: **92/92 caught**. The
  worktree has no `.venv` of its own, so the sweep ran through a wrapper that points its `PY` at the
  main checkout's interpreter (no junction).


## 2026-09-23 - the sitelink lane: plan, sealed pilot, dry fetch (no model call, nothing written)

**Why.** The mass run's finder answered `UNVERIFIABLE` on 7,761 fields; every one already had the
English article (6,019 also the Wikidata entity) as evidence, so asking again on the same evidence
buys the same answer. Of the 4,342 writable ones (`period_start` 3,028, `site_type` 887, `country`
427), 2,709 belong to sites whose item has a non-English Wikipedia article. The lane asks them again
with up to three of those articles. Zero MiniMax: finder and reviewer are the mass run's, the discover
prompt stays at round 5's wording (`discover_stage.py`/`model_stage.py` untouched).

**Production contacts, all reads:** two read-only exports through `lanes.psql` (the pilot's 26 sites,
`exported_at` 2026-09-23T11:01:49Z; the lane's 3,124 sites, 11:05:17Z - both byte-identical to the
first builds of 10:32 and 08:32), Wikidata `wbgetentities` and the Wikipedias' `query` API with the
project User-Agent at one request per second per host, and one dry fetch of the pilot's evidence into
its own scratch ledger. **No model call, no row in `phase3_runner/LEDGER.jsonl`, nothing written.**

### The route (`fetch_stage.py`, `wiki_sitelinks` on a record)

Each article is pinned to a revision when the plan is built; the target shows and is cited by its
permalink (`wikipedia_permalink`, moved here from `phase4/sources_stage.py`, which re-exports it) and
asks the extracts API (`wikipedia_article_url`: plain text, `formatversion=2`, the extract listed
last, no `redirects`). An answer that is not the pinned revision of the item's own article (edited
since, missing, normalised to another title, a redirect, a disambiguation page, another item's) is
refused and recorded as that target's failure, never stored; one cut at the page cap is stored as far
as it was read with `TRUNCATION_MARKER`. English (`enwiki`, `simplewiki`) and the bot-generated wikis
(`cebwiki`, `warwiki`, `arzwiki`, each with an en.wikipedia oldid citation) are refused in the record
itself; a sitelink badged `Q70893996`/`Q70894304` is refused by the plan, a sitelink list without
`badges` stops it. At most three per site, in a fixed order: the stored country's own language(s)
(`COUNTRY_WIKIS`; all 3,124 lane sites' countries are covered), then `FIXED_ORDER`, then the rest by
site id; every sitelink not taken is recorded with its rule (`wiki_sitelinks_skipped`).

### Found and fixed while finishing the interrupted builder's work

1. **A request without a ledger line** (review finding, confirmed): `one_attempt` read a sitelink
   answer before writing the attempt's line, and reading raises on an unreadable 2xx (MediaWiki sends
   `{"error": ...}` with HTTP 200). The line now goes down first, recorded as an answered attempt
   that was not given up, and the contract break propagates - as for a rendered feature whose answer
   `stored_body` cannot read. Red first: the new test found no ledger file.
2. **Articles dropped without a word:** the articles ride on the `enwiki` slot; a record none of whose
   findings reached it would have bought none of them, and the transport count reads the same
   targets. `targets_for_site` now refuses such a record.
3. **Two answer shapes crashed with `AttributeError`** instead of the stage's `EvidenceUnrenderable`:
   a `query` that is no object, and `pageprops` that is no object.
4. **Wave 3 of the external-id repair** (applied for its two replacements) was not read, and read
   naively it would have been wrong: `gap_plan.withheld_reason` took every kept link for "mis-resolved,
   replaced with None", and `shared_counts` stopped counting a kept link toward a shared item - Cave 20
   of the Pandavleni Caves would have looked like the sole carrier of the whole complex's item. The
   item rule now names each wave-3 rule: `keep-type` withheld (the item is the monument type, its
   articles describe the type), `duplicate-candidate` withheld (the owner's merge first), `link-right`
   given - and that verdict answers the owner-case classifier's suspicion of the link (in this lane
   it gives Psychro Cave its item and three articles; the Temple of Artemis-Selçuk stays withheld
   as shared, and the other three link-right sites have no open question). A kept link production
   no longer carries, and a repair rule the plan does not know, stop the build; the reasons name
   each wave's `PLAN.md`.
5. **B10 was only half excluded:** the hand-decided countries came from `bcases/b2.jsonl`, i.e. the
   T02 findings; six of the 29 geopolitical census rows B10 left as they are are no T02 finding, and
   three of them had an open `country` question: Kourion Ancient Amphitheatre, Nebi Samuel National
   Park, the Sanctuary of Apollo Hylates. The plan now reads `logs/_country_mismatches.txt` with the
   classifier's own rule (`bcases.classify.political_line`, extracted from `classify_b2` unchanged)
   and stops on a list that does not read to 29 rows.
6. **`logs/search_lane/written_keys.txt`**, which the assignment names, was not read (the fresh
   journal stood in for it, untested). It is now a check on the fresh export: every key it names for a
   site of the export must have its journal row there, or the export is partial and stops the build.
7. **A resolution recorded under other inputs:** `plan` re-derives each site's item, withholding,
   stored country and evidence room and refuses a `sitelinks.json` that differs. It caught the pilot's
   own file at once: Amyntas Rock Tombs, withheld before as "shared", is now withheld as wave 3's
   duplicate candidate - same decision, other reason; `sitelinks --pilot` was run again.
8. `lanes.PHASE3_BATCH_PREFIX` carries `"sitelink": "slk"`, so the unmerged phase-4 writer branch,
   which splits `BATCH_PREFIX` into that table and its own lanes, keeps the lane's stamp family.

### The lane (`sitelink_plan.py`, `sitelink/lane/summary.json`; built, run only after the pilot)

| step | result |
| --- | --- |
| census | 4,342 questions over 3,124 sites (period_start 3,028, site_type 887, country 427) |
| not open | 34: duplicate 16 (period_start 11, site_type 5), hand-country (b2) 14, political line (B10) 3, written 1 (`2026-09-21_mechanical-country`) |
| item | (`sitelinks`, 7.5 minutes of read-only lookups, none that stopped the build) 3,109 sites with an open question; 2,579 with a usable item; 530 withheld - no item 361, shared 73, unresolved in the repair 50, suspect link 32, duplicate candidate 11, type 3 |
| articles | 2,040 sites given at least one (3: 1,306, 2: 299, 1: 435); 4,951 articles, dewiki 1,001, eswiki 947, frwiki 682, itwiki 350, then 97 other wikis; not taken: cap 10,341, English 2,097, bot-generated 692, room 587, redirect badge 30 |
| plan | `PLAN.sitelink.jsonl`, 136 batches `slk-0001`..`slk-0136`, 2,040 sites, **2,399 fields** (period_start 1,970, site_type 389, country 40), sha256 `3dfd1d5e7f487ae245eae90bdc1e30be6a9f01e1cc01ba6c94483a8283ba9a12` |
| no article | 1,909 fields: item withheld 1,303, no usable article 606 |

**Country by geometry (spec item 3, report only):** of the 427 `country` fields, **412 are verified
by the stored point** - T02 of the 2026-09-20 census found the point inside the stored country and
neither the country nor the point has changed since; 14 are T02 findings, 1 passed T02 but changed
since. All 40 country fields in the plan are among the 412.

### The pilot (`--pilot`): sealed before any model call

`phase3_runner/SITELINK_PILOT.md` (commit 2fe862b, sha256 of the committed text
`47f9adc4bb9e9f99da08d05672059ba0fa1f2c0e5816fe9a1e8faa9d8558dac6`) fixes the four thresholds of
`SEARCH_PILOT.md` word for word - threshold 4 counted over the lane's articles (`score_search_pilot.py
--lane sitelink`, the search scorer generalised: its search output is unchanged) - on the plan
`PLAN.sitelink-gold.jsonl`, sha256 `593501abbfc21ec6e3e9cc6f09dc9a968ac5f1bdc9f0b7e194165a1d7851b522`:
19 gold-standard sites, 41 of the 59 UNVERIFIABLE fields (period_start 16, description 10,
card_description 9, site_type 5, country 1; human verdicts CORRECT 25, WRONG 10, UNVERIFIABLE 6),
2 batches, 52 articles. The other 18 fields: 12 at 4 sites without a usable item, 6 at 3 sites
without a usable article. The mass driver's dry run projects 41 calls, $0.034.

**Dry fetch** (`runs/sitelink-gold-dry2`, scratch ledger `logs/sitelink_scratch/LEDGER.dry2.jsonl`):
191 requests, all answered 200; 52 of 52 articles stored, 0 cut, 0 refused; all 19 sites under the
64,000-character bound (largest 29,925); stored/estimate at most 0.806; 0 articles unaccounted for.
The builder's first dry fetch at 10:33 (`runs/sitelink-gold-dry`, 192 requests: one Wikidata `wbgetclaims`
answered 429 and was asked again) had the same outcome.

### Tests and proofs

* `tests/remediation/test_phase3_fetch_sitelinks.py` (31 tests, 59 with parameters) and
  `tests/remediation/test_sitelink_plan.py` (50), plus 4 in `test_gap_plan.py` and 1 in
  `test_remediation_tools.py`; no test reads production, Pi or the network. Every fix above was red
  before it.
* `mutation_sweep.SITELINK_MUTATIONS`, 140 `"sitelink: "` entries, registered once. First run
  139/140: the missed one dropped the list reader's language check, which the test only reached
  through `targets_for_site`, whose permalink refuses a bad subdomain later; the test now asks the
  reader first (1/1). The final run, through the sweep's own `main` with the main venv's
  interpreter, took every entry anchored in a file this branch changed - the 140 `sitelink: `
  entries and the 123 older ones on `fetch_stage.py`, `phase4/sources_stage.py`,
  `bcases/classify.py`, `gap_plan.py`, `lanes.py` and `score_search_pilot.py`: **263/263
  caught**, the tree byte-identical to the sweep's start for 7 files
  (`logs/sitelink_scratch/sweep_final.txt`).
* Gate suite from the worktree: 4,277 passed, 108 skipped (the snapshot and Natural Earth caches are
  not in a worktree), 57 deselected; ruff, `ruff format --check` on the touched files, lint-imports
  and vulture clean.

### Open

* The pilot's run (41 finder calls, their reviews, the score) is the orchestrator's, by
  `SITELINK_PILOT.md`'s commands; the lane runs only after the pilot passes.
* The lane's plan and summary are git-ignored (`output/remediation/sitelink/`,
  `phase3_runner/PLAN.sitelink.jsonl`), like every plan; they are rebuilt by the README's commands
  and must be, if the pilot passes later than the pins hold.
* Merging `wip/p4-write` onto this: `lanes.py` conflicts textually; keep `"sitelink": "slk"` in
  `PHASE3_BATCH_PREFIX`.


## 2026-09-23 - the sitelink lane after its independent check: item rule, generated wikis, pilot re-sealed (no model call, nothing written)

An independent check of `wip/sitelink` raised three findings. All three held; the first reached one
case more than the check saw. **Production contacts, all reads:** Wikidata and the Wikipedias' `query`
API (the lane's and the pilot's `sitelinks` again, 1 s per host; the first revision of 832 chosen
pages, to see who wrote them) and one more dry fetch of the pilot's evidence into its own scratch
ledger. No model call, no row in `phase3_runner/LEDGER.jsonl` (0 `slk`/`slkg` rows), no export,
nothing written.

### 1. The item rule ignored the classifier's "this item is the site's place" verdicts (major, confirmed)

`item_for` withheld an item for the repair waves, a shared item and a suspect link, but never read the
owner-case classifier's verdicts that the item is a town, commune, state or island holding the site:
`bcases/coords.jsonl` classes `container-item` and `item-is-not-the-site`, and `bcases/names.jsonl`'s
N7 `anchor-is-locality`. Measured on the first plan (`3dfd1d5e...`): **93 sites, 137 fields**
(period_start 91, site_type 39, country 7) - Colima - Eastern Shaft Tomb asked from the articles on
the Mexican state, Kintradwell Broch from Brora's, Kameishi from Asuka village's, Site de Tiklat from
El Kseur's, the Roman Bridge (Elguentra) from El Kantara's, Ancient Thasos from the island's, Ahin Posh
Tape (HUMAN_ONLY B1/B2 item 4, open) from a Pakistani village's. The check found none of them in the
pilot; **one is**: Hebbariyeh Roman Temple (`slkg-0001`), whose item Q5695359 is the village of
Hebbariye (N7 `anchor-is-locality`) - its plan record put its period and card text to the village's
arwiki, itwiki and fawiki articles.

`classifier_verdicts` reads every verdict under its own rule name - `suspect-link`, `container-item`,
`item-is-not-the-site`, `item-is-a-locality` - and `item_for` withholds on the first one about the item
the site still carries, the rule named in the reason (`Q61309: item-is-not-the-site - ...`). Wave 3's
`link-right` answers the suspicion only; nobody has read the containers, so an ancient city among them
(Abusir, Karpasia) is withheld too (safety over coverage; the owner's N7 reading is HUMAN_ONLY item 6).
`linear-or-areal-item` is not a withholding rule: the class is about a line's arbitrary point, and of
the 20 such items in the first plan 19 are the site itself (the Icknield Way, the Pannonian Limes) and
one the national park named after it (Yaxhá).

**A second mismatch in the same reader:** a suspicion was paired with `qid_now` - the link the site
carried when the classifier ran - instead of `qid`, the item it judged. For the 18 rows whose census
item the repair had replaced before the classifier ran, the reviewed replacement was withheld for a
suspicion about the old item (Kourion's amphitheatre: Q1 on Q11635 "amphitheatre" withheld
Q4453457). Ten of them had an open question; they get their item back, five of them articles.

### 2. Generated wikis still reached the finder (minor, confirmed, one more found)

Read on each wiki's own API, the first revision of every page the first plan chose on `cewiki`,
`lldwiki`, `zh_min_nanwiki` and `svwiki` (131 pages) and on the 81 wikis outside `FIXED_ORDER` (701):
all 3 Chechen pages by `CheWikibot`; all 30 Ladin pages by one account with AWB in eleven days
("creps using [[Project:AWB|AWB]]", 509-650 bytes); the Min Nan page by `Taigiholic.bot`; of 97
Swedish pages, 53 of the 75 chosen for sites outside Sweden and Finland by Lsjbot ("Botskapande
Storbritannien", "Botskapande Irland", ...) and none of the 22 chosen for Swedish and Finnish sites.
**And Corsican**, which the check had not named: of 15 pages, 13 are Botu's "Automated import of
articles" of 2005-10-18 and a 14th came the same day (220-253 bytes; 12 still under 400; 8 sites had
nothing else).

`fetch_stage.BOT_GENERATED_WIKIS` gains `cewiki`, `lldwiki`, `zh_min_nanwiki` and `cowiki`, each with
its citation (ru.wikipedia "Чеченская Википедия" oldid 153105098; en.wikipedia "Ladin Wikipedia" oldid
1375555468; zh.wikipedia "閩南語維基百科" oldid 93375724; Corsican by the measurement alone - no
article says how it was written). Swedish is read only where it is the site's own language:
`sitelink_plan.HOME_ONLY_WIKIS` refuses `svwiki` unless the stored country's `COUNTRY_WIKIS` name it
(Sweden, Finland), and `svwiki` leaves `FIXED_ORDER`, where it could only rank a wiki the rule refuses.

**Open, measured:** bot-created pages inside editor-written wikis stay readable - `srwiki` 5 of 37
(FelixBot's 2007 census imports, 6-8 KB), `cywiki` 5 of 64, `urwiki` 3 of 18, `hrwiki` 2 of 37, `shwiki`
2 of 6, `anwiki` 1 of 2; `astwiki`'s one page is Tradubot's translation of the Spanish article. A
wiki-wide refusal would be disproportionate there, and a page-level check costs one more request per
candidate (`creators_small_wikis_2026-09-23.json` in `logs/sitelink_scratch/`).

### 3. The pilot's threshold 4 was not the search pilot's text (minor, confirmed)

`SITELINK_PILOT.md` said "word for word" and rewrote threshold 4 with articles in place of searches
and slots; the scorer said "unchanged". The document now copies all four thresholds verbatim and states,
beside them, how the lane reads threshold 4 - it buys no search, so a search is one sitelink article,
its stored result the evidence file, a recorded failure the fetch stage's record, a slot an article:
what `TRANSPORTS["sitelink"]` counts. The scorer's docstring says the same. A test compares the two
documents' threshold blocks.

### The rebuilt lane and the re-sealed pilot

| | first build | after the check |
| --- | --- | --- |
| sites with an open question / with a usable item | 3,109 / 2,579 | 3,109 / 2,491 |
| withheld | 530: no item 361, shared 73, unresolved 50, suspect link 32, duplicate candidate 11, type 3 | 618: no item 361, shared 73, container-item 57, unresolved 50, item-is-not-the-site 23, suspect-link 22, item-is-a-locality 18, duplicate candidate 11, keep-type 3 |
| sites given at least one article (3 / 2 / 1) | 2,040 (1,306 / 299 / 435) | 1,920 (1,210 / 281 / 429) |
| articles | 4,951 | 4,621 |
| not taken | cap 10,341, English 2,097, bot-generated 692, room 587, redirect badge 30 | cap 8,596, English 1,968, bot-generated 849, home-only 370, room 543, redirect badge 28 |
| plan | 136 batches, 2,399 fields (period_start 1,970, site_type 389, country 40), `3dfd1d5e...9a12` | **128 batches, 2,236 fields (period_start 1,852, site_type 347, country 37), `0e3116558fd65ed4dad02760b70dec705e193e051073e96d4622267cefaf4923`** |
| no article | 1,909: item withheld 1,303, no usable article 606 | 2,072: item withheld 1,422, no usable article 650 |

Of the 125 sites the plan lost, 93 (137 fields) are the item rule's (container-item 54,
item-is-not-the-site 22, item-is-a-locality 17) and 32 (40 fields) had nothing left but generated
wikis (12 bot-generated only, 6 Swedish only, 14 both); it gained the 5 repaired sites of finding 1
(14 fields). The country geometry is unchanged: 412 of 427 country fields verified by the stored
point, all 37 in the plan among them. `plan` refused the old `sitelinks.json` for 130 sites and the
pilot's for Hebbariyeh ("resolved under other inputs") before `sitelinks` ran again.

**The pilot** (`PLAN.sitelink-gold.jsonl`, sha256
`d8a78e58f02255570bd6a7c94dd42b0a04fdbddadca440b9bc12e39dabc28b81`): 18 sites, 39 fields
(period_start 15, description 10, card_description 8, site_type 5, country 1; human verdicts CORRECT
23, WRONG 10, UNVERIFIABLE 6), 2 batches, 49 articles - every pin the first build's revision,
Hebbariyeh withheld. The mass driver's dry run projects 39 calls, $0.0322. Dry fetch
(`runs/sitelink-gold-dry3`, scratch ledger `logs/sitelink_scratch/LEDGER.dry3.jsonl`): 181 requests,
180 answered; one WDQS query (The Merry Maidens' narrowed Wikidata evidence) drew a 429 asking for 120
s and was recorded as that target's failure; 49 of 49 articles stored, 0 cut, 0 refused; all 18 sites
under 64,000 characters (largest 29,925); stored/estimate at most 0.806; 0 articles unaccounted for.
`SITELINK_PILOT.md` re-sealed (commit d10d469), sha256 of the committed text
**`9467e7259b3cc164b60e5cb754ade2e2ed07ae9e909e7b3e2b4eb3b3f69b3d1e`**. The first version
(`47f9adc4...8dac6`, plan `593501ab...b522`) and the first lane plan (`3dfd1d5e...9a12`) recorded in
the section above do not apply any more.

### Tests and proofs

Red first, each shown failing before its fix: the old `item_for` gave all eight named cases (the
check's seven and Hebbariyeh) their item and withheld Kourion's repaired one; the fetch stage read a
record naming `cewiki`, `lldwiki`, `zh_min_nanwiki` or `cowiki`, the plan offered them and Swedish for
an Irish site; the old `SITELINK_PILOT.md`'s threshold block differed from `SEARCH_PILOT.md`'s.
`test_sitelink_plan.py` 60 tests, 10 of them new (64 with parameters; the named owner cases are read
on the classifier's own tracked output), `test_phase3_fetch_sitelinks.py` 4 more parameters. `mutation_sweep.SITELINK_MUTATIONS` 158 `"sitelink: "`
entries, registered once, labels unique (1,012 in all): 18 new, the moved anchors re-pointed. The
sweep's own `main`, with the main venv's interpreter, over every `"sitelink: "` entry and every older
one anchored in a file this session changed (`fetch_stage.py`, `sitelink_plan.py`,
`score_search_pilot.py`, `SITELINK_PILOT.md`): **208/208 caught**, the tree byte-identical to the
sweep's start for 6 files (`logs/sitelink_scratch/sweep_after_check.txt`).
Gate suite from the worktree: 4,295 passed, 108 skipped (the snapshot and Natural Earth caches are not
in a worktree), 57 deselected; ruff, `ruff format --check` on the touched files, lint-imports and
vulture clean.

### Open

* The pilot's run (39 finder calls, their reviews, the score) is the orchestrator's, by
  `SITELINK_PILOT.md`'s commands; the lane runs only after the pilot passes, on a plan rebuilt then.
* The page-level bot pages of finding 2 (18 pages of the first plan, in editor-written wikis).


## 2026-09-23 - the liveness write as a chunk, and the 20 two-URL `source_url` values (planned, not applied)

Branch `wip/ops2`. **Nothing was written to production.** Production contacts, all read-only or
rolled back: the reads named below, `chunk_writer.py --rehearse` of the liveness chunk, the
rehearsal of external-id wave 4 (and of wave 4 followed by its reversal), and migration 0023 inside
`BEGIN; ... ROLLBACK;`. Network reads: English Wikipedia (`resolve_titles`, the project user agent)
for 19 titles, and one `wbgetentities` read of the 19 items for the notes below.

### A. The liveness lane gets its write (`liveness.py chunk`)

`liveness.py` could sweep and recheck; nothing turned the store's `PLANNED.jsonl` (the L1/L2 rows
`decide.py liveness` makes) into something that can reach production. The new `chunk` command builds
`chunk_writer.Change` records from it: old and new values exactly as planned (booleans in their text
form `'true'`/`'false'`), the rule (L1/L2), a reason from the Commons log class ("Commons deleted
File:X as a copyright violation (log N, time); the row is excluded"), and the planned evidence
pointers plus the store they point into. Lane `img-liveness`, test id `T09/liveness`, confidence
`authoritative`, stamp `img-liveness-<store date>` (here `img-liveness-2026-09-23`, run stamp
`...-001`).

It refuses: a planned row whose `liveness_sha256` names no line of `NOT_LIVE.jsonl`, or whose line
does not state the row's class, file, log id and rule, or does not reference the row; a role that
writes a column or acts on a class it does not own; an L2 value that is not the store's live move
target; a hero promotion without the hero drop L1 made on its site; and a store whose `RECHECK.json`
is not a clean recheck of every logged line. The one production read is the live rows of the touched
sites: the chunk is emitted only when the sites the plan leaves without a live image are exactly the
ones named with `--may-empty`.

**`may_empty` = the Lion Tombs of Dedan (`9a9a0dca-52c8-44c2-94f6-adb655db17dd`), and only it.**
Production, read 2026-09-23: Dedan has exactly two image rows (87351 `Dedan_tomb_1`, 87352 the hero,
both files deleted as copyright violations), both planned excluded -> 0 live after. The other five
sites keep live images: Chesterfield 13 -> 12, Stadium at Olympia 18 -> 17, Theatre of Dionysus
18 -> 17, Stoa of Eumenes 20 -> 19, Roman Forum 20 -> 20 (L2 only). Without `--may-empty` the command
stopped: `the plan leaves ['9a9a0dca-...'] without a live image, --may-empty names []`.

`chunk-001`: **9 rows over 6 sites** - `is_excluded` false -> true on 107331 (deleted-other: the
Minecraft/McDonald's promotion photo on Chesterfield), 97070, 80453, 87352, 87351, 70233
(deleted-copyvio); `is_hero` true -> false on 87352; `commons_page_url` and `original_url` of 75145
(Roman Forum) to the live target `File:Forum Romanum - panoramio (3).jpg`.

* `chunk_writer.py <chunk> --check` (offline): `CHECK OK: ... chunk-001 is the plan's, 9 row(s)`.
* `--rehearse` (production, COMMIT -> ROLLBACK): `INSERT 0 9`, `INSERT 0 1` (may_empty), `SELECT 6`,
  `DO`, journal rows for this run 9, planned rows 9, `ROLLBACK`, then
  `REHEARSAL OK: chunk 001, 9 row(s), rolled back` (0 journal rows survive).
* Open after the write (not this lane's rule): Dedan's `unified_sites.thumbnail_url` is
  `/data/images/wiki/9a9a0dca/hero.webp`, the local derivative of the deleted hero; no replacement
  hero exists (`LISTED.json`), so the page falls back to `is_lead`/`sort_order` over no live image.
  The thumbnail lane (T1) or the owner decides what the site shows.
* Tests: 8 new in `test_gallery_liveness.py` (the sweep -> `decide.plan_liveness` -> chunk path over
  the fake Commons, every refusal, the recheck gate, the stamp, the emptied-site computation, the
  command's `--may-empty` gate, and the delivered chunk re-derived from the versioned store).
  `mutation_sweep.py "liveness chunk: "`: **19/19 caught**.

Apply, in this order (the orchestrator):

```bash
PY=./.venv/Scripts/python.exe
$PY scripts/remediation/gallery_audit/liveness.py recheck --store output/remediation/gallery_audit/liveness-2026-09-23   # the day of the write; must report no problem
C=output/remediation/gallery_audit/liveness-2026-09-23/chunk-001
$PY scripts/remediation/gallery_audit/chunk_writer.py $C --check
$PY scripts/remediation/gallery_audit/chunk_writer.py $C --rehearse
$PY scripts/remediation/gallery_audit/chunk_writer.py $C --apply        # reads back plan <-> journal <-> data
$PY scripts/remediation/gallery_audit/chunk_writer.py $C --rehearse-rollback
```

### B. The 20 curated `source_url` values that hold two URLs

Measured (read-only): exactly 20 `unified_sites` rows carry a control character in `source_url`, all
`ancient_nerds`, all created 2026-03-04, each `'<url1>\n<url2>'` (one `\n`, no `\r`, no whitespace in
either URL). 19 Mesoamerican sites carry a megalithic.co.uk URL first and an English Wikipedia URL
second (Cantil de las animas: a blogspot URL); none of them had a `site_external_ids` row, because
`refresh_site_external_ids` reads only `source_url LIKE 'https://en.wikipedia.org/wiki/%'`. Petra has
the article first and a Khan Academy page second, and its `enwiki_title` row held
`'Petra\nhttps://www.khanacademy.org/...'` (the only external-id value with a control character); no
`wikidata_qid` row.

**Root cause, two defects in `pipeline/lyra/prospector/wiki.py`, both fixed:** `enwiki_title_from_url`
turned the whole two-URL value into a title, and `_parse_query` stored it - the API answers such a
title with `invalid: true` and no `missing` (measured live), and `_parse_query` took an invalid title
for the canonical one. `enwiki_title_from_url` now raises `ValueError` for a URL or a decoded title
with a C0 control or DEL (`CONTROL_RE`, the class migration 0023 enforces), and an `invalid` page is
no page. The Lyra import check passes. The boot refresh (`only_missing=True`) reads none of the 20
rows today (Petra has a row, the others no Wikipedia prefix), so the new raise cannot stop a boot;
`--all` would raise on Petra until wave 4 is applied - by design.

**Data fix: external-id repair wave 4** (`qid_repair.py --wave 4`, `output/remediation/qid_repair/
wave4/`, run stamp `2026-09-23_source-url-split-wave4`). `resolve --wave 4` wrote the versioned
`RESOLUTION.json` (production read 10:52:11Z, Wikipedia 10:52:14Z); `render` plans from it alone:

| what | rows |
| --- | --- |
| `unified_sites.source_url` -> the first URL, through `apply_remediation_change()` (its allow-list names the table `unified_sites`, so the primitive allows the column - no migration needed) | 20 |
| `site_external_ids` new rows (`INSERT`, old value NULL = no row; guarded: no row of that (site, kind) exists) | 35 (17 Mesoamerican sites x 2, Petra's `wikidata_qid` `Q5788`) |
| `site_external_ids` corrected (Petra `enwiki_title` -> `Petra`) | 1 |
| **total** | **56** |

Left, with their reasons: **Cantil de las animas** - neither URL is an English Wikipedia article (its
`source_url` is split all the same); **Chiapa de Corzo** (`24aa135d`) - `Q4384315` is already carried by the
curated site **Zoque Culture Archaeological Zone** (`ed186ea9`, whose own `source_url` is the same
article): a duplicate candidate for the owner, not a link. No title redirected, none is a
disambiguation page.

Flagged, written under the rule (the boot refresh would have stored the same had the URL stood
alone), for the orchestrator to keep or drop before the apply: three curator articles are about the
place, not the site - `Acanceh` -> Q8186545 (locality, the municipal seat), `Santa María Atzompa` ->
Q3846612 (municipality), `Trincheras` -> Q1434929 (locality in Sonora; the site is Cerro de
Trincheras). Wave 2's rule A refused settlements; the orchestrator's rule for this wave does not.
`Cascajal Block` -> Q1046912 is the block itself (P31 tablet), as the record is.

The statement: guards (curated sites; every `source_url` still the old value; an external-id row with
an old value is the one row of its kind and holds it; a new row is new; no other curated site carries
a planned item), the writes (primitive for `source_url`, a conditional `UPDATE` or an `INSERT` for
the ids, exactly one row each, one journal row each, `row_pk` `site/kind` as in waves 1-3), and
invariants (new values held, one row per kind, the journal equal to the plan both ways). A value with a
control character is spelled `'a' || chr(10) || 'b'` so no raw line break stands in the file. The
reversal deletes exactly the inserted rows by their value, puts Petra's title back, restores every
two-URL `source_url` through the primitive, and journals all of it under `...-wave4-rollback`.
Waves 1-3 render byte for byte what is committed (test).

* `qid_repair.py check --wave 4` (read-only): **`check: 56 rows, 0 deviation(s)`**.
* Production rehearsal of `REHEARSAL.sql`: `INSERT 0 20`, `INSERT 0 36`, `DO`,
  `NOTICE: source-url split: 56 row(s) changed and journalled`, `ROLLBACK`, journal rows for this
  stamp 0; afterwards 20 control-character values, Petra 1 external-id row, 0 journal rows.
* Rehearsal of the undo (APPLY and ROLLBACK.sql in one transaction, then `ROLLBACK`): both DO blocks
  56 rows; inside, before the rollback: 56 + 56 journal rows, 20 control-character values again, 1
  external-id row among the 20 sites, Petra's title broken again - the pre-state exactly.

**Migration `0023_source_url_no_control_chars.sql`**: a first transaction counts the offending rows
with a plain read and raises if any, then adds `CHECK (source_url !~ '[\x00-\x1f\x7f]') NOT VALID`
only if `pg_constraint` lacks `unified_sites_source_url_no_control_chars`; the `VALIDATE` runs in its
own transaction (the 0020 pattern); a catalog selftest follows. The selftest compares with `strpos`:
a first draft used `LIKE`, which reads the pattern's backslashes as its own escapes - measured on a
temp table, it would have failed a correct migration and stopped the deploy.

* Rehearsed on production inside `BEGIN; ... ROLLBACK;` (its first transaction):
  `ERROR: 0023: 20 unified_sites row(s) carry a control character in source_url - apply the data fix
  (output/remediation/qid_repair/wave4) before this migration`, psql exit 3; no constraint exists
  afterwards. **Expected until the data fix is applied.**
* The success path, run verbatim twice against a session temp table that shadows `unified_sites`
  (the script stops unless the name resolves to the temp table): added, validated, selftest
  `CHECK ((source_url !~ '[\x00-\x1f\x7f]'::text))`, the second run `already exists - no ALTER`, and
  the CHECK refuses a newline. The real catalog is untouched.

Apply, in this order (the orchestrator) - the migration must not reach `main` before step 5:

```bash
PY=./.venv/Scripts/python.exe
$PY output/remediation/tools/qid_repair.py render --wave 4   # REHEARSAL.sql is not versioned
$PY output/remediation/tools/qid_repair.py check --wave 4    # read-only: 56 rows, 0 deviations
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" < output/remediation/qid_repair/wave4/REHEARSAL.sql
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" < output/remediation/qid_repair/wave4/APPLY.sql
$PY output/remediation/tools/qid_repair.py verify --wave 4   # read-only
# only now may migrations/0023_source_url_no_control_chars.sql reach main (the deploy applies it);
# from then on the source_url half of wave4/ROLLBACK.sql cannot run - the CHECK refuses it
```

Tests: 3 new in `tests/pipeline/test_prospector_units.py` (control character in the URL, after
decoding, the invalid page), 14 new in `test_remediation_tools.py` (wave 4 plan, Petra, every
refusal, the record gate, `chr(n)` spelling, the statement's guards and writes, the reversal, the
control-character refusal, the plan line of waves 1-3, waves 1-3 byte for byte, the delivered files,
`resolve`, check/verify over both tables, NULL as "no row"), 6 in the new `test_migration_0023.py`.
`mutation_sweep.py "source url: "`: **28/28 caught**.

### B, revised the same day: no link to a place-level item (orchestrator decision) - supersedes the 56-row plan

The orchestrator's decision: wave 4 writes no link to a town or municipality - the defect waves 1-3
repaired - as a rule, not a hand exception. The rule is the gate waves 2 and 3 applied,
`bcases.qid_research.is_site_kind` (`classify.is_container_class`: a P31 class naming a settlement,
an administrative unit or a natural feature, unless a site word such as "ancient" or "archaeological"
makes it a site again; or a Wikimedia page), imported, not copied. `phase4/subject_gate.py`'s
place-level list was not taken: its verdict accepts a place-level item for a site whose own type is a
settlement type, and Acanceh, Atzompa and Cerro De Trincheras are all `City/town/settlement` in the
catalogue, so it would have let exactly these three through. A refused item refuses **both**
`enwiki_title` and `wikidata_qid` of the site; its `source_url` is split all the same.

`resolve --wave 4` now also records each resolved item's P31 class labels, read the way the bcases
research reads them (`bcases.collect.fetch_claims` + `fetch_labels`, the census Fetcher, the bcases
cache; a class without an English label stops the read). Re-resolved 2026-09-23 11:38Z; production
and Wikipedia answered as before. PLAN.md gains a duplicate-candidate table built from the plan.

| what | rows |
| --- | --- |
| `unified_sites.source_url` -> the first URL (primitive) | 20 |
| `site_external_ids` new rows (14 sites x 2) | 28 |
| corrected | 0 |
| **total** | **48** (digest `8da78ba0...`) |

Left, each with its reason in PLAN.md: **Acanceh** (Q8186545, P31 locality of Mexico), **Atzompa**
(Q3846612, municipality of Mexico), **Cerro De Trincheras** (Q1434929, locality of Mexico) - a place,
not the site; **Petra** (Q5788, P31 ancient city, **city**, archaeological site) - the canonical gate
reads the plain class "city" (Q515) as a container, so Petra's ids are refused too, and **Petra's
stored `enwiki_title` keeps its newline** (the wave has no replacement to write; a removal is a
`DELETE`, the owner's call) - PLAN.md says so, and says that the manual `--all` refresh would write
Petra's refused ids; **Cantil de las animas** (no article); **Chiapa de Corzo** (Q4384315 carried by
Zoque Culture Archaeological Zone). Duplicate candidate, in PLAN.md with its evidence: Chiapa de Corzo
(`24aa135d`) / Zoque Culture Archaeological Zone (`ed186ea9`) - this site's article
`Chiapa_de_Corzo_(Mesoamerican_site)` resolves to Q4384315, the item the other row carries, and the
other row's `source_url` is the same article.

* `qid_repair.py check --wave 4` (read-only): **`check: 48 rows, 0 deviation(s)`**.
* Production rehearsal of `REHEARSAL.sql`: `INSERT 0 20`, `INSERT 0 28`, `DO`,
  `NOTICE: source-url split: 48 row(s) changed and journalled`, `ROLLBACK`, journal rows for this
  stamp 0; afterwards 0 journal rows, 20 control-character values.
* Apply-then-undo rehearsal (one transaction, rolled back): 48 + 48 journal rows, then 20
  control-character values, 1 external-id row among the 20 sites and Petra's broken title - the
  pre-state exactly.
* Tests: the wave-4 fixture gains a municipality item and the real Petra class set; 3 new tests (the
  place gate for both kinds with the split kept, the duplicate candidates with their evidence, the
  class read's refusal of an unlabelled class). `mutation_sweep.py "source url: "`: **33/33 caught**.

The apply commands above are unchanged; `check` now reads 48 rows.

### B, revised again: Petra as a hand-read entry (orchestrator decision) - supersedes the 48-row plan

The place gate stays as it is; Petra is written as a **hand-read entry**, the way wave 2's hand
entries carry quoted evidence. `qid_repair.WAVE4_HAND_READ` holds one entry; its guard: a hand entry
must name, verbatim, the refusal the rule made for that site, and it overrides only that one - a
different reason, a site the rule did not refuse, a refusal that is not the place gate's (an item
another curated site carries) or a site whose article the wave never resolves stops the plan, and so
does an entry without evidence. PLAN.md lists the entry under "Hand-read" with the refusal it
overrides and its evidence; each of Petra's rows carries both.

Evidence, verified read-only on 2026-09-23 (`wbgetentities` Q5788 with its class labels,
`resolve_titles(['Petra'])`, the production row): Q5788 'Petra' - 'ancient rock-cut historical city
in Jordan', P31 archaeological site (Q839954), ancient city (Q15661340) and city (Q515), all normal
rank; P1435 heritage designation World Heritage Site (Q9259); P757 World Heritage Site ID 326; its
enwiki sitelink is 'Petra', and `resolve_titles` answers 'Petra' -> 'Petra', Q5788, no redirect, not a
disambiguation page; the stored name is 'Petra' (Jordan).

| what | rows |
| --- | --- |
| `unified_sites.source_url` -> the first URL (primitive) | 20 |
| `site_external_ids` new rows (14 sites x 2, Petra's `wikidata_qid` Q5788) | 29 |
| corrected (Petra `enwiki_title` `'Petra\nhttps://www.khanacademy.org/...'` -> `Petra`) | 1 |
| **total** | **50** (digest `a5f3503d...`) |

Left: Acanceh, Atzompa, Cerro De Trincheras (a place, not the site), Cantil de las animas (no
article), Chiapa de Corzo (Q4384315 carried by Zoque Culture Archaeological Zone; duplicate
candidate). With Petra corrected, no external-id value with a control character is left, and the
`--all` refresh would write none of the refused ids back (both PLAN.md bullets are computed).

* `qid_repair.py check --wave 4` (read-only): **`check: 50 rows, 0 deviation(s)`**.
* Production rehearsal of `REHEARSAL.sql`: `INSERT 0 20`, `INSERT 0 30`, `DO`,
  `NOTICE: source-url split: 50 row(s) changed and journalled`, `ROLLBACK`, journal rows for this
  stamp 0; afterwards 0 journal rows, 20 control-character values, Petra's broken title unchanged.
* Apply-then-undo rehearsal (one transaction, rolled back): 50 + 50 journal rows, then the pre-state
  exactly (20 control-character values, 1 external-id row among the 20 sites, Petra's title broken).
* Tests: 2 new (Petra written with its entry and refused without it, on the delivered record; a hand
  entry must name the refusal it overrides - wrong reason, unrefused site, a sharer refusal, an
  unresolved site, no evidence). `mutation_sweep.py "source url: "`: **38/38 caught**.

## 2026-09-23 - the cell lanes and journal-reversal-2: planned, not applied

Branch `wip/mech2` (merged with `integrate/wave1` at `b6de246`, and with its tip `9046ef9` after
this section was written). Four lanes of the mechanical write path
(`scripts/remediation/mechanical/`) are planned and committed; **none of them has written anything**
(read-only at 11:11 UTC: 0 journal rows for any of their stamps, 0 `card_stats` journal rows, 0
curated rows with a `scope_status`). Production was only read (`SELECT`s, `BEGIN READ ONLY`): the
reversal plans, their read-backs, the owned-card count and a re-read of the duplicate list. The
apply order at the end of this section is the orchestrator's.

### What each lane does

* **`card-stats-<wave>`** (`card_stats.py`): recomputes the twelve `card_stats` columns of every
  curated card whose inputs moved, with the generator's own code (`api/cardgame/generator.py`
  `site_card_stats`/`content_stats`, extracted behaviour-neutrally and imported, never copied). It
  plans only after a counterfactual proves the model: the journalled inputs put back must reproduce
  every stored cell. Each wave is a lane of its own (stamp `<wave>_mechanical-card-stats`), carries
  a premise per site (its inputs plus one digest of all curated `(site_type, period_name)` pairs)
  and commits a `BASIS.json` the next wave's proof reads. Its `ROLLBACK.sql` expires at the next
  write to any curated `site_type` or `period_name` (HANDOVER, "A card_stats wave's ROLLBACK.sql
  expires").
* **`scope-e4`** (`scope.py`): fills `scope_status` and `scope_reason` (E3/E4: out of the window,
  undated, duplicate, museum) in one transaction, every decision conditioned on the date, point,
  type, name and description it rests on (guard 5). It now also retires the owner-case duplicate
  list `output/remediation/bcases/DUPLICATES.jsonl` (below).
* **`journal-reversal-1`** and **`journal-reversal-2`** (`reversal.py --lane <name>`): each restores
  the value a named list of journal rows replaced, conditioned on the live value being the value the
  row wrote and on that row being the last write of its cell (guard 6). Every row needs a reason and
  quotes that are checked where they say they are.

### journal-reversal-2: the 45 rows the re-review reverses

`output/remediation/phase3_runner/REREVIEW_1.md` fixed the rule before the call: each of the 77
written rows whose reviewer answered `REFUTED: NO` while its own WHY named a failing half
(`HUMAN_ONLY.md` B11) got one new reviewer call and was kept only on a clean clearance; a hand read
then moved 8 rows from keep to reverse. Its result, `logs/review_holds/REREVIEW_1_FINAL.jsonl`
(gitignored in the main checkout; sha256 `adc678ce...79063eb`), is copied unchanged into
`output/remediation/mechanical_reversal_2/`: **45 reverse** (30 `site_type`, 15 `period_start`),
**32 keep**. The 32 stay written.

* **The period label.** 8 of the 15 `period_start` writes had moved a site into another bucket,
  and the period-name lane (2026-09-22) had then relabelled it (journal rows 30335-30536).
  Restoring the start alone would leave 8 sites whose label contradicts their date. The list
  therefore also restores those 8 labels, and `reversal.py` checks the list as a whole
  (`keep_the_period_label`): a restored label must be the bucket of the start the list leaves, and
  a start must not leave behind a label that was its bucket - a refused start takes its label with
  it and back. **53 cells over 45 sites.**
* **Evidence.** Each of the 45 quotes the re-review's hand-read WHY and the reviewer's new WHY
  (`rereview:<change_key>`; the lane accepts it only when that row decided `reverse` for exactly
  the write the journal row made - same key, site, column, old and new value). Each label quotes the
  period-name lane's own journal evidence ("... the write that left the label behind").
* **The Trundle** is among the 45 (`period_start` -500 -> -1000, and its label back to
  '1500 - 500 BC'). Its residual keeps the hand read's note: both values miss the Neolithic
  causewayed enclosure (c. 3500 BC), the field stays open. Every reversed field is open again, not
  corrected (REREVIEW_1.md).
* **Planned from production** (`reversal.py --lane journal-reversal-2 --write`, read-only, 10:53
  UTC): 53 of 53 planned, 0 refused - every journal row is the last write of its cell, every live
  value is the value its row wrote, every restored `site_type` is canonical. Read-back before the
  apply (read-only, about 11:00 UTC): `curated sites still holding a value this reversal list
  undoes` 45, `curated rows whose period_name is not the bucket of period_start` 11 (none of them
  among the 45; the list leaves the count as it is).

### scope-e4 reads the owner-case duplicate list

`DUPLICATES.jsonl` (19 losers, each with its survivor and evidence, "for the scope lane") was not
read by the lane: its own 100 m rule found 3 of them. It is now: each listed loser is retired
with `duplicate_of:<survivor>` after its claim is re-read in the export - both rows curated (else
the plan is refused), both still carrying the one item the line names, still within the list's 2 km
(`bcases.classify.DUP_MAX_M`, imported). A pair the lane finds itself and the list names too is one
retirement with both evidences (the 3: Tarxien Temples, Bishop's Basilica of Philippopolis, Dooey's
Cairn); a loser the two name with different survivors is refused. No duplicate touches a site of
`DUPLICATES_HELD.jsonl` (Banias / Caesarea Philippi, B10), whoever found it.

Re-planned offline from the same export as before (07:41:01 UTC): **115 sites, 230 cells: 79
retired (55 rule a, 2 rule b, 19 duplicates, 3 museums), 19 pending, 17 in_scope, 0 refused**
(before: 99 sites, 198 cells, 63 retired). All 19 listed pairs held in that export and still hold
in production (read-only re-read, 11:00 UTC: same item on both rows, within 2 km, both curated and
unassessed). The plan is stale on arrival and is re-planned in the apply order below: Yenikale's
point moved at 07:45 UTC (guard 5 would refuse the whole transaction), and the reversals change
`period_start`/`site_type` of sites the scope premise holds.

### card-stats-2026-09-23, as committed

Planned from the 03:59:54 UTC export: 6,104 cells over 1,566 of 5,004 cards; the counterfactual put
back 1,275 journalled inputs and reproduced all 60,048 stored cells; `BASIS.json` horizon
`journal_max_id` 30815. Stale by design: 35 journalled input rows at 25 curated sites since
(the inventory's read, 09:21 UTC), and both reversals and the scope lane write before it. **Owned cards**
(read-only, about 11:00 UTC, `card_collections` on the planned sites): **12 rows of 4 users on 11
sites** change stats; **3 rows of 2 users on 3 sites** change rarity (the 502 sites whose
`rarity_tier` moves). The re-plan will move these numbers.

### Corrections to the builder's report (review findings R0-5, R1-5)

The operator list in the builder's report of `1ad071a` is not versioned; these are the facts as the
code and the data give them, each re-checked here:

* **Step 3d names the wrong metrics.** The card_stats read-back prints `curated rows whose
  card_stats civilization differs from the site country` (`card_stats.py:207`; 62 today, read as
  journal-reversal-1's equivalent count, one card per site) and `card_stats rows whose total_power
  is not the sum of the five stats`
  (`card_stats.py:268`). `card_stats rows whose civilization differs from the site country` is
  journal-reversal-1's read-back, not the card_stats wave's.
* `DECISIONS.json` holds **41** decisions, not 42: a/pending 8, b/pending 11, b/retired 2,
  d/in_scope 17, d/retired 3.
* The builder re-pointed **11** existing sweep needles, not 12 (sweep `c186008` vs `1ad071a`: 167 ->
  267 cases, 11 changed, 0 removed, 100 added).
* **Owned cards**: 12 rows / 4 users / 11 sites change stats, 3 of them (2 users, 3 sites) in rarity
  - not "3 card_collections rows (2 users, 3 sites)".
* `card_stats.py --wave` is checked against `CARD_STATS_LANE` (`card_stats_lane` raises for a label
  `apply.py --lane card-stats-<label>` could not resolve; `main` exits 2,
  `test_a_wave_label_nothing_could_apply_is_refused`), and the `apply.py` docstring example is
  `card-stats-2026-09-24` (`apply.py:1708`), not the unresolvable `card-stats-w2`.
* The scope counts of the builder report (196 cells, 62 retired) are outdated twice over: the
  fixer's re-plan made them 198/63 (+Prambanan Temple), the duplicate list makes them 230/79.
* The reversal read-back counted sites under the name "curated cells ...": it is now `curated sites
  still holding a value this reversal list undoes` (45 for the 53 cells of reversal-2).

### Tests, sweep, gates

* Red first: 18 of the new scope tests fail on the previous `scope.py`, 46 of the new and adapted
  reversal tests on the previous `reversal.py`, the residual-name test on the previous `lane.py`.
* Mechanical tests (`tests/remediation/test_mechanical*.py`,
  `tests/api/test_cardgame_generator_stats.py`, with the map-units cache copied into the worktree):
  **716 passed, 0 skipped** (84 s).
* Mechanical sweep, all cases, run in this worktree after the merge, 11:03-11:59 UTC:
  **`cases: 469  fired: 469  skipped: 0  survived: 0  invalid: 0  unproven: 0  errored: 0`**,
  exit 0 (`mechanical/evidence/21_mutation_sweep_merged.txt`); 33 of the cases are new. One more
  case came after that run (`reversal: --lane names a reversal lane`); the reversal cases, run again
  with it after the second merge: **38 of 38 fired**
  (`mechanical/evidence/22_mutation_sweep_reversal.txt`), 470 cases in all. The fixer's run of 820358c (319 of 319 fired) is kept as
  `mechanical/evidence/20_mutation_sweep_fix.txt`.
* Full DB-less suite (`-m "not integration and not live_llm"`, timeout 300): **4569 passed, 32
  skipped** (gitignored data and fonts only), 57 deselected, exit 0, 297 s; after the second merge
  **4609 passed, 32 skipped**, exit 0, 306 s. `ruff check api/
  pipeline/ scripts/remediation tests/ output/remediation/tools/` clean, `ruff format --check` clean
  on every file this branch touches, lint-imports 2 kept / 0 broken, vulture exit 0.
* gitleaks over `integrate/wave1..HEAD`: clean after the 9 premise digests of `1984834` were
  triaged in `.gitleaksignore` (md5 premises after a site name containing "api"/"key"; a re-plan
  of a card_stats wave writes new ones - scan its commit).

### The apply order (the orchestrator runs it; nothing here was applied)

Owner gates first (`HUMAN_ONLY.md`): **"Was nur du entscheiden kannst" item 4** under B1/B2
(Ahin Posh Tape: the reversal and its point) before step 1; **B11** (keep or reverse the written
rows the new rules would not write: REREVIEW_1 decided 45 reverse / 32 keep - confirm the owner's
go covers applying it) before step 2; **item 2 / B6**, the per-site go for the 19 duplicate
retirements (`mechanical_scope/REVIEW.md`, rule c), before step 3. Each step: rehearse, probe,
apply, read back. Commands from the repo root with `PYTHONIOENCODING=utf-8`;
`A=scripts/remediation/mechanical/apply.py`.

0. `./.venv/Scripts/python.exe $A --check-primitive` -> the 0022 body.
1. **journal-reversal-1** (3 cells on 3 sites).
   `./.venv/Scripts/python.exe scripts/remediation/mechanical/reversal.py --lane journal-reversal-1 --collect --write`
   -> `PLAN.jsonl` unchanged (re-rendered byte for byte at 10:53 UTC); if it changed, `$A --lane
   journal-reversal-1 --emit` and read the diff. Then `$A --lane journal-reversal-1` with
   `--verify` (before: `curated sites still holding a value this reversal list undoes` 3) and
   `--interests`; `--rehearse` (NOTICE `journal reversal: 3 of 3 planned cell(s) changed and
   journalled over 3 curated site(s)`); `--probe-guards` -> exit 0, 7 probes each refused by its
   own guard: guard3-foreign-old-value, guard2-no-op, guard2-foreign-column, guard2-too-long,
   guard1-other-source, guard6-journal-row, guard6-not-the-inverse; `--rehearse-rollback`;
   `--apply` -> APPLY OK, 3 journal rows; `--verify` -> the residual 0.
2. **journal-reversal-2** (53 cells on 45 sites), the same sequence with `--lane
   journal-reversal-2` (`reversal.py --lane journal-reversal-2 --collect --write`, NOTICE `53 of 53
   planned cell(s) ... over 45 curated site(s)`, the same 7 probes). After: `curated sites still
   holding a value this reversal list undoes` 0, `curated rows whose period_name is not the bucket
   of period_start` unchanged (11 on 2026-09-23), 53 journal rows. Then the acceptance:
   `./.venv/Scripts/python.exe output/remediation/tools/verify_writes.py --allow-stamp
   2026-09-22_mechanical-uk-parts --allow-stamp 2026-09-23_mechanical-journal-reversal-1
   --allow-stamp 2026-09-23_mechanical-journal-reversal-2` -> 0 deviations (48 more rows
   superseded: 3 + 45; the 8 label rows are the period-name lane's, not phase 3's). In the
   period-name lane's own read-back, `journal rows for this run whose value is not the row's
   bucket` rises by 8: its 8 labels are undone together with the starts they came from - by
   design.
3. **scope-e4**, re-planned: `./.venv/Scripts/python.exe scripts/remediation/mechanical/scope.py
   --export --collect`, then `scope.py --write` (T11 needs geopandas and Natural Earth in
   `output/remediation/cache/naturalearth/`; every DECISIONS quote and every DUPLICATES line is
   re-checked; expect about 115 sites / 230 cells, Yenikale re-read), `$A --lane scope-e4 --emit`,
   commit the lane directory. Then `--verify` / `--interests` / `--rehearse` (NOTICE `E4 scope
   decision: <n> of <n> planned cell(s) ...`) / `--probe-guards` (6: guard3-foreign-old-value,
   guard2-no-op, guard2-foreign-column, guard1-other-source, guard4-not-owned, guard5-premise) /
   `--rehearse-rollback` / `--apply`. After: `curated rows with scope_status retired` = the plan's
   retired count (79 at the 07:41 export), `curated rows retired as a duplicate` 19, and 0 for
   `curated rows outside the E3 window with no scope decision`, `curated rows without a date and
   no scope decision`, `curated rows with a scope_status but no scope_reason` and `retired
   duplicates whose survivor is retired or not curated`. `/api/sites/all` serves from a 30-minute
   Redis cache.
4. **card-stats-2026-09-23, last**, re-planned: `./.venv/Scripts/python.exe
   scripts/remediation/mechanical/card_stats.py --wave 2026-09-23 --export`, then `--write`
   (refuses unless the counterfactual reproduces every stored cell), `$A --lane
   card-stats-2026-09-23 --emit`; commit `PLAN.md`, `SKIPPED.jsonl`, `ROLLBACK.sql` and
   `BASIS.json` (the next wave's proof reads it) and run gitleaks over that commit. Then `--verify`
   / `--interests` / `--rehearse` (about 6,100 `apply_remediation_change` calls in one DO block
   under `statement_timeout` 120 s - watch the time; a timeout is psql exit 3, NOT COMMITTED) /
   `--probe-guards` (7: guard3-foreign-old-value, guard2-no-op, guard2-foreign-column,
   guard2-too-long, guard1-other-source, guard4-not-owned, guard5-premise) / `--rehearse-rollback` /
   `--apply`. **Straight after the apply** `--verify`: `curated rows whose card_stats civilization
   differs from the site country` 0 (62 before), `card_stats rows whose total_power is not the sum
   of the five stats` 0, `journal rows for this run whose row is not a card_stats row` 0, plus the
   tier counts. Completion: `card_stats.py --wave 2026-09-23b --export --write` must print
   `"cells": 0` and write no statement (a read-back, not a wave: do not apply or commit it).
## 2026-09-23 - owner-case coordinates, wave 2: a third witness from the web (planned, not applied)

Wave 1 (`2026-09-23_owner-case-coordinates`, 9 sites, 27 journal rows) is applied. It left 171 of its
cases `review` (`bcases/coords.jsonl`): one witness only, two witnesses that are one (a copy, a rounded
copy, one point), two that disagree, none. This lane looks for a third statement of where each site
is, outside Wikipedia and Wikidata, and weighs it under wave 1's rule. **Nothing was written to
production.** Production contacts, all reads: `bcases/run.py check --wave 2` and one journal count
per coordinate stamp.

The builder of this lane (workflow `wf_bb241314-8a0`) died with its work uncommitted; the salvaged
state was committed as it stood, merged with `integrate/wave1`, and its review phase - which never
ran - was done here, with every finding fixed test-first (below).

### The lane (`scripts/remediation/bcases/web_witness.py`, `run.py web-verify|reweigh|plan|check --wave 2`)

* **Research** (agents, untrusted): `coords3/RESEARCH.jsonl`, one line per case, candidates with a
  URL, the two numbers and the page's own words (`coord_text`). 171 lines, 108 with candidates,
  141 candidates, 63 with a `none_reason`.
* **web-verify** (network) proves each candidate from the live page or rejects it with the first check
  that fails: not a Wikipedia/Wikidata host or mirror (`WIKI_HOSTS`), not our own site or a blocked
  host, a public address (every redirect hop too, inside the transport; the host checks run again on
  the URL a redirect ends at), one request through `census.fetch.Fetcher` with the project user agent
  (an HTTP error or a transport failure is a rejection with its status, never asked another way), an
  HTML page and no challenge page, `coord_text` standing whole in the page text (Lyra's reader,
  entities undone, NFKC and glyph variants unified), parsed to exactly the candidate's numbers
  (1e-6 degrees; decimal, D M, D M S; grid references refused), and a distinctive word of the stored
  name within 1,500 characters. Output: `coords3/WEB_WITNESSES.jsonl`, one row per candidate.
* **reweigh** (offline) classifies each case again with the same cache - first without web witnesses,
  which must reproduce `coords.jsonl` row for row, then with its accepted ones - under wave 1's rule:
  two independent witnesses agree within the tolerance and the stored point lies outside it. A web
  witness is named by its publisher (the registered domain) and comes last in priority. A move into
  another country is held as `review`; a wave-1 site is refused. Output: `coords3/VERDICTS.jsonl`,
  `coords3/COUNTS.json`.
* **plan --wave 2 / check --wave 2**: wave 1's renderer, parameterised (`coord_plan.Wave`): stamp
  `2026-09-23_owner-case-coordinates-wave2`, directory `bcases/coords_plan_wave2/`, confidence
  `two_source`, three journalled changes per site (`geom`, `lat`, `lon`), conditional on the old value,
  a stamp-scoped journal guard, `ROLLBACK.sql` under its own stamp. Wave 1's `APPLY.sql`,
  `ROLLBACK.sql`, `PLAN.jsonl` and `PLAN.md` still render byte for byte (a test compares all four).

### Review findings, each fixed with a test that goes red without it and a mutation case

1. A redirect was checked against the wiki list only: a page redirecting to our own site or to a
   blocked host passed. The final URL now goes through every host check.
2. `--wave` was accepted and silently ignored by every command but plan/check/verify; it is now a
   parser error there.
3. A web witness was named by its host minus `www.`, so two subdomains of one publisher
   (`whc.unesco.org`, `en.unesco.org`) were two independent witnesses. It is now the registered domain
   (three labels under a country's shared second level such as `co.uk`, `gov.pk`); an unknown shared
   level groups more hosts, never fewer.
4. A sign parted from its number by a space, or an en dash the glyph table does not make a minus, was
   dropped: the number read positive. Such a text is now unparsed.
5. Two signed decimals were read latitude first whatever the labels said ("Longitude / Latitude
   -0.358, 51.754"). A signed quote whose first axis label is a longitude one is now unparsed.
6. The quote was matched as a plain substring, so a quote cut from a longer or signed number matched
   ("17.5744" inside "-17.5744", "-89.9958" inside "-89.99583"): a sign error in the stored point could
   so be confirmed. A quote now counts only where it stands whole; for a quote without hemisphere
   letters also no sign, dash or lone hemisphere letter one space away. (A first version refused a
   dash before a lettered quote - measured on cestenfrance.fr, "Franche-Comte – 47°14'02.9"N" - and
   was narrowed to signed quotes.)
7. Independence was tested pair by pair: two pages that are each the item's point (within an
   arcsecond, or roundings of it) but 40 m apart moved the site on one statement counted three times.
   `copy_groups` now follows "are one" through chains; with two witnesses a group is the pair itself.
8. Measured on the live run: Pusilha's P625 was imported from the Cebuano Wikipedia, whose geographic
   articles were generated from GeoNames, and its web witness was geonames.org - a planned 5.2 km move
   on one source. Mersinaki's P625 cites phrc.it by URL, its web witness is phrc.it. A P625 whose
   references name the page's publisher (`cited_publishers`: P854 URLs; P143 Q837615 and P248 Q830106
   for GeoNames) is now one with that page.
9. `COUNTS.json` counted "one witness only (web:geonames.org)" as "one witness only (web" - the reason
   class now keeps the bracket.
10. The sweep itself found one: after finding 6, "the quote occurs in the page" was subsumed by "the
    quote stands whole in the page", so its mutation case survived (93/94). The two are one check now,
    with the same two messages.

Findings 7 and 8 change `classify.py`; the field they add is not part of a verdict's record, and a full
reclassification over the main checkout's cache still reproduces `COUNTS.json` and all seven delivered
files of the first wave.

### The run (2026-09-23)

web-verify, 141 candidates, each page asked once (cache: the main checkout's gitignored
`output/remediation/cache/bcases/web/`, 82 pages):

| outcome | candidates | what |
| --- | --- | --- |
| accepted | 45 | 23 publishers: geonames.org 8, ahlfeldt.se (DARE) 7, topostext.org 5, vici.org 5, paganplaces.com 2, 18 others 1 each |
| http | 59 | megalithic.co.uk 47 read timeouts (30 s), whc.unesco.org 10 HTTP 403, patrimoniocultural.gov.pt 1 HTTP 403, culture.tw 1 TLS certificate failure |
| unparsed | 13 | labels this parser does not read (`geo:` 3, Lonxitude 2, Latitud/Longitud 2, Chinese hemisphere words), a longitude-first quote twice, a decimal comma, degrees written with `d` or without a degree sign |
| not-on-page | 10 | the quoted text is not in the page's text - numbers in a map link, a script or a JavaScript-drawn page (OpenStreetMap 4, wikimapia, alaska.org, heritagemalta, sindhculture, mersin.bel.tr, isprambiente) |
| identity | 6 | no distinctive word of the name within 1,500 characters |
| not-html | 4 | Pleiades answered JSON and Turtle, two PDFs |
| grid-reference | 2 | "Easting ... Northing" and a decimal comma read as a projected value |
| mismatch | 2 | datahub.drago.pe prints longitude first; the agent's latitude-first numbers did not match |

megalithic.co.uk (47 candidates, the largest source) and whc.unesco.org (10) were not readable from this
workstation with the project user agent; their candidates were never checked, not rejected on content.

reweigh, 171 cases: **7 move, 8 stored-agrees, 156 review** (35 cases have one web witness, 5 two,
131 none). One move is held for its country (Flevum: Wikidata and vici.org agree in the Netherlands,
225 km from the stored point in Germany). `plan --wave 2`: 7 sites, 21 journalled changes.
`check --wave 2` against production: **21 rows, 0 deviations**; the journal holds 27 rows of wave 1's
stamp and none of wave 2's.

| site | moved | Wikidata P625 | web witness (quote) | pair |
| --- | --- | --- | --- | --- |
| Teanum Apulum | 27.26 km | Q3017180 41.763700, 15.241690 | imperium.ahlfeldt.se/places/23226 "41.77125, 15.23548" | 985 m |
| Aziz Dheri | 15.81 km | Q88078046 34.245464, 72.393405 | doam.gov.pk/public/sites/2330 "Latitude: 34.241666667 Longitude: 72.402333333" | 923 m |
| Kephala, Kea | 4.15 km | Q1739125 37.680899, 24.328623 | topostext.org/place/377243XKef "Latitude: 37.681700 Longitude: 24.328600" | 89 m |
| Jordbro Grave Field | 3.92 km | Q10540828 59.131944, 18.122694 | guidebook-sweden.com "59°7′53.7″N 18°7′29.0″E" | 122 m |
| Dalj | 2.69 km | Q912341 45.484361, 18.987394 | geonames.org/3202215 "45.48438, 18.98610" | 101 m |
| Great Dolmen of Dwasieden | 1.39 km | Q575698 54.502100, 13.609100 | paganplaces.com "54.5020817, 13.6069502" | 139 m |
| Karnak Temple Complex | 1.14 km | Q522862 25.718333, 32.658333 (imported from enwiki) | imperium.ahlfeldt.se/places/21108 "25.7191736, 32.6566111" | 196 m |

Every move goes to the Wikidata point (first in priority). Stored-agrees (no change): Tenam Puente,
Baking Pot and Argishtikhinili (geonames.org), Colybrassus (nomisma.org), Tower of Elahbel (vici.org),
Talgua Caves (showcaves.com), Menir da Cabeça do Rochedo (prehistoricportugal.com, 3 m) and Lycaean
Tomb (allovergreece.com).

### For the reader of the plan

* Dalj's record describes the village (its item is "settlement in Croatia"); the move puts it at the
  village's Wikidata and GeoNames point.
* Teanum Apulum's pair agrees within 985 m of a 1,000 m tolerance.
* Two accepted witnesses matched their name on a type word only (Lycaean Tomb: "tomb", page "Lykian
  Grave | Kastelorizo"; Menir da Cabeça do Rochedo: "menir", the full name in the page title). Both
  pages were read by hand: they are the site's own pages. Both are stored-agrees, no move.
* Three pairs rest on a P625 "stated in" an item this workstation could not identify offline:
  Xultun and Cusichaca River (P248 Q1194038, web witness geonames.org) and Mankby (P248 Q31017965,
  web witness kyppi.fi). None of them is a move; if Q1194038 is a source GeoNames copies, or Q31017965
  the register kyppi.fi publishes, `REFERENCE_PUBLISHERS` should name them before a later run.
* Stored points far from every witness while the witnesses are one source stay `review`: Trajan's
  Forum 374 km, Petroglyph Beach 236 km from Wikidata/enwiki (1.7 km from its web witness), Hadrian's
  Gate 42 km, Cusichaca River 35 km, El Kab 26 km. These are wrong points the rule cannot move.

### Tests and proofs

* `tests/remediation/test_bcases_web.py`: 74 tests, no network (a scripted fetcher that refuses what
  the real one refuses, the real fetcher on a mock transport, a fake psql reader); with
  `BCASES_CACHE` at the main checkout's cache all 74 pass, including the reproduction of the delivered
  second wave and the no-web-witness identity with the first.
* `mutation_sweep.py bcases` after the last code change: **180/180 caught**, among them all
  **94/94 "bcases web:"** cases (70 from the builder, 24 added for the findings above); the tree
  byte-identical to the sweep's start for 9 files - and again 180/180 after the second merge of
  `integrate/wave1` (wip/ops2). The standalone "bcases web" run before finding 10
  read 93/94. The sweep now runs from a worktree with the interpreter that runs it (`sys.executable`,
  from `integrate/wave1`), so no wrapper was needed.
* Gates on the merged tree (after the second merge of `integrate/wave1`): full suite (`pytest -q -rs
  --timeout 300 -m "not integration and not live_llm"`) **4,275 passed**, 110 skipped - every skip is gitignored data this worktree does not
  carry (Natural Earth caches, snapshots, worklists, the bcases caches; the three bcases ones pass
  with `BCASES_CACHE` at the main checkout's cache, and the full reclassification was reproduced by
  hand) - 57 deselected; `ruff check` over api, pipeline, scripts/remediation, tests and
  output/remediation/tools clean; `ruff format --check` on the six touched Python files clean;
  `lint-imports` 2 kept, 0 broken; `vulture` clean.

## 2026-09-23 - Track C's "every guard is proven" was not true; the p4-verify findings closed, with the real counts

Commit `6782fe3` on wip/p4-verify is titled "Prove every Track C guard with a mutation case (100/100
caught)" and says its sweep "breaks each guard of verify4 ... of verify_writes4 ... and of the
shorts S13 card trace". The 100/100 was real for its 100 cases; the claim that they were every
guard was not:

* **Rules review** (wf_57d89c7d-7ac, read-only): 46 guard conditions that no case named, removed one
  at a time, left the Phase-4 suite green in 42 cases; 34 of them were reachable gaps (V1's pin
  checks, V8's citation checks, V12's citation equality, V13's card presence, S13's inputs, the
  one-sided and bracketed dash, each V5 artefact, curly-quote balance, the strong-own conditions,
  lane T's trimmed quote, the batch's lane sources, the acceptance's planned-outside-lane check).
  The inventory re-checked 17 of them in memory: all green without the guard.
* **Correctness review**: four majors and three minors the 100 cases did not touch - V7 matched a
  lane-S heading in both directions (C1), nothing checked that a range is one whole sentence (C2),
  V10 rebuilt T/R cards from French or restricted text (C3), the acceptance failed every card-held
  site (C4), one trailing space passed (C5), `name_in` matched inside words (C6), V14 held the
  eight `Chile, Easter Island` sites (C7).

### What wip/p4-verify-sup changed (commits `21822ea` .. `be79b23`)

* The interrupted fixer's verify4 finder (section 7 before the evening's decision) was committed as
  found (`21822ea`), then finished: the shared-comma refusal (two insertion pairs that share a
  comma offer neither), and D2 - V10's spoken edit is `model4.CIRCA_PATTERN`, no circa pattern of
  verify4's own (`c. AD 79` now reads as S4 reads it).
* C1-C7 as the reviews proposed; see PHASE4_CONTRACTS.md section 5, Track C, for each reading.
* Found on the way: V8 compared a citation's domain with the URL's full netloc, while S4
  (`assemble.domain_of`) and production (`api/main.py`'s seeded citations) write the host without
  `www.`; every lane-R citation on a `www.` host would have been held. V8 now reads the production
  form, and the lane-R fixture follows it.
* V14's string-equality fallback was dead code (every name `countries_named` finds has a code) and
  is gone; a stored country with no code agrees with no named country, as before.
* The acceptance: C4, and the follow-up wip/p4-write-sup left for this merge - a lane row with its
  own kept reversal (its change key **and** its run stamp, each plus `-rollback`, revert4's
  `_reversed`) is reverted, not "changed later" and not a second write; a row whose lane rows are
  all reverted is judged like one not yet written. Both journal reads now carry `change_key`.
* R3: S13's two inputs come from `shorts_audit.card_trace`; `measure_site`'s use of it is pinned by
  an AST test, because `measure_site` itself needs a rendered short (ffprobe).

### The counts, measured on wip/p4-verify-sup at `be79b23`

* **Tests.** `test_phase4_verify.py`: 112 test functions (76 at `6782fe3`), 242 collected, 241
  passed, 1 skipped (the brand fonts, gitignored). `test_phase4_accept.py`: 34 (29). The S13 tests
  in `tests/pipeline/video/test_shorts.py`: 8 (6). Every fix was red first: 25 failures in the two
  Phase-4 files plus the shorts module's `card_trace` import error, before any code change.
  The tests of guards that already existed (R1, R2, R4, R5) were green before; their sweep
  cases are what shows each of them red without its guard.
* **Sweep.** `PHASE4_VERIFY_MUTATIONS` (100) plus the new `PHASE4_VERIFY_SUP_MUTATIONS` (105, each
  list registered once): **205 of 205 caught**, the four mutated files byte-identical afterwards,
  `git status` clean, no `# mutant` line outside the sweep files. By family: 165 `p4 verify4:`, 32
  `p4 verify_writes4:`, 7 `p4 shorts_audit:`, 1 `p4 shorts_export:`. Eight older cases were
  re-anchored where the new code replaced their lines. The first run of the new list read
  **204/205**: "a row without a change key has a reversal" survived, because the keyless test had
  no row under the reversal stamp and `any()` never reached the null key; the test now also holds
  a keyless write followed by its keyless reversal open (SQL `NULL || '-rollback'` equals nothing),
  and the case is caught.
* **D3 parity.** The parity test runs `sentences.split_source` and verify4's finder over the 50
  `SPAN_CASES` and 17 texts of the verifier's own: identical ranges. Read-only over the 3,661 local
  enwiki extracts (`phase3_runner/runs/mass`): 170,528 sentences, 81,979 of them in a lane-W pool,
  144,272 spans offered by S2 - **0** sentences on which the two finders differ, and every S2
  sentence range is one sentence of verify4's split, so V2's whole-sentence check holds no S2 pick.
* **Gates** on the merged tree (integrate/wave1 `234e198` and wip/p4-select-sup `c5c4335` merged
  in): `pytest -q -rs --timeout 300 -m "not integration and not live_llm"` **5,306 passed**, 116
  skipped (gitignored data, caches and the brand fonts), 57 deselected; `ruff check` over api,
  pipeline, scripts/remediation, tests and output/remediation/tools clean; `ruff format --check`
  on the eight touched Python files clean; `lint-imports` 2 kept, 0 broken; `vulture` clean.

### What 205/205 still does not prove

The sweep proves that each listed case is caught; it cannot prove that the list is complete. Left
without a case, on purpose: the `l` rule's "text after the comma" check (unreachable once the
sentence must end in `.`, `!` or `?`), the split's `if piece:` and heading-line skip (equivalent:
an empty range or a heading range is never a published sentence's), the lane read's key map
(equivalent: the chain read records every lane row's key as well), and `change_key` in
`JOURNAL_COLUMNS` (removing it raises `KeyError`; it never passes). The pre-pilot end-to-end run of write4, write_gate4 `--round 2`, revert4 and the
acceptance together needs wip/p4-write-sup on the same tree; it is not on this branch.
## 2026-09-23 - the Phase-4/5 writer (Track D), reviewed: 13 findings, what the supplement changed

Branch `wip/p4-write-sup`, on `wip/p4-write` (708cf0b, WB-D1 ... WB-D5), with `integrate/wave1`
(f32c95d) merged in. Two reviews of Track D - correctness (5 findings, C1-C5) and rules/teeth (8,
R1-R8) - were each checked against the code and closed. A first fixer answered 11 of them and died
before committing; its tree was committed as found (676e1f9), then merged with `integrate/wave1`
(one conflict, the tools README table, both sides kept) and finished under the orchestrator's
decisions D4-D6. **Nothing was written to production, and this supplement read nothing from it**;
the production figures below are the reviewers' read-only measurements.

### Correctness

* **C1 (major) - `revert4` could not undo a second write round.** Confirmed: a change key names a
  transition, not a write, so round 2 of a batch journals the same keys as round 1, and the
  "reverted already" guard matched on the key alone - after one revert, `--stamp-like 'phase5:%'`
  (the red-CI answer of the P5 sitting) was refused for good. Now "reverted already" is the key
  **and** the stamp plus `-rollback` (`revert4._reversed`), and `revert4` **skips** a matched write
  that already has its own reversal instead of refusing the pattern; it raises only when the
  pattern matches nothing or only reverted writes. Why skip rather than refuse: refusing left the
  live round revertable only by its exact stamp, and reverting the reverted round again would need
  its field to hold its written value - which round 2 may have put back - and would undo round 2's
  write under round 1's stamp. The set is fixed inside the transaction before anything moves, and
  every guard, the loop and both invariants run over exactly that set. Test:
  `test_revert4_reverts_the_live_round_and_refuses_the_reverted_one` (the rendered set query and the
  post-read evaluated in SQLite). **The new PL/pgSQL has never run on PostgreSQL**: rehearse it
  (`revert4.py --rehearse`) before relying on it.
* **C2 (major) - the gate never required the acceptance between steps.** Confirmed by the reviewer's
  probe (two `--apply --step 100` calls wrote 120 sites with no check between). Now a handshake:
  every written batch is recorded in `STEP.json`; while it exists `--apply` writes nothing; `--accept
  <file>` records `ACCEPTED/step-NNNN.json` only for a `verify_writes4.py` output that ends in
  `ACCEPT_EXIT=0`, says `RESULT: 0 deviation(s)`, has one lane line of the step's lane whose stamps
  cover the step's, read at least the rows written so far, and accepted no earlier step. Tests:
  `test_a_step_without_its_acceptance_blocks_the_next_step` (nothing is sent, not even a preflight),
  `test_an_acceptance_that_does_not_accept_this_step_is_refused` (6 cases),
  `test_one_acceptance_output_never_accepts_two_steps`. The lane line is parsed in the print format
  of `verify_writes4.py` on `wip/p4-verify`; a change there must change `write_gate4._ACCEPT_LANE`.
  Found while documenting it: the command the gate printed for the acceptance lacked `--run`, which
  `verify_writes4.py` requires for lanes p4 and p5 - it now names the run directory
  (`test_the_gate_prints_the_acceptance_command_it_will_accept`, red first).
* **C3 (minor) - a step of 100 wrote up to 114 sites.** Now a batch is written only while it still
  fits: 8 batches of 15 sites give exactly 90 journalled sites
  (`test_a_step_of_100_sites_never_writes_more_than_100`); a batch larger than the step is refused.
* **C4 (minor) - every journalled column moved the sitemap lastmod.** The ~4,300 P5 card writes would
  have re-announced (sitemap and the hourly IndexNow cycle) pages whose content does not change.
  `public_sites.PAGE_COLUMNS` now lists the columns the SSR page reads, per table - see D6 below.
* **C5 (minor) - lane L claimed the March chain for sites the snapshot does not have** (decision
  D4). `snapshot_description` is NULL both for a site d4526691 lacks and for one it holds without a
  text, so a held site created after 2026-03-04 (8 curated sites, 7 of them on 2026-04-24, by the
  reviewer's read) would have been marked "generated by the 2026-03 enrichment chain" with a basis
  that has nothing to compare against. `PlanSite` gains `in_snapshot` (model4 change accepted by the
  orchestrator; `plan4` reads it with `EXISTS` on `snapshot_rows`), and `legacy4` makes no claim
  for an absent site and lists it under the closed reason `NoClaim.NOT_IN_SNAPSHOT`
  (`not-in-snapshot`, in UNCLAIMED.jsonl for HUMAN_ONLY). Red first: the two legacy tests planned
  the claim before the fix.

### Rules and teeth

* **R1 (major) - the SQL guards had no teeth.** The fake psql applies its own Python checks when a
  comment marker is present, so a predicate or RAISE could be deleted with the suite green. Every
  predicate and RAISE of `render_apply`, `render_rollback` and `render_revert` is now pinned byte for
  byte (`tests/remediation/phase4_write_pins.py`), and 33 mutation cases each break one of them.
* **R2 (major) - round 2's read-back read either round's journal row.** `write_stage.journal_rows_sql`
  now takes the run stamp and filters on it; the per-row comparison is one helper,
  `write_stage.journal_mismatches`, used by Phase 3's and Phase 4's read-back. Test:
  `test_a_batch_written_again_after_a_revert_reads_back_its_own_round`, for either journal order.
* **R3 (major) - the checks around a chunk were untested.** The fake psql got sabotage hooks (a
  write moved after commit; a rolled-back statement whose journal rows survive); 9 tests make the
  read-back, the rehearsal trace, the inverse proof, a surviving reversal, a journal row with other
  values, a stamp's extra row, a non-curated site and a missing `card_stats` row each stop the run.
* **R4 (major) - most plan-side guards were untested.** One red test per guard: `validate_rows` (8
  tampered fields, 4 raw_data cases, the 200-character card), `Chunk4`, `load_batch` (a site twice, 6
  files naming a site wrongly), `model_files`, the open-lane and step checks, the audited list, the
  card-clear evidence (`phase3_card_findings`), `card_json` and the API disclosure.
* **R5 (minor) - the journal evidence was weaker than documented** (decision D5). Every call had to
  be complete, but none was required by name: a site whose only answer was a translation was
  planned. `model4` now names the calls (`SELECT_FEATURE` ... `REVIEW_FEATURE`, `LANE_ANSWERS` - the
  names Track B's `batch4` stores under) and `write4.evidence_problems` requires the lane's calls by
  name - the selector's for W, S and T (the design's "selector-answer sha256"), T's translation
  beside it, lane R's restricted call - and the reviewer's for every lane. The test fixtures now use
  Track B's names (`select`, `review`) instead of invented ones. Red first:
  `test_a_site_without_the_selectors_answer_is_refused` planned the site before the fix.
* **R6 (minor) - duplicated utilities.** `ReadBack4` is gone (`write_stage.ReadBack`), the journal
  loop is `journal_mismatches`, the UTF-8 stream setup is `write_stage.utf8_streams()` for
  `write_gate.py` and `write4.exit_line`.
* **R7 (minor) - the empty-list half of the card-clear evidence guard** is tested (`{}` and
  `{site: []}`), and its mutation case now keeps `None` handling intact.
* **R8 (minor) - `provenance_of` silently read a malformed provenance as none.** It now raises when
  `_description_provenance` is present but not an object, as the public route already did; no
  production row carries the key today.

### The site page's lastmod (decision D6)

The first fix of C4 counted only `unified_sites` rows, so an image lane's hero change - journalled
with the site in `site_id_ref` - no longer moved the date although the page shows that image.
`PAGE_COLUMNS` is now per table and equal to what the detail route reads: 12 `unified_sites` columns
(the design's six plus period_end, period_name, lat, lon, source_url and parent_site_id, which the
page renders and later lanes journal), `card_stats.best_wiki_url` and `source_language` (the page's
Wikipedia link), and the `wiki_images` columns that pick the page's one image (is_hero, is_excluded,
is_lead, sort_order) or that it renders of it (filename, author, license, commons_page_url, width,
height). Not counted: the card, the card game's stats, `geom`, `thumbnail_url`, and the image
columns the page never shows. `test_the_page_columns_are_exactly_the_ones_the_ssr_route_reads`
derives the three lists from the route's own SQL. A rendered image column counts for every image of
the site, not only the shown one - the journal does not say which image was shown at the time, and
announcing a gallery change is the cheaper error than missing a hero change.

### Measured (the worktree of `wip/p4-write-sup`, main venv)

* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`): **4,355 passed, 108
  skipped**, 57 deselected; every skip names gitignored data (Natural Earth, the snapshot, the
  worklist, the design file) or the pre-existing `_write_article_body` refactor. Merged tree before
  the supplement's own fixes: 4,342 passed.
* Mutation sweep, every "p4 " case (`mutation_sweep.py "p4 "`): **383/383 caught**, the tree
  byte-identical to the sweep's start for 23 files. Of them 111 are the supplement's
  (`PHASE4_WRITE_SUP_MUTATIONS`: the first fixer's 96, and 15 for D4, D5, D6 and the printed
  command), 54 Track D's first cases, 8 the API's. The fixer's two lastmod cases were re-anchored
  to the per-table filter, and Track D's legacy case moved with the legacy guard.
* `ruff check` (api, pipeline, scripts/remediation, tests, tools) clean; `ruff format --check`
  clean on every file the supplement touched and on api/ and pipeline/; `lint-imports` 2 kept, 0
  broken; `vulture --min-confidence 80` clean; the Lyra import check (no markdown, no nh3) passes.

### Not proven here, and what the merge must carry

* `revert4`'s PL/pgSQL and the write statements have run only as pinned text and through the fake;
  the first production contact is a `--rehearse`.
* `write_gate4 --accept` parses `verify_writes4.py`'s lane line, which lives on `wip/p4-verify`;
  `write_gate4` imports `phase4.verify4` (Track C) for P4. Neither is on this branch.
* On the merge with `wip/p4-select`: `batch4.SELECT_FIELD` ... `REVIEW_FIELD` take their values from
  `model4` (one spelling), and Track B's `tests/remediation/p4_fixtures.py` gains `in_snapshot`; on the
  merge with `wip/p4-verify`, `tests/remediation/phase4_cases.py` gains it too.
* No migration: `_description_provenance` is a key inside `raw_data`, the journal is 0017/0018/0022
  (applied), and `in_snapshot` is a field of the local plan file.
* Push #1 (HUMAN_ONLY D1) from this branch: the disclosure API (`api/services/description_provenance.py`,
  `api/routes/sites.py`, `sites_html.py`, `public_v1.py`, `api/schemas/public_v1.py`), the seed removal
  (`api/main.py`), the page lastmod (`pipeline/utils/public_sites.py`, read by the sitemap and by
  Lyra's IndexNow), and the frontend line, AI footnote and licence lines (`ancient-nerds-map/src/...`
  and `terms.html`). The sentence splitter (`pipeline/lyra/text_sentences.py`) is Track B's, on
  `wip/p4-select`. The frontend was not type-checked or tested in this worktree (it has no
  `node_modules`); `npm run type-check`, `npm run test` and the Playwright bundle swap against
  production come before that push.

## 2026-09-23 - the Track D supplement, checked: write round 2, the handshake after a revert, D7

An independent checker read `wip/p4-write-sup` at db6dcef and found three issues (C1 major, C2 and
C3 minor). Each was verified here; C1 is fixed, the gate's share of C2 is fixed and its Track-C
share is open for the orchestrator, C3 needs the orchestrator's HUMAN_ONLY edit (the gate's count
is fixed). **Nothing was written to production, and nothing was read from it.**

### C1 (major) - the documented write round 2 was a false success (fixed, 5e29f56)

Reproduced with the checker's probe (`C:/tmp/p4wcheck/probe_round2.py`): round 1 `--apply`, its
acceptance, the round's `ROLLBACK.sql` committed (what `revert4` journals), then `--apply --round 2`
printed "open batches: 0", "done: no open batch left to write", `WRITE_EXIT=0`, 0 statements, and
the journal held only chunk-0001 and its reversal. Cause: `render()` returned a batch that still had
its round-1 `APPLIED.json` with its round-2 chunk, and `run_batches()` skipped it as applied.

Fix: `--round N` re-opens a batch applied in round N-1 only on production's read-only word that the
round is reverted - as many journalled writes under its stamp as it wrote, each with its own
reversal kept. The read is `revert4`'s own post-read, now one function (`reversal_read`, parsed
strictly by `reversal_counts`), so gate and reversal share one definition of "reverted". The round's
`APPLIED.json` moves to `chunks/chunk-NNNN/` beside `REVERTED.json` (the proof) and chunk-000N is
written. Refused with `WRITE_EXIT=1` instead of skipped: round 3 over round 1, round 2 for a batch
never written, round 1 for a re-opened batch. The acceptance's rows-read rule counts every written
round, live and reverted, under the stamps the output read - counting only the live records would
have let an output taken between the revert and round 2 accept round 2. The same probe now sends 12
statements in round 2 and the journal holds chunk-0002.

### C2 (minor) - no way out of a pending step after a revert (gate share fixed, Track-C share open)

Verified: `acceptance_problems` needs `ACCEPT_EXIT=0`, `run_batches` blocks while `STEP.json`
exists, only `accept_step` removes it. The gate's share is fixed in the same commit:
`--close-reverted` closes a pending step on the proof above for every batch of the step, records it
in `CLOSED/step-NNNN.json` (never in `ACCEPTED/`), re-opens its batches and removes `STEP.json`; a
live row refuses the whole close, and `--round` does not re-open a batch of a pending step. The
Track-C share is open: `verify_writes4.accept4` (on `wip/p4-verify`) reads a write followed by its
kept reversal as CHANGED LATER and two rounds of a key as WRITTEN TWICE. A round-scoped
`--stamp-like` is no cure once a lane mixes rounds - probe `C:/tmp/p4wcheck/probe_mixed_rounds.py`
against the checker's export of `wip/p4-verify` 6782fe3: batch 1 reverted and written as round 2,
batch 2 live in round 1 gives `WRITTEN TWICE` and `CHANGED LATER` under `phase5:%` and `MOVED` for
batch 2 under `phase5:%:chunk-0002`. `accept4` needs to treat a link with its own kept reversal as
closed (PHASE4_CONTRACTS section 7, "After a revert"); the merged-branch test (write, revert,
round 2, accept) belongs to that merge.

### C3 (minor) - HUMAN_ONLY D7 does not name the sites absent from the snapshot (orchestrator)

Verified: HUMAN_ONLY D7 speaks only of held texts equal to the pre-March state, while
`legacy4.NoClaim.NOT_IN_SNAPSHOT` (e8480fd) lists sites that snapshot `d4526691` does not have in
the same `UNCLAIMED.jsonl`, each line with its `reason`. HUMAN_ONLY is the orchestrator's file. On
this branch the gate's report no longer sums the reasons: it prints "unclaimed by reason (HUMAN_ONLY
D7): {...}" (35ce513).

### Measured (worktree of `wip/p4-write-sup`, main venv)

* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`): **4,373 passed, 108
  skipped**, 57 deselected (18 more than before the check).
* Mutation sweep, every "p4 " case: **398/398 caught**, the tree byte-identical for 23 files; 15
  new cases (13 `write_gate4`, 2 `revert4`), and the kept-reversals case re-anchored to the shared
  read.
* `ruff check` (api, pipeline, scripts/remediation, tests, tools) clean, `ruff format --check`
  clean on every touched file, `lint-imports` 2 kept, 0 broken, `vulture --min-confidence 80`
  clean.

## 2026-09-23 - the Opus handoff: every model judgement answered by Opus, the DeepSeek transports removed

**Owner order (Martin, 2026-09-23, binding): "no DeepSeek any more - everything with Opus".** Until
then every model judgement of the remediation was bought from DeepSeek: the Phase-3 finder and
reviewer - and with them the sitelink, search and gap reruns, which run the same stages - and the
Phase-4 selector, translator, restricted-lane and reviewer calls on `opencode-go/deepseek-v4.1-flash`,
one `pi.cmd` process per call (`phase3/model_stage.PiRunner`); the gallery vision questions on
`deepseek-v4-flash-vision-exp` over the opencode gateway (`vlm_pilot/ask_vlm.ask_once`, called by
`gallery_audit/vision.py`). Branch `wip/opus-handoff` (from `integrate/wave1` 8a957b4, commits
`aa44da2` .. this one) replaces both transports with an **Opus handoff**: a stage writes its questions
to files, the orchestrating Claude Code session's Opus agents answer them, and the stage reads the
answers back. **Nothing was written to production, nothing was read from it, and no model API was
called** - no DeepSeek, Pi, opencode gateway or other model, in code or in tests.

### The design

**One contract, `scripts/remediation/opus_handoff.py`.** `OPUS_MODEL = "anthropic/claude-opus-5-5
(Claude Code agent)"` - one string, pinned by a test, named by every answer file, ledger line and
disclosure. A handoff directory (one per round; it may hold several batches and stages):

    <dir>/<batch_id>/MANIFEST.jsonl                 one line per exported question
    <dir>/<batch_id>/<stage>/<label>.prompt.txt     the exact prompt, UTF-8
    <dir>/<batch_id>/<stage>/<label>.answer.json    the answer, written by an Opus agent
    <dir>/images/<image_id>.jpg                     vision only: the exact JPEG the question is about

`<label>` is the call's label escaped as the evidence store escapes it (`quote(label, safe="")`:
`site-1/description` -> `site-1%2Fdescription`); the stage is a path component because the Phase-3
finder and reviewer ask about the same `<site>/<field>` label. Batch ids and stages are refused
unless they are one plain name (no separator, no `..`; `images` is reserved). A manifest line is
`{batch_id, stage, label, field, prompt_sha256, prompt_path, answer_path, image_path}`, paths relative
to `<dir>` with `/`, `image_path` null except for vision; one manifest per batch, so parallel
exports of different batches never share a file. An answer file is exactly

    {"prompt_sha256": "<sha256 of the exact prompt text, UTF-8>", "text": "<the answer, verbatim>",
     "model": "anthropic/claude-opus-5-5 (Claude Code agent)",
     "answered_at": "<ISO 8601 with a zone>", "answered_by": "<the agent's name>"}

* `export` writes the prompt (and image) write-once and then the manifest line: the same prompt again
  is a no-op, a different prompt or image for an exported question is refused (an answer may exist).
  No model call.
* `answer` (`write_answer`) is the helper the agents answer through, so no agent computes a digest:
  the question must be in the manifest, its prompt file must still hash to the manifest's digest, and
  the answer is write-once (the identical text again is a no-op; another text is refused - delete the
  file to answer again).
* `read_answer` refuses (never defaults) a missing file, a file not exactly in the answer shape, an
  empty text, a model that is not `OPUS_MODEL` and an answer to another prompt (stale digest).
* `validate` checks every manifest line: the prompt file still the exported one, the image present,
  the answer present, in shape, by Opus, for this prompt. It reports `missing`, `stale`, `malformed`
  (wrong model included) and `orphans` (answer files nobody exported); exit 0 only when all are empty.

**Phase 3.** `model_stage.HandoffRunner(directory=...)` implements the `ModelRunner` seam through
`read_answer`; every refusal is a plain `ModelCallFailed`, never an `UnreadableStream`, so the batch
stops at the question and the orchestrator answers it again, instead of a permanent named hole.
`MODEL = OPUS_MODEL`. `Usage` gained a required `metering` field and `Usage.unmetered()` (zero tokens,
cost 0, `metering="unmetered"`): an Opus answer on a subscription has no per-call meter, and the
record says so rather than faking a measurement. A ledger line (`LEDGER.jsonl`) keeps its shape and
adds `"metering": "unmetered"`; `phase3.ledger` refuses an unmetered line that carries any token or a
cost other than 0, any other metering value, and metering on a fetch line; a line without the key
(the Pi lines, and every fetch line) is written byte-for-byte as before; `StageTotals` counts
`unmetered_calls`. `run.py judge` has three modes: the preview (no flag), `--handoff-export DIR` and
`--handoff-import DIR` (mutually exclusive). **The export runs the stage's own judge function**
(`judge_batch`, `discover_stage.judge_discover_batch`, `review_stage.judge_review_batch`) with a
`RecordingRunner` against a scratch copy of the store it writes (`answers/` for the finder, `reviews/`
for the reviewer) and a scratch ledger: every call it would buy is captured with its exact prompt -
the frozen questions stay frozen - an answer already on disk is skipped exactly as the import skips
it, and nothing the recording run writes survives (no ledger line, no answer, no `model.json`).
`mass_run.py --live` is one half of a round: `--handoff-export DIR` runs a batch's stages up to and
including the judge (prepare, fetch or search, judge) and counts it handed off, not done;
`--handoff-import DIR` runs the judge and what follows it (`verify-hits` for a search plan) and then
the artefact check as ever. A live run without either is refused. `review_all.py` takes the same pair.

**Phase 4.** `run4 select` (S3 and S3R, which need no answer), `run4 translate` (S3T, a new command:
its questions are built from the selector's answers, so it is the next round) and `run4 review` (S6)
each take `--handoff-export DIR` or `--handoff-import DIR`. The export runs the stages themselves,
unchanged, over a scratch copy of the batch directory (under its own run and batch names) with a
recording runner, so holds, selections, answers and reports of the export never reach the batch.
The import runs them through `HandoffRunner`; every call still goes through `batch4.buy` and
`judge_site`, so write4's journal evidence (decision D5: the selector's answer by name, the
reviewer's, each with its prompt on disk and its ledger line) holds for handoff answers - proved end
to end through the CLI (`test_the_journal_evidence_of_a_site_answered_through_the_handoff_is_complete`).
`mass4.py` runs one round per live run: `--stages` (a contiguous part of `prepare, sources, routes,
select, translate, assemble, verify, review`) and at most one model stage, placed by the half
(`check_round`: an export ends at it, an import starts at it, a round with a model stage and no
handoff is refused). **`model4.AI_SYSTEM`**, the EU AI Act Art. 50 disclosure published with every
Phase-4 text, is now `"Claude Opus (Anthropic): anthropic/claude-opus-5-5 (Claude Code agent),
an-sites-remediation-2026-09"`; `LEGACY_AI_SYSTEM` (the March texts) is unchanged; no Phase-4 text
had been written, so no row carries the old disclosure. PHASE4_CONTRACTS section 6 records it as
accepted by the orchestrator 2026-09-23 on the owner's order; rules 3 and 4 and section 5 follow.

**Gallery vision.** `vision.py export --jobs J --run-dir D --handoff H` hands every job the run's
ledger holds no ok verdict for to the handoff: the filled frozen question (`GALLERY_PROMPT` /
`HERO_PROMPT`, unchanged; batch = the job's stage, stage `vision`, label `<image_id>/<prompt_id>`) and
the image as `pipeline.video.shorts_select.vlm_bytes` of the offsite copy (RGB, longest side 1280,
JPEG q85 - the bytes the pilot sent) at `images/<image_id>.jpg`. `vision.py import` refuses to start
while any job lacks a valid answer (exit 1, nothing written), then writes one `VERDICTS.jsonl` line
per job through the existing parsing (`extract_json`, `validate`: the in-vocabulary check, status ok
or failed, never `other` for a non-answer); an answer given about other bytes than today's JPEG is a
failed line. A line names `model` = `OPUS_MODEL`, carries `metering: "unmetered"`, `cost_usd` 0,
`answered_by` and `answered_at`; `verdicts_by_image` (and `decide.py`) already refuse any other
model, so the pilot transport's verdicts count no more. Because `calibrate.THRESHOLDS` names the
model, its sealed digest moved (`1040cd59...` -> `e6560457...`); the tracked
`calibration-2026-09-23/` stays untouched as the DeepSeek seal (the model is the only difference,
tested) and admits no Opus verdict: **the Opus C1 calibration needs a directory of its own, sealed
before its first question is exported** (commands below).

### What was removed

`PiRunner`, `pi_argv`, `PROGRAM`, `PI_FLAGS`, `THINKING`, `PROVIDER`, `DEFAULT_TIMEOUT`,
`Usage.from_message_end`, `parse_stream`, `_assistant_text`, `_count` and the `subprocess`/`os`
imports of `model_stage`; `judge --live/--timeout`; `run4.pi_runner` and `--live/--timeout` on
`select`/`review`; the two captured Pi transcripts (`tests/remediation/fixtures/pi_probe*.json`) and
the 11 tests that parsed them or drove a Pi process; in `mass_run` the DeepSeek cost projection
(`MEASURED_COST_PER_CALL`) and the spawn-failure shape "a program the child started could not be
started" (`UNSTARTABLE_PROGRAM`; the judge's Pi process was its only producer) with its 2 tests - the
NTSTATUS shape stays; in `vision.py` the `ask_vlm` import, the gateway call, its three attempts
(`VLM_ATTEMPTS`, `VLM_RETRY_WAIT_S`), the `run` command and the gateway ramp probe (`ramp_allows`,
`MAX_WORKERS_UNPROVEN`, `RAMP_*`) with its test and mutation case. `vlm_pilot/` stays as pilot
history: nothing that runs imports `ask_vlm.py` any more; the two pure helpers vision read from it
(`EXPECTED_KINDS`, `extract_json`) moved to `vlm_pilot/common.py`, which `ask_vlm.py` now imports.
The historical ledger lines, `PIECE3.md` and the sealed pilot documents are untouched; HANDOVER,
SITES_DB_REMEDIATION, the search stage's docstring and the gallery DESIGN name Opus where they
described the live route.

**Kept on purpose.** `UnreadableStream` and the loops' named-hole / `MODEL_STREAM_UNREADABLE`
branches: no runner raises it any more (every handoff refusal stops the batch), but it is the seam's
contract for an answer that is not one and the mass run's `model.json` files carry named failures
that `mass_run.batch_state` still reads; removing the branches is a separate change. The dollar
ceilings (`--max-usd`, vision's `--budget-usd`) stay: Opus lines add 0, historical lines still count.

### The orchestrator's commands, per stage

`PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe`, run from the repository root with
`PYTHONIOENCODING=utf-8`; `H` is a fresh handoff directory per round (for example
`output/remediation/handoff/<lane>-<stage>-<date>`). Every round is **export -> the Opus agents answer
-> validate -> import -> the stage's own gates**. The answering is the orchestrator's: for each line
of every `H/*/MANIFEST.jsonl` whose `answer_path` does not exist, an agent reads `H/<prompt_path>`
(and `H/<image_path>` for vision), writes its answer text - exactly the shape the question asks
for, nothing else - to a file, and runs

    $PY scripts/remediation/opus_handoff.py answer --dir H --batch-id <batch_id> --stage <stage> \
        --label <label> --answered-by <agent> --text-file <answer.txt>

then `$PY scripts/remediation/opus_handoff.py validate --dir H` must exit 0 before any import.

* **Phase 3, one batch** (discover, rerun, search or finding-driven): `$PY scripts/remediation/phase3/
  run.py judge --run-dir R --batch-id B --handoff-export H`; answer; validate; `... judge --run-dir R
  --batch-id B --ledger L --handoff-import H` (writes answers, ledger lines, `model.json`); for a
  search batch then `run.py verify-hits --live`; the reviewer the same way with `--stage reviewer`
  (a fresh `H`); then the writer as ever (`write_stage.py`, `write_dry_all.py`, `write_gate.py`,
  `verify_writes.py`).
* **Phase 3, a lane's plan**: `$PY scripts/remediation/phase3/mass_run.py --live --plan P --run-dir R
  [--stages prepare,search,judge,verify-hits] --handoff-export H`; answer; validate; the same with
  `--handoff-import H` (the judge, then `verify-hits`; done only by the artefact check). Reviewer:
  `$PY output/remediation/tools/review_all.py --lane <lane> --handoff-export H2`; answer; validate;
  `... --handoff-import H2` (writes each `review.json`).
* **Phase 4, a run** (`R` = `phase4_runner/runs/<run>`), six rounds, each followed by answering and
  validating where it hands off:

      $PY scripts/remediation/phase4/mass4.py --run-dir R --live --stages prepare,sources,routes,select --handoff-export H/select
      $PY scripts/remediation/phase4/mass4.py --run-dir R --live --stages select --handoff-import H/select
      $PY scripts/remediation/phase4/mass4.py --run-dir R --live --stages translate --handoff-export H/translate
      $PY scripts/remediation/phase4/mass4.py --run-dir R --live --stages translate,assemble,verify --handoff-import H/translate
      $PY scripts/remediation/phase4/mass4.py --run-dir R --live --stages review --handoff-export H/review
      $PY scripts/remediation/phase4/mass4.py --run-dir R --live --stages review --handoff-import H/review

  (`run4.py select|translate|review --run-dir R --batch-id B --handoff-export|--handoff-import DIR`
  does one batch.) Then the stage's gates as ever: `mass4`'s done state, the independent audit,
  `run4.py writeplan` (write4, whose D5 evidence check reads these answers), `write_gate4.py`,
  `verify_writes4.py`.
* **Gallery vision** - the Opus C1 calibration first, in a directory of its own (`C`, e.g.
  `output/remediation/gallery_audit/calibration-opus-2026-09-23`):
  `$PY scripts/remediation/gallery_audit/calibrate.py seal --run-dir C`, then `... jobs --run-dir C`;
  `$PY scripts/remediation/gallery_audit/vision.py export --jobs C/JOBS.jsonl --run-dir C --handoff H`
  (exit 3 names every image that cannot be found or read); answer (each agent looks at
  `H/images/<id>.jpg` and answers with the JSON the question asks for); validate;
  `$PY scripts/remediation/gallery_audit/vision.py import --jobs C/JOBS.jsonl --run-dir C --handoff H`;
  then `calibrate.py evaluate --run-dir C --eye-labels ...` and `decide.py` as the design has it.
  The G stages' JOBS files go the same way.

### Measured (worktree `.claude/worktrees/opus-handoff`, main venv)

* Tests: 18 new in `test_opus_handoff.py`; in the stage suites 11 Pi tests and 2 spawn-shape tests
  and the ramp test removed and replaced by handoff tests (the Phase-3 runner and its export/import
  round trip through the real CLI, the unmetered ledger line, mass_run's two halves, review_all's
  argv against the real parser, run4's select and translate rounds over lanes W, T and R with the
  batch directory byte-identical after each export, mass4's round rules, D5 end to end, vision's
  export/import round trip with the exact JPEG); the API fixtures carry the new disclosure.
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`, the snapshot and
  `WORKLIST.jsonl` copied into the worktree's ignored paths from the main checkout): **5,555
  passed, 103 skipped, 57 deselected, 0 failed**.
* Mutation sweep: the 62 new cases (`opus handoff: `) **62/62 caught**; every existing case whose
  file or test this branch changed (740 cases, the 62 included) **740/740 caught** - 737 in one run,
  and the 3 whose tests need the gitignored snapshot and worklist caught once those were copied in;
  the tree byte-identical after each run, no `# mutant` line outside the sweep files. The AI_SYSTEM
  case was re-anchored to the new disclosure.
* `ruff check` and `ruff format --check` clean on all 31 touched Python files, `ruff check api/
  pipeline/` clean, `lint-imports` 2 kept 0 broken, `vulture api/ pipeline/ .vulture_whitelist.py
  --min-confidence 80` clean, the Lyra import check (`markdown` and `nh3` masked) passes.

### Open

* The Opus C1 calibration directory is not sealed here: sealing is the first act of that production
  run and needs the gitignored state (`calibrate.py seal`, then `jobs`).
* The answering workflow (which agents, how many questions per agent) is the orchestrator's; this
  branch gives it the files, the helper and the validator.
* `mass_run.package_digest` hashes `phase3/` (and `mass4` `phase4/`), not `opus_handoff.py`: an edit to
  the handoff module mid-run is not caught by the digest guard.
* Removing the now-unraised `UnreadableStream` branches (see "Kept on purpose").


## 2026-09-23 - the sitelink lane moves to the Opus handoff: merge, pilot addendum, runbook, the pilot's export (no model call, nothing written)

Branch `wip/sitelink` (worktree `.claude/worktrees/agent-af14d4b87c0be3d40`), from `4287b5d`, after the
owner's order of 2026-09-23 (Martin: "no DeepSeek any more - everything with Opus"). **Nothing was
written to production, nothing was read from it, and no model was called** - no DeepSeek, Pi,
opencode gateway or other model API, in code or in tests. Network: the pilot's fetch only (Wikipedia
and Wikidata, the project user agent, the fetch stage's per-host pace).

### The merge of integrate/wave1 (`490d114`, merge commit `66ec1da`)

Three textual conflicts, both sides kept. `lanes.py`: `"sitelink": "slk"` stays in
`PHASE3_BATCH_PREFIX`, beside integrate's `PHASE4_LANES`, `BATCH_PREFIX` and `STAMP_FAMILY` (the
sitelink lane's family is `phase3`, its stamps `phase3:slk-%`). `test_remediation_tools.py`: the
sitelink lane test beside the two phase-4 lane tests. `mutation_sweep.py`: `SITELINK_MUTATIONS` and
`OPUS_HANDOFF_MUTATIONS` each defined once and registered once (25 lists, 1,886 labels, all unique).
`AUDIT_LOG.md` and the tools README merged as an append-only union; `classify.py` without a conflict
(integrate's web witnesses, this branch's `political_line`). The classifier outputs the item rule
reads (`bcases/coords.jsonl`, `names.jsonl`, `b2.jsonl`, the duplicate lists) did not change on
integrate, so the pilot plan's inputs stand.

### The independent check's three findings (`recovery__check_sitelink.json`): each confirmed fixed

1. **Item rule** (major): `sitelink_plan.classifier_verdicts` reads `coords.jsonl`'s
   `container-item` and `item-is-not-the-site` and `names.jsonl`'s N7 `anchor-is-locality`, and
   `item_for` withholds on a verdict about the item the site still carries, under the rule's name.
   The check's seven cases (Colima, Kintradwell, Kameishi, Tiklat, Elguentra, Thasos, Ahin Posh Tape)
   and the pilot's Hebbariyeh are tested on the classifier's tracked output.
2. **Generated wikis** (minor): `fetch_stage.BOT_GENERATED_WIKIS` refuses `cewiki`, `lldwiki`,
   `zh_min_nanwiki` and `cowiki` beside `cebwiki`, `warwiki`, `arzwiki`; `HOME_ONLY_WIKIS` reads
   `svwiki` only for Swedish and Finnish sites, and `svwiki` left `FIXED_ORDER`.
3. **Threshold 4** (minor): `SITELINK_PILOT.md` copies all four thresholds of `SEARCH_PILOT.md`
   verbatim and states the article reading beside them; a test compares the two blocks; the scorer's
   docstring says "their text copied verbatim".

### What still named DeepSeek (commit `8e6b335`)

`sitelink_plan.py`'s docstring named `opencode-go/deepseek-v4.1-flash` as the lane's finder and
reviewer; it now names the mass run's frozen prompts answered by Opus agents through the handoff.
`test_sitelink_plan.py`'s docstring said it reads no Pi; it now says no model. No lane code builds a
runner: the lane's model stages are `mass_run.py` and `review_all.py`, which integrate moved to the
handoff. The lane had no cost projection of its own - the "$0.034" and "$0.0322" in the two sitelink
sections above were `mass_run`'s DeepSeek projection (`MEASURED_COST_PER_CALL`), which integrate
removed; the driver now prints the model as unmetered. Those sections are history and stay as written.

### The pilot's addendum (commit `28fef01`)

`SITELINK_PILOT.md` gains, below the seal, "Addendum 2026-09-23: the answering model is Opus (owner
order), written before any model call": the order, the model (`opus_handoff.OPUS_MODEL`), that no
model call was ever made for this pilot, what did not change (the four thresholds, not loosened; the
reading of threshold 4; the plan, its fields and articles; the human verdicts; the scorer), and how
two sections are read now - "the model cost per call" is the number of unmetered calls, never a price,
and "How it runs" is superseded by the runbook below (its commands predate the handoff and a live
`mass_run.py` or `review_all.py` refuses them). No model call, verified at that commit: 0 `slkg` or
`slk` rows in `phase3_runner/LEDGER.jsonl`, on this branch and in the main checkout; no
`runs/sitelink-gold`; no answer, review or `model.json` in the three dry fetches, 0 `model_call` rows
in their scratch ledgers; no handoff directory.

**The sealed part is byte-identical**: the file's first 6,978 bytes hash to
`9467e7259b3cc164b60e5cb754ade2e2ed07ae9e909e7b3e2b4eb3b3f69b3d1e`, the re-sealed sha256 recorded
above. **The file's sha256 with the addendum: `fa4cfc46f15a49c02513ae44a72d8c5dc3285387467977440e0a062bd67777b8`.**
`test_the_sitelink_pilot_keeps_its_sealed_text_and_names_opus_only_below_it` pins the sealed prefix
and that the model is named only below it (red before the addendum existed).

### The orchestrator's runbook (commit `4020c2f`)

As committed in `output/remediation/tools/README.md` ("The sitelink lane's runbook"), which is the
living copy; `test_the_runbook_runs_every_model_stage_as_one_handoff_round_with_the_drivers_own_flags`
parses every driver line of it with the driver's own parser and checks the rounds (below). Every
model stage is one handoff round: export -> the Opus agents answer -> `opus_handoff.py validate`
exits 0 -> import. The pilot first; the lane only after `score_search_pilot.py --lane sitelink`
exits 0 and the result is recorded. One ledger, `output/remediation/phase3_runner/LEDGER.jsonl`.
Run directories: the pilot `output/remediation/phase3_runner/runs/sitelink-gold`, the lane
`output/remediation/phase3_runner/runs/sitelink` (the write tools' `--lane sitelink`). Handoff
directories: `output/remediation/handoff/sitelink-gold-finder`, `-gold-reviewer`, `sitelink-finder`,
`sitelink-reviewer`. The export writes its own progress file (`progress.export.json`), answered only
when it shows `"stopped": null` and `"failed": {}`; the pilot's import writes
`logs/sitelink_gold/progress.json`, which the scorer reads for threshold 4.

```bash
cd /c/PythonProjects/AncientMap && export PYTHONIOENCODING=utf-8
PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe; M=output/remediation; T=$M/tools
P3=scripts/remediation/phase3; OH=scripts/remediation/opus_handoff.py; L=$M/phase3_runner/LEDGER.jsonl

# == the pilot: the sealed plan, batches slkg-0001 and slkg-0002, 39 finder questions
P=$M/sitelink/pilot/PLAN.sitelink-gold.jsonl; R=$M/phase3_runner/runs/sitelink-gold
G=$M/logs/sitelink_gold; HF=$M/handoff/sitelink-gold-finder; HR=$M/handoff/sitelink-gold-reviewer
# 1. plan: the sealed one, never rebuilt for the pilot
sha256sum $P    # d8a78e58f02255570bd6a7c94dd42b0a04fdbddadca440b9bc12e39dabc28b81, or it does not apply
# 2. fetch and 3. finder export: prepare, fetch, then the judge writes its prompts to $HF (no model)
$PY $P3/mass_run.py --live --jobs 2 --plan $P --run-dir $R --ledger $L --log-dir $G \
    --progress $G/progress.export.json --handoff-export $HF
# 4. Opus answers: for each line of $HF/*/MANIFEST.jsonl whose answer_path does not exist, an agent
#    reads $HF/<prompt_path>, writes its answer text (the shape the question asks for) to a file, and
$PY $OH answer --dir $HF --batch-id <batch_id> --stage finder --label <label> \
    --answered-by <agent> --text-file <answer.txt>
# 5. validate: exit 0 only when every question is answered, in shape, by Opus, for its exact prompt
$PY $OH validate --dir $HF
# 6. finder import: the judge on the answers - ledger line first, answers/, model.json
$PY $P3/mass_run.py --live --jobs 2 --plan $P --run-dir $R --ledger $L --log-dir $G \
    --handoff-import $HF
# 7. reviewer export (it asks about the finder's answers)
$PY $T/review_all.py --lane sitelink --run-dir $R --ledger $L --log-dir $M/logs/review_sitelink_gold \
    --handoff-export $HR
# 8. Opus answers, as in 4
$PY $OH answer --dir $HR --batch-id <batch_id> --stage reviewer --label <label> \
    --answered-by <agent> --text-file <answer.txt>
# 9. validate
$PY $OH validate --dir $HR
# 10. reviewer import: each batch's review.json
$PY $T/review_all.py --lane sitelink --run-dir $R --ledger $L --log-dir $M/logs/review_sitelink_gold \
    --handoff-import $HR
# 11. score: exit 0 only when all four sealed thresholds hold; it reads $R and $G/progress.json
$PY $T/score_search_pilot.py --lane sitelink

# == the lane: only after step 11 passed and its result is recorded (SITELINK_PILOT.md, AUDIT_LOG.md)
# 12. plan, rebuilt then: the pins age, and `plan` refuses a sitelinks.json resolved under other inputs
IN="--mass-run $M/phase3_runner/runs/mass --data $M --rows $M/logs/_write_dry/ALL_ROWS.jsonl \
    --written-keys $M/logs/search_lane/written_keys.txt --country-census $M/logs/_country_mismatches.txt"
$PY $T/sitelink_plan.py census --mass-run $M/phase3_runner/runs/mass
$PY $T/sitelink_plan.py export
$PY $T/sitelink_plan.py sitelinks $IN
$PY $T/sitelink_plan.py plan $IN
PL=$M/phase3_runner/PLAN.sitelink.jsonl; RL=$M/phase3_runner/runs/sitelink; GL=$M/logs/sitelink_mass
HLF=$M/handoff/sitelink-finder; HLR=$M/handoff/sitelink-reviewer
# 13.-16. the finder's round, as 2-6
$PY $P3/mass_run.py --live --jobs 4 --plan $PL --run-dir $RL --ledger $L --log-dir $GL \
    --progress $GL/progress.export.json --handoff-export $HLF
$PY $OH answer --dir $HLF --batch-id <batch_id> --stage finder --label <label> \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $HLF
$PY $P3/mass_run.py --live --jobs 4 --plan $PL --run-dir $RL --ledger $L --log-dir $GL \
    --handoff-import $HLF
# 17.-20. the reviewer's round, as 7-10, on the lane's own run (runs/sitelink, logs/review_sitelink)
$PY $T/review_all.py --lane sitelink --ledger $L --handoff-export $HLR
$PY $OH answer --dir $HLR --batch-id <batch_id> --stage reviewer --label <label> \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $HLR
$PY $T/review_all.py --lane sitelink --ledger $L --handoff-import $HLR
# 21. the write plan, no database: logs/_write_dry_sitelink/ALL_ROWS.jsonl
$PY $T/write_dry_all.py --lane sitelink
# 22. write_gate dry ("dry run, nothing is written"): read its refusals, holds and rows before 23
$PY $T/write_gate.py --lane sitelink --step 100
# 23. apply: production, 100-site steps, each read back; a short write or a deviation stops the wave
$PY $T/write_gate.py --lane sitelink --apply --step 100
# 24. the independent acceptance: RESULT: 0 deviation(s)
$PY $T/verify_writes.py --lane sitelink
```

**Where the pilot stands:** steps 1-3 are done (below); the next step is 4. The gitignored state is
in this worktree: `output/remediation/sitelink/pilot/` (the plan), `output/remediation/snapshot/`
(copied from the main checkout, byte-identical; the judge reads its `site_type` list),
`output/remediation/phase3_runner/runs/sitelink-gold/`, `output/remediation/handoff/sitelink-gold-finder/`
and `output/remediation/logs/sitelink_gold/`. Run steps 4-11 from this worktree, or merge
`wip/sitelink` (it carries the export's ledger rows) and copy those directories to the same relative
paths of the checkout that runs them: the import rebuilds each prompt from the run directory's
evidence and refuses an answer to any other prompt, so the run directory travels with its handoff
directory.

### The pilot's finder export (steps 2-3; no model call)

The runbook's step 2-3 command on the sealed plan (`d8a78e58...8b81`), 21:07:59-21:11:56 UTC: both
batches handed off after prepare, fetch and judge; `stopped` null, `failed` {}. The fetch: 182
requests (24 host probes, 18 English articles, 49 other-language articles, 72 Wikidata claim reads,
19 narrowed WDQS queries), 179 answered 200, one WDQS transport failure answered on its retry, and two WDQS 429s
("asked for 120s") on the narrowed Wikidata route of Xcaret and of Aubrey Holes - Stonehenge, each
given up and recorded as that target's failure, as the fetch stage records every such answer - so 5
of the 39 prompts carried a failure note. Nothing had been answered (`validate`: 0 answered, 0
orphans), so the fetch was resumed (`run.py fetch --live` per batch, 21:12:47): 2 host probes and 2
answers, both 200, `fetch.json` without a failure. Xcaret's query was asked again 85 s after its 429,
35 s sooner than the 120 s the server asked for: the pace directory keeps each host's last request,
not a `Retry-After` across runs (Aubrey Holes' came after 299 s). The handoff directory was removed
and the export run again (21:13:46; no request, every target on disk).

**The export: 39 finder prompts** (`slkg-0001` 32, `slkg-0002` 7; period_start 15, description 10,
card_description 8, site_type 5, country 1; 18 sites - the pilot's fields exactly), 5 of them other
than the first export's (the two sites' fields), each carrying the site's pinned permalinks (`oldid=`
in 39 of 39); 10,356 to 35,159 characters, median 15,612. **Handoff directory:
`output/remediation/handoff/sitelink-gold-finder`** (gitignored, left in place for the orchestrator);
`opus_handoff.py validate` on it: 39 questions, 39 missing, 0 stale, 0 malformed, 0 orphans. 49 of 49
articles stored, 0 unaccounted for (`score_search_pilot.sitelink_unaccounted`, both batches). The
ledger: 186 `fetch` rows, 0 `model_call` rows (commit `2718e2b`). The first export's manifest:
`logs/sitelink_gold/first_export_manifest.jsonl`.

### Tests, sweep, gates

* Two new tests in `test_sitelink_plan.py` (66 there now), each red before what it guards existed:
  the sealed prefix and the Opus addendum (`..._keeps_its_sealed_text_and_names_opus_only_below_it`),
  and the runbook (`test_the_runbook_runs_every_model_stage_as_one_handoff_round_with_the_drivers_own_flags`:
  every `mass_run.py`, `review_all.py`, `score_search_pilot.py` and `write_dry_all.py` line parses
  with the driver's own parser; each of the four handoff directories is exported once, answered
  with its stage (`finder` for the finder, `reviewer` for the reviewer), validated and imported
  once, in that order, by one driver on the same plan, run directory, ledger and logs; the export has
  its own progress file and the import none; the pilot's import writes the run directory and the
  progress file the scorer reads; the lane's run directory is the write tools' `--lane sitelink`;
  the pilot is scored after its two rounds and before the lane's first export; the writers come
  last, dry gate before apply).
* `mutation_sweep.SITELINK_MUTATIONS`: 9 new `"sitelink: "` cases (3 on the addendum: a sealed line
  edited, the addendum joined onto the seal, the model name dropped; 6 on the runbook: the finder
  imported from the reviewer's directory, a second progress file for the pilot's import, no
  validate, a flag the driver does not know, no dry gate, the lane's run directory moved), 167 in
  all, registered once; 1,895 labels, all unique. The sweep's own `main`, run with the main venv's
  interpreter (`sys.executable`), over every label that names `sitelink` - the 167 `"sitelink: "`
  cases and 9 older gap and fetch cases: **176/176 caught**, the tree byte-identical to the sweep's
  start for the 7 files it touched (`sitelink_plan.py` 86, `fetch_stage.py` 68, `gap_plan.py` 7,
  the tools README 6, `score_search_pilot.py` 4, `SITELINK_PILOT.md` 4, `lanes.py` 1), no `# mutant`
  line outside the sweep files (`logs/sitelink_scratch/sweep_opus_handoff.txt`).
* Full gate suite from the worktree (`-m "not integration and not live_llm"`, `--timeout 300`,
  `-p no:cacheprovider`, the main venv): **5,685 passed, 107 skipped, 57 deselected, 0 failed**
  (366 s); every skip names gitignored data a worktree does not have (the Natural Earth caches,
  `WORKLIST.jsonl`, the bcases cache, the fonts, ...).
* `ruff check` and `ruff format --check` clean on the touched Python files (`lanes.py`,
  `sitelink_plan.py`, `mutation_sweep.py`, `test_sitelink_plan.py`, `test_remediation_tools.py`);
  `ruff check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean (ruff 0.15.11).

### Open

* Steps 4-11 of the pilot: the answers are the orchestrator's (39 finder questions now, then the
  reviewer's); the lane runs only after the pilot passes, on a plan rebuilt then (step 12).
* The fetch stage does not carry a host's `Retry-After` across runs, so a resumed fetch may ask
  sooner than a host asked (once here, 35 s early; WDQS answered).
* `mass_run.package_digest` hashes `phase3/`, not `opus_handoff.py` (integrate's open point): an edit
  to the handoff module during the lane's run is not caught by the digest guard.
* From the section above: the page-level bot pages inside editor-written wikis (18 pages of the first
  plan).

## 2026-09-24 - the sitelink pilot, answered by Opus: FAIL, the mass run does not start

`SITELINK_PILOT.md` (thresholds sealed before any model call; addendum: answering model Opus by owner
order) was run through the Opus handoff: 39 finder questions exported from the pinned pilot plan
(sha256 `d8a78e58...8b81`), answered by four Opus agents one after another (about 450k subagent
tokens), validated (39/39), imported through the unchanged parser and gates; the 16 WRONG findings
went to the reviewer the same way (two agents, 16/16). Result (`phase3_runner/SITELINK_PILOT_RESULT_1.txt`,
`score_search_pilot.py --lane sitelink`):

| threshold | result |
|---|---|
| 1 no fabricated citation | PASS (0) |
| 2 no harmful decision | **FAIL** (8 fields) |
| 3 agreement >= 90 % | **FAIL** (18/32 = 56.2 %) |
| 4 transport | PASS |

32 of the 39 fields moved from UNVERIFIABLE to a decision - the lever is real - but the decisions
disagree with the human gold too often. What the writer itself would have written: 7 rows, 4
agreeing with the gold, 2 harmful, 1 unverifiable. The two harmful writes show the cause:

* **Las Labradas** `period_start` 500 -> -1000: the finder followed the other-language article's
  "1000 BC - 300 AD" - the very dating the gold standard lists as a human-found prose error (LS-1).
* **Metsamor** `period_start` -4000 -> -5000: a different bucket on a reading the English article
  and the site's own record (4th millennium BC) do not support.

Other-language Wikipedias carry their own errors, and a finder that takes them as evidence imports
them. The search pilot (DeepSeek, MiniMax hits) failed on the same class. Under the sealed rule the
mass run does not start and nothing is written; the thresholds are not moved. The writable fields
the mass run answered UNVERIFIABLE stay **unverifiable** (the outcome the remediation defined for a
field no source decides), listed per field in the mass run's answers. A future route needs a source
the gold standard can trust more than a Wikipedia of another language (national registers,
excavation reports) - it is not built.

## 2026-09-24 - the Phase-4 pilot, sealed before its first model question (no model called, nothing written)

Branch `wip/p4-pilot` (worktree `.claude/worktrees/p4-pilot`, from `integrate/wave1` `3f54247`). The
design is entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json` (sha256
`515601c3e91a770ce096ee001e6bfc1659c875d008f11d1b508d07a31d20e5af`), key `pilot_and_thresholds`.
**Nothing was written to production; no model and no MiniMax endpoint was called** - no DeepSeek, Pi,
opencode gateway, MiniMax or other model API, and no MiniMax client was even built. Production was
read only with SELECTs: `plan4.py read`, `pilot4.py routeless`, and a few hand queries (the named
sites, the Q309/title sites, the routeless count); the network was Wikipedia and Wikidata with the project's
user agent, paced per host.

### The order the design's stages imply

A draw by lane needs the lanes, and the lanes are the routes stage's (S1b), which needs S1, which
needs S0. So the pilot was drawn from a **census**: every curated site through S0, S1 and S1b, with
searches off, then the seeded draw (`scripts/remediation/phase4/pilot4.py`, its docstring has the
commands):

1. **S0** - `run4.py plan read` (the fresh read-only export: 5,004 rows, `S0_ROWS.jsonl` sha256
   `2c99f96f899447000659ad3ff6b24bc2dc9eddd2f96cdfe73afeabb1829272a8`, gitignored), `plan names`
   (76 shared items' labels and aliases, 9 Wikidata requests, `S0_ITEM_NAMES.json`), `plan build
   --out PLAN4.census.jsonl` (335 batches, sha256
   `644b9032ed43e8ecc285cc9c783a7852c6546fefcc2501e33534897d4676b591`; flags: scope-pending 96,
   shared-qid 173, shared-title 205, duplicate-pair 14, cleared-description-defect 322,
   cleared-card-defect 709, t03 875, t03-severe 185; no invalid title).
2. **The B3 read** - `pilot4.py routeless`: the curated sites with no enwiki title, no QID, no
   http(s) URL in `source_url` and no `site_content_links` URL (the AUDIT_LOG's "routing
   measurement" definition; 17 on the 2026-09-21 snapshot, **20 today**). `S0_ROUTELESS.json`.
3. **The census** - `mass4.py --plan PLAN4.census.jsonl --run-dir runs/census-2026-09-24 --live
   --stages prepare,sources,routes --searches-off --jobs 4 --ledger LEDGER.census.jsonl`,
   2026-09-23 22:50-23:25 UTC: 335 batches, 6,995 fetch lines (en.wikipedia.org 5,873,
   www.wikidata.org 1,007, other Wikipedias 115; 77 answered 429 and were answered on retry, none
   given up), 0 searches, 0 model calls. The Phase-3 mass run's 4,618 `wikidata_entity` files were
   copied from the main checkout with their mtimes. **Lanes: W 3,887, S 372, 0 745** - the 745 are
   held `search-stopped` 582, `scope-pending` 96, `revision-too-fresh` 67; S1 statuses pinned 4,251,
   no-title 353, rejected 238, held 66, scope-pending 96. No lane T or R exists with searches off:
   the route stage searches whenever no own English article was found, and a spent allowance holds
   the site (`_assign`: `search-stopped` before lane S, T or R).
4. **The draw** - `pilot4.py build --run-dir runs/census-2026-09-24` (seed 20260922,
   `audit4.draw_sample`, each stratum excluding every site placed before it).

**Found on the way, fixed with red-first tests** (commit `7481088`): one census batch (`p4-0054`) died
in S1 with `PermissionError` (errno 13) from `os.open` in `fetch_stage.HostPacer.wait` - on Windows a
lock file its holder is deleting stays "delete pending" while another process holds a handle, and
creating it again is refused as access denied, not as `FileExistsError`. The pacer now waits for such
a lock like a held one and ends at its deadline naming the refusal; the batch was re-run and
completed. `route_stage.no_search` (a run told `--max-searches 0` builds no MiniMax client; its seams
raise), `mass4.py --searches-off` (every routes stage told 0, no search ceiling - a ceiling of 0 stops
a run before its first batch) and `plan4.py build --pilot` (the pilot from PILOT.jsonl, **in batches of
its own**: 132 = 8 x 15 + 12, so a ninth batch would otherwise carry 3 sites that are not the
pilot's into its model calls and its audit) are commit `2047a7f`.

### The pilot set (`PILOT.jsonl`, 132 sites)

Fixed, 70 sites: the 36 gold-standard sites; the 10 canaries; the 3 B5 fixtures (all three are also
gold sites); the 8 named identity traps; the 7 sites on 'History'/Q309 (the external-id repair's plan
moved all 7 off Q309 - `qid_repair/PLAN.jsonl`, applied; 2 still store the title 'History'); the 3
'Theatre' and 4 'Mortuary temple' title sites; f6b8fa8a (Abri de la Madeleine) and Wroxeter Stone.
Every canary, fixture and trap was resolved from its id prefix and carries the design's name.

| stratum | asked | population | eligible | taken |
|---|---|---|---|---|
| draw-W (census lane W) | 30 | 3,887 | 3,843 | 30 |
| draw-S (census lane S) | 8 | 372 | 363 | 8 |
| draw-T-candidate | 6 | 38 | 38 | 6 |
| draw-R-candidate | 8 | 252 | 251 | 8 |
| draw-B3-routeless | 5 | 20 | 20 | 5 |
| draw-extract-over-40000 | 5 | 65 | 63 | 5 |

No stratum was smaller than asked. **The T and R strata are candidates**, because searches are off (owner
order 2026-09-23, "everything with Opus"): the sites the census held `search-stopped` whose
`source_url` names an article on another-language Wikipedia (T, the design's langlinks route) or only
http(s) pages on no wiki host (R; design entry [2]: "whose only route is a non-Wikipedia source_url").
They stay held in the pilot and are reported; nobody guesses their lane. The census lanes of the 132:
W 77, S 19, 0 36.

### The sealed artefacts (committed `fab4f57`, LF-pinned by `.gitattributes`)

| file | sha256 |
|---|---|
| `output/remediation/phase4_runner/PILOT.jsonl` | `7f66f987186151108879105745f082da3b4c8623ca5bd0a201c32a95e4e063fc` |
| `output/remediation/phase4_runner/gold_prose_errors.json` | `e4e63d56cbc9cca0f9cea018967fac40e897faddb9c43ad064e6203a74ebb7df` |
| `output/remediation/phase4_runner/PILOT_THRESHOLDS.md` | `64ac53341068234c905cff00095a9d7244cd4703353f63bbd0997add63fe0c13` |

Their inputs: `PLAN4.census.jsonl` `644b9032...b591`, `S0_ROUTELESS.json`
`81c3b426421e5958ee4e6fbe43ab139fe967f7dad030bd795c77d68d37997746`, `gold_standard/sites.json`
`18653fc12607bc7b25c160ab022d114b86500c5dd15641979dc4cfdb72d2b756`, `qid_repair/PLAN.jsonl`
`9d57b4315bea6fe6c7cfc1d94cae8776b442bce1443159eef2328579f9a6ce4f`, the export `2c99f96f...72a8`.

* **`gold_prose_errors.json`** (`pilot4.py prose-errors`): the 15 prose errors of the gold standard
  (every `errors_found` entry whose field names `description` or `card_description`, 12 plain and 3
  combined with `period_start`), each claim copied from `gold_standard/sites.json` by code and each
  anchor checked to occur in that record's stored text (e.g. LS-1 `1000 BC-300 AD`); then the 10
  canary defects, each claim checked verbatim in its source (plan sections 4.2 and 5.1, design
  entries [2], [5], [6]) and each stored anchor checked in the fresh export (Choquequirao on
  Hatunmarka, `10,000 BC` on House of Taga, `30,000 km` on Maray Qalla, `hillfort` on Kit Hill, the
  Dacian fort on Partiscum, `3rd-century BC` on Justinianopolis, `from the 1st millennium BC` on Neos
  Panteleimonas, `Pakistan` on Ahin Posh Tape as the wrong item's country). Two canaries carry no
  prose anchor, and say why: Eileithyia Cave (a `period_start` defect its stored prose does not carry)
  and El Tintal (a coordinate).
* **`PILOT_THRESHOLDS.md`** (`pilot4.py thresholds`): T1-T13, "Reported, not gating" and ON FAILURE,
  copied verbatim from the design by code (a test compares them with the design file), then the dated
  note: the answering model is Opus through the handoff (owner order 2026-09-23); MiniMax route
  searches are not used (owner order "everything with Opus"), so lane-R/S1b candidates that need a
  search are held as the route stage's `search-stopped` hold and reported, never guessed; and what
  follows under the unchanged thresholds - no search, so T13 records nothing; no lane T or R site,
  so T11 and T12 cannot be met and lanes T and R do not pass their pilot; T9's dollar bound reads an
  unmetered ledger, reported as a count of unmetered calls.

`tests/remediation/test_phase4_pilot.py` pins the three digests against this section and checks the
pilot's members and the verbatim blocks.

## 2026-09-24 - the Phase-4 pilot's non-model stages and its select export (no model called, nothing written)

After the seal above (commit `e0e3e13`, 01:29:41 +02:00; the first question was exported at 01:30:25),
`plan4.py build --pilot PILOT.jsonl` wrote `PLAN4.jsonl` from the same export (sha256
`a39a8c9558cede1a62e8668d0dc79fa4742b8394b31794ee97252da24ca3aabb`, gitignored): **the pilot is its
first 9 batches, `p4-0001` .. `p4-0009`** (8 x 15 + 12, in PILOT.jsonl's order, no other site among
them), the rest follows from `p4-0010` (334 batches). The mass run can later continue in the pilot's
run directory; the census run directory cannot be reused (its batches are the census plan's).

    mass4.py --plan PLAN4.jsonl --run-dir runs/pilot-2026-09-24 --only p4-0001,..,p4-0009 --live \
        --stages prepare,sources,routes,select --searches-off \
        --handoff-export output/remediation/handoff/p4-pilot-select --jobs 3

2026-09-23 23:30-23:31 UTC, `STAGE_EXIT=0`, every batch "done" for its round. 228 fetch lines in
`LEDGER.jsonl` (en.wikipedia.org 160, www.wikidata.org 52, other Wikipedias 16), all 200; 0 searches;
0 model calls (the ledger has no `model_call` line). Every lane equals the census's.

| stage | result |
|---|---|
| S0 plan | 132 sites in 9 batches |
| S1 sources | pinned 96, scope-pending 3, no-title 19, rejected 14 |
| S1b routes | **lane W 77, S 19, 0 36**; 0 searches |
| S3 select, export | **91 questions** (lane W 77, lane S 14); prompts 1,681-34,448 characters, median 4,047 |
| S3R restricted | no lane-R site: nothing asked |

The 96 selecting sites (lane W or S, not held) minus 91 questions are 5 lane-S sites whose article
offers no sentence that names them (`sentences.candidate_pool`, lane S): Amyntas Rock Tombs, Priene
Ruins, Hebbariyeh Roman Temple (gold), Templos de Tarxien (identity trap), Pergamon Amfitiyatrosu
(long extract). The import holds them `no-source` with no call bought (`select_stage`).

**The 36 holds** (`HOLDS4.jsonl`): `scope-pending` 3 - Midford Castle (gold and B5 fixture, 1775), Ksar
el Barka (1690), Museo Campano (1869); `search-stopped` 33 - every site whose free routes found no own
English article: the gold sites Font dels Coms and Temple of Dedun (article 'Dedun': verdict none); the
canaries El Tintal (verdict none) and Ahin Posh Tape (verdict wrong); the Q309 traps Tlalpan, Estipeon
and Crantit Chambered Cairn (the last two on the title 'History'); the 3 'Theatre' and 4 'Mortuary
temple' traps (the generic article is a class and shared: verdict wrong; for Mortuary Temple of Seti I
geosearch found its own article and the gate called it shared); all 6 T candidates, each with an
other-language article and no English langlink - the gate called 3 of those articles `own` (Poblat de
Son Catlar, Cirque Romain de Vienne, Pozzo Sacro del Predio Canopoli: lane T if a search found no English
article) and 3 `none`; all 8 R candidates; all 5 B3 sites. By stratum:
gold 26 W / 5 S / 5 held (28 exported); canaries 8 W (all 8 exported) / 2 held; B5 2 W / 1 held;
named traps 4 W / 4 S (7 exported); Q309 4 W / 3 held; Theatre and Mortuary temple 7 held; f6b8fa8a
and Wroxeter Stone W; draws W 30 and S 8 all exported; T, R and B3 all held; long extracts 3 W / 2 S (4
exported).

**Handoff directory** `output/remediation/handoff/p4-pilot-select` (gitignored, left in place; 91
prompts, 816 KB, stage `finder`, labels `<site_id>/select`). `opus_handoff.py validate` on it: 91
questions, 91 missing, 0 answered, 0 stale, 0 malformed, 0 orphans (exit 1 until they are answered).
The run directory `runs/pilot-2026-09-24` (7.5 MB) travels with it: the import rebuilds each prompt
from its evidence and refuses an answer to any other prompt.

### What the thresholds can and cannot measure now

T11 and T12 cannot be met (no lane-R or lane-T site) - lanes T and R do not pass their pilot and stay
closed; T13 has no search; T9's dollars are unmetered (the note in `PILOT_THRESHOLDS.md`). T7: of the
25 gold and canary errors, the canaries El Tintal and Ahin Posh Tape and the gold errors FC-2 (Font
dels Coms) and TD-1 (Temple of Dedun) sit on sites held `search-stopped`, and AM-1 (Amyntas Rock Tombs)
on a lane-S site the import will hold `no-source` - closed-list reasons, which T7 accepts; the other 20
are asked.

### The orchestrator's next commands (from this worktree, main venv)

```bash
cd /c/PythonProjects/AncientMap/.claude/worktrees/p4-pilot && export PYTHONIOENCODING=utf-8
PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe; M=output/remediation; R4=$M/phase4_runner
P4=scripts/remediation/phase4; OH=scripts/remediation/opus_handoff.py; H=$M/handoff/p4-pilot
RUN=$R4/runs/pilot-2026-09-24; ONLY=p4-0001,p4-0002,p4-0003,p4-0004,p4-0005,p4-0006,p4-0007,p4-0008,p4-0009
ROUND="--plan $R4/PLAN4.jsonl --run-dir $RUN --log-dir $M/logs/p4_pilot --only $ONLY --searches-off --live"
# 1. answer the 91 selector questions: for each line of $H-select/*/MANIFEST.jsonl, an Opus agent reads
#    $H-select/<prompt_path>, writes only DESC:/CARD: lines (or ABSTAIN:) to a file, and runs
$PY $OH answer --dir $H-select --batch-id <batch_id> --stage finder --label <site_id>/select \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $H-select                                   # exit 0: 91 answered
$PY $P4/mass4.py $ROUND --stages select --handoff-import $H-select  # S3 (+S3R: nothing to ask)
# 2. the translate round: lane T is empty, so the export writes no question and no directory -
#    skip `validate` when every batch reports 0 calls; the import still runs assemble and verify
$PY $P4/mass4.py $ROUND --stages translate --handoff-export $H-translate
$PY $P4/mass4.py $ROUND --stages translate,assemble,verify --handoff-import $H-translate
# 3. the review round (stage `reviewer`, labels <site_id>/review)
$PY $P4/mass4.py $ROUND --stages review --handoff-export $H-review
$PY $OH answer --dir $H-review --batch-id <batch_id> --stage reviewer --label <site_id>/review \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $H-review
$PY $P4/mass4.py $ROUND --stages review --handoff-import $H-review  # the batches are then done
$PY $P4/run4.py holds --run-dir $RUN                               # HOLDS4.jsonl
# 4. the Claude Code audit of every sentence and card of the pilot (design S6b; T1-T7), against the
#    pinned passages and gold_prose_errors.json - the reviewer's verdicts are never shown
$PY -c "import sys; sys.path.insert(0, 'scripts/remediation'); from pathlib import Path; \
from phase4 import audit4; print('\n'.join(sorted(audit4.reviewed_sites(Path('$RUN')))))" > $M/logs/p4_pilot/reviewed.txt
$PY $P4/audit4.py sheet --run-dir $RUN --site-ids $M/logs/p4_pilot/reviewed.txt --out $M/logs/p4_pilot/AUDIT_SHEETS.md
# 5. score T1-T13 against PILOT_THRESHOLDS.md; only the lanes whose pilot passed are opened
# 6. P4 and P5 rehearsed against production (APPLY ending in ROLLBACK; nothing is written)
$PY $M/tools/write_gate4.py --group P4 --run pilot-2026-09-24 --open-lanes W,S            # dry: plan + render
$PY $M/tools/write_gate4.py --group P4 --run pilot-2026-09-24 --open-lanes W,S --rehearse
$PY $M/tools/write_gate4.py --group P5 --run pilot-2026-09-24 --rehearse
```

P5 plans cards only for sites that carry a live Phase-4 provenance (a read-only question the gate
asks), so before the committed P4 write of step 5 of the design's PILOT RUN its rehearsal may plan
no row; `--open-lanes` names only lanes whose pilot passed (W and S at most; T and R are closed).

### Tests, sweep, gates (worktree `.claude/worktrees/p4-pilot`, main venv)

* New tests, each guard red before its code existed except `pilot4.py`'s (a new module, proven by its
  mutation cases): `test_phase4_pilot.py` 41 (the fixed members, the draws, the census read, the
  prose errors, the thresholds, the seal); `test_phase4_routes.py` +4 (`no_search`);
  `test_phase4_runner.py` +4 (a zero allowance builds no client, `--searches-off`);
  `test_phase4_plan.py` +5 (`--pilot`, the pilot's own batches) and one test rewritten stronger (the
  gold pilot now fills its own batch); `test_phase3_fetch.py` +2 (the pacer).
* `mutation_sweep.P4_PILOT_MUTATIONS`: 44 `"p4 pilot: "` cases (searches off 8, the pacer 2, the
  pilot's batches 5, the fixed members 5, the draws 8, the census 3, the prose errors 7, the seal 3,
  the thresholds 2), registered once; 1,939 labels, all unique, every anchor present. The sweep's
  own `main` with the main venv over the label: **44/44 caught**, the tree byte-identical to the
  sweep's start for its 9 files, no `# mutant` line left.
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`, `-p no:cacheprovider`):
  **5,734 passed, 114 skipped, 57 deselected, 0 failed** (352 s); every skip names gitignored data
  this worktree does not have (Natural Earth, the snapshot, the worklist, the fonts, the bcases
  cache, ...) or an opt-in live test.
* `ruff check` and `ruff format --check` clean on the 12 touched Python files (ruff 0.15.11); `ruff
  check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean.
* `phase3/fetch_stage.py` and `phase3/mutation_sweep.py` changed, so `mass_run.package_digest` over
  `phase3/` changes with this branch: merge it while no Phase-3 mass run is in flight.
  `docs/procedures/PHASE4_CONTRACTS.md` section 8 records the additions (`write_plan` now takes
  `pilot`).

## 2026-09-24 - Phase-4 pilot 2, sealed before its first model question (no model called, nothing written)

Branch `wip/p4-pilot` (worktree `.claude/worktrees/p4-pilot`). Pilot 1 failed T2, T5 and T8
(`output/remediation/phase4_runner/PILOT_RESULT_1.md`, commit `087e38f`). Under the failure rule of
`PILOT_THRESHOLDS.md` ("STOP, find the root cause, fix it, and re-pilot on a fresh draw of the same
strata in a new run directory") the causes were fixed first, each with red-first tests and mutation
cases, before this draw:

* `ba14b94` - the selector question carries rules (6)-(9) after the design's five: the description's
  200-1100 characters (V9), a first sentence that names the site (V6), never a sentence about the
  modern village, town or municipality - ABSTAIN when only such a sentence names the site (T2,
  Orolik) - and no definite reference whose antecedent is not picked (T5); the reviewer question
  the two matching DROP criteria. Answer lines and parsers unchanged.
* `0e397cd` - V6 accepts, beside the stored name and aliases, the pinned article's title and the
  pinned Wikidata item's English label, for a strong 'own' verdict only (QID + coordinates + no
  place-level item: the subject gate already tied article and item to the site); S3 reads the same
  rule in its own code and shows the extra names to the selector as `also_named`. Re-measured on a
  scratch copy of pilot 1's run: its V6 name holds fall from 14 to 9.
* `a1ab602` - `pilot4.py build --after`: pilot 2's draw.

**Nothing was written to production; no model and no MiniMax endpoint was called; production was not
read for this draw** (the census, the export and the routeless read are pilot 1's, digests below).

    pilot4.py build --plan PLAN4.census.jsonl --run-dir runs/census-2026-09-24 \
        --after PILOT.jsonl --seed 20260924 --out PILOT2.jsonl

### The pilot set (`PILOT2.jsonl`, 132 sites)

Fixed, 70 sites: **exactly pilot 1's fixed members** - the same code resolved them from the same
census, and `build` refuses any list that is not PILOT.jsonl's fixed lines, site for site, in its
order, with their strata; the 70 lines are byte-identical to PILOT.jsonl's first 70. The seeded strata
are drawn anew with seed **20260924**, each excluding everything placed before it **and all 62 of
pilot 1's seeded draws**: 0 sites of pilot 1's draws are in pilot 2.

| stratum | asked | population | eligible | taken |
|---|---|---|---|---|
| draw-W (census lane W) | 30 | 3,887 | 3,810 | 30 |
| draw-S (census lane S) | 8 | 372 | 353 | 8 |
| draw-T-candidate | 6 | 38 | 32 | 6 |
| draw-R-candidate | 8 | 252 | 243 | 8 |
| draw-B3-routeless | 5 | 20 | 15 | 5 |
| draw-extract-over-40000 | 5 | 65 | 58 | 5 (4 W, 1 S) |

No stratum was smaller than asked. The census lanes of the 132: **W 78, S 18, 0 36** (pilot 1: W 77,
S 19, 0 36). As in pilot 1, the T and R strata are candidates held `search-stopped` (searches off,
owner order 2026-09-23): they stay held and are reported, never guessed into a lane.

### The sealed artefacts

| file | sha256 |
|---|---|
| `output/remediation/phase4_runner/PILOT2.jsonl` (new) | `9caaaa0312369155bb489a0c96ba6fb1b5e57ec988e787a0206c10503cc9f81c` |
| `output/remediation/phase4_runner/PILOT_THRESHOLDS.md` (pilot 1's, unchanged) | `64ac53341068234c905cff00095a9d7244cd4703353f63bbd0997add63fe0c13` |
| `output/remediation/phase4_runner/gold_prose_errors.json` (pilot 1's, unchanged) | `e4e63d56cbc9cca0f9cea018967fac40e897faddb9c43ad064e6203a74ebb7df` |

The thresholds are the ones sealed before pilot 1's first question, byte for byte: nothing in them
was changed or loosened after the data was seen (`test_phase4_pilot.py` pins all three digests to
this section). The draw's inputs: `PILOT.jsonl` (sealed in pilot 1's section, `7f66f987...e063fc`),
`PLAN4.census.jsonl` `644b9032ed43e8ecc285cc9c783a7852c6546fefcc2501e33534897d4676b591`,
`S0_ROUTELESS.json` `81c3b426421e5958ee4e6fbe43ab139fe967f7dad030bd795c77d68d37997746`,
`gold_standard/sites.json` `18653fc12607bc7b25c160ab022d114b86500c5dd15641979dc4cfdb72d2b756`,
`qid_repair/PLAN.jsonl` `9d57b4315bea6fe6c7cfc1d94cae8776b442bce1443159eef2328579f9a6ce4f`. Without
`--after`, the same build rewrites pilot 1's `PILOT.jsonl` byte-identically (checked before this draw).

## 2026-09-24 - Phase-4 pilot 2's non-model stages and its select export (no model called, nothing written)

After the seal above (commit `ee89b8e`, 03:51:16 +02:00; the first question was exported at 03:52:26),
`plan4.py build --pilot PILOT2.jsonl --out PLAN4.pilot2.jsonl` wrote pilot 2's plan from the same
export as the census and pilot 1 (`S0_ROWS.jsonl` `2c99f96f...72a8`; sha256
`400e28a0d7bc5a4432ec8e659fb1fbafcc66abe95b57e54eb948c4067c8f1bd9`, gitignored): **pilot 2 is its first
9 batches, `p4-0001` .. `p4-0009`** (8 x 15 + 12, in PILOT2.jsonl's order), 334 batches in all, the
same flags as pilot 1's plan. Pilot 1's `PLAN4.jsonl` and run directory are untouched.

    mass4.py --plan PLAN4.pilot2.jsonl --run-dir runs/pilot2-2026-09-24 --log-dir logs/p4_pilot2 \
        --only p4-0001,..,p4-0009 --live --stages prepare,sources,routes,select --searches-off \
        --handoff-export output/remediation/handoff/p4-pilot2-select --jobs 3

2026-09-24 01:52-01:53 UTC, `STAGE_EXIT=0`, every batch "done" for its round. 226 fetch lines in
`LEDGER.jsonl` (en.wikipedia.org 159, www.wikidata.org 51, other Wikipedias 16), all 200, none given
up; 0 searches; 0 model calls (no `model_call` line). Every lane equals the census's.

| stage | result |
|---|---|
| S0 plan | 132 sites in 9 batches |
| S1 sources | pinned 96, scope-pending 3, no-title 20, rejected 13 |
| S1b routes | **lane W 78, S 18, 0 36**; 0 searches |
| S3 select, export | **87 questions** (lane W 78, lane S 9); prompts 2,400-30,722 characters, median 5,455; 19 carry a non-empty `also_named` (the pinned title or item label V6 accepts, e.g. Beacon Hill, Justinianopolis, Galava for Ambleside Roman Fort) |
| S3R restricted | no lane-R site: nothing asked |

Every exported prompt carries the selector question `8969add9...` (rules (6)-(9)). The 96 selecting
sites (lane W or S, not held) minus 87 questions are 9 lane-S sites whose article offers no sentence
that names them (`sentences.candidate_pool`, lane S); the import holds them `no-source` with no call
bought: Soyuqbulaq (Agstafa), Mitla Entrance to Tomb 1, Coria (Corbridge), Dilmun Burial Mounds - Aali
(draw-S); Templos de Tarxien (identity trap); Hebbariyeh Roman Temple, Priene Ruins, Amyntas Rock
Tombs (gold); Temple of Nefertari - Abu Simbel (long extract).

**The 36 holds** (`HOLDS4.jsonl`): `scope-pending` 3 - Midford Castle, Ksar el Barka, Museo Campano
(the gold members pilot 1 held the same way); `search-stopped` 33 - the gold sites Font dels Coms and
Temple of Dedun, the canaries El Tintal and Ahin Posh Tape, the Q309 traps Tlalpan, Estipeon and
Crantit Chambered Cairn, the 3 'Theatre' and 4 'Mortuary temple' traps (all fixed members, held as in
pilot 1), and the 19 new T, R and B3 candidates (6 T: Tomba dei Giganti di Laccaneddu, Tongobriga,
Kusilluchayoc, Santa Cristina, Museo de Sitio Wari, Yunus Sütunu; 8 R: Acropolis of Alatri, Lycaean
Tomb, Tubuco, Castro de Sabroso, Itá Letra Petroglyphs, Paracas History Museum, Temple of Apollo,
Al-Ukhdud; 5 B3: Ruínas Romanas da Bobadela, Selva di Malano, Chichén Viejo, Beşkardeşler Kaya
Mezarları, the hut circle south-east of Bod Silin). By stratum: gold 26 W / 5 S / 5 held (28
exported); canaries 8 W exported / 2 held; named traps 7 exported; Q309 4 exported / 3 held; the new
draws W 30 and S 4 of 8 exported; long extracts 4 of 5 exported.

**Handoff directory** `output/remediation/handoff/p4-pilot2-select` (gitignored, 900 KB, stage
`finder`, labels `<site_id>/select`). `opus_handoff.py validate`: 87 questions, 87 missing, 0
answered, 0 stale, 0 malformed, 0 orphans (exit 1 until they are answered). The run directory
`runs/pilot2-2026-09-24` (7.6 MB, gitignored) travels with it.

**T7 for pilot 2** is what it was for pilot 1 (the same fixed members): the canaries El Tintal and
Ahin Posh Tape and the gold errors FC-2 (Font dels Coms) and TD-1 (Temple of Dedun) sit on sites held
`search-stopped`, AM-1 (Amyntas Rock Tombs) on a lane-S site the import holds `no-source` -
closed-list reasons; the other 20 are asked.

### The orchestrator's next commands (from this worktree, main venv)

```bash
cd /c/PythonProjects/AncientMap/.claude/worktrees/p4-pilot && export PYTHONIOENCODING=utf-8
PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe; M=output/remediation; R4=$M/phase4_runner
P4=scripts/remediation/phase4; OH=scripts/remediation/opus_handoff.py; H=$M/handoff/p4-pilot2
RUN=$R4/runs/pilot2-2026-09-24; ONLY=p4-0001,p4-0002,p4-0003,p4-0004,p4-0005,p4-0006,p4-0007,p4-0008,p4-0009
ROUND="--plan $R4/PLAN4.pilot2.jsonl --run-dir $RUN --log-dir $M/logs/p4_pilot2 --only $ONLY --searches-off --live"
# 1. answer the 87 selector questions: for each line of $H-select/*/MANIFEST.jsonl, an Opus agent reads
#    $H-select/<prompt_path>, follows the question's rules (1)-(9), writes only DESC:/CARD: lines (or
#    ABSTAIN:) to a file, and runs
$PY $OH answer --dir $H-select --batch-id <batch_id> --stage finder --label <site_id>/select \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $H-select                                   # exit 0: 87 answered
$PY $P4/mass4.py $ROUND --stages select --handoff-import $H-select  # S3 (+S3R: nothing to ask)
# 2. the translate round: lane T is empty, so the export writes no question and no directory -
#    skip `validate` when every batch reports 0 calls; the import still runs assemble and verify
$PY $P4/mass4.py $ROUND --stages translate --handoff-export $H-translate
$PY $P4/mass4.py $ROUND --stages translate,assemble,verify --handoff-import $H-translate
# 3. the review round (stage `reviewer`, labels <site_id>/review)
$PY $P4/mass4.py $ROUND --stages review --handoff-export $H-review
$PY $OH answer --dir $H-review --batch-id <batch_id> --stage reviewer --label <site_id>/review \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $H-review
$PY $P4/mass4.py $ROUND --stages review --handoff-import $H-review  # the batches are then done
$PY $P4/run4.py holds --run-dir $RUN                               # HOLDS4.jsonl
# 4. the Claude Code audit of every sentence and card of pilot 2 (design S6b; T1-T7, T5 "broken"
#    included), against the pinned passages and gold_prose_errors.json - never the reviewer's verdicts
$PY -c "import sys; sys.path.insert(0, 'scripts/remediation'); from pathlib import Path; \
from phase4 import audit4; print('\n'.join(sorted(audit4.reviewed_sites(Path('$RUN')))))" > $M/logs/p4_pilot2/reviewed.txt
$PY $P4/audit4.py sheet --run-dir $RUN --site-ids $M/logs/p4_pilot2/reviewed.txt --out $M/logs/p4_pilot2/AUDIT_SHEETS.md
# 5. score T1-T13 against PILOT_THRESHOLDS.md (unchanged since pilot 1); only passing lanes open
# 6. P4 and P5 rehearsed against production (APPLY ending in ROLLBACK; nothing is written)
$PY $M/tools/write_gate4.py --group P4 --run pilot2-2026-09-24 --open-lanes W,S            # dry: plan + render
$PY $M/tools/write_gate4.py --group P4 --run pilot2-2026-09-24 --open-lanes W,S --rehearse
$PY $M/tools/write_gate4.py --group P5 --run pilot2-2026-09-24 --rehearse
```

**Open before any write of a pilot-2 site:** pilot 2 reuses the batch ids `p4-0001` .. `p4-0009` in
its own run directory, and `write4.ledger_labels` reads a site's calls from `LEDGER.jsonl` by batch id
and site id, not by run. The 70 fixed members sit in the same batch ids in both pilots, so their
journal evidence would list pilot 1's select and review labels beside pilot 2's (the evidence check
itself passes: it compares sets). Nothing is written before a pilot passes; scope the ledger read to
the run (or give pilot 2's model rounds their own `--ledger`) before step 6's committed write.

### Tests, sweep, gates for pilot 1's fixes and pilot 2 (worktree `.claude/worktrees/p4-pilot`, main venv)

* 20 new test functions, each red before its code (the pilot-2 seal tests red before this log's
  seal section): `test_phase4_select.py` +7 (the four selector rules and the two reviewer DROP
  criteria verbatim, `also_named` shown and escaped, the names only for a strong 'own' verdict and
  only from a pinned witness of the stored item), `test_phase4_verify.py` +5 (the label counts for a
  strong 'own' verdict only, never from an unpinned witness, another item, a meta under another id or
  an item without an English label; `verify_batch` reads the store's `src.D`; the S3/V6 names parity
  over 10 cases), `test_phase4_runner.py` +1 (the select preview and export carry the names) and one
  test extended (the review's S5 hands over the witness), `test_phase4_write.py` +1,
  `test_phase4_accept.py` +1 (the P4 plan and the acceptance verify with the site's witness),
  `test_phase4_pilot.py` +5 (pilot 2's draw, its refusals, the CLI's `--after`, the seal).
* `mutation_sweep.P4_PILOT2_MUTATIONS`: 34 cases (`p4 prompts` 7, `p4 select` 8, `p4 verify4` 8,
  `p4 run4` 2, `p4 write4` 2, `p4 verify_writes4` 1, `p4 pilot` 6 - the draw 4, the seal 2),
  registered once; two existing cases re-anchored on the calls the witness wrapped (`p4 write4: the
  verifier is shown other raw_data than the row writes`, `p4 verify_writes4: the store's slices
  replace the journal quotes`); 1,973 labels, all unique, every anchor and test present. The sweep's
  own `main` over **every case whose target is a file this branch changed** (verify4 173, write4 97,
  verify_writes4 33, pilot4 30, run4 26, select_stage 17, review4 13, prompts4 10, AUDIT_LOG.md 2,
  PILOT_THRESHOLDS.md 2): **403/403 caught**, the tree byte-identical to the sweep's start for its
  10 files, no `# mutant` left.
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`, `-p no:cacheprovider`):
  **5,778 passed, 111 skipped, 57 deselected, 0 failed** (312 s); every skip names gitignored data this
  worktree does not have (Natural Earth, the snapshot, the worklist, the bcases cache, ...) or an
  opt-in live test.
* `ruff check` and `ruff format --check` clean on the 18 touched Python files (ruff 0.15.11); `ruff
  check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean.
* `phase3/mutation_sweep.py` changed again, so `mass_run.package_digest` over `phase3/` changes with
  this branch: merge it while no Phase-3 mass run is in flight.

## 2026-09-24 - Phase-4 pilot 3, sealed before its first model question (no model called, nothing written)

Branch `wip/p4-pilot` (worktree `.claude/worktrees/p4-pilot`). Pilot 2 failed T3, T4, T6 and T8
(`output/remediation/phase4_runner/PILOT_RESULT_2.md`, commit `5773608`; the audit's verdicts are
`pilot2_evidence/AUDIT_VERDICTS.json`). Under the failure rule of `PILOT_THRESHOLDS.md` the causes were
fixed first, each with red-first tests and mutation cases, before this draw:

* `c4614a0` (T3) - the protected tokens gain correction and contrast markers (`actually`, `in fact`,
  `in reality`, `instead`, `rather`, `whilst`, `nevertheless`, `nonetheless`, `contrary`, `unlike`) and
  error words (`wrongly`, `mistaken*`, `erroneous*`, `incorrect*`, `misidentif*`, `misattribut*`):
  House of the Faun's `p` drop removed "(actually a satyr, since the lower body is that of a man)".
  Over the census run's 4,259 lane-W/S pools (89,072 pool sentences, 86,343 offered spans) **472**
  offered spans carried one and are offered no more.
* `fff21ba` (T4/T6) - `pipeline/utils/country_lookup.ISO_TO_DEMONYMS`, the demonym table the design's
  V10 promises: every one of `NAME_TO_ISO`'s 199 country codes with its nationality adjective and
  people noun (the retired style rule's `DEMONYM_MAP` kept, completed). V10 holds a card with any
  country's demonym (plural and `-man` nouns too; an ancient culture's use as well - the safe
  reading); the selector's card rule (4) says "names no country and no nationality adjective such as
  Greek or Danish". 3 of pilot 1's 47 and 2 of pilot 2's 49 cards carry one ("a Danish hill", "the
  first Greek site"); over the census pools 4,924 of 58,622 card-length sentences do, and the sites
  with a clean whole-sentence card candidate fall from 3,680 to 3,646.
* `bc17222` (T5) - V5 holds, and S2's pool never offers, a sentence with a full stop before a
  lowercase word (not after an initialism or a single letter; Bassae "Cotylion Mountain. near") or a
  preposition of `model4.PREPOSITIONS_NO_COMMA` right before a comma (Vindobala "the hamlet of,
  Rudchester"): 186 + 66 of the 89,072 pool sentences (251 together); the reviewer question gains
  "DROP a sentence that is garbled or ungrammatical, even when it copies the source word for word."
  (Bejsebakke). Selector question `ce36085f...`, reviewer question `59a1714e...`.
* `1d5049b` (T8) - for a strong 'own' verdict V6 (and S3, in its own code) accepts the stored name's
  base, `X (Y)` -> X and `X, Y` -> X; never for another verdict (Clare, Suffolk; Argos, Peloponnese;
  Marion, Cyprus stay held). Re-verified on a scratch copy of pilot 2's run: V6 holds **16 -> 14**
  (Partiscum (Castra); Al Thumamah, Riyadh). The same re-verification now holds House of the Faun (V4,
  `actually`), Arc de Berà (V4, `erroneous*`), Bassae and Vindobala (V5) and the Danish, Greek,
  Australian and British cards (V10).
* `f7886af` (pilot 2's open item) - every run has its own ledger, `<run>/LEDGER.jsonl`
  (`model4.LEDGER_FILE`); run4, mass4 and write_gate4 take no other, so pilot 1's calls in the shared
  batch ids can never enter pilot 2's (or 3's) journal evidence.
* `a1a5181` - `pilot4.py build --after` once per earlier pilot.

**Nothing was written to production; no model and no MiniMax endpoint was called; production was not
read for this draw** (the census, the export and the routeless read are pilot 1's, digests below).

    pilot4.py build --plan PLAN4.census.jsonl --run-dir runs/census-2026-09-24 \
        --after PILOT.jsonl --after PILOT2.jsonl --seed 20260925 --out PILOT3.jsonl

(2026-09-24 06:59:32 UTC.) With this code, `build` without `--after` still writes pilot 1's
`PILOT.jsonl` and `--after PILOT.jsonl --seed 20260924` pilot 2's `PILOT2.jsonl`, each byte for byte.

### The pilot set (`PILOT3.jsonl`, 132 sites)

Fixed, 70 sites: **exactly pilots 1's and 2's fixed members** - `build` refuses any list that is not
each earlier pilot's fixed lines, site for site and in order; the 70 lines are byte-identical to the
first 70 of `PILOT.jsonl` and of `PILOT2.jsonl`. The seeded strata are drawn anew with seed
**20260925**, each excluding everything placed before it **and all 124 seeded draws of pilots 1 and
2**: 0 sites of either earlier draw are in pilot 3.

| stratum | asked | population | eligible | taken |
|---|---|---|---|---|
| draw-W (census lane W) | 30 | 3,887 | 3,776 | 30 |
| draw-S (census lane S) | 8 | 372 | 344 | 8 |
| draw-T-candidate | 6 | 38 | 26 | 6 |
| draw-R-candidate | 8 | 252 | 235 | 8 |
| draw-B3-routeless | 5 | 20 | 10 | 5 |
| draw-extract-over-40000 | 5 | 65 | 53 | 5 (4 W, 1 S) |

No stratum was smaller than asked. The census lanes of the 132: **W 78, S 18, 0 36**, as in pilot 2.
The T and R strata are again candidates held `search-stopped` (searches off, owner order
2026-09-23), reported and never guessed into a lane. The B3 stratum had 10 routeless sites left of
20; a fourth pilot could draw only 5 more.

### The sealed artefacts

| file | sha256 |
|---|---|
| `output/remediation/phase4_runner/PILOT3.jsonl` (new) | `a4fa2f5ff26676374a48ced6fa249fc530d2003d340647e84581ef87f04152fc` |
| `output/remediation/phase4_runner/PILOT_THRESHOLDS.md` (pilot 1's, unchanged) | `64ac53341068234c905cff00095a9d7244cd4703353f63bbd0997add63fe0c13` |
| `output/remediation/phase4_runner/gold_prose_errors.json` (pilot 1's, unchanged) | `e4e63d56cbc9cca0f9cea018967fac40e897faddb9c43ad064e6203a74ebb7df` |

The thresholds are the ones sealed before pilot 1's first question, byte for byte: nothing in them
was changed or loosened after pilot 1's or pilot 2's data was seen (`test_phase4_pilot.py` pins all
three digests to this section). The draw's inputs: `PILOT.jsonl` `7f66f987...e063fc`, `PILOT2.jsonl`
`9caaaa03...cc9f81c`, `PLAN4.census.jsonl` `644b9032...d4676b591`, `S0_ROUTELESS.json`
`81c3b426...37997746`, `gold_standard/sites.json` `18653fc1...b2756`, `qid_repair/PLAN.jsonl`
`9d57b431...a6ce4f`.

## 2026-09-24 - Phase-4 pilot 3's non-model stages and its select export (no model called, nothing written)

After the seal above (commit `30dccce`, 09:01:34 +02:00; the first question was exported at 09:02:16),
`plan4.py build --pilot PILOT3.jsonl --out PLAN4.pilot3.jsonl` wrote pilot 3's plan from the same
export as the census and pilots 1 and 2 (`S0_ROWS.jsonl` `2c99f96f...72a8`; sha256
`5854486313ab874c155bcb04761e173cdfc942fa4781fa7245db83602cc52468`, gitignored): **pilot 3 is its first
9 batches, `p4-0001` .. `p4-0009`** (8 x 15 + 12, in PILOT3.jsonl's order), 334 batches in all, the
same flags as pilot 2's plan. Pilot 1's and pilot 2's plans and run directories are untouched.

    mass4.py --plan PLAN4.pilot3.jsonl --run-dir runs/pilot3-2026-09-24 --log-dir logs/p4_pilot3 \
        --only p4-0001,..,p4-0009 --live --stages prepare,sources,routes,select --searches-off \
        --handoff-export output/remediation/handoff/p4-pilot3-select --jobs 3

2026-09-24 07:01:59-07:03:41 UTC, `STAGE_EXIT=0`, every batch "done" for its round. **The run's own
ledger** (`runs/pilot3-2026-09-24/LEDGER.jsonl`, `model4.LEDGER_FILE`; the shared
`phase4_runner/LEDGER.jsonl` was not written): 231 fetch lines (en.wikipedia.org 160, www.wikidata.org
54, it/ca/tr/fr/de.wikipedia.org 17), all 200, none given up; 0 searches; 0 model calls. Every lane
equals the census's.

| stage | result |
|---|---|
| S0 plan | 132 sites in 9 batches |
| S1 sources | pinned 96, scope-pending 3, no-title 20, rejected 13 |
| S1b routes | **lane W 78, S 18, 0 36**; 0 searches |
| S3 select, export | **87 questions** (lane W 78, lane S 9); prompts 2,466-29,810 characters, median 5,467; 23 carry a non-empty `also_named` (the pinned title, the item label or - new - the stored name's base V6 accepts for a strong 'own' verdict) |
| S3R restricted | no lane-R site: nothing asked |

Every exported prompt carries the selector question `ce36085f...` (rules (6)-(9) and the card rule
(4) with the nationality adjectives), and every pool is built with this branch's spans (the
correction and contrast markers protected) and without the two garbles V5 holds. The 96 selecting
sites minus 87 questions are 9 lane-S sites whose article offers no sentence that names them; the
import holds them `no-source` with no call bought: Amyntas Rock Tombs, Priene Ruins, Hebbariyeh
Roman Temple (gold), Templos de Tarxien (identity trap) - the four pilot 2 held the same way - and
five of the eight new lane-S draws: Aspendos Theatre, Dungur Palace (Queen of Sheba Palace), Dacian
Fortress Costesti, Ciudad Romana de Cáparra, The Temple of Artemis-Selçuk.

**The 36 holds** (`HOLDS4.jsonl`): the 17 of the fixed members are pilot 2's, reason for reason
(`scope-pending` 3: Midford Castle, Ksar el Barka, Museo Campano; `search-stopped` 14: Font dels
Coms, Temple of Dedun, El Tintal, Ahin Posh Tape, Tlalpan, Estipeon, Crantit Chambered Cairn, the 3
'Theatre' and 4 'Mortuary temple' traps); the 19 new are the T, R and B3 candidates, all
`search-stopped` (6 T: Tomba dei Giganti e Nuraghe Imbertighe, Necropoli di Realmese, Poblat
Talaiòtic de Talatí de Dalt, Ayanis Kalesi, Table des Marchand, Karasis Kalesi; 8 R: Gavur Kalesi,
Archaeological Site of Eleusis, Medusa Mozaiği, Ancient City of Sillyon, Cueva del Maguey, Upuigma
Rock Shelter, Kinichná, Ancient Theatre of Thassos; 5 B3: Cras - Ring Cairn to North of, Tapınak,
GOLOGOÇ VİRANŞEHİR ŞANLIURFA TARİHİ KEMER, Foel Dduarth Enclosure, "Cras  Round Cairn" - two spaces in the stored name).

**Handoff directory** `output/remediation/handoff/p4-pilot3-select` (gitignored, 933 KB, stage
`finder`, labels `<site_id>/select`). `opus_handoff.py validate`: 87 questions, 87 missing, 0
answered, 0 stale, 0 malformed, 0 orphans (exit 1 until they are answered). The run directory
`runs/pilot3-2026-09-24` (7.7 MB, gitignored, its ledger inside) travels with it.

**T7 for pilot 3** is pilot 2's (the same fixed members): El Tintal, Ahin Posh Tape (canaries), FC-2
(Font dels Coms) and TD-1 (Temple of Dedun) sit on sites held `search-stopped`, AM-1 (Amyntas Rock
Tombs) on a lane-S site the import holds `no-source` - closed-list reasons; the other 20 are asked.

### The select questions re-exported before any answer (two owner decisions, 2026-09-24)

None of the 87 questions above had been answered (`opus_handoff.py validate`: 87 questions, 0
answered, 87 missing) when the owner took two decisions; both are recorded in PHASE4_CONTRACTS.md
(section 6, and section 7 "Pilot 3's decisions"):

1. **Design entry [6] wins** - "Cultural adjectives such as Roman, Egyptian or Maya are allowed".
   `pipeline/utils/country_lookup.py` splits the demonyms into `ANCIENT_CULTURE_ADJECTIVES` (74
   words, each an ancient culture: the design's three examples, the owner's list of 42, Hellenic,
   Hellene and Macedonian - ancient Greece and Macedon, which the table carries as modern demonyms -,
   Romano-British and Gallo-Roman, three spellings and 24 more ancient cultures of the catalogue's
   regions; never held, nor their plurals, `-man` nouns or a demonym inside them) and
   `MODERN_NATIONALITY_DEMONYMS` (the table without them: what V10 holds). Pilot 2's safe reading
   is retired. Measured (`verify4.card_demonyms`, safe reading -> split): pilot 1's held cards 3 -> 1
   and pilot 2's 2 -> 1 - "Bulgarian" and "a Danish hill" stay held; Al-Mnaykhrat's "Greek
   rock-tomb", "the Bronze Age and Romano-British period" and Bassae's "the first Greek site to be
   inscribed on the World Heritage List" pass (the last means Greece: the reviewer's CARD line and
   the audit, T6, judge it now); over the census run's lane-W/S pools the card-length sentences with
   a held demonym fall from 4,912 to 3,553 of 58,570, and the sites with a clean whole-sentence card
   candidate rise from 3,645 to 3,656 of 4,259.
2. **V6's positional pronoun rule is the selector's rule (10)**, after (9): "(10) a DESC sentence
   may open with It, Its, This, These, They, Their, He, She, His, Her, The latter, The former, Here
   or There (after its removals) only if the sentence numbered one lower, in the same section, is
   also one of your DESC sentences; so your first DESC sentence never opens with one of these
   words." Rule (4) now reads "... names no country and no modern nationality adjective such as
   Danish or Spanish, has no parentheses, does not open with a pronoun, and states something
   concrete; cultural adjectives such as Roman, Egyptian or Maya are fine; prefer one that carries a
   date;". The wording "numbered one lower, in the same section" agrees with V6's adjacency (same
   source, only whitespace between) on all 6,575 consecutive sentence pairs of pilot 3's 96 pinned
   texts, and on 207,655 of 207,656 over the census run's 4,259 (one article repeats its "See also"
   heading; there V6 is the stricter and holds).

Selector question sha256 `85e6e47b17aa30abdf415e797e8c95def4a83aef489f7d617e658bb39066b701` (was
`ce36085f...afb79c`); the reviewer question `59a1714e...a7d999`, the answer lines and the parsers are
unchanged.

**The re-export.** The first export was moved out of the tree, compared with the new one below and
deleted; then only S3's export ran again, over the S0/S1/S1b results already in the run directory:

    mass4.py --plan PLAN4.pilot3.jsonl --run-dir runs/pilot3-2026-09-24 --log-dir logs/p4_pilot3 \
        --only p4-0001,..,p4-0009 --live --stages select --searches-off \
        --handoff-export output/remediation/handoff/p4-pilot3-select --jobs 3

2026-09-24 08:21:13-08:21:20 UTC, `STAGE_EXIT=0`, every batch "done" for its round. **No per-batch
state had to be reset**: the first export ran the stage over a scratch copy of each batch directory
(`run4.handed_off`), so none of its selections, answers, reports, holds or ledger lines was ever in
the run directory, and `mass4` keeps no other round state than `batch_done` (the review's
`review4.json`, absent) and its progress file, which every run rewrites
(`logs/p4_pilot3/progress.json`). **Nothing was fetched**: the run directory's 764 files - ledger,
`HOLDS4.jsonl` (rewritten to the same bytes, 36 holds), lanes, evidence, the stage reports - are
byte-identical before and after (sha256 of every file), and the ledger still has its 231 fetch lines,
0 searches and 0 model calls. **87 questions** again (p4-0001 .. p4-0009: 12, 12, 12, 10, 8, 15, 12, 1,
5), the same 87 labels; every prompt's site block is byte-identical to the first export's and only
its question differs (`ce36085f...` -> `85e6e47b...`, 382 characters longer: prompts 2,848-30,192
characters, median 5,849). `opus_handoff.py validate`: 87 questions, 0 answered, 87 missing, 0 stale,
0 malformed, 0 orphans (969 KB). `PILOT3.jsonl` (`a4fa2f5f...`), `PILOT_THRESHOLDS.md` (`64ac5334...`)
and `PLAN4.pilot3.jsonl` (`58544863...`) are byte-identical. No model and no MiniMax endpoint was
called; production was neither read nor written. The read-only measurements are
`logs/p4_pilot3/measure_v10_split.py`, `check_rule10_adjacency.py` and `compare_reexport.py`
(gitignored).

### The orchestrator's next commands (from this worktree, main venv)

```bash
cd /c/PythonProjects/AncientMap/.claude/worktrees/p4-pilot && export PYTHONIOENCODING=utf-8
PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe; M=output/remediation; R4=$M/phase4_runner
P4=scripts/remediation/phase4; OH=scripts/remediation/opus_handoff.py; H=$M/handoff/p4-pilot3
RUN=$R4/runs/pilot3-2026-09-24; ONLY=p4-0001,p4-0002,p4-0003,p4-0004,p4-0005,p4-0006,p4-0007,p4-0008,p4-0009
ROUND="--plan $R4/PLAN4.pilot3.jsonl --run-dir $RUN --log-dir $M/logs/p4_pilot3 --only $ONLY --searches-off --live"
# every stage writes the run's own ledger, $RUN/LEDGER.jsonl; no command takes --ledger any more
# 1. answer the 87 selector questions: for each line of $H-select/*/MANIFEST.jsonl, an Opus agent reads
#    $H-select/<prompt_path>, follows the question's rules (1)-(10), writes only DESC:/CARD: lines (or
#    ABSTAIN:) to a file, and runs
$PY $OH answer --dir $H-select --batch-id <batch_id> --stage finder --label <site_id>/select \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $H-select                                   # exit 0: 87 answered
$PY $P4/mass4.py $ROUND --stages select --handoff-import $H-select  # S3 (+S3R: nothing to ask)
# 2. the translate round: lane T is empty, so the export writes no question and no directory -
#    skip `validate` when every batch reports 0 calls; the import still runs assemble and verify
$PY $P4/mass4.py $ROUND --stages translate --handoff-export $H-translate
$PY $P4/mass4.py $ROUND --stages translate,assemble,verify --handoff-import $H-translate
# 3. the review round (stage `reviewer`, labels <site_id>/review)
$PY $P4/mass4.py $ROUND --stages review --handoff-export $H-review
$PY $OH answer --dir $H-review --batch-id <batch_id> --stage reviewer --label <site_id>/review \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $H-review
$PY $P4/mass4.py $ROUND --stages review --handoff-import $H-review  # the batches are then done
$PY $P4/run4.py holds --run-dir $RUN                               # HOLDS4.jsonl
# 4. the Claude Code audit of every sentence and card of pilot 3 (design S6b; T1-T7, T5 "broken"
#    included), against the pinned passages and gold_prose_errors.json - never the reviewer's verdicts
$PY -c "import sys; sys.path.insert(0, 'scripts/remediation'); from pathlib import Path; \
from phase4 import audit4; print('\n'.join(sorted(audit4.reviewed_sites(Path('$RUN')))))" > $M/logs/p4_pilot3/reviewed.txt
$PY $P4/audit4.py sheet --run-dir $RUN --site-ids $M/logs/p4_pilot3/reviewed.txt --out $M/logs/p4_pilot3/AUDIT_SHEETS.md
# 5. score T1-T13 against PILOT_THRESHOLDS.md (unchanged since pilot 1); keep $RUN/LEDGER.jsonl and
#    HOLDS4.jsonl with the audit verdicts (pilot3_evidence/), as pilots 1 and 2 did; only passing lanes open
# 6. P4 and P5 rehearsed against production (APPLY ending in ROLLBACK; nothing is written); the P4
#    plan reads $RUN/LEDGER.jsonl and no other
$PY $M/tools/write_gate4.py --group P4 --run pilot3-2026-09-24 --open-lanes W,S            # dry: plan + render
$PY $M/tools/write_gate4.py --group P4 --run pilot3-2026-09-24 --open-lanes W,S --rehearse
$PY $M/tools/write_gate4.py --group P5 --run pilot3-2026-09-24 --rehearse
```

### Tests, sweep, gates for pilot 2's fixes and pilot 3 (worktree `.claude/worktrees/p4-pilot`, main venv)

* 22 new test functions, each red before its code: `test_phase4_verify.py` +9 (the correction
  markers V4 refuses; a card naming a nationality; the two garbles V5 holds, over the shared
  `p4_garble_cases.py` and against S2's; the stored name's base, for a strong 'own' verdict only,
  and its S3/V6 parity over 12 names x 10 gate and witness cases), `test_phase4_pilot.py` +4 (pilot
  3's draw, its refusal of an earlier pilot whose fixed members moved, the seal, the sealed file),
  `tests/pipeline/test_country_demonyms.py` +4 (new: the table covers `NAME_TO_ISO` exactly, proper
  nouns, the modern adjectives, the retired style rule's demonyms kept), `test_phase4_select.py` +2
  (card rule (4), the reviewer's garble DROP), `test_phase4_sentences.py` +2 (the garble fixture, the
  pool), `test_phase4_write.py` +1 (the gate reads the ledger of its own run only: pilot 1's labels
  never reach pilot 2's evidence). Extended: 5 `SPAN_CASES`, 16 S2 protected-token cases, the
  `model4` additions pin, S1, S1b and the select round handed the run's ledger, mass4's ledger, and
  the 47 write-gate call sites moved to the run's ledger. Red first, measured: T3 28 failures, T4/T6
  two collection errors (no table), T5 77 failures, T8 50, the ledger `AttributeError` (no
  `LEDGER_FILE`), pilot 3 5 failures.
* `mutation_sweep.P4_PILOT3_MUTATIONS`: 42 cases (`p4 verify4` 16, `p4 sentences` 6, `p4 pilot` 5,
  `p4 model` 3, `p4 country_lookup` 3, `p4 select` 3, `p4 prompts` 2, `p4 run4` 2, `p4 write_gate4`
  1, `p4 mass4` 1), registered once; three older cases re-anchored on lines this branch rewrote (`p4
  model: unknown is not protected`, `p4 pilot: pilot 2 takes fixed members other than pilot 1's`,
  `p4 pilot: build ignores the earlier pilot it is told`); 2,015 labels, all unique, every anchor and
  test present. The sweep's own `main` over **every case whose target is a file this branch changed
  since `5773608`** (verify4 189, write4 97, model4 80, sentences 61, route_stage 56, mass4 45,
  write_gate4 35, pilot4 33, run4 28, select_stage 20, prompts4 12, mutation_sweep 3, lanes 3,
  PILOT_THRESHOLDS.md 3, AUDIT_LOG.md 3, country_lookup 3): **671 cases, 670 caught on the first run**
  - `p4 sentences: an overlong sentence is offered` survived because the new garble rule refused its
  test's long sentence ("old. and a fragment.") before the length bound was read; the test was
  re-isolated (`e338225`) and the case is caught - **671/671**; the tree byte-identical to the
  sweep's start for its 16 files; no `# mutant` left.
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`, `-p no:cacheprovider`):
  **6,060 passed, 111 skipped, 57 deselected, 0 failed** (318.7 s). The first run had 1 failure,
  `test_every_mutation_names_an_anchor_and_a_test_that_exist` (the two pilot-2 cases above; fixed in
  `c88d72a`). The skips are the same 111 as before: gitignored data (Natural Earth, the snapshot, the
  worklist, the bcases cache, the Phase-3 enwiki extracts, ...), two tests of refactored-out legacy
  functions and one opt-in live test. After `e338225` (one test's data) the Phase-4 files and the
  sweep test were run again: 1,580 passed.
* `ruff check` and `ruff format --check` clean on the 24 touched Python files (ruff 0.15.11); `ruff
  check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean; the Lyra import check (country_lookup is under
  `pipeline/`, which both images ship) passes.
* `phase3/mutation_sweep.py` changed again, so `mass_run.package_digest` over `phase3/` changes with
  this branch: merge it while no Phase-3 mass run is in flight.

### Tests, sweep, gates for the two decisions (worktree `.claude/worktrees/p4-pilot`, main venv)

* 9 new test functions, each red before its code (33 new test items with the parametrizations):
  `tests/pipeline/test_country_demonyms.py` +5 (the owner's cultures are in (a); (a) is written as
  proper nouns and names no country; (b) is the table without (a) and disjoint from it; 16 modern
  nationalities held; Greek, Hellenic, Hellene, Egyptian, Macedonian in the table and not held),
  `test_phase4_verify.py` +3 (six culture cards pass V10 - Egyptian, Roman, Maya, Greek, Greeks,
  Hellenistic, Hellenic, Macedonian(s), Romano-British, Egyptians, Hellenes, Norsemen; no word of (a)
  is ever held, alone, as a plural or a `-men` noun; a full V10 case holds "Danish" and passes
  "Egyptian"), `test_phase4_select.py` +1 (rule (10) verbatim after (9), its words
  `model4.PRONOUN_OPENERS` in order). Rewritten: the card-rule test (the new rule (4); Danish and
  Spanish in (b), Roman, Egyptian and Maya in (a) and not in (b)) and the V10 nationality test (its
  Greek examples moved to the culture test); pilot 1's rules test no longer ends at the answer lines.
  Red first, measured: all three files a collection error (no `ANCIENT_CULTURE_ADJECTIVES`); with the
  data alone, 10 failures (8 V10, 2 selector question).
* `mutation_sweep.P4_PILOT3_MUTATIONS`: 12 new cases ("pilot 3, decision 1": `p4 country_lookup` 5,
  `p4 verify4` 3, `p4 prompts` 1; "decision 2": `p4 prompts` 2, `p4 model` 1) and 4 re-anchored on
  the lines this rewrote (`p4 verify4`: plural or -man noun, lower-case word, inside a longer word;
  `p4 prompts`: the card's nationality adjective); 2,027 labels, all unique, every anchor and test
  present. The sweep's own `main` over **every case whose target this change touched** (verify4 192,
  prompts4 15, country_lookup 8, mutation_sweep 3, AUDIT_LOG.md 3) plus the new `p4 model` case:
  **222/222 caught**; the tree byte-identical to the sweep's start for its 6 files; no `# mutant` left
  (driver `logs/p4_pilot3/sweep_decisions.py`, log `sweep_decisions.log`).
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`, `-p no:cacheprovider`):
  **6,093 passed, 111 skipped, 57 deselected, 0 failed** (310.8 s); the skips are the same 111.
* `ruff check` and `ruff format --check` clean on the 7 touched Python files (ruff 0.15.11); `ruff
  check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean; the Lyra import check (`country_lookup` is under
  `pipeline/`) passes.
* `phase3/mutation_sweep.py` changed again, so `mass_run.package_digest` over `phase3/` changes with
  this branch: merge it while no Phase-3 mass run is in flight.

### Open

* ~~The demonym table's safe reading departs from one sentence of the final design~~ - **decided
  2026-09-24 by the owner: design entry [6] wins** (cultural adjectives pass V10; "The select
  questions re-exported before any answer" above). Open with it: a word that is both a culture and a
  nationality passes whatever it means ("the first Greek site to be inscribed" means Greece) - the
  reviewer's CARD line and the audit judge such a card.
* **T8 may fail again.** Pilot 2's own selections, re-verified with this branch: 51 of 78 lane-W
  sites pass before review (V6 14 - 9 of them the pronoun rule, a sentence opening with It, This,
  These, ... whose immediate source predecessor is not published right before it - abstained 7, V14
  6, V4 2, V8 1, V5 1; a site may carry several). The selector question does not state V6's
  positional pronoun rule; rule (9) asks only for an antecedent among the picks. Pilot 3's selector
  picks anew, so the number is not its result. **Done 2026-09-24:** the rule is the selector's rule
  (10), and the 87 questions were re-exported before any answer (above).
* 5 of pilot 3's 8 new lane-S draws offer no name-bearing sentence and are held `no-source` without a
  question (lane S is not in T8).
* Pilot 3's ledger lives in its gitignored run directory; keep it with `HOLDS4.jsonl` and the audit
  verdicts in `pilot3_evidence/` when the result is recorded.

## 2026-09-24 - Phase-4 pilot 4, sealed before its first model question (no model called, nothing written)

Branch `wip/p4-pilot` (worktree `.claude/worktrees/p4-pilot`). Pilot 3 failed T1, T4, T7 and T8
(`output/remediation/phase4_runner/PILOT_RESULT_3.md`, commit `67b4185`; the audit's verdicts are
`pilot3_evidence/AUDIT_VERDICTS.json`). Under the failure rule of `PILOT_THRESHOLDS.md` the causes were
fixed first, each with red-first tests and mutation cases, before this draw. The read-only
measurements are `logs/p4_pilot4/extract_pronoun_corpus.py` (the census pools' 88,936 lane-W/S pool
sentences of 4,100 sites with a pool, and pilots 1-3's 1,185 published sentences and cards with their
audit verdicts), `measure_pronoun_rules.py`, `measure_v14_subnational.py` and
`measure_follow_drops.py` (gitignored); the census run directory and pilot 3's run and handoff
directories were only read (sha256 of every file, 31,727, identical before and after).

* `a522227` (T1 + T4, one gap) - **the pronoun past the first word.** V6 held a sentence, and V10 a
  card item, only when the *first* word was one of `model4.PRONOUN_OPENERS`. Stanydale Temple's "Pottery
  sherds show that it was also occupied ..." and Dolebury Warren's card "Standing on a limestone ridge
  ..., it was made into a hill fort ..." leaned on an unpublished source sentence past it. **The rule,
  in one sentence:** a sentence also leans on the sentence before it in its source when its first word
  of `model4.PERSONAL_PRONOUNS` (it, its, they, their, them, he, his, him, she, her; whole, any case) is
  one of `SUBJECT_PRONOUNS` (it, they, he, she) and stands right after the sentence's first comma
  (`, `), or right after the word `that` with no word of `ARTICLES` (the, a, an) before it. V6 holds
  such a sentence unless its source predecessor is published right before it, as it holds an opener
  (`verify4.leaning_pronoun`); V10 holds a card item that leans (card scope). Rule (10) states it, rule
  (4) refers the card to it, and the reviewer gains "DROP a sentence in which it, its, ... - at its
  start, after a fronted phrase or in a that-clause - refers to something no published sentence
  before it names, and DROP the card when such a pronoun has no antecedent inside the card: the card
  is read on its own." **Measured, every candidate** (census: pool sentences it binds beyond the
  opener rule, those of them whose source predecessor is not in the pool - never publishable -, the
  sites that keep a possible sentence 1 (names the site, does not lean; 3,806 of the 4,100 today),
  card-length (80-200) plain sentences it holds beyond the opener rule of 42,401, the sites that keep
  a whole-sentence card candidate (3,656 today); pilots 1-3: published sentences it would hold - it
  fires and the source predecessor is not published right before - and cards):

  | candidate | binds | never | sentence 1 | cards held | card sites | pilot sentences (1/2/3) | pilot cards | both cases |
  |---|---|---|---|---|---|---|---|---|
  | the opener list only (V6 until now) | 0 | 0 | 3,806 | 0 | 3,656 | 0 | 0 | neither |
  | any personal pronoun | 15,632 | 2,975 | 3,750 | 8,265 | 3,562 | 68 (20/21/27) | 9 | yes |
  | any subject pronoun | 8,605 | 1,445 | 3,781 | 4,438 | 3,604 | 40 (12/10/18) | 5 | yes |
  | the first personal pronoun is a subject form | 7,826 | 1,295 | 3,784 | 4,080 | 3,609 | 36 (11/9/16) | 5 | yes |
  | a subject pronoun right after the first `,`, or after any "that" | 2,523 | 268 | 3,805 | 1,316 | 3,640 | 13 (2/4/7) | 1 | yes |
  | the first personal pronoun a subject form, no capitalised word but the first before it | 3,765 | 353 | 3,805 | 2,192 | 3,632 | 14 (6/4/4) | 2 | no: Dolebury's card |
  | the first personal pronoun a subject form, no article before it | 2,784 | 292 | 3,802 | 1,463 | 3,642 | 7 (2/2/3) | 1 | no: Dolebury's card |
  | the last, or a subject pronoun right after the first `,` | 3,690 | 386 | 3,802 | 1,960 | 3,634 | 11 (2/3/6) | 2 | yes |
  | a subject pronoun right after the first `,`, alone | 1,710 | 146 | 3,805 | 922 | 3,643 | 7 (1/2/4) | 1 | no: Stanydale |
  | the first personal pronoun a subject form right after "that", alone | 652 | 97 | 3,806 | 327 | 3,653 | 2 (0/1/1) | 0 | no: Dolebury |
  | a subject pronoun right after the first `,`, or the first personal pronoun a subject form right after "that" | 2,361 | 243 | 3,805 | 1,249 | 3,640 | 9 (1/3/5) | 1 | yes |
  | the first personal pronoun a subject form right after the first `,` or "that" | 2,193 | 234 | 3,805 | 1,151 | 3,642 | 7 (1/2/4) | 1 | yes |
  | a subject pronoun right after the first `,`, or any after "that" with no article before it | 1,895 | 162 | 3,805 | 1,017 | 3,643 | 9 (1/3/5) | 1 | yes |
  | the first personal pronoun a subject form right after the first `,`, or any after "that" with no article before it | 1,731 | 153 | 3,805 | 922 | 3,645 | 7 (1/2/4) | 1 | yes |
  | the first personal pronoun a subject form right after the first `,`, or right after "that" with no article before it | 1,703 | 152 | 3,805 | 905 | 3,645 | 7 (1/2/4) | 1 | yes |
  | **the chosen rule** (`verify4.leaning_pronoun`): the same, the first comma being the first `, ` | **1,738** | **158** | **3,805** | **915** | **3,645** | **7 (1/2/4)** | **1** | **yes** |

  The chosen rule is the most precise that holds both pilot-3 cases: in pilots 1-3's published texts
  it holds 7 sentences and 1 card - Stanydale's (UNSUPPORTED, the only one the audit found broken),
  The Gop's "Oval in form, it is the second-largest Neolithic mound in Britain ..." (a fixed member,
  in all three pilots), the Altar Stone's "Some believe that it always was recumbent.", Teman's
  "Outside of the Bible, it was mentioned by Ptolemy ..." and Dolebury Warren's sentence 2, and
  Dolebury's card - each a pronoun whose antecedent lies outside its sentence, as an opener's does.
  The literal reading of "the first comma" (a `,` anywhere, so a digit group's) binds 35 fewer, and
  those 35 are fronted phrases with a thousands comma ("With a population of 824,340, it is the third
  most-populous city in Spain.", "Estimated to be 300,000 years old, they represent ..."): the comma
  that ends a fronted phrase is followed by a space. Over a seeded sample of 60 of the 1,738 (seed
  20260926, read by hand), 46 refer outside their sentence; of the 14 others, 9 are an expletive
  *it* ("According to the material collected, it is possible that ...") and 5 refer inside it.
  Selector question `0f64868f...`, reviewer question `3ec5024c...` after this commit.
* `a59e535` (T7) - **a sentence the article contradicts.** Partiscum (Castra), CANARY-03: the selector
  picked the lead ("a fort in the Roman province of Dacia", "the most Western fort of Dacia") that the
  article's own body contradicts and reduces to a presumption; the pool showed W5 "the area was the
  territory of the Iazyges", W16 "... only testifies to a Roman settlement", W17 "the presumed castle",
  W40 "the assumed fort" and W49 "the direct road connection from Pannonia via Partiscum to Dacia". The
  selector gains rule (11), "never pick a sentence that another listed sentence contradicts, or
  reduces to a presumption, an assumption or a dispute, even when it is the article's lead". **The
  gap in the reviewer's prompt:** it showed each published sentence, its untrimmed source sentence,
  the two source sentences before it and its heading - for a lead, nothing before it - so none of
  those sentences was ever in front of the reviewer and no DROP could see the contradiction. Closed in
  the prompt builder: `review4.passage` puts the passage the sentences were chosen from before the
  numbered sentences, as `<source id="PASSAGE">` - the selector's pool for lanes W, S and T (bounded
  by `sentences.MAX_POOL_CHARS`, 24,000 characters), lane R's pages whole - and the reviewer question
  says so and gains "DROP a sentence that another sentence of the passage contradicts, or reduces to a
  presumption, an assumption or a dispute, even when it is the article's lead; ask the same of the
  card." A general rule: no canary's words are in any code or prompt. Selector `751816c1...`,
  reviewer `89e6035d...`.
* `7d05cda` (V14) - **sub-national names.** Lake Mungo, "a dry lake located in New South Wales,
  Australia", was held as placing the site in Wales. The scan of the census pools for a `NAME_TO_ISO`
  name directly preceded by a capitalised word or inside a longer proper name found 263 distinct
  runs; almost all are the country itself ("Upper Egypt", "Historic England", "South Wales", "Western
  Australia"), a person ("Anatole France", "John Ireland", "Quaritch Wales", "Pescennius Niger") or an
  organisation. Those whose real country differs from the name inside, each verified, are
  `country_lookup.SUBNATIONAL_NAME_TO_ISO` (15): New South Wales AU, New Mexico US, New England US
  (both census sentences are the US region), Central Macedonia, Western Macedonia, Eastern Macedonia
  and Thrace, Greek Macedonia GR, West Azerbaijan province IR, Upper Jordan Valley IL, Jordan Hill GB
  (Dorset), Kraku Lu Jordan RS, El Peru GT (El Perú-Waka'), Inner Niger Delta ML, Lapis Niger IT (the
  Roman Forum), Denmark Fjord GL. Found and left out: New Guinea (PG and ID; the census's six sentences are
  about a cave in Victoria), Belize River (GT and BZ), Caucasian and Caucasus Albania, British India, Middle
  Niger (no one country), the bare "West Azerbaijan" (the census also uses it for western
  Azerbaijan), British Honduras (the colony that is all of Belize, no sub-national place), Little
  Canada (not verified). "South Wales" stays Wales. `verify4`'s country regex reads both tables,
  longest first; V14 compares the whole name's code. Over the census pools V14's location holds fall
  from **74 to 67 sentences (69 to 62 sites)**: Lake Mungo, Jordan Hill Roman Temple, Independence
  Fjord, Kraku Lu Jordan, El Perú, Paradeisos, Azargoshnasp; Horvat Omrit stays held for "Syria" (the
  demilitarised zone). V10 still holds a card that carries such a name (no card-length sentence's
  country verdict changes).
* `98f276b` (T8) - **the review's drop takes the sentence that leans on it along.**
  `review4.follow_drops`, after the reviewer's verdict is parsed: a kept sentence that leans on the
  sentence before it (`sentences.leans_on_predecessor`, the same rule in the review's own code, a
  parity test over `tests/remediation/p4_pronoun_cases.py`) whose published predecessor is dropped is
  dropped too, in order, so a chain goes whole; each is recorded in `review4.json` under `followed`
  (`sentence`, `follows`, reason `leans-on-a-dropped-sentence`), the reviewer's lines stay as written,
  and the site is judged on what remains (two sentences at least, V1-V15 again, V9 included).
  Rebuilt read-only from pilot 3's stored selections and answered reviews: **3 of its 63 reviewed
  sites** have such a drop - Stanydale Temple R6 (the T1 sentence), Mersinaki R4 ("Here the Swedish
  Expedition found a lot of sculptures"), Diana Fort R4 ("It was built in the Tiberian-Claudian age
  ...") - and nothing else changes.
* `5f85ba3` (rule 7) - **the name V6 accepts, stated.** Pilot 3's selectors abstained on "Argos,
  Peloponnese" and "Clare, Suffolk", never told when the stored name without its disambiguator counts
  (pilot 2's `name_base`). Rule (7) now reads "... its name, an alias or an also_named name of the site
  element, all of that name's words in their order with nothing but spaces or punctuation between
  them (case and accents do not matter); a name written "X (Y)" - ending in one bracket with no
  bracket inside it - or else "X, Y" - X before the first comma - is named by X alone only when
  also_named lists X; if no listed sentence names the site so, answer ABSTAIN with that reason;". A
  test reads the two forms literally and gets `name_base`'s base in verify4's and select_stage's code
  for 17 names, and shows S3 lists "Argos" in `also_named` exactly where V6 accepts it (a strong 'own'
  verdict). Selector `a0b422e7...`.
* `76a5757` - `pilot4.SEED_PILOT4` 20260926.

**The questions this pilot asks:** selector `a0b422e73474f6ba8cd59c7477d49f51c8aabd131f6e3d56742597c2a367ef93`
(was `85e6e47b...` in pilot 3), reviewer
`89e6035d1e295764b5a77e904bc24e080ff57d63b8d05ef786cc7f5fc71e7523` (was `59a1714e...`); the answer
lines and both parsers are unchanged.

**Nothing was written to production; no model and no MiniMax endpoint was called; production was not
read for this draw** (the census, the export and the routeless read are pilot 1's, digests below).

    pilot4.py build --plan PLAN4.census.jsonl --run-dir runs/census-2026-09-24 \
        --after PILOT.jsonl --after PILOT2.jsonl --after PILOT3.jsonl --seed 20260926 \
        --out PILOT4.jsonl

(2026-09-24 11:48:17 UTC.) With this code `build --after PILOT.jsonl --after PILOT2.jsonl --seed
20260925` still writes pilot 3's `PILOT3.jsonl`, byte for byte (`a4fa2f5f...`, rebuilt to a scratch
path and compared).

### The pilot set (`PILOT4.jsonl`, 132 sites)

Fixed, 70 sites: **exactly the fixed members of pilots 1, 2 and 3** - `build` refuses any list that is
not each earlier pilot's fixed lines, site for site and in order; the 70 lines are byte-identical to
the first 70 of `PILOT.jsonl`. The seeded strata are drawn anew with seed **20260926**, each
excluding everything placed before it **and all 186 seeded draws of pilots 1, 2 and 3**: 0 sites of
any earlier draw are in pilot 4.

| stratum | asked | population | eligible | taken |
|---|---|---|---|---|
| draw-W (census lane W) | 30 | 3,887 | 3,742 | 30 |
| draw-S (census lane S) | 8 | 372 | 335 | 8 |
| draw-T-candidate | 6 | 38 | 20 | 6 |
| draw-R-candidate | 8 | 252 | 227 | 8 |
| draw-B3-routeless | 5 | 20 | 5 | 5 |
| draw-extract-over-40000 | 5 | 65 | 47 | 5 (all lane W) |

No stratum was smaller than asked; **the B3 stratum is now used up** (20 routeless sites, 15 drawn by
pilots 1-3, the last 5 here): a fifth pilot would find none. The census lanes of the 132: **W 79, S
17, 0 36**. The T and R strata are again candidates held `search-stopped` (searches off, owner order
2026-09-23), reported and never guessed into a lane.

### The sealed artefacts

| file | sha256 |
|---|---|
| `output/remediation/phase4_runner/PILOT4.jsonl` (new) | `30ab5e9d28b71388f79319b93e945dfd223d5d3edeb9a62e42064844757b2a26` |
| `output/remediation/phase4_runner/PILOT_THRESHOLDS.md` (pilot 1's, unchanged) | `64ac53341068234c905cff00095a9d7244cd4703353f63bbd0997add63fe0c13` |
| `output/remediation/phase4_runner/gold_prose_errors.json` (pilot 1's, unchanged) | `e4e63d56cbc9cca0f9cea018967fac40e897faddb9c43ad064e6203a74ebb7df` |

The thresholds are the ones sealed before pilot 1's first question, byte for byte: nothing in them
was changed or loosened after the data of pilots 1, 2 or 3 was seen (`test_phase4_pilot.py` pins all
three digests to this section). `PILOT.jsonl` (`7f66f987...`), `PILOT2.jsonl` (`9caaaa03...`) and
`PILOT3.jsonl` (`a4fa2f5f...`) are byte-identical. The draw's inputs: `PLAN4.census.jsonl`
`644b9032...d4676b591`, `S0_ROUTELESS.json` `81c3b426...37997746`, `gold_standard/sites.json`
`18653fc1...b2756`, `qid_repair/PLAN.jsonl` `9d57b431...a6ce4f`.

## 2026-09-24 - Phase-4 pilot 4's non-model stages and its select export (no model called, nothing written)

After the seal above (commit `f571be3`, 13:51:32 +02:00; the first question was exported at
11:51:54 UTC), `plan4.py build --pilot PILOT4.jsonl --out PLAN4.pilot4.jsonl` wrote pilot 4's plan
from the same export as the census and pilots 1-3 (`S0_ROWS.jsonl` `2c99f96f...72a8`; sha256
`e99f3f7f45e5006d0201d93a3c32e470ae380b123b0ebfb07d1e47c25aee0330`, gitignored): **pilot 4 is its first
9 batches, `p4-0001` .. `p4-0009`** (8 x 15 + 12, in PILOT4.jsonl's order), 334 batches in all, the
same flags as pilot 3's plan. The plans and run directories of pilots 1-3 are untouched.

    mass4.py --plan PLAN4.pilot4.jsonl --run-dir runs/pilot4-2026-09-24 --log-dir logs/p4_pilot4 \
        --only p4-0001,..,p4-0009 --live --stages prepare,sources,routes,select --searches-off \
        --handoff-export output/remediation/handoff/p4-pilot4-select --jobs 3

2026-09-24 11:51:54-11:53:37 UTC, `STAGE_EXIT=0`, every batch "done" for its round. **The run's own
ledger** (`runs/pilot4-2026-09-24/LEDGER.jsonl`): 229 fetch lines (en.wikipedia.org 160,
www.wikidata.org 52, it.wikipedia.org 5, de/es/pt/fr.wikipedia.org 3 each), all HTTP 200, none given
up; 0 searches; 0 model calls. Every lane equals the census's.

| stage | result |
|---|---|
| S0 plan | 132 sites in 9 batches |
| S1 sources | pinned 96, scope-pending 3, no-title 20, rejected 13 |
| S1b routes | **lane W 79, S 17, 0 36**; 0 searches |
| S3 select, export | **90 questions** (lane W 79, lane S 11); per batch p4-0001 .. p4-0009: 12, 12, 12, 10, 8, 15, 14, 2, 5; prompts 3,795-30,692 characters, median 6,017; 23 carry a non-empty `also_named` |
| S3R restricted | no lane-R site: nothing asked |

Every exported prompt carries the selector question `a0b422e7...` (rules (7), (10) and (11) and the
card rule (4) as pilot 3's fixes wrote them). The 96 selecting sites minus 90 questions are 6 lane-S
sites whose article offers no sentence that names them; the import holds them `no-source` with no
call bought: Amyntas Rock Tombs, Priene Ruins, Hebbariyeh Roman Temple (gold), Templos de Tarxien
(identity trap) - the four of pilots 2 and 3 - and two of the eight new lane-S draws, Historic Site
Tipasa and Archaeological Park Carnuntum.

**The 36 holds** (`HOLDS4.jsonl`): the 17 of the fixed members are pilot 3's, reason for reason
(`scope-pending` 3, `search-stopped` 14); the 19 new are the T, R and B3 candidates, all
`search-stopped` (6 T: Necròpolis de Son Morell Nou, Conchalito, Villaggio Bizantino, Capela de São
Dinis, La strada Romana delle Gallie ed il suo arco, Remains of Roknia; 8 R: Tepeapulco Pyramid,
Öküzlü Ören Yeri, Pisarissos Antik Kenti, Jannusan Burial Mound Field, Granite Thrones of Judges of
Axum, Trebenna Antike Stadt, Baltalı Kapı, Ancient Theatre of Makyneia; 5 B3: Roma Dönemi Agora
Harabeleri, Selinunte Archaeological Park, "Cras -  Round Cairn to North of" (two spaces in the
stored name), Rocha da Mina, Tempio di Poseidone).

**Handoff directory** `output/remediation/handoff/p4-pilot4-select` (gitignored, 803 KB, stage
`finder`, labels `<site_id>/select`). `opus_handoff.py validate`: **90 questions, 0 answered, 90
missing, 0 stale, 0 malformed, 0 orphans** (exit 1 until they are answered). The run directory
`runs/pilot4-2026-09-24` (762 files, 5.5 MB, gitignored, its ledger inside) travels with it.
`PILOT_THRESHOLDS.md`, `PILOT.jsonl`, `PILOT2.jsonl` and `PILOT3.jsonl` are byte-identical; pilot 3's
run directory and its answered handoff directories (`p4-pilot3-select`, `-review`) and the census run
were only read (sha256 of every file, identical before and after).

**T7 for pilot 4** is pilot 3's (the same fixed members): El Tintal, Ahin Posh Tape (canaries), FC-2
(Font dels Coms) and TD-1 (Temple of Dedun) sit on sites held `search-stopped`, AM-1 (Amyntas Rock
Tombs) on a lane-S site the import holds `no-source` - closed-list reasons; the other 20 are asked,
Partiscum (CANARY-03) under the new rule (11) and the reviewer's PASSAGE.

### The orchestrator's next commands (from this worktree, main venv)

```bash
cd /c/PythonProjects/AncientMap/.claude/worktrees/p4-pilot && export PYTHONIOENCODING=utf-8
PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe; M=output/remediation; R4=$M/phase4_runner
P4=scripts/remediation/phase4; OH=scripts/remediation/opus_handoff.py; H=$M/handoff/p4-pilot4
RUN=$R4/runs/pilot4-2026-09-24; ONLY=p4-0001,p4-0002,p4-0003,p4-0004,p4-0005,p4-0006,p4-0007,p4-0008,p4-0009
ROUND="--plan $R4/PLAN4.pilot4.jsonl --run-dir $RUN --log-dir $M/logs/p4_pilot4 --only $ONLY --searches-off --live"
# every stage writes the run's own ledger, $RUN/LEDGER.jsonl; no command takes --ledger
# 1. answer the 90 selector questions: for each line of $H-select/*/MANIFEST.jsonl, an Opus agent reads
#    $H-select/<prompt_path>, follows the question's rules (1)-(11), writes only DESC:/CARD: lines (or
#    ABSTAIN:) to a file, and runs
$PY $OH answer --dir $H-select --batch-id <batch_id> --stage finder --label <site_id>/select \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $H-select                                   # exit 0: 90 answered
$PY $P4/mass4.py $ROUND --stages select --handoff-import $H-select  # S3 (+S3R: nothing to ask)
# 2. the translate round: lane T is empty, so the export writes no question and no directory -
#    skip `validate` when every batch reports 0 calls; the import still runs assemble and verify
$PY $P4/mass4.py $ROUND --stages translate --handoff-export $H-translate
$PY $P4/mass4.py $ROUND --stages translate,assemble,verify --handoff-import $H-translate
# 3. the review round (stage `reviewer`, labels <site_id>/review); every prompt now opens with the
#    PASSAGE, and the import drops a sentence that leans on a dropped one (review4.json `followed`)
$PY $P4/mass4.py $ROUND --stages review --handoff-export $H-review
$PY $OH answer --dir $H-review --batch-id <batch_id> --stage reviewer --label <site_id>/review \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $H-review
$PY $P4/mass4.py $ROUND --stages review --handoff-import $H-review  # the batches are then done
$PY $P4/run4.py holds --run-dir $RUN                               # HOLDS4.jsonl
# 4. the Claude Code audit of every sentence and card of pilot 4 (design S6b; T1-T7, T5 "broken"
#    included), against the pinned passages and gold_prose_errors.json - never the reviewer's verdicts
$PY -c "import sys; sys.path.insert(0, 'scripts/remediation'); from pathlib import Path; \
from phase4 import audit4; print('\n'.join(sorted(audit4.reviewed_sites(Path('$RUN')))))" > $M/logs/p4_pilot4/reviewed.txt
$PY $P4/audit4.py sheet --run-dir $RUN --site-ids $M/logs/p4_pilot4/reviewed.txt --out $M/logs/p4_pilot4/AUDIT_SHEETS.md
# 5. score T1-T13 against PILOT_THRESHOLDS.md (unchanged since pilot 1); keep $RUN/LEDGER.jsonl and
#    HOLDS4.jsonl with the audit verdicts (pilot4_evidence/), as pilots 1-3 did; only passing lanes open
# 6. P4 and P5 rehearsed against production (APPLY ending in ROLLBACK; nothing is written); the P4
#    plan reads $RUN/LEDGER.jsonl and no other
$PY $M/tools/write_gate4.py --group P4 --run pilot4-2026-09-24 --open-lanes W,S            # dry: plan + render
$PY $M/tools/write_gate4.py --group P4 --run pilot4-2026-09-24 --open-lanes W,S --rehearse
$PY $M/tools/write_gate4.py --group P5 --run pilot4-2026-09-24 --rehearse
```

### Tests, sweep, gates for pilot 3's fixes and pilot 4 (worktree `.claude/worktrees/p4-pilot`, main venv)

* 22 new test functions (101 new test items with the parametrizations), 20 of them red before their
  code; the other two check a claim about existing code or data (rule (7)'s "only when also_named
  lists X", the sealed draw's members): `test_phase4_verify.py` +7 (the 31 `PRONOUN_CASES` V6 judges
  exactly, and the review's reading alike; V6 past the first word, after a comma and after "that";
  V10's card; V14's sub-national names; rule (7)'s two forms read literally against `name_base` in
  both modules for 17 names, and its also_named clause), `test_phase4_review.py` +5 (the PASSAGE for
  lanes W and R; the followed drops, a kept predecessor, too few left), `test_phase4_select.py` +3
  (the reviewer's pronoun and contradiction lines, rule (11)),
  `tests/pipeline/test_country_subnational_names.py` +3 (new: the table pinned, each entry carries a
  country name and maps elsewhere, South Wales stays Wales), `test_phase4_model.py` +1 (the three
  word lists), `test_phase4_pilot.py` +3 (pilot 4's draw after three pilots, its seal, the sealed
  file). Rewritten: the pronoun rule (10), card rule (4), rule (7) and the reviewer's DROP-order pins
  in `test_phase4_select.py`, with the four re-pins and their reasons. New shared fixture
  `tests/remediation/p4_pronoun_cases.py`. Red first, measured: T1/T4 38 failures, T7 5, V14 a
  collection error and 1, T8 34, rule (7) 18, pilot 4's seed 1, its seal 1.
* `mutation_sweep.P4_PILOT4_MUTATIONS`: 37 cases (`p4 verify4` 8, `p4 prompts` 11, `p4 review` 5,
  `p4 sentences` 4, `p4 country_lookup` 3, `p4 model` 2, `p4 select` 1, `p4 pilot` 3), registered once;
  five older cases re-anchored on lines this rewrote (`p4 verify4: V10 a card may open with a
  pronoun`, `p4 prompts: the selector's card rule forbids a cultural adjective`, `... the selector is
  not told V6's pronoun rule`, `... rule (10) lets the first DESC sentence open with a pronoun`,
  `... the selector's first sentence need not name the site`); 2,064 labels, all unique, every anchor
  and test present. The sweep's own `main` (drivers `logs/p4_pilot4/sweep_targets.py` and
  `sweep_labels.py`): over **every case whose target is a file the five fixes changed** (verify4
  200, model4 83, sentences 65, prompts4 26, review4 18, country_lookup 11, mutation_sweep 3, and the
  new `p4 select` case) **407/407 caught**, the tree byte-identical for its 8 files (`sweep_fixes.log`);
  after the draw, over every case targeting `pilot4.py`, `AUDIT_LOG.md`, `mutation_sweep.py` or the
  contracts plus all 37 new cases **76/76 caught**, byte-identical for its 11 files
  (`sweep_final.log`); no `# mutant` left.
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`, `-p no:cacheprovider`,
  `-rs`): **6,194 passed, 111 skipped, 57 deselected, 0 failed** (325.6 s) on the final tree, the same
  111 skips (gitignored data) as before; after the five fixes alone, 6,191 passed.
* `ruff check` and `ruff format --check` clean on the 15 touched Python files (ruff 0.15.11); `ruff
  check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean; the Lyra import check (`country_lookup` is under
  `pipeline/`) passes.
* `phase3/mutation_sweep.py` changed again, so `mass_run.package_digest` over `phase3/` changes with
  this branch: merge it while no Phase-3 mass run is in flight.

### Open

* **T8 may fail again**, and not for a defect: pilot 3's 18 correct holds alone kept its coverage
  under 80 % (at most 60 of 78 with its three defects removed). Pilot 4 draws other sites; the
  thresholds are never loosened after the data is seen, so a shortfall goes to the owner as pilot 3's
  did.
* The pronoun rule's cost stays: 158 census pool sentences can never be published (their source
  predecessor is not in the pool), and an expletive *it* after a fronted phrase is held like a
  pronoun (9 of the 60 sampled); the reviewer and the audit see what it holds.
* V10 still holds a card that carries a sub-national name ("New South Wales"): conservative, not
  measured as a loss (no census card-length sentence's verdict changed).
* The B3 stratum is used up (20 routeless sites, all drawn by pilots 1-4): a fifth pilot would draw
  none.
* Pilot 4's 90 selector questions wait for their answers (runbook above); its ledger lives in its
  gitignored run directory - keep it with `HOLDS4.jsonl` and the audit verdicts in
  `pilot4_evidence/` when the result is recorded.

## 2026-09-24 - the Opus re-verification applied: quote check, decision rule, keep sample (no model called, nothing written)

Branch `integrate/wave1` (main checkout). The owner's order of 2026-09-23 - no DeepSeek any more,
everything with Opus - put the 934 production rows a DeepSeek finder and reviewer decided in front
of Opus judges, under rules sealed before the first verdict (`output/remediation/opus_audit/RULES.md`,
commit `02260ee`). The judging is done. This section applies the rules to it: the machine quote
check RULES.md demands, the decision rule, rule 4's keep sample, the list of rows to judge again and
the input of the reversal. Code: `scripts/remediation/opus_audit/` (`quotes.py` the check,
`decide.py` the rule, `run.py` the command line), tests `tests/remediation/test_opus_audit_quotes.py`
and `test_opus_audit_decide.py`. **Nothing was written to production, production was not read, and
no model was called.**

| file | sha256 |
|---|---|
| `output/remediation/opus_audit/RULES.md` (sealed in `02260ee`, unchanged) | `671ef6d68faea2cdda5046c110a3dc53dce63e8cd727b5fccc5637b985469f31` |
| `output/remediation/opus_audit/INPUT.jsonl` (sealed in `02260ee`, unchanged; 934 rows) | `099c9380f252e77ca6a086a6a0b532dbfb1175b4f62817b7c15a9dfc553a6c11` |
| `output/remediation/opus_audit/VERDICTS_RAW.json` (the judges' verdicts, committed with this section) | `98b88a54d5ccae5a219c88876e2338524bc90f3187333f4cc44015450fed9f57` |

`decide.py` pins the first two digests (`RULES_SHA256`, `INPUT_SHA256`) and refuses to run on other
bytes; `.gitattributes` now pins `opus_audit/*.json` to LF, so a checkout keeps VERDICTS_RAW.json's
digest.

### The verdicts

| pass | verdicts | keep | revert | wrong-both | undecidable |
|---|---|---|---|---|---|
| p1 (one judge per row) | 934 | 502 | 401 | 31 | 0 |
| p2 (independent, every pass-1 non-keep) | 432 | 64 | 337 | 30 | 1 |
| tie (every pass-2 keep) | 64 | 13 | 47 | 4 | - |

`decide.validate` holds the verdicts to the routes RULES.md gives: p1 covers exactly INPUT.jsonl, p2
exactly the pass-1 verdicts that are not keep, the tie exactly the pass-2 keeps; every verdict is
filed under its own change key, every wrong-both names its right value, no tie is undecidable. All
three hold. Where a keep or revert carries a `right_value` too, it is the written value (keep: 164)
or the old one (revert: 88), never a third value.

**`VERDICTS_partial_1.jsonl` is not a prefix of the raw pass 1.** The partial copy (commit `ac869cc`,
the 705 pass-1 verdicts written before the pause) was compared line by line with the raw file's p1:
one of its lines carries a cut change key, `phase3:71148c9835936`, which is the prefix of exactly one
INPUT key (`phase3:71148c98...6099670`, compared under that key); **only 15 of the 705 are identical**
(the first batch, `p1:1-15`), and 83 name another verdict (keep -> revert 33, revert -> keep 40,
keep -> wrong-both 5, wrong-both -> keep 2, wrong-both -> revert 2, revert -> wrong-both 1); the
reasons differ on 690, the quotes on 482. Pass 1 was judged again after the pause; the raw file
supersedes the partial, which stays as committed and is not read by anything here.

### Rule 4's keep sample, stated before any judge sees it

`output/remediation/opus_audit/KEEP_SAMPLE.json` (sha256
`96da2842e2f5423026a68898d5c2ce773a3576c72b8de20f0725493361bb1053`), written by
`run.py sample` (`decide.keep_sample`):

* **method**: `random.Random(20260923).sample(population, 60)`, where the population is the change
  keys of the pass-1 verdicts that are `keep` - all of them, before and regardless of the quote check -
  sorted ascending in Python's string order; the keys stand in the order `sample` returns them;
* **population**: 502 keys, sha256 of the keys joined with `\n`
  `bdb5eb41884c5ed18c1446c6069f056172e423ad2cb5b77fee25ff02451ebf7f`;
* **rule**: if more than 3 of the 60 (5 %) come back not `keep`, every pass-1 keep is judged a second
  time under rule 3.

The draw was checked independently of the module (the same call over the raw file gives the same 60
keys). `write_keep_sample` never writes a second, different sample over it. Nobody has judged the
sample yet; the orchestrator runs the Opus judges on it.

### The quote check (`quotes.py`, run 2026-09-24)

RULES.md: "A verdict whose quotes cannot be found verbatim (whitespace-normalised) in the cited
evidence file or fetched page does not count; the row is judged again." What the check normalises,
applied to the quote and the text alike, and nothing else: **Unicode NFC, then every maximal run of
characters for which Python's `str.isspace()` is true becomes one U+0020 space, then both ends are
stripped.** Case, punctuation, quotation marks, dashes, ellipses, ligatures and citation markers are
compared as they are. A verdict counts only when it has at least one quote and every quote is found.

Where a quote may be found:

* **an evidence file** - only one of the row's own `evidence_files` (RULES.md: "an evidence file path
  from the row"): the file as UTF-8 text, and, for the JSON API answers the finder was shown, each
  string it holds, decoded - to the cut of a file the fetch stage truncated at its byte cap (the
  largest evidence files end inside their last string);
* **a URL** - fetched once (`run.py fetch`, 2026-09-24 18:44-18:53 UTC, the project's User-Agent
  `AncientNerdsSiteAudit/1.0`, redirects followed, a 60 s bound, 1 s between two requests to one
  host), the raw bytes kept under `opus_audit/pages/<sha256 of the URL>.body` (48 MB, gitignored;
  `PAGES.jsonl` records every URL's status, final URL, Content-Type, size and body sha256). JSON (a
  MediaWiki `api.php` answer, a Wikidata entity) is compared as served and as its decoded strings;
  HTML as its visible text (tags removed, entities unescaped, `<script>`, `<style>`, `<template>`
  and `<title>` dropped, a block element's edges read as a line break, an inline element's as
  nothing); a PDF as the text `pdftotext -enc UTF-8` extracts (xpdf 4.00 here); other `text/*` as
  served. A text page is decoded by its header's charset, else its first `<meta>` charset, else UTF-8
  when the bytes are UTF-8 and windows-1252 when they are not (the HTML Standard's fallback: the
  Wayback copies of two mincetur.gob.pe sheets declare nothing and are Latin-1 - read as UTF-8 their
  accents were U+FFFD and two verbatim quotes failed, fixed test-first before the counts below). A
  URL written with `&amp;` for `&` is the same URL; none of the 362 cited URLs carried one.

**362 distinct URLs were cited; 361 were fetched once, 349 answered 2xx.** Not read: Historic England
list entries 1005789, 1005850, 1007297, 1008695, 1017899 (403 to this User-Agent), whc.unesco.org
list 560 (403), megalithic.co.uk sid 55192 (403), busquedas.elperuano.pe 2483726-1 (404),
agora.ascsa.net (connection reset), ejournals.eu and www.ejournals.eu (TLS: unable to get the local
issuer certificate), repositorio.unsaac.edu.pe (a PDF, read timeout) - and one never fetched:
`https://ancientnerds.com/api/sites/...`, the production API of the database under audit (never
touched here, and no evidence for itself). One page answered 200 but is not the article:
pmc.ncbi.nlm.nih.gov PMC6258758 served "Checking your browser before accessing
pmc.ncbi.nlm.nih.gov" - both judges of Península de Kola quote the article, so neither counts.

| pass | verdicts checked | counted | failed | not found | fetch failed | not fetched | not the row's evidence file |
|---|---|---|---|---|---|---|---|
| p1 | 934 | **927** | 7 | 2 | 4 | 1 | 0 |
| p2 | 432 | **421** | 11 | 1 | 9 | 0 | 1 |
| tie | 64 | **60** | 4 | 0 | 4 | 0 | 0 |

Of 2,727 quotes, 2,697 were found (2,181 as served, 509 in a page's visible text, 6 in a PDF's text,
1 only in a decoded JSON string), 24 sat on a page that could not be fetched, 2 on the page that
was not, 3 were not found and 1 cited another row's file. The failures, row by row (a verdict that
fails does not count; the row is judged again):

| row | column | route | failed | why |
|---|---|---|---|---|
| Padderbury Top | site_type | revert / revert | p1, p2 | Historic England 403 |
| Old Winchester Hill | period_start | revert / revert | p1, p2 | Historic England 403 |
| Paquime | period_start | revert / revert | p1, p2 | UNESCO 403 |
| Artashat | period_start | revert / revert | p1, p2 | ejournals.eu TLS failure |
| Península de Kola | site_type | wrong-both / wrong-both | p1, p2 | not found: the PMC page is a browser check |
| Ta' Ċieda Tower | site_type | revert / revert | p1 | cites the production API (not fetched) |
| Qhunqhu Wankani | site_type | revert / revert | p1 | not found: the judge wrote "Es considerado ..." where es.wikipedia reads "Además es considerado ..." |
| Hamble Common Camp | site_type | revert / revert | p2 | Historic England 403 |
| Muntham Court Romano-British Site | site_type | revert / revert | p2 | Historic England 403 |
| Qhapaq Kancha | site_type | revert / revert | p2 | unsaac.edu.pe PDF timeout |
| Tarmatambo | site_type | revert / revert | p2 | cites `batch-0052/evidence/60722e7e...%2Fenwiki.txt` - Stanydale Temple's evidence, "when Neolithic farmers first came to Shetland" - not a file of this row |
| Ferrybridge Henge | period_start | revert / keep / keep | p2, tie | Historic England 403 |
| Knockmaree Dolmen | period_start | revert / keep / revert | p2, tie | megalithic.co.uk 403 |
| Stoa Poikile | site_type | wrong-both / keep / wrong-both | tie | agora.ascsa.net reset |
| Inka Raqay, Ayacucho | site_type | revert / keep / keep | tie | elperuano.pe 404 |

No pass-1 keep failed its check. Six found quotes drawn at random were read in their page: each sits
in the page's own sentence. 36 found quotes are shorter than 20 characters ("Roman fort", "dolmen",
"Q35509") - verbatim, so they count, but they carry little.

### The decision (`decide.py`)

Applied to counting verdicts only. **keep 513, revert 406, rejudge 15** (`DECISIONS.jsonl`, one line
per INPUT row: the row, the decision, its basis - each route verdict with whether it counted -, the
passes to judge again, the route's own decision, the proposals, whether it goes to the reversal and
every quote's outcome; `COUNTS.json` the counts; `REJUDGE.json` the keys).

| decision | route | rows |
|---|---|---|
| keep | pass-1 keep (rule 4) | 502 |
| keep | pass 2 keep, third judge keep (rule 3) | 11 |
| revert | pass 1 and pass 2 not keep (rule 3) | 357 |
| revert | pass 2 keep, third judge revert or wrong-both (rule 3) | 49 |
| rejudge | a route verdict failed the quote check | 15 (route: revert 13, keep 2) |

**Revert by column:** site_type 218, period_start 182, country 6. **By superseded (rule 6):** 398 not
superseded, **8 superseded - judged, never reverted**: the five Northern-Ireland country rows (Annadorn
Dolmen, Dooey's Cairn, Giant's Ring, Craigs Dolmen, Moylehid: old "Ireland", written "United Kingdom",
today "Northern Ireland"; the deciding judges said wrong-both and proposed "Northern Ireland", the
value a later lane already wrote - for Craigs Dolmen pass 2 said keep and the third judge
wrong-both), and three site_type rows whose cell already holds the old value again
(Treasure of Osztrópataka, Witham Shield, Library of Ashurbanipal).

**Rule 5, the wrong-both proposals:** 33 reverted rows carry a wrong-both on their route - 30 with one
proposed value (6 of them superseded: the five "Northern Ireland" and Witham Shield's "Archaeological
site"), 3 where the two judges named different values and nothing is proposed (Nine Stones,
Winterbourne Abbas `period_start` -2000 / -2500; Altar of Athena Polias `site_type` Sanctuary /
Religious; Chanhudaro `period_start` -2500 / -3000). **No proposal is written by this lane**: they
go, as `proposed_value` in DECISIONS.jsonl, to a later correction lane that writes only with a
machine-verified verbatim quote.

**`REJUDGE.json`**: p1 7, p2 11, tie 4 verdicts over the 15 rows. Re-run p1 first (a new p1 keep
ends the route); a counted p2 stays valid when p1 is re-run (p2 never sees p1); a row that reaches the
tie again after a new p1 or p2 verdict needs a new tie, since the tie saw both reasonings.

### The reversal input (`REVERSAL_3_INPUT.jsonl`, 398 rows)

Every row decided revert and not superseded: site_type 215, period_start 182, country 1. **Nothing
is planned or written here.** The lane that writes it already exists: the mechanical journal-reversal
lane, `scripts/remediation/mechanical/reversal.py` (plan) and `apply.py --lane <lane>` (rehearsal,
apply, read-back), as used for `journal-reversal-1` and `-2`. What that lane reads, and what each line
here carries:

* **`REASONS.json`** in the lane's directory, `{"_about", "reversals": [{journal_id, site_id, name,
  column, reason, quotes: [{source, text}], residual}]}`, listing exactly the journal ids the lane
  registers in `mechanical/lane.py` (`REVERSAL_LISTS`, a `Lane` with its own run stamp, test id, key
  prefix, plan table and cells - site_type, period_start and period_name varchar/integer as for
  reversal 2, plus country for the one country row). Each line of REVERSAL_3_INPUT.jsonl is such an
  entry, with `old_value` (the value restored), `new_value` (the value the undone write wrote), the
  judges' verdicts and reasons, and `journal_id: null`.
* **The journal ids** are in neither INPUT.jsonl nor the local write logs: they are read from
  production, read-only, by `change_key`
  (`SELECT id, change_key FROM remediation_change_log WHERE change_key IN (...)`).
* **The quotes' sources.** `reversal.quote_problem` checks only `description`, `enwiki:<title>`,
  `wikidata:<QID>`, `gold_standard:<site_id>`, `journal` and `rereview:<change_key>`. The 1,193
  quotes of the 398 rows (each source and text once per row) cite evidence files (820) and URLs
  (373) - no kind the lane can check today. Lane 3 needs a source kind for them, e.g.
  `opus:<change_key>` read from `DECISIONS.jsonl` (decision revert, the same change key, site,
  column, old and new value), the way `rereview:` reads REREVIEW_1_FINAL.jsonl.
* **The period labels.** `keep_the_period_label` refuses a period_start reversal that leaves its
  `period_name` label behind. 39 of the 182 period_start rows restore a start in another bucket than
  the written one (`period_bucket.changes`); where the period-name lane of 2026-09-22 re-derived the
  label from the written start, that label's journal row has to join the list (reversal 2 carried 8
  such rows).
* Guard 5 (the named row is the cell's last write), the live-value guard and the curated-source
  guard are the lane's own and are read live at plan time; INPUT.jsonl's snapshot shows every one of
  the 398 cells still holding the written value.

### Next

1. **Judge the keep sample**: the 60 keys of `KEEP_SAMPLE.json`, each by an independent Opus judge
   that does not see pass 1. More than 3 not keep: every pass-1 keep is judged a second time (rule 4).
2. **Judge the 15 rows again** (`REJUDGE.json`, 22 verdicts, p1 first). The quotes must come from the
   row's own evidence files or a page that answers `run.py fetch` - Historic England, UNESCO,
   megalithic.co.uk and PMC do not answer this User-Agent. Then `run.py fetch` (new URLs only) and
   `run.py decide` over the verdicts file with the new verdicts in place (its new sha256 recorded here).
3. **Then the reversal**, through the journal-reversal lane as `journal-reversal-3`, from
   REVERSAL_3_INPUT.jsonl as it stands after steps 1 and 2 - with its own plan, rehearsal, read-back
   and rollback, and the owner's go before the write.

| output | sha256 |
|---|---|
| `DECISIONS.jsonl` (934 lines) | `9db7c7dd7515fe8cd31068417c4a7a99a866c3e445ad5b41470de7778799e859` |
| `COUNTS.json` | `5be6ecbce77de7e0e439b31ad58015e37b10b16422ca18e46a77cd81a0b37c8e` |
| `REJUDGE.json` | `0c55c5a17c01b43749a1c524abed9d6d5cea3885c90923183580e873c0bec21c` |
| `REVERSAL_3_INPUT.jsonl` (398 lines) | `e7c51dbd4dbb7f6e2bbcbdaee56c7589b14420b435f3110398c96c8cff2a6602` |
| `PAGES.jsonl` (362 lines) | `35c9f45e66bf60d146385fc506cb844e0b26727b8583177b5a66e11bea554e9f` |

`run.py decide` writes these byte-identically on a second run.

### Tests, sweep, gates (main checkout, branch `integrate/wave1`, main venv)

* 62 new test functions (77 cases with the parametrisations), each red before its code:
  `test_opus_audit_quotes.py` 33 (the normaliser, every reading, every failure outcome, the fetch
  once, the pace, the page index), `test_opus_audit_decide.py` 29 (every route, rejudge per failed
  pass, rules 5 and 6, the verdicts' shape, the rejudge list, the keep sample and its write-once, the
  reversal input, the counts, the seal, the whole run twice byte-identical). The run on the real
  verdicts found two things no test had pinned (the Wayback pages' charset, a quote two judges share
  listed twice in the reversal input); both were fixed test-first before the counts above.
* `phase3/mutation_sweep.OPUS_AUDIT_MUTATIONS`: 46 cases (quotes.py 26, decide.py 20), registered
  once; 2,019 labels, all unique, every anchor and test present. The sweep's own `main` over
  **`"opus audit:"` only: 46/46 caught**, the tree byte-identical to the sweep's start for its 2
  files, no `# mutant` left. `mutation_sweep.py` is imported by neither `opus_handoff.py` nor
  anything it imports (checked before the edit); it is in `phase3/`, so `mass_run.package_digest`
  changes with it - no Phase-3 mass run was in flight.
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`, `-p no:cacheprovider`):
  **5,960 passed, 6 skipped, 57 deselected, 0 failed** (409 s); the skips are two refactored-away
  article tests, the opt-in Shining Ones regen and three card_stats tests whose gitignored export
  this checkout does not hold.
* `ruff check` and `ruff format --check` clean on the 7 new or touched Python files (ruff 0.15.11);
  `ruff check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean.

### Round 2: the sample judged again, the failed verdicts judged anew (quote check, overlay, rule 4 fired)

Branch `integrate/wave1` (main checkout), code in commits `0b37911` (the overlay, rule 4, `pending`
and the two lists, test-first) and `b44e904` (the mutation cases); the data and this subsection are
committed together after them. Opus judges, run outside this checkout with the pass-1 judge prompt
plus a note to cite only sources that answer a plain fetch, judged **rule 4's 60 sample keys again,
independently** (never shown pass 1), and **the 18 failed p1 and p2 verdicts of `REJUDGE.json`
anew**. The four failed ties were left out: whether their rows still reach a tie depends on the new
p1 and p2. The verdicts: `output/remediation/opus_audit/VERDICTS_ROUND2.json`, `{"sample", "p1",
"p2"}`, sha256 `56471faf9cb40363f281383a39e6c9a6857ce5173a725cee3c6139b330b25ea8` (committed with
this subsection; LF only, so the checkout keeps the digest). **No model was called here, and
production was neither read nor written.**

| section | verdicts | keep | revert | wrong-both | undecidable |
|---|---|---|---|---|---|
| sample (the 60 keys of `KEEP_SAMPLE.json`) | 60 | 51 | 7 | 2 | 0 |
| p1 (`REJUDGE.json` p1) | 7 | 3 | 4 | 0 | 0 |
| p2 (`REJUDGE.json` p2) | 11 | 2 | 8 | 1 | 0 |

`decide.read_round_2` holds the file to round 1's shape: every verdict filed under its own key, a
verdict name of RULES.md, a wrong-both with its right value, quotes a list. It also holds the sample
to exactly the keys `KEEP_SAMPLE.json` states, and each p1 or p2 verdict to a round-1 verdict of its
pass. `decide.load_rounds` refuses a `KEEP_SAMPLE.json` that is not rule 4's draw from
`VERDICTS_RAW.json`. All of this holds. One sample verdict carries an extra, empty `reasoning_note`.
Nothing reads it.

#### Round 2's quote check

It is **exactly round 1's check**: `quotes.py` is unchanged (the same normaliser and readings, only
the row's own evidence files, a page fetched once). `run.py fetch` now collects the URLs that verdicts
of both rounds cite. That makes 386 URLs. The 362 of round 1 were left as kept, and their
`PAGES.jsonl` lines are unchanged. **24 URLs only round 2 cites were fetched once**, on 2026-09-24
from 20:48:30 to 20:48:46 UTC (5.2 MB), and **all 24 answered 200**:

* 11 JSON answers (10 MediaWiki `api.php`, 1 Wikidata entity);
* 3 MediaWiki `action=raw`;
* 8 HTML pages, 3 of them Wayback copies;
* 1 PDF (coflein.gov.uk);
* 1 `application/xml`.

| section | verdicts | counted | failed | quotes | found |
|---|---|---|---|---|---|
| sample | 60 | **60** | 0 | 111 | 111 |
| p1 | 7 | **7** | 0 | 14 | 14 |
| p2 | 11 | **10** | 1 | 24 | 22 |

The 147 found quotes break down as follows: 129 found as served, 13 in a page's visible text, 4 only
in a decoded JSON string and 1 in a PDF's text. **The one failure** is Península de Kola's p2
(`wrong-both`, proposing "Cemetery"). Two of its three quotes cite Europe PMC's full text of
PMC6258758 as `application/xml`
(`https://www.ebi.ac.uk/europepmc/webservices/rest/PMC6258758/fullTextXML`). The check has no reading
for that type, so both are "unreadable content". Its third quote is found in the row's evidence file.
Measured outside the check: **both quotes stand verbatim in that XML**, both as served and with its
tags removed. The check was not widened between rounds, so this verdict does not count. Whether an
XML reading is added is open (see "Next"). Either way the row stays `pending`: without this verdict
it waits on a second judgement, with it on a tie.

#### The overlay (`decide.overlay`)

* **p1**: all 7 round-2 verdicts count, and each replaces the failed round-1 p1 of its row.
* **p2**: 10 of the 11 count and replace. Kola's does not, so its failed round-1 p2 stays on the
  route, uncounted.
* **sample**: all 60 count. Each is its pass-1 keep's second, independent judgement under rule 3 and
  stands as the row's p2 (`from: VERDICTS_ROUND2.json sample`).
* **A counted verdict is never judged again.** A round-2 p1 or p2 over a counted round-1 verdict is
  refused, and so is one with no round-1 verdict of its pass. A round-2 verdict that fails replaces
  nothing.
* **The ties, and how "the pair is unchanged" is decided.** A round-1 tie counts only while the p1
  and the p2 verdicts on the row's route are, compared as JSON records, the very `VERDICTS_RAW.json`
  p1 and p2 of that row. Those are the two reasonings the third judge was shown. Once a later round
  replaces either one, the tie is set aside as stale, and if the new pair still disagrees it needs a
  new tie. A round-2 verdict is another judge's record (its reason and quotes differ), so any
  replacement changes the pair. **62 of the 64 round-1 ties stand.** That covers the 60 counted ties
  whose pair nothing touched, plus the failed ties of Stoa Poikile and Inka Raqay, Ayacucho: there
  only the tie had failed, so the pair is unchanged and the row waits on a new tie. **2 ties are set
  aside as stale**: Ferrybridge Henge and Knockmaree Dolmen. Each tie had been shown a p2 `keep`, and
  that p2 is now `revert`, so the pair agrees and needs no tie.

Every `DECISIONS.jsonl` line now names, for each route verdict, the file and section it came from
(`basis[].from`). It also lists the verdicts set aside and why (`set_aside`). The 15 rows of round 1's
`REJUDGE.json`:

| row | column | route now (r1 = VERDICTS_RAW, r2 = VERDICTS_ROUND2) | decision |
|---|---|---|---|
| Padderbury Top | site_type | p1 keep (r2), p2 keep (r2) | keep |
| Artashat | period_start | p1 keep (r2), p2 keep (r2) | keep |
| Paquime | period_start | revert (r2) / revert (r2) | revert |
| Old Winchester Hill | period_start | revert (r2) / revert (r2) | revert |
| Qhunqhu Wankani | site_type | revert (r2) / revert (r1) | revert |
| Ta' Ċieda Tower | site_type | revert (r2) / revert (r1) | revert |
| Hamble Common Camp | site_type | revert (r1) / revert (r2) | revert |
| Muntham Court Romano-British Site | site_type | revert (r1) / revert (r2) | revert |
| Qhapaq Kancha | site_type | revert (r1) / revert (r2) | revert |
| Tarmatambo | site_type | revert (r1) / revert (r2) | revert |
| Ferrybridge Henge | period_start | revert (r1) / revert (r2); r1 tie stale | revert |
| Knockmaree Dolmen | period_start | revert (r1) / revert (r2); r1 tie stale | revert |
| Península de Kola | site_type | keep (r2) / wrong-both (r1, failed; r2 failed too) | pending: second judgement |
| Stoa Poikile | site_type | wrong-both / keep / tie failed, pair unchanged | pending: tie |
| Inka Raqay, Ayacucho | site_type | revert / keep / tie failed, pair unchanged | pending: tie |

#### Rule 4 fired

All 60 sample verdicts count: 51 `keep`, 7 `revert`, 2 `wrong-both` (both propose -500). **9 of the
60 are not keep. The threshold is "more than 3 of the 60 (5 %)", so rule 4 fires**: every pass-1
keep is judged a second time under rule 3. `decide.rule_4` counts only counted sample verdicts. Had
failed ones been able to tip the count, the run would have refused until they were judged again.
After the overlay, the pass-1 keeps are the 502 of round 1 plus the three new p1 keeps (Padderbury
Top, Artashat, Península de Kola). Their round-2 p2 never saw pass 1, so it is their second judgement
wherever it counts. Under rule 3, a second `keep` keeps the row, and any other verdict calls the third
judge. The 9 sample rows not kept:

| row | column | old -> written | sample verdict |
|---|---|---|---|
| Marayniyoq | site_type | City/town/settlement -> Archaeological site | revert |
| Roborough Castle | site_type | Earthwork -> Fortress/citadel | revert |
| Inka Raqay | site_type | City/town/settlement -> Archaeological site | revert |
| Dolni Glavanak Cromlech | period_start | -1500 -> -800 | revert |
| Wanakawri, Huánuco | site_type | City/town/settlement -> Archaeological site | revert |
| Huilai Monument Archaeology Park | site_type | City/town/settlement -> Archaeological site | revert |
| Maiden Castle, Cheshire | period_start | -1500 -> -600 | revert |
| Aquae Calidae, Bulgaria | period_start | 1 -> -6000 | wrong-both, -500 |
| Holyhead Mountain Hut Circles | period_start | -2000 -> -1000 | wrong-both, -500 |

#### The two lists

* **`SECOND_JUDGE.json`: 443 keys.** These are the pass-1 keeps without a counted second judgement:
  the 442 round-1 keeps outside the sample, plus Península de Kola (its p2 failed in both rounds).
  The file carries rule 4's numbers (sample 60, counted 60, not keep 9, threshold 3, fired).
* **`TIE_ROUND2.json`: 11 rows**, each `{change_key, judge_1, judge_2}`: judge_1 is the p1 and
  judge_2 the p2 on the route, each with verdict, right_value, reason and quotes. That is the shape
  the third judge needs, with the evidence read from the row in INPUT.jsonl. The 11 are the 9 sample
  splits above (p1 keep, second judgement not keep), plus Stoa Poikile (wrong-both / keep) and Inka
  Raqay, Ayacucho (revert / keep). The file states the pair rule.

#### The decision now (`run.py decide`, both rounds)

**keep 64, revert 416, rejudge 0, pending 454** (443 wait on a second judgement, 11 on a tie).
`pending` is new: a row whose route lacks a counted verdict it waits for. The two cases are rule 4's
second judgement of a pass-1 keep, and a third judge for a pair that disagrees, whether that verdict
was never given or was given and failed. `rejudge` now means only a failed pass 1, or a failed pass 2
of a pass-1 verdict that is not keep (`REJUDGE.json`, now empty: `{"p1": [], "p2": []}`). A row waits
for the first verdict its route lacks, never a later one. So Ferrybridge-like rows (pass 2 and tie
both failed) re-judge pass 2 first.

| decision | route | rows |
|---|---|---|
| keep | p1 keep, second judgement keep (rule 4 under rule 3) | 53 (51 sample, Padderbury Top, Artashat) |
| keep | p1 not keep, p2 keep, third judge keep | 11 |
| revert | p1 and p2 not keep | 367 |
| revert | p2 keep, third judge revert or wrong-both | 49 |
| pending | a pass-1 keep waiting on its second judgement | 443 |
| pending | a pair that disagrees, waiting on a third judge | 11 |

The move from round 1's decisions:

* keep -> keep 62 (the 51 sample keeps and the 11 tie keeps);
* keep -> pending 451 (442 unsampled, 9 sample splits);
* revert -> revert 406 (unchanged);
* rejudge -> revert 10, rejudge -> keep 2, rejudge -> pending 3.

**A "keep" is final for 64 rows only.** The other 443 pass-1 keeps are undecided until judged a second
time.

* **Revert by column:** site_type 224, period_start 186, country 6.
* **By superseded (rule 6):** 408 not superseded. 8 superseded, the same eight as in round 1: none of
  the 10 new reverts is superseded.
* **Rule 5:** 30 reverted rows carry one proposed value and 3 carry two different values, unchanged
  from round 1. Nothing is written.

#### `REVERSAL_3_INPUT.jsonl` (408 rows)

These are regenerated from final reverts only: a line is written only for `decision == "revert"` and
not superseded, so `pending` and `rejudge` rows can never reach it (tested, and guarded by mutation
cases). **The 398 lines of round 1 are unchanged** (compared as JSON records), and 10 are new:

| row | column | restored (written -> old) |
|---|---|---|
| Hamble Common Camp | site_type | Settlement -> Fortress/citadel |
| Muntham Court Romano-British Site | site_type | Archaeological site -> City/town/settlement |
| Tarmatambo | site_type | Archaeological site -> City/town/settlement |
| Qhapaq Kancha | site_type | Archaeological site -> City/town/settlement |
| Qhunqhu Wankani | site_type | Archaeological site -> City/town/settlement |
| Ta' Ċieda Tower | site_type | Fortification -> Minaret/tower |
| Paquime | period_start | 1130 -> 1000 |
| Ferrybridge Henge | period_start | -3000 -> -4500 (bucket changes) |
| Old Winchester Hill | period_start | -600 -> -3000 (bucket changes) |
| Knockmaree Dolmen | period_start | -3000 -> -4500 (bucket changes) |

By column: site_type 221, period_start 186, country 1. 42 period_start rows restore a start in
another bucket (round 1's 39 plus the three above). **This input is not final.** Of the 454 pending
rows, those that end in `revert` join it once their second judgements and ties are decided.

#### Next

1. **Judge `SECOND_JUDGE.json`'s 443 keys.** Each gets an independent Opus judge that is not shown
   pass 1 (the pass-1 prompt), and the verdicts go into a round-3 file as p2.
2. **Judge `TIE_ROUND2.json`'s 11 rows** with the third judge, which sees the evidence and both
   judgements and answers keep, revert or wrong-both.
3. Among the 443, every second judgement that is not keep splits its pair and needs a tie as well.
4. **Open: the XML reading.** Europe PMC answers `application/xml`, and both of Kola's quotes stand
   in it verbatim. Adding the reading would be a change to the check, stated here and test-first, as
   the Latin-1 fix was in round 1.
5. `decide.py` reads rounds 1 and 2. A round-3 file (p2 for the SECOND_JUDGE keys, ties for the
   current pairs) needs its own overlay step, test-first: a counted verdict is never judged again,
   and a tie counts only for the pair it was shown.
6. Then the reversal, through the journal-reversal lane as `journal-reversal-3`. It gets its own
   plan, rehearsal, read-back and rollback, and the owner's go before the write.

| output | sha256 |
|---|---|
| `DECISIONS.jsonl` (934 lines) | `022da98563914992e32abd606e22bfaf823f703a8a556403fe92163657b3bb00` |
| `COUNTS.json` | `a8dcb32975ee1ec29309863ba1e59c2a21ed41af078df944c6649e60d3c967db` |
| `REJUDGE.json` | `9bc2e5bda9a5e75f569b247d893e30a15a33960df2a0c93f09ad551f1e93b649` |
| `REVERSAL_3_INPUT.jsonl` (408 lines) | `9344be9c8c3da21d68a03d765a06a15925cb72614f07c54de4cd7d0f25ac5037` |
| `SECOND_JUDGE.json` (443 keys) | `f2ca9b2b99332a42ea41f3e93a6c0f39303058b3b5040dfeb2ef571bd9ef04c2` |
| `TIE_ROUND2.json` (11 rows) | `4196b2a6bd6d7b5fd205508f7264196110f1e208565e5c98b881df75e2caf974` |
| `PAGES.jsonl` (386 lines) | `7d0c7d0050726f37d98c8c93acb58026600aefc3d708d27c36006d3ecd5626e6` |

`run.py decide` writes these byte-identically on a second run (checked). Inputs, as `COUNTS.json`
records them: RULES.md and INPUT.jsonl the sealed digests, VERDICTS_RAW.json `98b88a54...`,
KEEP_SAMPLE.json `96da2842...`, VERDICTS_ROUND2.json `56471faf...`.

#### Tests, sweep, gates (main checkout, branch `integrate/wave1`, main venv)

* `test_opus_audit_decide.py`: 28 new test functions, each red before its code. They cover the route
  once rule 4 fires, rejudge against pending, rule 4 and its refusal, the overlay (replace, fail,
  refuse, sample as p2, stale ties by p1 and by p2), the trace, the round-2 file and the stated
  sample, both lists, no pending row in the reversal, and the fetch of round 2's URLs. The round-1
  whole-run test became a round-2 whole-run test (62 keeps, the draw, the overlay, all six outputs
  written twice byte-identically). Three round-1 tests follow the new meaning: a failed tie waits as
  `pending`, `REJUDGE.json` lists p1 and p2 only, and the counts are split into `verdict_counts` and
  `decision_counts`. 75 cases in the file.
* `phase3/mutation_sweep.OPUS_ROUND2_MUTATIONS`: 31 cases in a block of their own after the round-1
  block (decide.py 30, run.py 1). Four round-1 anchors follow the reshaped `decide_row` and
  `_verdict_shape`. That makes 2,050 labels, all unique, and `test_every_mutation_names_an_anchor_and_a_test_that_exist`
  passes. **`mutation_sweep.py "opus audit:" "opus round 2:"`: 77/77 caught** (46 + 31), each at
  its intended assertion. The tree is byte-identical to the sweep's start for its 3 files, and no
  `# mutant` is left.
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`, `-p no:cacheprovider`):
  **5,991 passed, 6 skipped, 57 deselected, 0 failed** (249 s). The skips are the same six as in
  round 1.
* `ruff check` and `ruff format --check` are clean on the 4 touched Python files (ruff 0.15.11).
  `ruff check api/ pipeline/` is clean, `lint-imports` shows 2 kept and 0 broken, and `vulture api/
  pipeline/ .vulture_whitelist.py --min-confidence 80` is clean.

### Round 3: the 443 second judgements and the 11 ties (one code path for every round)

Branch `integrate/wave1` (main checkout), code in commits `62ff379` (every round through one
overlay, test-first) and `e1c7c2a` (the mutation cases); the data and this subsection are committed
after them. Opus judges, run outside this checkout, judged **the 443 keys of `SECOND_JUDGE.json`**
independently with the pass-1 prompt (never shown pass 1) and **the 11 rows of `TIE_ROUND2.json`**
as the third judge (the evidence and both embedded judgements). The verdicts:
`output/remediation/opus_audit/VERDICTS_ROUND3.json`, `{"second", "tie"}`, sha256
`2c56ba19fbc18137bad2c4e88ea773197533823d88af7b308f23c4c93cd4b2f4` (LF only). **No model was called
here, and production was neither read nor written for this subsection.**

| section | verdicts | keep | revert | wrong-both | undecidable |
|---|---|---|---|---|---|
| second (the 443 keys of `SECOND_JUDGE.json`) | 443 | 409 | 29 | 5 | 0 |
| tie (the 11 rows of `TIE_ROUND2.json`) | 11 | 0 | 8 | 3 | - |

#### One code path for every round (`decide.round_files`, `read_round`, `overlay`)

Round 2 had its own reader and overlay. Now every round file after round 1 is read in number order
(`VERDICTS_ROUND2.json`, `VERDICTS_ROUND3.json`, ...; a gap, or a file named otherwise, is refused)
and laid over round 1 by one overlay. A round was judged from the lists the run before it wrote, so
each of its verdicts is laid on the routes **as they stood before the round**, and is refused unless
its row waited on exactly that verdict (`_waits_on`; a counted verdict is never judged again). What a
counted verdict of each section does:

* `p1`, `p2`: replaces the failed verdict of its pass (round 2's rule, unchanged);
* `sample`: rule 4's stated sample, judged in one round only, stands as the keep's p2; rule 4 is
  decided on it at the end of its round;
* `second`: rule 4's second judgement of a pass-1 keep without a counted one, accepted only once rule
  4 fired in an earlier round; it stands as the keep's p2 under rule 3;
* `tie`: accepted only for a pair that disagrees and counts and has no counted tie (for a pass-1
  keep only once rule 4 fired). It decides the row only while the p1 and p2 on its route are the
  very pair it was shown: a round-1 tie the `VERDICTS_RAW.json` pair, a later round's tie the pair
  on the route before its round (the pair the round before's `TIE_ROUND<n>.json` listed). A tie
  whose pair a later round replaced is set aside as stale (`PAIR_RULE`, generalised).

The run writes the next lists under the number of the last round laid: **`TIE_ROUND3.json`** (the
tie judge's shape, `{change_key, judge_1, judge_2}`) and **`REJUDGE_ROUND3.json`** (the round's
verdicts that failed the quote check, by section). `TIE_ROUND2.json` is round 3's input and is left
as committed. A failed verdict replaces nothing; the round-1 set-aside note for a replaced verdict
now reads "a counted verdict of a later round replaces it" (12 `DECISIONS.jsonl` lines of already
final rows differ from round 2's in that wording only - checked).

#### Round 3's quote check

Exactly round 1's check: `quotes.py` is unchanged. `run.py fetch` collects the URLs every round
cites (441). The 386 of rounds 1 and 2 were left as kept, their `PAGES.jsonl` lines unchanged. **55
URLs only round 3 cites were fetched once**, 2026-09-25 01:29:01-01:29:48 UTC (9.8 MB): 54 answered
200 (31 JSON answers, 20 HTML pages, 2 MediaWiki `action=raw`, 2 PDFs), 1 answered 403
(earthdoc.org).

| section | verdicts | counted | failed | quotes | found |
|---|---|---|---|---|---|
| second | 443 | **441** | 2 | 761 | 759 |
| tie | 11 | **11** | 0 | 34 | 34 |

Of the 793 found quotes, 791 are on the routes: 719 found as served, 44 in a page's visible text,
20 only in a decoded JSON string, 8 in a PDF's text. **The two failures, both second judgements
`keep`:**

* **El Caño Archaeological Park** (`period_start` 500 -> -100): its second quote cites
  earthdoc.org's paper 10.3997/2214-4609.20141971, which answers 403 to this User-Agent (the first
  quote, from the row's enwiki evidence, is found);
* **Killarumiyuq** (`site_type` City/town/settlement -> Archaeological site): its second quote,
  "archaeological site in Serbia", is not in the row's `wikidata_entity.txt` (a Peruvian site; the
  line is not in either of the row's evidence files).

Both rows stay `pending` on their second judgement: `SECOND_JUDGE.json` lists exactly these 2 keys,
and `REJUDGE_ROUND3.json` names them under `second` (`tie`: none).

#### The overlay of round 3

* **second**: 441 counted verdicts laid as their keeps' p2. One replaced a failed verdict: Península
  de Kola's round-1 p2 (the round-2 p2 had failed too and replaced nothing). Kola's second judgement
  is `wrong-both` ("Archaeological site"), so its pair now waits on a tie.
* **tie**: all 11 laid; each was shown the pair on its route before round 3, and that pair is its
  route's. Two replaced the failed round-1 ties of Stoa Poikile and Inka Raqay, Ayacucho, whose pairs
  had stood unchanged.
* No tie went stale. Every round-3 verdict was accepted by `_waits_on`: each second judgement's row
  was a pass-1 keep without a counted p2, each tie's pair disagreed and counted.

The 11 third judges, all not keep, so all 11 rows revert:

| row | column | old -> written | p1 / p2 | tie |
|---|---|---|---|---|
| Inka Raqay | site_type | City/town/settlement -> Archaeological site | keep / revert | revert |
| Dolni Glavanak Cromlech | period_start | -1500 -> -800 | keep / revert | revert |
| Roborough Castle | site_type | Earthwork -> Fortress/citadel | keep / revert | revert |
| Stoa Poikile | site_type | Megalithic stones -> Infrastructure | wrong-both / keep | wrong-both, Monument |
| Aquae Calidae, Bulgaria | period_start | 1 -> -6000 | keep / wrong-both | wrong-both, -500 |
| Holyhead Mountain Hut Circles | period_start | -2000 -> -1000 | keep / wrong-both | wrong-both, -500 |
| Maiden Castle, Cheshire | period_start | -1500 -> -600 | keep / revert | revert |
| Inka Raqay, Ayacucho | site_type | City/town/settlement -> Archaeological site | revert / keep | revert |
| Huilai Monument Archaeology Park | site_type | City/town/settlement -> Archaeological site | keep / revert | revert |
| Wanakawri, Huánuco | site_type | City/town/settlement -> Archaeological site | keep / revert | revert |
| Marayniyoq | site_type | City/town/settlement -> Archaeological site | keep / revert | revert |

#### The decision now (`run.py decide`, rounds 1-3)

**keep 471, revert 427, rejudge 0, pending 36** (2 wait on a second judgement, 34 on a tie).

| decision | route | rows |
|---|---|---|
| keep | p1 keep, second judgement keep | 460 (51 sample, Padderbury Top, Artashat, 407 of round 3) |
| keep | p1 not keep, p2 keep, third judge keep | 11 |
| revert | p1 and p2 not keep | 367 |
| revert | p1 not keep, p2 keep, third judge not keep | 51 |
| revert | p1 keep, second judgement not keep, third judge not keep | 9 |
| pending | a pass-1 keep whose second judgement failed the quote check | 2 |
| pending | a pair that disagrees, waiting on a third judge | 34 |

The move from round 2's decisions: keep -> keep 64; pending (second) -> keep 407; pending (second)
-> pending (tie) 34; pending (second) -> pending (second) 2; pending (tie) -> revert 11; revert ->
revert 416. No row decided in round 2 changed its decision.

* **Revert by column:** site_type 231, period_start 190, country 6. **Superseded (rule 6):** 8, the
  same eight as in rounds 1 and 2; none of the 11 new reverts is superseded.
* **Rule 5:** 33 reverted rows carry one proposed value (30 + Stoa Poikile "Monument", Aquae Calidae
  -500, Holyhead Mountain Hut Circles -500), 3 carry two different values. Nothing is written.

#### `TIE_ROUND3.json` (34 rows)

The rows whose p1 keep and counted second judgement disagree and that lack a counted tie: the 29
second judgements `revert` and the 5 `wrong-both` (Pampas Gramalote -1500, South Stoa I, Athens
"Ruin", Maa Palaeokastro -3800, Sidi Said "Fort", Península de Kola "Archaeological site"); by
column site_type 18, period_start 16. judge_1 is the p1 `keep`, judge_2 the round-3 second
judgement, each with verdict, right_value, reason and quotes. The file states the generalised pair
rule.

#### `REVERSAL_3_INPUT.jsonl` (419 rows)

Final reverts only, not superseded; `pending` never reaches it. **The 408 lines of round 2 are
unchanged** (compared as JSON records), and the 11 rows the round-3 ties reverted are new: site_type
7 (Inka Raqay, Roborough Castle, Stoa Poikile, Inka Raqay Ayacucho, Huilai Monument Archaeology
Park, Wanakawri Huánuco, Marayniyoq), period_start 4 (Dolni Glavanak Cromlech and Maiden Castle,
Cheshire in the same bucket; Aquae Calidae, Bulgaria -6000 -> 1 and Holyhead Mountain Hut Circles
-1000 -> -2000 in another). By column: site_type 228, period_start 190, country 1; **44 period_start
rows restore a start in another bucket** (round 2's 42 plus those two). This input is still not
final: the 34 ties and the 2 second judgements decide the rest.

#### Next

1. **Judge `TIE_ROUND3.json`'s 34 rows** with the third judge, and **the 2 keys of
   `SECOND_JUDGE.json`** with an independent judge (quotes only from the row's own evidence files or
   pages that answer `run.py fetch`); a second judgement that is not keep calls a third judge in the
   round after. They go into `VERDICTS_ROUND4.json` as `tie` and `second`, then `run.py fetch` and
   `run.py decide` - the same code path, which writes `TIE_ROUND4.json` and `REJUDGE_ROUND4.json`.
2. **Open, unchanged: the XML reading** (Europe PMC's `application/xml`). Kola's round-3 second
   judgement counted without it.
3. Then the reversal, `journal-reversal-3` (the next section): regenerate its list from the final
   `REVERSAL_3_INPUT.jsonl` and run the command sequence given there, with the owner's go before the
   write.

| output | sha256 |
|---|---|
| `DECISIONS.jsonl` (934 lines) | `d48f5f7303336deea97721866aeb39c269c8c3b89a5c4faacd30172d6c3355d4` |
| `COUNTS.json` | `4395096a32161b3f7abb29f924c5d21cd8e14516c45074a78ecc7169defc7155` |
| `REJUDGE.json` (p1 0, p2 0) | `40b6cfa76a18e050575aa2122805c50d854917ce5a22e0032ceee1ca9fa76b07` |
| `REVERSAL_3_INPUT.jsonl` (419 lines) | `98d4cfabfd0965f0352ee7f14d3eaece02797fe201939a02156c66f16fb50a4e` |
| `SECOND_JUDGE.json` (2 keys) | `b2022334e4e44c6d11a8e47f76bda13f572bf93837cdd898b827214eaaefec28` |
| `TIE_ROUND3.json` (34 rows) | `8807be866dcc6a6954c2edaefbb14ec0342375e7a5f137b7e093e7acd15dad7a` |
| `REJUDGE_ROUND3.json` (second 2, tie 0) | `0fdaff608cc0014142af08dbc021ac2fde36533eaf53a554f136d6d60d62bf68` |
| `PAGES.jsonl` (441 lines) | `092196b3c30d46124491c480e727dc89ce27f6e4a140f17381928531959295d7` |

`run.py decide` writes these byte-identically on a second run (checked). Inputs, as `COUNTS.json`
records them: RULES.md and INPUT.jsonl the sealed digests, VERDICTS_RAW.json `98b88a54...`,
KEEP_SAMPLE.json `96da2842...`, VERDICTS_ROUND2.json `56471faf...`, VERDICTS_ROUND3.json `2c56ba19...`.
The tests, sweeps and gates of this round are recorded with journal-reversal-3's, at the end of the
next section.

## 2026-09-24 - The owner's defect scope: Phases 4/5 write only proven text defects (nothing written)

**Decision** (Martin, 2026-09-23, answer "Nur Defekt-Sites (Recommended)"): after a passing Phase-4
pilot, Phases 4/5 write only the sites with proven text defects - the Phase-3 cleared defects plus
the 904 ungrounded card texts, in the design's order; every other site's description and card stay
exactly as they are. Pilot 4 passed T1-T7 (`PILOT_RESULT_4.md`); its P4 plan then planned 128 rows for
all 64 write-eligible pilot sites, 44 of them without any defect flag, and nothing in the code knew
the decision. Contracts: `docs/procedures/PHASE4_CONTRACTS.md` section 9.

### The 904: no list existed, so it was recomputed

Searched for a list of the 904 site ids: `output/remediation` of the main checkout and of this
worktree (every `.md`, `.json`, `.jsonl`, `.py`, `.txt`, `.log` outside the HTTP cache), the census
runs (`run_t01` .. `run_t11`, `CENSUS.md`: no test measures card grounding), `AUDIT_LOG.md`,
`HANDOVER.md`, `HUMAN_ONLY.md`. Only the plan (section 5.1, O3) and the design log name the number;
no file lists the sites. **Recomputed with the documented method** (plan section 5.1: every number in
the card checked against the generator's input, `LEFT(description, 500)` of snapshot d4526691,
`scripts/export_card_sites.py:36`) from the S0 export `S0_ROWS.jsonl`
(`2c99f96f...72a8`, the census's and every pilot's), whose `card` and `description` are
byte-identical to the census snapshot of 2026-09-20 for all 5,004 sites (checked) and whose
`snapshot_description` is d4526691's text (`snapshot_rows`). `phase4/scope4.py` states the reading:
a number is a numeral as written - ASCII digits, comma thousands separators, a decimal part - read
as its value (`10,000` = `10000`, `7.10` = `7.1`); it appeared when the same value is a numeral of the
input's first 500 characters, never a digit run inside a longer numeral (`50` is not in `500`).

**876 ungrounded cards** (the documented cohort: 904). The plan's three named examples are among
them (House of Taga `10,000 BC`, Hatunmarka, Maray Qalla). One more card writes numbers but its site
is not in d4526691 (Temple of Baalshamin 95b33efa, created after it): its generator input is unknown,
so it is **not claimed** and the file lists it under `unclaimed`. The 2026-09-19 matcher was not
kept, so 904 is not reproducible to the site: 40 readings measured on the same data give 788-897
(counting Baalshamin, as the plan's table did - it places every carded site; this reading gives 877
so). Digit runs matched as substrings give 788-793 and miss House of Taga, because `10` hides in
`10th` and `000` in `1,200`. None reproduces the plan's other cohorts (1,225 / 1,925 / 943; cards
without a digit are 942 here): the 2026-09-19 measurement read something this export does not
reproduce - another number reading, or a card state before the census snapshot.

### The scope (`output/remediation/phase4_runner/SCOPE4.json`, v1)

sha256 `19a57e9fd17f53601fecdd5424d3ea3e085c2690e8250cb72b004f010f833d6a`, pinned in
`scope4.SCOPE_SHA256`; built by `plan4.py scope` from `S0_ROWS.jsonl` (`2c99f96f...`) and
`logs/_write_dry/ALL_REFUSED.jsonl` (`7b4026d0...`), byte for byte again on every build (a test
rebuilds it). Every site id with the lists it came from, the inputs' digests, each list's method and
the site list's own digest (`sites_sha256`).

| list | source | sites |
|---|---|---|
| `phase3-cleared-description` | `ALL_REFUSED.jsonl`, rule `report-only-field`, field `description` | 322 |
| `phase3-cleared-card` | the same, field `card_description` | 709 |
| `ungrounded-card` | plan section 5.1, recomputed (above) | 876 |
| **the scope** | the union | **1,623** |

Overlaps: description and card 85, description and ungrounded 69, card and ungrounded 157, all three
27; the cleared defects are 946 sites (the design's number), 677 sites are in the scope for an
ungrounded card alone. By combination: ungrounded only 677, card only 494, description only 195,
card and ungrounded 130, description and card 58, description and ungrounded 42, all three 27. 37
scope sites are `scope-pending` (S1 holds them before any model question).

**Which flags count.** `cleared-description-defect`, `cleared-card-defect` and the ungrounded cards.
Not `t03` (its own comment: order only; counted, it would add 555 sites) and not `t03-severe` on its
own (it would add 101 of its 185 sites; 84 are in the scope already): T03 says the text's years and
the period bucket disagree, not which is wrong - the census counts 0 of its findings applicable
(proposals for human review), plan section 4.3 lists severe T03 patterns 7 and 8 as false alarms, V14
holds a severe finding "for reading" for that reason, and on the 185 sites Phase 3's reviewer cleared
the description defect of 18 (in the scope), refuted it on 16, left 2 unresolved and was not asked on
149 (no usable finding). V9's floor waiver needs less than the owner's "proven" - it lets a shorter
text replace one that may be wrong - so `t03-severe` keeps that job, and the order, inside the scope.

### The rule

`write4.RULE_OUT_OF_SCOPE = "outside-defect-scope"`, the writer's new refusal (contracts section 9;
not a `model4.HoldReason`: no stage holds a site for the scope, the mass run's plan never carries
one). `plan_p4`, `plan_legacy` and `plan_cards` take `scope` as a required keyword and ask it before
every other rule - an out-of-scope site is counted under it whatever else holds it, and nothing of it
is verified or read. `write_gate4` loads the pinned file for P4, L and P5 alike (a file that is not
the pin: `WRITE_EXIT=1`), prints it, and counts the refusals on its "refused by rule" line; it has no
flag to switch the rule off.

* **L is scoped too.** L marks only a scope site Phase 4 held; an out-of-scope site gets no legacy
  provenance and no HUMAN_ONLY line. The owner said the other sites stay as they are, and the design
  sized L for the few hundred sites Phase 4 would hold ("about 300-600 L rows"), not for every site
  outside the scope. What that leaves open is recorded, not decided: an out-of-scope site whose text
  the March chain changed keeps it **without** the legacy AI marking the design meant for every held
  site ("so no LLM-processed text stays unmarked"); whether those sites get it is the owner's
  question (HUMAN_ONLY), not a write this gate makes.
* **P5**: no card and no clear outside the scope; a held card that is only ungrounded keeps its text
  (the design clears the 709 alone).
* **V9 inside the scope**: its floor stays waived only for description defects and `t03-severe`. A
  site in the scope for its card alone keeps the 50 % floor on its description, so
  `PILOT_RESULT_4.md`'s "this hold cannot occur for the defect sites of the mass run" is true for the
  description defects only - Brewer's Castle, held V9 in pilot 4, is an ungrounded-card site.
* **Stale statements**: the scope emptied pilot 4's `p4-0004`, and its `APPLY.sql` from the unscoped
  dry run (22:25, never rehearsed or applied) stayed beside the new, empty `PLAN.jsonl`. The gate now
  drops the statements of a round whose new plan has no row (`drop_unwritten_statements`), never a
  round's record (`APPLIED.json`, `REVERTED.json`) nor a stopped batch's; re-running the dry plan
  removed them.

### Pilot 4 under the scope (`runs/pilot4-2026-09-24`; 45 of its 132 sites are in the scope)

| group | before the scope | with the scope |
|---|---|---|
| P4 (dry, sends nothing) | 128 rows (64 sites), `site-held` 68 | **52 rows (26 sites)**; `outside-defect-scope` 87, `site-held` 19; 7 open batches (`p4-0004`, `p4-0008` plan no row) |
| P5 (dry; one read-only SELECT: live phase-4 provenance 0 of 132) | - | **22 rows, all `P5/card-clear`**; `no-card` 23, `outside-defect-scope` 87; 9 open batches |
| L (dry; the same read) | - | 45 rows; `outside-defect-scope` 87 |

The 26 P4 sites: 4 carry a description defect, 12 a card defect, 16 an ungrounded card (with
overlaps); 38 of the 64 eligible sites are outside the scope (the 44 without a defect flag less 9
ungrounded cards; 3 flagged `t03` only). P5's clears are what P5 plans while no P4 provenance is
live: after the P4 pilot write a written site's card is written (`P5/card`), not cleared - the P5
sitting follows P4 (design, production_write), so this plan is a rehearsal object, not the P5 write.
L likewise waits for the final held set.

**Rehearsed against production** (`--rehearse`: each batch's APPLY ending in ROLLBACK, then the
read-back): **P4 7 batches, 52 rows; P5 9 batches, 22 rows** - every row still at its old value, 0
journal rows under every stamp, no batch blocked, `every open batch rehearsed`, `WRITE_EXIT=0` both
(`logs/p4_pilot4/scope_rehearse_p4.log` `89b676a5...`, `scope_rehearse_p5.log` `c146f562...`,
gitignored). Plan digests, P4 `d6f0b44b` `c14e0e57` `fcc85d8f` `e395bb18` `8e192554` `151f94e4`
`e7ff6470`; P5 `6e733f80` `44febdb2` `c6303a56` `2b43a5ac` `2756d8be` `f9f60024` `421c480d`
`6beea591` `8e7a8e91`. Nothing was applied.

### The mass run's plan

`plan4.py build --pilot PILOT4.jsonl --defect-scope --out PLAN4.scope.jsonl` (sha256
`fec903797a36f9616598fca9e7e228d0e38a15fa51f07fef2706f41de7077d22`, gitignored; offline, no model
call): **1,578 sites in 106 batches, `p4-0010` .. `p4-0115`** (the last 3 sites), numbered after
pilot 4's 9 so no journal stamp reuses a pilot batch id. Its sites are exactly pilot 4's plan
(`PLAN4.pilot4.jsonl` `e99f3f7f...`, unchanged) after the pilot, filtered to the scope, same records,
same order: 918 cleared-defect sites, then 143 T03-flagged, then 517 others. Lists over it:
cleared card 687, cleared description 313, ungrounded card 850; flags `t03-severe` 83,
`scope-pending` 35 (held at S1, no question), `shared-title` 51, `shared-qid` 43, `duplicate-pair` 3.

* **Excluded: pilot 4's 132 sites** (45 of them in the scope: 26 write-eligible, 19 held with their
  closed-list reasons). They are the pilot run's - the design runs the pilot first and the mass run
  on the plan's later batches - and "hold, never retry" keeps a held pilot site held.
* **Included: the draws of pilots 1-3** that are in the scope (59 sites). Those pilots failed their
  thresholds and were re-drawn (the design's failure rule); nothing of theirs was written, and their
  answers were given to prompts since changed.
* Without the scope the mass part of pilot 4's plan is 4,872 sites in 325 batches; the scope removes
  3,294 of them. `mass4.py` dry over `PLAN4.scope.jsonl`: `0 site(s) of the open batches outside it`;
  over `PLAN4.pilot4.jsonl` in pilot 4's run directory: 3,294 (its 9 pilot batches are done and ask
  nothing) - a live round with a model stage over it is refused.

### Tests, sweep, gates (worktree `.claude/worktrees/p4-pilot`, main venv)

* 37 new test functions (48 items): `test_phase4_scope.py` 29 (40 items), `test_phase4_write.py` 7,
  `test_phase4_legacy.py` 1; every existing planner call passes the scope (a scope of every site where
  a test asks another rule, `phase4_write_fixtures.EVERY_SITE`). Red first: the scope's tests before
  `scope4` existed, the writer's and the gate's before `scope` and `_defect_scope` did, the
  stale-statement test before its fix. Two were written after their code - a reverted round's record
  survives a re-plan, and `--only` narrows the mass run's guard - and go red under their mutants.
* 42 new sweep cases (`P4_SCOPE_MUTATIONS`); 2,106 labels, all unique, every anchor and test present.
  The sweep's own `main` (driver `logs/p4_pilot4/sweep_scope.py`) over **every case whose target the
  change touched** (write4 103, mass4 50, write_gate4 40, plan4 32, scope4 19, AUDIT_LOG 5,
  mutation_sweep 3): **252/252 caught**, the tree byte-identical for its 7 files
  (`logs/p4_pilot4/sweep_scope.log`; the eight touched files' sha256 checked again by hand); no
  `# mutant` left.
* Full gate suite (`-q -rs --timeout 90 -m "not integration and not live_llm"`): **6,242 passed, 111
  skipped, 57 deselected, 0 failed** (216 s), the same 111 skips (gitignored data) as before.
* `ruff check` and `ruff format --check` clean on the 10 touched Python files (ruff 0.15.11); `ruff
  check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean; the Lyra import check passes.
* `phase3/mutation_sweep.py` changed again, so `mass_run.package_digest` over `phase3/` changes with
  this branch: merge it while no Phase-3 mass run is in flight.

### Open

* **The legacy AI marking of the out-of-scope March texts** (L above): the owner's question.
  Decided 2026-09-24, "Alle kennzeichnen": every March-AI text is marked (entry of 2026-09-25,
  "Lane L marks every March-AI text").
* **876, not 904**: the owner decided on "the 904"; the scope is the documented method's 876 on the
  pinned export, the 2026-09-19 list being lost. If the owner holds the old count to be the scope,
  the 2026-09-19 inventory would have to be found and pinned as a new scope version.
* Which run directory the mass run uses (a new one, or pilot 4's, whose 9 batches are done): the
  plan's batch ids are after the pilot's either way.

## 2026-09-25 - journal-reversal-3: the Opus re-verification's reverts as a reversal list (planned, checked and rehearsed on production; not applied)

Branch `integrate/wave1` (main checkout), commits `0492fd8` (the source kind, the list's builder,
the lane, its list and plan, test-first) and `dffe140` (the mechanical sweep cases). The mechanical
journal-reversal lane (`scripts/remediation/mechanical/reversal.py`, `apply.py`, `lane.py`) now
takes the Opus re-verification's `REVERSAL_3_INPUT.jsonl`. The four gaps the section "The reversal
input" named are closed as follows. **Production was read (SELECTs) and rehearsed (every statement
ended in ROLLBACK, 0 journal rows left); nothing was applied, and no model was called.**

### (b) The source kind `opus:<change_key>` (`reversal.load_opus`, `_opus_text`)

A quote `{"source": "opus:<change_key>", "text": ...}` is checked against the audit's own files,
read where the audit keeps them (`output/remediation/opus_audit/`):

* `DECISIONS.jsonl` must hold that change key with `reversal: true` (a final `revert`, not
  superseded; `keep`, `pending`, `rejudge` and a superseded revert are refused), and the write it
  judged - change key, site, column, old and written value - must be exactly the write the undone
  journal row made;
* the text must stand in the quotes of that row's **deciding verdicts**: the verdicts on its route
  that count and are not `keep`, read from the verdict file and section each `basis[].from` names
  (`VERDICTS_RAW.json` or `VERDICTS_ROUND<n>.json` only), and of those only the quotes the audit's
  machine quote check recorded as `found`. `load_opus` refuses a decision whose verdict file holds
  another verdict name or no verdict, or whose quote check is not that verdict's (another list of
  sources).

So the lane's check stays machine-verifiable end to end: the lane proves the quote is one the audit
found, and the audit proved it against the cited evidence file or fetched page. The other kinds
(`description`, `enwiki`, `wikidata`, `gold_standard`, `journal`, `rereview`) and lanes 1 and 2 are
untouched: the new `opus` parameter defaults to no audit, their tests, plans and pinned statements
are byte-identical, and all 470 existing mechanical sweep needles still match once.

### (a) The journal ids and the list (`mechanical/reversal_opus.py --write`)

The builder reads REVERSAL_3_INPUT.jsonl, then production read-only:

* each change key's journal row (`SELECT ... FROM remediation_change_log WHERE change_key IN
  (...)`; only `phase3:<64 hex>` keys are ever sent), refused unless it is exactly one row and
  exactly the write the line names (`unified_sites`, site, column, old and written value);
* the `period_name` journal rows of the sites whose restored `period_start` falls in another bucket
  (gap (c) below).

It writes `output/remediation/mechanical_reversal_3/REASONS.json` (each audit row quoting its
input quotes as `opus:<change_key>`, each label quoting its own journal evidence as `journal`, and
the input's sha256) and the generated module `scripts/remediation/mechanical/reversal_3_list.py`
(`JOURNAL_IDS`, 13 to a line, `# fmt: skip`, the input's sha256 in its docstring), which `lane.py`
imports as `REVERSAL_3_JOURNAL_IDS`. `reversal.load_reasons` still refuses unless the two name the
same rows, and `test_the_delivered_list_is_the_lane_s_and_every_audit_row_is_on_it` refuses a
REASONS.json built from another input than the committed REVERSAL_3_INPUT.jsonl.

### (c) The period labels, in the same run

44 of the input's 190 `period_start` rows restore a start in another bucket. For each, the label
row is the period-name lane's journal row (`2026-09-22_mechanical-period-name`) whose evidence names
the start's own journal row (`remediation_change_log:<id>`, "... the write that left the label
behind"); two such rows for one start are refused. **42 have one** and join the list (the lane's
`keep_the_period_label` then checks the list as a whole: every restored label is the bucket of the
start the list leaves, no start leaves its label behind). **2 have none**: Elche (-500 -> -1500) and
Elephanta Caves (500 -> -500). Their live labels ('1500 - 500 BC', '500 BC - 1 AD') are already the
buckets of the restored starts - the pair is broken today (both are among the 11 curated rows whose
label is not their start's bucket), and restoring the start mends it; `keep_the_period_label`
accepts both starts alone.

### (d) The lane `journal-reversal-3` (`lane.py`)

Run stamp `2026-09-25_mechanical-journal-reversal-3`, test id `P6/journal-reversal-3`, change keys
`journal-reversal-3:<site_id>:<column>`, plan table `_journal_reversal_3_plan`, directory
`mechanical_reversal_3/`, the lock and statement bounds of lanes 1 and 2 (10 s, 120 s), cells
`site_type`, `period_start` (integer), `period_name` and `country`, `reverses_journal` (guard 6).
Its read-back is lane 2's (the residual - curated sites still holding a value the list undoes - and
the listed rows a later write superseded, plus the period pair) with lane 1's card-country metric
added for the country row. It is registered **below** the lists of lanes 1 and 2
(`REVERSAL_LISTS[...] = ...`, `LANES[...]`, `LANE_READBACKS[...]`), so their definitions stay byte
for byte as written - the sweep case "reversal: the second list reads back the period pair" pins
the text that ends lane 2's read-back. `.gitignore` versions the lane directory except its
`REHEARSAL.sql`, as for lanes 1 and 2.

### The run on the current input (round 3's REVERSAL_3_INPUT.jsonl, 419 rows), 2026-09-25

* **Builder** (01:52 UTC, read-only): 419 change keys, each exactly one journal row and exactly the
  judged write; 44 bucket changes, 42 labels, 2 unlabelled (Elche, Elephanta Caves). **461 journal
  rows over 413 sites** (site_type 228, period_start 190, country 1, period_name 42).
* **Plan** (`reversal.py --lane journal-reversal-3 --collect --write`, 01:56 UTC, read-only; no page
  to collect): 461 reversals, **458 cells over 410 sites** (site_type 228, period_start 188,
  period_name 42; 414 of the mass run's rows, 2 of the gap lane's, 42 labels), **3 refused**, each
  `not-the-last-write`: Stanydale Temple `period_start` (28018), Ahin Posh Tape `country` (28384),
  Agri Bavnehøj `period_start` (28638). These are journal-reversal-1's three rows: that lane undid
  them on 2026-09-23 (journal rows 32328-32330), after the audit's INPUT.jsonl snapshot, and each
  cell already holds exactly the value the audit would restore (-3000, Afghanistan, -3000; read
  2026-09-25). They are done, and stay visibly refused in SKIPPED.jsonl. `apply.py --emit` pinned
  APPLY.sql to the plan.
* **Check**: `--check-primitive` the 0022 body (casts the value to the column type, casts the old
  value, re-reads the stored value); `--verify` before the apply: curated sites 5,004, **curated
  sites still holding a value this reversal list undoes 410**, journal rows of this list a later
  write superseded 3 (the three above), curated rows whose period_name is not the bucket of
  period_start 11, card_stats rows whose civilization differs from the site country 61, every journal
  metric of the lane's stamp, test id and rollback stamp 0; `--interests` 148 (column, value) rows with their live counts;
  **`--probe-guards` exit 0: 7 probes, each refused by its own guard, 0 journal rows left**
  (guard3-foreign-old-value, guard2-no-op, guard2-foreign-column, guard2-too-long,
  guard1-other-source, guard6-journal-row, guard6-not-the-inverse).
* **Rehearsal** (`--rehearse`, 02:06 UTC): `NOTICE: journal reversal: 458 of 458 planned cell(s)
  changed and journalled over 410 curated site(s)`, `ROLLBACK`; afterwards journal rows for this run
  stamp 0, the residual 410, the temp table gone. A second `--verify` read the same numbers as before.
* **Acceptance before** (`verify_writes.py`, read-only, 01:44 UTC): mass lane 938 carried, 56
  superseded (uk-parts 5, site-type-shape 3, reversal-1 3, reversal-2 45), 80 withheld unchanged,
  **0 deviations**; gap lane 17 carried, 12 withheld unchanged, **0 deviations**.

| file (`mechanical_reversal_3/`) | sha256 |
|---|---|
| `REASONS.json` (461 reversals) | `c402301a5115ff4e4108cca0495bc194490bd5a36d3b76a2f0551639647aac5f` |
| `PLAN.jsonl` (458 cells) | `40f5656f4201c1bbbc237b730d5139d101778b8dbabc8cd7b7d748b96d1f1751` |
| `SKIPPED.jsonl` (3) | `7164ab1ab38a54a053e8667f85840415225f86b2d0bbaaba9c7a29d83f3b9bc1` |
| `APPLY.sql` | `d5c9e4bf2f17ed1af640d471d6b5e349cdd904caa3dda142ad470ba30ac31aed` |
| `ROLLBACK.sql` | `beb954cc3b869013ec470be2237f1a9f0df2348bdc5b856b1f3e1394b20cfa05` |

**This plan is the rehearsal of an input that is not final** (36 rows are pending in round 3). The
apply runs on the list regenerated after the last round.

### The apply (the orchestrator runs it, after the last round is decided; the owner's go first)

From the repo root, main venv, `export PYTHONIOENCODING=utf-8`,
`A=scripts/remediation/mechanical/apply.py`:

0. **The final input.** After the last round's verdicts are in place:
   `./.venv/Scripts/python.exe scripts/remediation/opus_audit/run.py fetch`, then
   `./.venv/Scripts/python.exe scripts/remediation/opus_audit/run.py decide` -> `pending` 0 and
   `rejudge` 0 in its output, or the list is not final.
1. **Plan.**
   `./.venv/Scripts/python.exe scripts/remediation/mechanical/reversal_opus.py --write` (production
   read-only: REASONS.json and reversal_3_list.py; read its `unlabelled` and refusals), then
   `./.venv/Scripts/python.exe scripts/remediation/mechanical/reversal.py --lane journal-reversal-3 --collect --write`
   (PLAN.jsonl, PLAN.md, SKIPPED.jsonl, ROLLBACK.sql; expect Stanydale Temple, Ahin Posh Tape and
   Agri Bavnehøj refused `not-the-last-write` and nothing else unexplained), then
   `./.venv/Scripts/python.exe $A --lane journal-reversal-3 --emit` (APPLY.sql). Then
   `./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical.py tests/remediation/test_mechanical_reversal.py tests/remediation/test_mechanical_reversal_opus.py -q -m "not integration and not live_llm"`
   green, and commit `reversal_3_list.py` and `mechanical_reversal_3/` (the list, the plan and the
   two statements).
2. **Check.** `./.venv/Scripts/python.exe $A --check-primitive` (the 0022 body);
   `./.venv/Scripts/python.exe $A --lane journal-reversal-3 --verify` (the residual = the plan's
   site count; journal rows for the stamp 0); `./.venv/Scripts/python.exe $A --lane journal-reversal-3 --interests`;
   `./.venv/Scripts/python.exe $A --lane journal-reversal-3 --probe-guards` -> exit 0, the same 7
   probes each refused by its own guard.
3. **Rehearse.** `./.venv/Scripts/python.exe $A --lane journal-reversal-3 --rehearse` -> NOTICE
   `journal reversal: <n> of <n> planned cell(s) changed and journalled over <s> curated site(s)`,
   ROLLBACK, 0 journal rows.
4. **Apply.** `./.venv/Scripts/python.exe $A --lane journal-reversal-3 --apply` -> `APPLY OK: the
   read-back matches the plan, row for row` (exit 0; exit 3 NOT COMMITTED, 5 OUTCOME UNKNOWN - read
   the journal for the stamp before anything else, never apply twice).
5. **Read back.** `./.venv/Scripts/python.exe $A --lane journal-reversal-3 --verify` -> journal rows
   for this run stamp and for this test id = n, the residual 0, the listed rows a later write
   superseded 3 (lane 1's), 0 outside the lane's cells, on non-curated rows or with another site's
   `site_id_ref`. On today's plan: 458 journal rows, period-pair residual 11 -> 9 (Elche and
   Elephanta Caves mended; computed read-only from the plan and the live pairs), card country 61
   unchanged. The period-name lane's own read-back (`journal rows for this run whose value is not the
   row's bucket`) rises by the label count (42 today) - its labels are undone with the starts they
   came from, by design, as for lane 2.
6. **Rehearse the rollback on the landed rows.** `./.venv/Scripts/python.exe $A --lane journal-reversal-3 --rehearse-rollback`
   -> the reversal's own NOTICE, ROLLBACK, the cells still holding the restored values; commit
   `REHEARSAL_ROLLBACK.sql` as for lanes 1 and 2. (Before the apply it refuses, correctly.)
7. **Acceptance.**
   `./.venv/Scripts/python.exe output/remediation/tools/verify_writes.py --allow-stamp 2026-09-22_mechanical-uk-parts --allow-stamp 2026-09-22_mechanical-site-type-shape --allow-stamp 2026-09-23_mechanical-journal-reversal-1 --allow-stamp 2026-09-23_mechanical-journal-reversal-2 --allow-stamp 2026-09-25_mechanical-journal-reversal-3`
   -> `RESULT: 0 deviation(s)` (on today's plan: 938 - 414 = 524 carried, 56 + 414 = 470
   superseded, reversal-3 414), and
   `./.venv/Scripts/python.exe output/remediation/tools/verify_writes.py --lane gap --allow-stamp 2026-09-25_mechanical-journal-reversal-3`
   -> 0 deviations (on today's plan: 15 carried, 2 superseded by reversal-3).

Afterwards: re-plan the scope lane and the card_stats recompute (their premises and cards derive
from these columns, `reversal.write_plan_md`), and the static export - none of them is run here.

### Tests, sweeps, gates for round 3 and journal-reversal-3 (main checkout, branch `integrate/wave1`, main venv)

* **Round 3 / one code path** (`test_opus_audit_decide.py`, 103 cases): 19 new test functions,
  each red before its code (the overlay's new signature did not exist): the round files in number
  order, a gap, a stray name, the sections a round may hold, a `second` as the keep's p2 (and the
  Kola case: a failed p2 replaced by a later second), a `second` before rule 4 fired or for a row
  that waits on none, the sample in one round only and an empty sample section, a later tie on the
  pair the round before left split, a later tie over a failed tie, every tie refusal, a round laid
  on the routes as they stood before it, REJUDGE_ROUND<n>, the whole run over rounds 2 and 3 (twice,
  byte-identical, TIE_ROUND2.json left alone), the run's refusals (no sample judged, a row INPUT does
  not hold) and the fetch of every round. The round-2 tests call the one overlay (`lay`); one of
  them now reaches its refusal through the overlay instead of the round-2 reader, one gained the
  stale-tie count.
* **journal-reversal-3** (`test_mechanical_reversal.py` +16 test functions, the new
  `test_mechanical_reversal_opus.py` 17 functions / 22 cases): every `opus:` refusal, the loader's
  refusals, the lane's cells, registration and read-back, a start the audit reverts with its label,
  `--write` through the audit's files; the builder's refusals, labels and generated list, the
  readers' statements, and two tests on the delivered list (it is the lane's, built from the
  committed input; every delivered `opus:` quote stands in its row's deciding verdicts in the real
  audit files). Red before the code: 26 of the reversal tests, the whole builder file (no module).
  Mechanical tests (`tests/remediation/test_mechanical*.py`, `tests/api/test_cardgame_generator_stats.py`):
  **786 passed, 3 skipped** (the card_stats export, gitignored); lanes 1 and 2 byte-identical.
* **`phase3/mutation_sweep.py "opus audit:" "opus round 2:" "opus round 3:"`: 112/112 caught**
  (46 + 31 + the new block `OPUS_ROUND3_MUTATIONS`, 35 cases); eleven round-2 anchors follow the one
  code path, labels and tests unchanged; the tree byte-identical to the sweep's start for its 3
  files, no `# mutant` left. 2,085 labels, all unique; `test_phase3_sweep.py` green.
* **`mechanical/mutation_sweep.py reversal`: cases 93, fired 93** (skipped, survived, invalid,
  unproven, errored 0) - the existing reversal cases and the new block `REVERSAL_3_CASES` (43
  cases, "reversal 3" alone: 43 of 43 fired); every needle of all 513 cases matches once
  (`test_mechanical_sweep.py` green), the files restored byte for byte.
* **Full gate suite** (`-m "not integration and not live_llm"`, `--timeout 300`,
  `-p no:cacheprovider`): **6,093 passed, 6 skipped, 57 deselected, 0 failed** (548 s); the skips
  are the same six as in rounds 1 and 2.
* `ruff check` and `ruff format --check` clean on the 11 touched Python files (ruff 0.15.11);
  `ruff check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean. `opus_handoff.py`, `phase3/fetch_stage.py` and
  `phase3/ledger.py` are untouched; `phase3/mutation_sweep.py` changed only in its Opus blocks and is
  imported by neither `opus_handoff.py` nor anything it imports (it moves `mass_run.package_digest`;
  no Phase-3 mass run was in flight).

## 2026-09-25 - Phase-4 mass run: the mid-run audit's WRONG_SITE (Roman Bath, York), its fix, and one written site taken back (nothing applied)

Run `runs/mass-2026-09-25` (plan `PLAN4.scope.jsonl`), P4 apply root `logs/_write_apply_p4`: 336
sites written in 5 accepted steps - pilot 4's 26 (`p4-0001` .. `p4-0009`) and the mass run's 310
(`p4-0010` .. `p4-0041`), 672 journal rows under `phase4:p4-%`, every step `RESULT: 0 deviation(s)`.
The design's mass-run gate (entry [6], "MASS RUN GATES"): "10 random written sites after every 500.
Any T1, T2 or T3 hit stops the writes and triggers re-verification of every written site of that
lane or rule; a systematic cause is reverted through revert4.py." Contracts: `PHASE4_CONTRACTS.md`
section 10.

### The mid-run audit

45 random written sites (`logs/p4_mass/midrun_sample.txt`; sheets `MIDRUN_AUDIT_SHEETS.md`
`b58de234...`, verdicts `MIDRUN_AUDIT_VERDICTS.json`
`15577da6f0fcc608547ed4e8ff7221e1decb6db7aabf12d7d7e54a435e383145`, gitignored): **280 sentences,
279 SUPPORTED, 1 WRONG_SITE**; 36 cards, all CONTAINED; 0 lost hedges or negations, 0 flipped
meanings, 0 broken sentences, 0 verifier false-passes, 0 gold errors. T1 and T3: 0. **T2: 1 - the
writes are stopped.**

The hit: **Roman Bath, York** (`70037a24-6487-4834-9b50-5242289009fe`, p4-0036, lane W, stored type
Residence/villa/farmhouse), sentence 1, verbatim from its article's lead: "The Roman Bath is a Grade
II* listed public house on St Sampson's Square in the city of York, England [1]." Its subject is
the pub built in 1929-31 over the Roman bath house the record stands for: the opening sentence tells
the reader the site is a listed pub.

### Root cause

* **The source.** The English article "Roman Bath, York" is about the pub; its Wikidata item is the
  pub too - S3's `also_named` for the site was "Roman Bath; The Roman Bath Public House" (the item's
  English label, which V6 accepts for a strong 'own' verdict). The only sentence of the pool that
  names the site is W1, the pub.
* **The selector** (answer `DESC: W1 W2 W3 W6 W7 W16`, `CARD: W3`). Rule (7) demands a first DESC
  sentence that names the site, or ABSTAIN - so W1 or nothing. Rule (8), the only rule that lets
  the selector refuse a name-carrying sentence about something else, names exactly "the modern
  village, town or municipality (its administration, its population, its modern founding)" and
  allows ABSTAIN only "if the only sentence that names the site is such a sentence". A pub is none
  of these; rule (1)'s "not a namesake" reads as another thing of another name, and "The Roman Bath"
  is the site's own name. Nothing in the question named the case, and W1 was the one way to satisfy
  rule (7).
* **The reviewer** (answer `R1-R6: KEEP`, `CARD: DROP` - the card's "The remains" and "the present
  pub" had no antecedent inside the card). The question asks "is it about this site", but its DROP
  lines - the lines it answers by - name, for "not this site", again only the modern village, town
  or municipality. R1's subject carries the site's name word for word, so the reviewer read it as
  the site; it was careful about antecedents (it dropped the card) but had no line for a later
  building that shares the name.
* **V6** passes the sentence on the name string alone (by design: V6 checks naming, not reference).

### The fix (reviewer only; the selector stays frozen)

`prompts4.REVIEWER_QUESTION` gains, right after the modern-place line:

    DROP a sentence whose subject is a later building, business or institution (a pub, hotel, house, museum, shop, church, station ...) that shares or contains the site's name rather than the ancient site itself, even when it names the site.

Re-pinned in `test_phase4_select.py` with its reason:
**`097c45891e5fb28051d64d582fe92e4ef747927d8b569790b4f1bd7d143106a8`** (was `89e6035d...fc71e7523`).
The selector question is unchanged (`a0b422e7...2a367ef93`): its rule (8) has the same gap, but the
mass run's selector questions (`handoff/p4-mass-select`, p4-0050 .. p4-0057 being answered now) are
answered under its pin. The cascade is the review import's own: `follow_drops` takes a pronoun
sentence along with the sentence it leans on, S4 and S5 run again. **Replayed on the real case**
(`logs/p4_mass/measure_roman_bath_cascade.py`, a scratch copy of p4-0036, the stored review answer
with only R1 turned into a DROP; log `7b7eae2a...`): R2 "It is built above an ancient Roman bath
house" follows R1, R3-R6 are assembled again, and **V6 holds the site** ("sentence 1 names none of
['Roman Bath, York', 'Roman Bath', ..., 'The Roman Bath Public House']"); the card is held as
before. Under the new line the site is not written.

### No deterministic check (measured)

`logs/p4_mass/measure_wrong_site_building.py` (gitignored), a sentence that names the site (S3's
reading) and says it "is/was a/an [up to five words] <noun>":

| detector | census pools (88,936 sentences, 18,364 naming the site) | written (336 sites, 2,046 sentences) | group 5 (520 sentences) |
|---|---|---|---|
| businesses: public house, pub, inn, hotel, restaurant, bar, cafe, shop, store, brewery | 2 - Roman Bath (true), Bent Pyramid "a small bar wall" (false) | 1 - Roman Bath | 0 |
| buildings: house, museum, church, chapel, station, school, theatre, hall, manor, ... | 48 sentences / 44 sites | 4 - Roman Bath (true); Roman Theatre of Arles, Ariconium "a road station", Schwarzenacker Roman Museum (false) | 1 - Second Ancient Theatre, Larissa (false) |

The business list catches the one pub and nothing else of the class; the building list catches the
rest of the class in the census (Killerton "an 18th-century house", Lydney Park "a 17th-century
country estate", St Laurence School "a coeducational secondary school", Great Tottington "a moated
manor farm") only beside ancient members of the same surface form (House of the Tragic Poet "a
Roman house", the Roman theatres of Cartagena, Tarraco and Zaragoza, Ariconium, Storgosia and Ad
Quintum "road station", Newport Roman Villa "a Romano-British farmhouse"). Which it is depends on
the subject's referent and its date, not on a word: the rule cannot be stated precisely in one
sentence, so **no V-rule is added** (logs `measure_wrong_site_census.log` `819c59d7...`,
`measure_wrong_site_written.log` `1395a4b5...`).

### Taking back one written site (rendered and rehearsed; not applied)

`revert4.py --site`, `audit4.py hold`, and `write_gate4`'s re-plan without a reverted site
(contracts section 10). Read-only first: the site's journal rows under `phase4:p4-0036:chunk-0001`
are 34909 (`unified_sites.description`) and 34910 (`raw_data`), both live at their written value;
the chunk holds 18 rows of 9 sites.

* **Rendered**: `logs/p4_mass/REVERT_ROMAN_BATH.sql` (`75acd4c2...`), the pinned reversal with
  `AND l.site_id_ref = '70037a24-...'` in its set (4 places: the count, the set, the read after).
* **Rehearsed against production** (`--rehearse`, ending in ROLLBACK; `REVERT_ROMAN_BATH.rehearse.sql`
  `3b6d1ec5...`, no COMMIT in it): `BEGIN / DO / ROLLBACK`, `NOTICE: revert: 2 row(s) reverted`
  (every guard and both invariants passed inside the transaction), then the read: **journalled
  writes matched 2, reversals kept 0** (rolled back). Afterwards production was read again: 672
  phase-4 writes, 0 phase-4 reversals, Roman Bath's description still the written one.
* **The hold is recorded in the run**: `audit4.py hold --run-dir runs/mass-2026-09-25 --site
  70037a24-6487-4834-9b50-5242289009fe --audit logs/p4_mass/MIDRUN_AUDIT_VERDICTS.json` ->
  `audit-wrong-site (site)`, 1 new line in p4-0036's `holds.jsonl` (9 -> 10 lines, `d593536f...` ->
  `04eaaaf3...`), `HOLDS4.jsonl` 436 -> 437 holds (`e082a5f3...`); the detail names the verdict file
  and its sha256.
* **The gate, dry and read-only, over p4-0036 now**: `WRITE_EXIT=1` - "the re-plan leaves out
  70037a24-..., whose 2 row(s) round 1 wrote are not reverted in production - 2 journalled write(s)
  of the site under phase4:p4-0036:chunk-0001, 0 with their own reversal kept. Revert the site
  first (revert4.py --stamp-like 'phase4:p4-0036:chunk-0001' --site 70037a24-...)". The other 8
  sites re-planned to exactly their written rows; `PLAN.jsonl`, `APPLIED.json` and `LANE_PLAN.jsonl`
  unchanged. The group helper names only its own batches (`--batch`), so the next groups are not
  blocked by it.

**The apply and its acceptance (the orchestrator's; from this worktree, main venv):**

    PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe; M=output/remediation; R4=$M/phase4_runner
    $PY scripts/remediation/phase4/revert4.py --stamp-like 'phase4:p4-0036:chunk-0001' --site 70037a24-6487-4834-9b50-5242289009fe --apply
        # the read after it: journalled writes matched 2, reversals kept 2; WRITE_EXIT=0
    $PY $M/tools/write_gate4.py --group P4 --run mass-2026-09-25 --open-lanes W,S --batch p4-0036
        # dry: "p4-0036: 70037a24-... left out of the re-plan; its 2 row(s) of round 1 have their own
        # reversal kept in production (read-only proof) ..."; WRITE_EXIT=0
    $PY $M/tools/verify_writes4.py --lane p4 --plan $M/logs/_write_apply_p4/LANE_PLAN.jsonl --run $R4/runs/pilot4-2026-09-24 --run $R4/runs/mass-2026-09-25 > $M/logs/p4_mass/accept-after-roman-bath-revert.log
        # expected: "lane p4 | stamps phase4:p4-% | planned rows 672 | lane journal rows 672 |
        # carried 670 | not yet written 2", "re-verified 335 written site(s) with V1-V15",
        # "RESULT: 0 deviation(s)", ACCEPT_EXIT=0. No step is pending, so it is recorded here and
        # not handed to --accept.

After the apply, `audit4 draw --written` must be given the live written set (Roman Bath no longer
in it), or it refuses the held site as "written but not reviewed". Lane L later treats Roman Bath
like any held site.

### Group 5's review questions exported again

Batches p4-0042 .. p4-0049 had their 78 review questions answered under the old reviewer pin and
not imported. The answers are kept, moved whole to `handoff/p4-mass-review-stale-reviewer-89e6035d/`
(`opus_handoff validate`: 78 answered, 0 stale, 0 malformed there); the batches' `reviews/` held
nothing. Re-exported with the helper's own command (`mass4.py --plan PLAN4.scope.jsonl --run-dir
runs/mass-2026-09-25 --log-dir logs/p4_mass --only p4-0042,..,p4-0049 --searches-off --live
--stages review --handoff-export handoff/p4-mass-review`, log `group-p4-0042-review-reexport.log`,
`STAGE_EXIT=0`): **78 questions** (9, 7, 11, 10, 11, 11, 11, 8 - the same labels as before), every
prompt digest new, every prompt carrying the new line and differing from the old by exactly that
line; 0 answers. `handoff/p4-mass-review` validates as 402 questions, 324 answered (groups 1-4), 0
stale.

### The re-verification of every written site for this rule

The design's consequence of a T2 hit, for the rule the hit showed: the orchestrator runs an Opus
check of every written site's sentences for this class. Its input is
**`logs/p4_mass/REVERIFY_WRONG_SITE_INPUT.jsonl`** (gitignored; `build_reverify_input.py` beside it):
one compact JSON line per written site of both runs - `site_id`, `run`, `batch`, the stored `name`
and `site_type` (read back from production), and `sentences`, the published sentences in order
(cut from the run's post-review assembly with `assemble.published_sentences`; the assembly was
checked byte for byte against the written `PLAN.jsonl` description and against production's live
description for every site). **336 sites (pilot 4 26, mass 310), 2,046 sentences (152 + 1,894),
312,629 bytes, sha256 `c5e56457ea242ccdaf32300cd9a5174e06aee9ba9712cf0ec7b18cb7152ba6ba`**. Roman
Bath is in it as the known positive. The check asks, per sentence: is its subject a later building,
business or institution that shares or contains the site's name rather than the ancient site? Any
further hit takes the same path: `audit4.py hold` with the check's verdict file, `revert4.py
--site`, the gate's proof, the acceptance.

### Tests, sweep, gates (worktree `.claude/worktrees/p4-pilot`, main venv)

* 13 new test functions (23 items): `test_phase4_select.py` 1 (the line, its place; the full-order
  test takes it in), `test_phase4_review.py` 1 (the cascade on a namesake lead), `test_phase4_write.py`
  6 (10 items: `revert4 --site` - only the site's rows, every guard kept, the site id's form, the
  command; the gate's re-plan without a reverted site, and a re-plan to other rows still refused,
  which no test covered before), `test_phase4_accept.py` 1 (a site reverted alone: 0 deviations),
  `test_phase4_runner.py` 4 (10 items: `audit4 hold`). Red first: the reviewer line's two tests, the
  `--site` tests, the gate's re-plan test and the hold tests failed before their code; the review
  cascade, the acceptance after a site revert, the other-rows refusal and the latest-batch test pass
  on code that already did it and go red under their mutants.
* 27 new sweep cases (`P4_MIDRUN_MUTATIONS`); 2,135 labels, all unique, every anchor and test
  present. The sweep's own `main` (driver `logs/p4_mass/sweep_midrun.py`) over every case whose target
  the change touched (write_gate4 45, run4 29, prompts4 28, revert4 26, audit4 22, review4 18,
  AUDIT_LOG 5, mutation_sweep 3): **176/176 caught**, the tree byte-identical for its 8 files
  (`logs/p4_mass/sweep_midrun.log` `a1668a63...`), `git status` clean afterwards, no `# mutant` line
  left.
* Full gate suite (`-q -rs --timeout 90 -m "not integration and not live_llm"`): **6,268 passed, 111
  skipped, 57 deselected, 0 failed** (377 s; `logs/p4_mass/gates_pytest_midrun.log`), the same 111
  skips (gitignored data) as before.
* `ruff check` and `ruff format --check` clean on the 12 touched Python files (ruff 0.15.11); `ruff
  check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean; the Lyra import check passes.
* `phase3/mutation_sweep.py` changed again, so `mass_run.package_digest` over `phase3/` changes with
  this branch; `phase4/` changed too (`mass4`'s digest `bcd11edf...` from the re-export on): a
  `mass4` invocation started before these commits stops between batches on its digest guard.

### Open

* **The apply of the Roman Bath revert and its acceptance** (the commands above), then the
  re-verification of the 336 written sites for this class; writes stay stopped until both are done.
* **Group 5's 78 review questions** (`handoff/p4-mass-review`, p4-0042 .. p4-0049) are to be
  answered under the new reviewer pin; the old answers stay in the stale directory.
* **The selector's rule (8)** carries the same gap. It stays frozen while the mass run's selector
  answers are given; whether to widen it for a later run is a decision for then.

## 2026-09-25 - Lane L marks every March-AI text: the owner's decision, L's own plan over the curated population, its dry plan and first step rehearsed (nothing applied)

**Decision** (Martin, 2026-09-24, answer "Alle kennzeichnen (Recommended)"): lane L - which writes
no text, only the provenance that makes a site show the existing "AI-generated text" footnote (EU AI
Act Art. 50) - marks **every** March-AI text, not only the 1,623 sites of the defect scope. The open
question of the defect-scope entry above ("The legacy AI marking of the out-of-scope March texts")
is answered. c9cf66e's scope refusal is undone for L only; P4 and P5 stay scoped ("Nur
Defekt-Sites"). What stays: a text equal to d4526691's gets no marking (HUMAN_ONLY D7, listed in
`UNCLAIMED.jsonl`), so does a site the snapshot lacks; a site with live phase-4 provenance is never
touched by L; L never changes a description. Branch `wip/p4-L` (from `wip/p4-pilot` 0a2a9a4);
contracts: `PHASE4_CONTRACTS.md` section 9, "Lane L marks every March-AI text".

### How L selected its sites, before and after

* **Before** (c9cf66e): `write_gate4.py --group L --run <run>` read one Phase-4 run's plan batches
  (`p4-NNNN` directories, `input.json` values from the S0 read) and planned one L write batch per
  plan batch (`p4l-NNNN`). `plan_legacy` refused every site outside the pinned scope first
  (`outside-defect-scope`, not listed for HUMAN_ONLY), then the sites production shows with a
  full (W/S/T/R) provenance (`written-by-p4`); the rest were "held" and marked where their text
  differs from d4526691. Its population was therefore the scope sites of that run's batches that P4
  did not write - and since the mass run's plan holds only scope sites, no invocation could reach a
  curated site outside the scope.
* **After**: the population is every curated site whose live description differs from d4526691's
  and that carries no live phase-4 provenance - the design's own reach (entry [6], "L (legacy
  disclosure; held sites only; no LLM)", with P4's population then every curated site, and
  licensing_and_ai_act, "so no LLM-processed text stays unmarked"); `legacy4`'s docstring already
  said "A site Phase 4 does not write keeps its stored description ... it must not stay live
  unmarked". `plan_legacy(batch, *, written)` takes no scope. L plans from **its own plan**:
  `plan4.py read --out LEGACY4_ROWS.jsonl` (the one read-only SELECT, a fresh read) and `plan4.py
  legacy` write `LEGACY4.jsonl` - every curated site in site-id order, batches of 15 marked
  `pass: phase4-legacy`, numbered from p4-1001 - and `write_gate4.py --group L --legacy-plan
  <file>` plans it; L never takes `--run`, P4 and P5 never take the L plan (one L population per
  lane). An apply root holding another L plan's write batches is refused by name.

### The plan (read-only read, offline build; worktree `.claude/worktrees/p4-L`, gitignored files)

* `plan4.py read --out phase4_runner/LEGACY4_ROWS.jsonl` (2026-09-25 07:54, one SELECT): **5,004
  rows**, sha256 `756455392d99503f825c3294802d6d0945a5225fe086f4fdbd2e5812b604fbba`.
* `plan4.py legacy`: `phase4_runner/LEGACY4.jsonl` sha256
  `b8c4f2e20c19e0a33ead4255b243a7f30597ca338c86914181618a93a6a9f6f1`, **334 batches p4-1001 ..
  p4-1334**, 5,004 sites; provenance at the read: W 477, S 10, none 4,517.
* A census the same morning, read-only and independent of the tool (one SELECT over
  `unified_sites` and `snapshot_rows`): 5,004 curated sites, 487 with W/S/T/R provenance, 0 with any
  other; without it 4,499 differ from d4526691, 10 equal it, 8 are not in it, 0 have no
  description - the dry run's numbers below, site for site in count.

### The dry run (`write_gate4.py --group L --legacy-plan phase4_runner/LEGACY4.jsonl`, read-only)

`logs/p4l/dry.log` sha256 `2732344aa1e6efcd31cc2a9d02965771cca22c2962b0c6ac69d8a8e1c46f85cc`,
`WRITE_EXIT=0`, 24 s (26 read-only SELECTs of the live provenance):

| | sites |
|---|---|
| curated sites in the plan | 5,004 |
| excluded as P4-written (live phase-4 provenance, `written-by-p4`) | 487 |
| UNCLAIMED, HUMAN_ONLY D7 (`no-legacy-claim`): same as d4526691 | 10 |
| UNCLAIMED, HUMAN_ONLY D7: not in d4526691 | 8 |
| provenance already present (`provenance-present`) | 0 |
| **rows planned = March-AI texts to mark** (`P4/legacy-provenance`) | **4,499** |

By the pinned scope (`SCOPE4.json` `19a57e9f...`, read from `wip/p4-pilot`'s runner): 3,365 of the
4,499 rows are outside the scope (the sites this decision adds), 1,134 inside it - **1,115 of them
sites of the mass run's plan** (`PLAN4.scope.jsonl`) that P4 may still write, 19 pilot 4's held
scope sites. Of the 18 unclaimed, 2 are scope sites. All 487 P4-written sites are scope sites. The
design sized L at "about 300-600 L rows" because its P4 would have written about 4,400 sites; with
P4 scoped, L carries the rest. At 100 sites per step the plan is **49 steps** (the first 94 sites in
p4l-1001 .. p4l-1007, the last 54, the largest 100).

`verify_writes4.py --lane p4l --plan logs/_write_apply_p4l/LANE_PLAN.jsonl` over the dry plan
(read-only; the lane plan written by `write_gate4.write_lane_plan`): "lane p4l | stamps
phase4l:p4l-% | planned rows 4499 | lane journal rows 0 | carried 0 | not yet written 4499",
`RESULT: 0 deviation(s)`, `ACCEPT_EXIT=0` (`logs/p4l/accept-before-any-write.log` `fbba7e3b...`):
the acceptance reads this plan and finds every row at its old value.

### The first step rehearsed against production (ROLLBACK)

`write_gate4.py --group L --legacy-plan phase4_runner/LEGACY4.jsonl --batch p4-1001 .. --batch
p4-1007 --rehearse` (each REHEARSE.sql checked first: `ROLLBACK;`, no `COMMIT;`): **7 batches, 94
rows over 94 sites** (14, 11, 14, 15, 14, 12, 14; 11 sites of the 105 refused `written-by-p4`),
every guard and invariant 3 held inside each transaction, every row read back at its old value, 0
journal rows under each stamp, no batch blocked, `every open batch rehearsed`, `WRITE_EXIT=0`
(`logs/p4l/rehearse_step1.log` `c4c99aa9133432927656ab7b98c517174d87ca9d5a2bc38a98c9eeb5ee86fef3`).
Plan digests `d2c05f2b` `cf25b72c` `73c07bc6` `d4516ca8` `dd5d58e1` `9b741c57` `1d421ca4`. Read
afterwards: 0 journal rows under `phase4l:%`, 0 curated sites with a lane-L provenance, 487 with
W/S/T/R. Nothing was applied.

### When L is written

The design's order (production_write, ORDER: "then the L rows once the held set is final") binds
the apply: an L row changes `raw_data`, and a scope site P4 writes after its L row no longer holds
the `raw_data` its P4 plan names - P4's preflight then refuses the whole P4 batch (fail-closed; the
way back is `revert4.py --stamp-like 'phase4l:...' --site <id>`). The first step alone holds 29
sites of the mass run's plan. So the plan is **read and built again after the last P4 step of the
mass run is accepted** (and after the Roman Bath revert and the re-verification), and L's 49-odd
steps follow; the plan of this entry is the rehearsal object, not the one to apply. A site held
because its lane (T, R) has not passed its pilot is marked like any held site; should such a lane
open later, its L row is reverted before its P4 write. The per-run L dry plans of pilot 4 in
`wip/p4-pilot`'s `logs/_write_apply_p4l` (`p4l-0001` .. `p4l-0009`, never rehearsed or written)
are moved aside first - the gate refuses the apply root otherwise.

**The apply and its acceptance (the orchestrator's; from the merged worktree, main venv):**

    PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe; M=output/remediation; R4=$M/phase4_runner
    mv $M/logs/_write_apply_p4l $M/logs/_write_apply_p4l.per-run-dry-2026-09-24
    $PY scripts/remediation/phase4/plan4.py read --out $R4/LEGACY4_ROWS.jsonl     # one read-only SELECT
    $PY scripts/remediation/phase4/plan4.py legacy                                 # offline: $R4/LEGACY4.jsonl
    $PY $M/tools/write_gate4.py --group L --legacy-plan $R4/LEGACY4.jsonl             # dry, read-only
    $PY $M/tools/write_gate4.py --group L --legacy-plan $R4/LEGACY4.jsonl --rehearse  # every batch, ROLLBACK
    # per step, until the gate says "done: no open batch left to write":
    $PY $M/tools/write_gate4.py --group L --legacy-plan $R4/LEGACY4.jsonl --apply --step 100
    $PY $M/tools/verify_writes4.py --lane p4l --plan $M/logs/_write_apply_p4l/LANE_PLAN.jsonl > $M/logs/p4l/accept-step-NN.log
    $PY $M/tools/write_gate4.py --group L --accept $M/logs/p4l/accept-step-NN.log
    # at the end: every planned row written
    $PY $M/tools/verify_writes4.py --lane p4l --plan $M/logs/_write_apply_p4l/LANE_PLAN.jsonl --complete

### Tests, sweep, gates (worktree `.claude/worktrees/p4-L`, main venv)

* 10 new test functions (13 items), 2 rewritten: `test_phase4_legacy.py` - L takes no scope and
  marks every March text (replaces the out-of-scope test); `test_phase4_write.py` - one site
  outside a real pinned scope through the gate (P4 and P5 refuse it, L plans it), L's population
  and its counts, L written in steps and accepted on lane p4l (the command names no run), the source
  checks for L, P4 and P5 (4 items), the foreign-batch refusal, `--batch` and a missing plan, the
  strict read of the plan; P4 and P5 need the scope and L takes none (rewritten);
  `test_phase4_plan.py` 3 - the L plan's order, numbering, mark and summary, its values byte for
  byte, bad rows. The fake psql answers the gate's live-provenance read. Red first: the scope
  removal's tests (10 failed) and the own plan's (12 failed) before their code; the `--batch` test
  was written after its code and goes red under its three mutants.
* `plan4.plan_site` is split out of `_site` unchanged: `plan4.py build` over wip/p4-pilot's inputs
  rebuilds `PLAN4.pilot4.jsonl` (`e99f3f7f...`) and `--defect-scope` `PLAN4.scope.jsonl`
  (`fec90379...`) byte for byte.
* 31 new sweep cases (`P4_LEGACY_MUTATIONS`, a block of its own after `P4_SCOPE_MUTATIONS`); the 3
  L cases of `P4_SCOPE_MUTATIONS` are retired with the code they guarded and the gate's options
  case follows its line; 2,163 labels, all unique, every anchor and test present. The sweep's own
  `main` (driver `logs/p4l/sweep_legacy.py`) over every case whose target the change touched (write4
  106, write_gate4 60, plan4 40, legacy4 6, AUDIT_LOG 5, mutation_sweep 3): **220/220 caught**, the
  tree byte-identical for its 6 files (`logs/p4l/sweep_legacy.log` `e319418e...`; the 8 touched
  files' sha256 checked again against the record taken before it), `git status` clean afterwards,
  no `# mutant` line left.
* Full gate suite (`-q -rs --timeout 90 -m "not integration and not live_llm"`): **6,274 passed,
  118 skipped, 57 deselected, 0 failed** (205 s; `logs/p4l/gates_pytest.log` `4893ef31...`); 6,379
  before plus the 13 new items. The 118 skips are all gitignored data this fresh worktree does not
  hold (Natural Earth, the snapshot, the S0 export, the design file ...); wip/p4-pilot's worktree,
  which holds it, skips 111.
* `ruff check` and `ruff format --check` clean on the 9 touched Python files (ruff 0.15.11); `ruff
  check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean; the Lyra import check passes.

### Merging into wip/p4-pilot

* `phase4/` changes (`write4`, `plan4`, `legacy4`), so `mass4`'s digest over `phase4/*.py` changes:
  a `mass4` invocation started before the merge stops between batches on its digest guard. Merge
  between invocations, or after the mass run (L's apply follows it anyway).
* `phase3/mutation_sweep.py` changes, so `mass_run.package_digest` over `phase3/` changes: merge
  while no Phase-3 mass run is in flight. Its hunks: the three retired L cases, the moved options
  anchor and the `P4S_L` constant inside `P4_SCOPE_MUTATIONS`, and the new block after
  `MUTATIONS += P4_SCOPE_MUTATIONS` - away from the file's end, where wip/p4-pilot appends.
* `write_gate4`: `--run` is no longer an argparse requirement (P4 and P5 still refuse to run without
  it, now with `WRITE_EXIT=1` and a message); `_run` branches on the L plan before the scope, and
  `run_batches` takes `run_dir: Path | None`. A wip/p4-pilot change to `_run` or `run_batches`
  meets these hunks.
* This entry is appended after the 2026-09-25 mid-run audit entry; a later wip/p4-pilot entry
  conflicts only as two appends, kept in date order.

### Open

* **L's apply**, after the mass run's last P4 step is accepted: the commands above.
* **HUMAN_ONLY D7**: 18 unclaimed today (10 same as d4526691, 8 not in it), listed per batch in
  `logs/_write_apply_p4l/*/UNCLAIMED.jsonl` of the apply's plan.

## 2026-09-25 - the wrong-both correction lane (planned, checked and rehearsed on production; not applied), and Ahin Posh Tape's coordinates (not planned)

Branch `integrate/wave1` (main checkout), commits `dba4bf6` (the lane, test-first, with its list and
plan), `5328c62` (two subsumed checks dropped, their subsumption pinned) and `423c7be` (the mechanical
mutation cases). journal-reversal-3 was applied before this started (488 cells over 435 sites; the
acceptance below reads it). **Production was read (SELECTs) and rehearsed (every statement ended in
ROLLBACK, 0 journal rows left); nothing was applied, no model was called, and `opus_handoff.py`,
`phase3/fetch_stage.py` and `phase3/ledger.py` are untouched.**

### The lane (`scripts/remediation/mechanical/wrong_both.py`, lane `wrong-both`)

RULES.md rule 5: "wrong-both rows carry a proposed value; it is not written by this audit. It goes
to a later correction lane that writes only with a machine-verified verbatim quote." The input is
the audit's final `DECISIONS.jsonl` (keep 481, revert 453; sha256
`a1f5cb87f2f6d5622a1762be96f2b62d9eecc9f6ac37b19f5d732175b845ae04`) and the verdict files each
`basis[].from` names. **A candidate is every decided row whose route carries a `wrong-both`
verdict: 42.** Each is decided in this order, the first failure listing it with its reason:

0. the final decision is revert (`not-reverted`);
1. **(a)**, read-only from production: the site is curated, the cell's journal is continuous and
   ends at the live value (`plan.journal_break`), and its last link is a journal-reversal-3 row
   (`2026-09-25_mechanical-journal-reversal-3`) that wrote exactly the judged write's old value over
   its written value (`not-restored-by-journal-reversal-3`). The live value is then the old one.
2. **(b)** every counted route verdict that names a `right_value` names the same one
   (`judges-disagree`). A keep that names one names the written value, a revert the old one: either
   is a judge naming another value. (A stricter reading - a keep holds the written value even when it
   names none - lists none of the 13 written rows: no keep stands on their routes.)
3. **(c)** not the old value, not the reverted one; `site_type` on the canonical list (every
   canonical type is a fixed point of `normalize_site_type`, pinned by a test, so this is
   `normalize_site_type(v) == v` without the pass-through of an unknown word such as "Treasury");
   `period_start` an integer year as the database prints it (`apply.typed_value`), its bucket the one
   `categorize_period` and the frontend's `categorizePeriod` agree on, and the site's `period_name`
   written with it where the bucket differs from the live label (the label must hold a value and its
   journal end at it); `country` a T05 fixed point with an ISO code, never the United Kingdom spelled
   whole (B9: England, Scotland, Wales, Northern Ireland).
4. **(d)** a quote of a counted route verdict whose outcome in the audit's machine quote check is
   `found`, that states the value and stands in text about the site. **How "states the value" is
   decided**: `site_type` - a run of consecutive words of the quote that the pipeline's own normalizer
   resolves to the value (`normalize_site_type(run) == value`: the name in any case, or a synonym -
   "statue" is a Monument, "hillfort" a Fort; "fortified", "memorial", "sacred building" are not);
   `period_start` - the year's absolute value as a whole number followed by an era marker of its sign,
   directly or after the rest of a range (BC, BCE, B.C., B.C.E., a.C., a. C., v. Chr., av. J.-C.,
   пр. Хр.; AD, CE, A.D., C.E., d.C., d. C., n. Chr., ap. J.-C., or AD before the year) - a number
   without an era, a century or millennium, and "years ago" state nothing; `country` - the name
   standing whole, not inside a longer country name of the vocabulary. **How "about the site" is
   decided**: a quote from one of the row's own evidence files (fetched for this site; the audit's
   check accepts no other file) is; a quote from a fetched page is only when a distinctive word of the
   site's name, or the whole name, stands within 1,500 characters of it in the reading where the
   audit found it (`bcases.web_witness.named_near`, the identity rule the coordinate lane's web
   witnesses are held to). A page the audit found a quote on that cannot be read now, or no longer
   holds it, refuses the whole plan. Where none of this can be decided mechanically for a row, the row
   is listed (`no-verbatim-evidence`), never written.

Registered as a cell lane (`lane.WRONG_BOTH`): run stamp `2026-09-25_mechanical-wrong-both`, test id
`P6/wrong-both`, change keys `wrong-both:<site_id>:<column>`, plan table `_wrong_both_plan`, cells
`site_type` (owns the canonical types), `period_start` (integer), `period_name` (owns the nine bucket
labels) and `country`, the 10 s / 120 s bounds, no premise, no journal reversal: every cell is
conditioned on its old value (guard 3). Its list (`wrong_both_list.py`, generated by `--list`) is the
journal-reversal-3 row of each corrected cell; the residual is "curated sites still holding a restored
value a wrong-both correction replaces", and the read-back adds the list's superseded rows, the period
pair and the card country. `--write` refuses unless its corrections follow exactly that list.

### The run (2026-09-25, 06:42-06:46 UTC)

`wrong_both.py --list`, then `--write` (a new process: the lane imports the list), then
`apply.py --lane wrong-both --emit`. **Written: 17 cells over 13 sites - 13 corrections and 4 period
labels. Listed: 29 of the 42.** All 13 corrected cells are mass-lane rows (`phase3:batch-*`).

| site | column | restored -> correction | the quote that carries it (the audit found it) |
|---|---|---|---|
| Labna | period_start | 500 -> -200 (label `500 - 1000 AD` -> `500 BC - 1 AD`) | lugares.inah.gob.mx node 4427: "El sitio estuvo poblado desde el año 200 a.C. ..." ('labna' near) |
| Cissbury Ring | period_start | -1500 -> -3700 (label -> `4500 - 3000 BC`) | own enwiki: "This individual was recently radiocarbon dated to c. 3700 BC." |
| Caerau Hillfort | period_start | -1500 -> -3600 (label -> `4500 - 3000 BC`) | own enwiki: "... Finds included flint tools and weapons dating to 3600 BC." |
| Piddington Roman Villa | period_start | -3000 -> -50 (label `3000 - 1500 BC` -> `500 BC - 1 AD`) | own enwiki: "The site was occupied from about 50 BC, ..." |
| Castleshaw Roman Fort | site_type | Fortress/citadel -> Fort | own enwiki: "Castleshaw Roman fort was a castellum ..." |
| Sturminster Newton Castle | site_type | Residence/villa/farmhouse -> Fort | own enwiki: "... an Iron Age promontory fort." |
| Bull of the Corcyreans | site_type | Megalithic structures -> Monument | own enwiki: "The statue was made by the sculptor Theopropus from Aegina." |
| Siphnian Treasury | site_type | Megalithic structures -> Religious | own enwiki: "the first religious structure made entirely out of marble" |
| Sagaholm | site_type | Cemetery -> Barrow | own enwiki: "had a large barrow with a circle of slabs of sandstone ..." |
| El Jem Amphitheatre | site_type | Megalithic stones -> Amphitheatre | own Wikidata: "Roman amphitheatre of El Jem" |
| Amphitheatre of the Three Gauls | site_type | Megalithic structures -> Amphitheatre | own Wikidata: "Roman amphitheatre in France" |
| Arles Amphitheatre | site_type | Megalithic structures -> Amphitheatre | own enwiki: "is a Roman amphitheatre in Arles, southern France." |
| Amphitheatre Alba Fucens | site_type | Megalithic structures -> Amphitheatre | en.wikipedia Alba_Fucens: "The well-preserved amphitheatre (96 x 79 m) ..." ('alba' near) |

| listed because | rows | which |
|---|---|---|
| `not-reverted` | 2 | Wichqana (proposal Temple complex), Sidi Said (Fort): the final decision kept the written value |
| `not-restored-by-journal-reversal-3` | 6 | the five Northern-Ireland country rows (Annadorn Dolmen, Dooey's Cairn, Giant's Ring, Craigs Dolmen, Moylehid: the UK lane already wrote "Northern Ireland", the proposal) and Witham Shield (the site-type-shape lane restored the old value; proposal Archaeological site) |
| `judges-disagree` | 8 | Nine Stones (-2000 / -2500), Chanhudaro (-2500 / -3000), Altar of Athena Polias (Sanctuary / Religious), South Stoa I (Infrastructure / Ruin / Monument), Alvastra Pile-Dwelling (p1 revert names the old City/town/settlement, p2 Sacred site), Choquequirao (p1 names the old 1000, p2 1450), Península de Kola (p1 keep names Natural feature, p2 and tie Archaeological site), Pampas Gramalote (p1 keep names -2000, p2 and tie -1500) |
| `no-verbatim-evidence`: no found quote states the value | 8 | Holyhead Mountain Hut Circles -500 ("middle years of the first millennium BC"), Aquae Calidae -500 ("5th century BC", "1st millennium BC"), Carteia -400 ("siglo IV a. C."), Lalibela 900 ("dating to 900", no era), Cave of Aurignac -33000 ("about 35,000 years ago"), Palaestra at Delphi Archaeological site, Stoa Poikile Monument ("memorial"), Cnidian Treasury Religious ("sacred building") |
| `no-verbatim-evidence`: stated only in text not about the site | 5 | Nine Ladies Stone Circle -2500 (en.wikipedia Bronze_Age_Britain), Gårdstånga -1750 (Nordic_Bronze_Age), Maa Palaeokastro -3800 (Yeronisos), Argura -6300 (Sesklo: "at Argissa as early as c. 6300 BC"), Boeotian Treasury Religious (the Wikidata answer "sacred building housing religious offerings", which names "Boeotians", not the name word "boeotian") |

Each listed row is in `SKIPPED.jsonl` with its note; the 21 of `judges-disagree` and
`no-verbatim-evidence` are the ones for a human.

| file (`mechanical_wrong_both/`) | sha256 (LF text) |
|---|---|
| `PLAN.jsonl` (17 cells) | `df15695702cfce859a6f84000ea977399547da4c0015cb028482483df2544eb7` |
| `SKIPPED.jsonl` (29) | `a9af492f589768a733182a3e16fbb1572f8798b09fe5e1785dde3d61d45496f4` |
| `APPLY.sql` | `915b782a0c32b50261b855984c472ab07c9b92964969e3cb5dfacff18caaba4a` |
| `ROLLBACK.sql` | `1c12df0c7426ad3a04e7a03205ef6b1148a49a7682e7c96dbbfdfec35ebfbc4b` |
| `scripts/remediation/mechanical/wrong_both_list.py` (13 ids) | `e8e5d6e925e19bf4dec45f842f4017ec58cd6aa0bf83bf58eef5fa370b15f592` |

### On production (read-only, and one rehearsal), 2026-09-25 06:46 UTC

* `--check-primitive`: the 0022 body (casts the value, casts the old value, re-reads the stored
  value: t, t, t).
* `--verify` before the apply: curated sites 5,004; **curated sites still holding a restored value a
  wrong-both correction replaces 13**; journal rows of this list a later write superseded 0; curated
  rows whose period_name is not the bucket of period_start 9; card_stats rows whose civilization
  differs from the site country 61; every journal metric of the stamp, test id and rollback stamp 0.
* `--interests`: the (column, value) rows of the 17 cells' old and new values, with their live counts.
* **`--probe-guards` exit 0: 6 probes, each refused by its own guard, 0 journal rows left**
  (guard3-foreign-old-value, guard2-no-op, guard2-foreign-column, guard2-too-long,
  guard1-other-source, guard4-not-owned).
* **Rehearsal** (`--rehearse`): `NOTICE: wrong-both correction: 17 of 17 planned cell(s) changed and
  journalled over 13 curated site(s)`, `ROLLBACK`; journal rows for the stamp 0, the residual 13, the
  temp table gone.
* **Acceptance before** (`verify_writes.py`, read-only, with the five stamps applied so far): mass
  lane 499 carried, 495 superseded (site-type-shape 3, uk-parts 5, reversal-1 3, reversal-2 45,
  reversal-3 439), 80 withheld unchanged, **0 deviations**; gap lane 14 carried, 3 superseded by
  reversal-3, 12 withheld unchanged, **0 deviations**.

### The apply (the orchestrator runs it; the owner's go first)

From the repo root, main venv, `export PYTHONIOENCODING=utf-8`,
`A=scripts/remediation/mechanical/apply.py`:

0. **The plan still stands.** `./.venv/Scripts/python.exe $A --lane wrong-both --verify` -> the
   residual 13, journal rows for this run stamp 0, journal rows of this list a later write
   superseded 0. If anything moved: `./.venv/Scripts/python.exe scripts/remediation/mechanical/wrong_both.py --list`,
   then in a new run `... wrong_both.py --write`, then `$A --lane wrong-both --emit`, then
   `./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical_wrong_both.py tests/remediation/test_mechanical.py -q -m "not integration and not live_llm"`
   green, and commit the list and the lane directory before going on.
1. **Check.** `./.venv/Scripts/python.exe $A --check-primitive`;
   `./.venv/Scripts/python.exe $A --lane wrong-both --interests`;
   `./.venv/Scripts/python.exe $A --lane wrong-both --probe-guards` -> exit 0, the same 6 probes each
   refused by its own guard.
2. **Rehearse.** `./.venv/Scripts/python.exe $A --lane wrong-both --rehearse` -> `17 of 17 planned
   cell(s) changed and journalled over 13 curated site(s)`, ROLLBACK, 0 journal rows.
3. **Apply.** `./.venv/Scripts/python.exe $A --lane wrong-both --apply` -> `APPLY OK: the read-back
   matches the plan, row for row` (exit 0; exit 3 NOT COMMITTED, 5 OUTCOME UNKNOWN - read the journal
   for the stamp before anything else, never apply twice).
4. **Read back.** `./.venv/Scripts/python.exe $A --lane wrong-both --verify` -> journal rows for this
   run stamp 17 and for this test id 17, **the residual 0**, the list's rows a later write superseded
   0, 0 outside the lane's cells, on non-curated rows or with another site's `site_id_ref`; the
   period pair 9 and the card country 61 unchanged (every start is written with its bucket's label;
   no country is written).
5. **Rehearse the rollback on the landed rows.**
   `./.venv/Scripts/python.exe $A --lane wrong-both --rehearse-rollback` -> `17 of 17`, ROLLBACK, the
   cells still holding the corrections; commit `REHEARSAL_ROLLBACK.sql` as for the reversal lanes.
6. **Acceptance.**
   `./.venv/Scripts/python.exe output/remediation/tools/verify_writes.py --allow-stamp 2026-09-22_mechanical-uk-parts --allow-stamp 2026-09-22_mechanical-site-type-shape --allow-stamp 2026-09-23_mechanical-journal-reversal-1 --allow-stamp 2026-09-23_mechanical-journal-reversal-2 --allow-stamp 2026-09-25_mechanical-journal-reversal-3 --allow-stamp 2026-09-25_mechanical-wrong-both`
   -> `RESULT: 0 deviation(s)`: 499 carried, 495 superseded - reversal-3 439 - 13 = 426,
   wrong-both 13, the others unchanged - and 80 withheld unchanged; and
   `./.venv/Scripts/python.exe output/remediation/tools/verify_writes.py --lane gap --allow-stamp 2026-09-25_mechanical-journal-reversal-3 --allow-stamp 2026-09-25_mechanical-wrong-both`
   -> 0 deviations, unchanged (14 carried, 3 superseded by reversal-3): no corrected cell is a gap row.

Afterwards: re-plan the scope lane and the card_stats recompute (their premises and cards derive
from these columns), and the static export - none of them is run here.

### Ahin Posh Tape's coordinates: no second independent witness, not planned

The stored point, 33.66801142959909, 70.95519786406209 (in Pakistan), came from Wikidata Q4695118,
which conflates the stupa near Jalalabad with a Pakistani village (wave 1 classed the site
`not-comparable`, container item). Its country is already Afghanistan (journal-reversal-1). A third,
hand-read coordinate wave was to take it with at least two independent witnesses, each quoted and
machine-checked from its fetched page. The pages were fetched once, 2026-09-25 07:00 UTC, with the
project User-Agent, and checked with the coordinate lane's own reader (`web_witness.page_text` /
`normalise`, `occurrences` - the quote standing whole -, `parse_coordinates`, `named_near`; the PDF
through `opus_audit.quotes.pdftotext`), then weighed with `classify.independent` and `classify.weigh`:

| witness | page (sha256 of the body) | quote | reads | name near it |
|---|---|---|---|---|
| enwiki "Ahin Posh", revision 1366870556 | `index.php?title=Ahin_Posh&oldid=1366870556` (`3ee399ce...d734`) | "34.412045°N 70.452130°E" | 34.412045, 70.45213 | "ahin" |
| Errington 2017, *Charles Masson and the Buddhist Sites of Afghanistan* (British Museum Research Publication 215), citing Ball and Gardin 1982, no. 17 | zenodo.org record 3355036, the PDF (`eeb1864a...f725`) | "lat. 34º24´N; long. 70º27´E" ("Ahin Push ... a stupa courtyard and adjacent monastery ... on a hill c. 2km south of Jalalabad") | 34.4, 70.45 | "ahin" |
| Pleiades 59662 "Ahin Posh" (Barrington Atlas 6 C3; DARMC location 21491, "5M scale point location") | `pleiades.stoa.org/places/59662/json` (`82900f53...9571`), JSON | its point | 34.288484, 70.234278 | - |

* enwiki and Errington: **1,354 m apart, not independent** under the lanes' rule - Errington's value
  is the enwiki point cut to whole arcminutes ("web is enwiki rounded to whole arcminutes"), and one
  arcminute step is 1,855 m. Had they counted as two, they would still not agree: 1,354 m is over the
  1,000 m tolerance.
* Pleiades: 24.3 km from enwiki and 23.4 km from Errington - disagrees (a point read off a
  1:5,000,000 map).
* `weigh` over the three: **review**, "no two of the 3 witnesses are independent and agree". All three
  put the site about 95 km from the stored point, near Jalalabad - the stored point is wrong - but no
  pair of them passes the rule that decides a move.

Not reachable as a witness from this workstation: GeoNames, the DAI gazetteer and OpenStreetMap
(Nominatim) have no Ahin Posh; the Getty TGN endpoint and the British Museum collection answer 403 to
the project User-Agent; the web search budget of this session was spent. **No coordinate is planned
and no third wave is added**: a wave whose only case fails the witness rule would render nothing.
The case is the owner's (FIELD_CONTRACT section 4.6): the enwiki point, with Errington 2017 /
Ball and Gardin 1982 placing the stupa within that arcminute cell 2 km south of Jalalabad, is the
reading to put before him.

### Tests, sweeps, gates (main checkout, branch `integrate/wave1`, main venv)

* `tests/remediation/test_mechanical_wrong_both.py`: 107 cases, red before the code (the module did
  not exist): the candidates and their refusals, every rule and its reason, what a quote states
  (types, years with and without their era, countries), about the site, the period label, the
  country convention, the readers' statements, `--list` / `--write` and their refusals, the lane's
  registration and residual, and two tests on the delivered plan (it follows exactly the lane's list;
  every written value is named by all its counted judges and carried by a found quote of theirs).
  The generic lane tests of `test_mechanical.py` now cover `wrong-both` too (its committed statements
  are what `--emit` renders, its probes, its commit states).
* **`mechanical/mutation_sweep.py wrong-both`: cases 67, fired 67** (37 guards and 23 replacements in
  `wrong_both.py`, 7 in its `lane.py` registration; skipped, survived, invalid, unproven, errored 0).
  Every existing case on `lane.py`: 42 of 42 fired; `reversal`: 95 of 95 (93 plus two of the new
  labels). Every needle of all cases matches once (`test_mechanical_sweep.py` green); the files
  restored byte for byte, no `# mutant` left.
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`, `-p no:cacheprovider`):
  **6,225 passed, 6 skipped, 57 deselected, 0 failed** (210 s); the skips are the six of the
  rounds before (two refactored-away article tests, the opt-in Shining Ones regen, three card_stats
  tests whose gitignored export this checkout does not hold).
* `ruff check` and `ruff format --check` clean on the 5 touched Python files (ruff 0.15.11);
  `ruff check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean.

## 2026-09-25 - scope-e4, Dedan's thumbnail and card-stats-2026-09-23 re-planned against today's production; Chiapa de Corzo / Zoque decided from data (checked and rehearsed; not applied)

Branch `integrate/wave1` (main checkout). Since the last plans of these lanes (2026-09-23),
production changed: journal-reversal-3 (488 cells over 435 sites: `site_type`, `period_start`,
`period_name`, `country`) and the wrong-both lane (17 cells over 13 sites) were applied, and the
Phase-4 mass run keeps writing `description` and `raw_data` of defect-scope sites
(`phase4:p4-00NN:chunk-0001`; 57 batches and 982 journal rows when this work began). **Production
was read (SELECTs) and rehearsed (every statement ended in ROLLBACK, 0 journal rows left); nothing
was applied, no model was called; `opus_handoff.py`, `phase3/fetch_stage.py`, `phase3/ledger.py`
and `.claude/worktrees/` are untouched.**

| commit | what |
|---|---|
| `0326fe1` | scope-e4 re-planned, five stale decisions out of `DECISIONS.json` |
| `b14afdb` | card_stats: a Phase-5 card text names no basis (test-first) |
| `272411d` | 4 mechanical sweep cases for it |
| `aac083b` | card-stats-2026-09-23 re-planned; `e5a34d4` triages its premise digests for gitleaks |
| `cad1e14` | `hero_repair/thumbnail.py`: T1 for a thumbnail on its site's excluded row (test-first); T1 names the NULL case |
| `cf1f557` | Dedan's thumbnail chunk (1 row) |
| `d9825c5` | 11 mechanical sweep cases for the thumbnail lane |

The independent acceptance, read with none of the three applied (`verify_writes.py`, read-only,
with the six stamps applied so far): mass lane 499 carried, 495 superseded (site-type-shape 3, uk-parts 5,
reversal-1 3, reversal-2 45, reversal-3 426, wrong-both 13), 80 withheld unchanged, **0 deviations**;
gap lane 14 carried, 3 superseded by reversal-3, 12 withheld unchanged, **0 deviations**. None of the
three lanes below writes a column that acceptance reads.

### 1. scope-e4: 109 sites, 218 cells, 0 refused

Re-planned from the export of 2026-09-25 07:16:05 UTC (`scope.py --export --collect`, then
`--write`): **78 retired** (54 rule a, 2 rule b, 19 rule c duplicates, 3 museums), **14 pending**
(3 rule a, 11 rule b), **17 in_scope** (museums); T11 90 findings (96 on 2026-09-23). Against the
2026-09-23 plan (115 sites, 230 cells):

* **Lalibela** left rule (a): journal-reversal-3 restored `period_start` 1200 -> -500 (row 35897).
* **Five rule-(a) `pending` decisions had no finding any more** and the planner refused them as
  `decision-without-finding`: each answered a phase-3 `period_start` write that had moved the site
  out of the window ("A period_start question before a scope one"), and journal-reversal-3 undid
  that write - Damascus Gate 1537 -> 1 (35670), Foso e Interior Citadelle De Victoria 1500 -> -3000
  (36102), Gårdstånga 900 -> -4500 (35860), Panamá Viejo 1519 -> 1000 (36014), Skopje Aqueduct
  1600 -> 1 (36038). The question is answered, so the five entries left `DECISIONS.json` (36 remain:
  a/pending 3, b/pending 11, b/retired 2, d/in_scope 17, d/retired 3; `_about` names the removal).
* Premises moved on five sites, all still decided the same way: Preah Palilay and Shanqal Fort
  (`site_type` restored by reversal-3; still retired), Dooey's Cairn (`period_start` -4000 -> -4500;
  still a duplicate), Yenikale Ruins (the owner-case coordinate wave moved its point), Augusta
  Bilbilis (its description rewritten by `phase4:p4-0030`; a listed duplicate, no quote).
* **The 19 owner-case duplicates** (`bcases/DUPLICATES.jsonl`) all still hold in the export: both
  rows curated, both carrying the item the line names, within 2 km. 3 are also found by the lane's
  own 100 m rule (Tarxien Temples, Bishop's Basilica of Philippopolis, Dooey's Cairn: one retirement,
  both evidences). The Banias / Caesarea Philippi pair stays held (`DUPLICATES_HELD.jsonl`, B10).

**What is decided about the duplicates, and what is not.** HANDOVER section 6 and HUMAN_ONLY (B1/B2)
list the 19 losers "for the scope lane", and the 2026-09-23 apply order put the owner's per-site go
(HUMAN_ONLY "Was nur du entscheiden kannst" item 2, B6) before the scope apply. Neither file records
that go. So the plan carries them as intended, and the apply below waits on it. Should the owner
refuse some, their pairs go into `DUPLICATES_HELD.jsonl` (the lane refuses a held pair whoever
found it, the lane's own rule included) and the lane is re-planned; nothing in the code changes.

**On production** (07:21-07:22 UTC): `--check-primitive` the 0022 body (t, t, t); `--verify` before:
curated sites 5,004, `scope_status` NULL 5,004 (in_scope/pending/retired 0), **curated rows outside
the E3 window with no scope decision 75**, curated rows without a date and no scope decision 15,
retired as a duplicate 0, every journal metric of the stamp, test id and rollback stamp 0;
`--interests`: `scope_status` and `scope_reason` NULL on 5,004 rows each; **`--probe-guards` exit 0,
6 probes each refused by its own guard, 0 journal rows left** (guard3-foreign-old-value,
guard2-no-op, guard2-foreign-column, guard1-other-source, guard4-not-owned, guard5-premise);
**`--rehearse`: `NOTICE: E4 scope decision: 218 of 218 planned cell(s) changed and journalled over
109 curated site(s)`, ROLLBACK**, journal rows for the stamp 0, the temp table gone. Computed from
the plan and the export: after the apply every one of the 75 out-of-window rows and the 15 undated
ones carries a decision.

**The Phase-4 run and this plan.** The premise holds `md5(description)`. Of the 109 sites, one has a
Phase-4 description so far (Augusta Bilbilis); a Phase-4 write to any other planned site between the
plan and the apply makes guard 5 refuse the whole transaction (psql exit 3, NOT COMMITTED - nothing
lands). 36 decisions quote their site's description; a rewritten description may no longer hold the
quote, and the re-plan then refuses it (`quote-not-in-description`) - re-read that decision against
the new text, never apply around it.

| file (`mechanical_scope/`) | sha256 (LF text) |
|---|---|
| `PLAN.jsonl` (218 cells) | `b066c84cc67a50929db91daa7ad6f0ca2744dbbae4f367cbaf9d2a7f0f9d4506` |
| `SKIPPED.jsonl` (0) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `APPLY.sql` | `d06ac5eba3e1554f8b4d4b5b213ccaccd2dc76d9080781b93d2700875fba2dbe` |
| `ROLLBACK.sql` | `fe86a3f59b31b10fa1c6d8ecc80c7053a80a7beaf5c37f2fe979e98ea4675bc3` |
| `DECISIONS.json` (36) | `94d997f81cf6c4673aa84908bfac100f9fa9a1b08c31f0bdcadd6b8bc8b712b8` |

### 2. Chiapa de Corzo / "Zoque Culture Archaeological Zone": the same site, not covered by the duplicate rules

Read 2026-09-25 (production read-only; Wikidata `wbgetentities` for Q4384315 with the project
User-Agent):

* **The data says one site.** The two points are **7.4 m** apart (16.702978, -93.004036 /
  16.703006, -93.004100); both rows have the thumbnail `Mound_1.JPG`; both descriptions describe the
  same place - the Zoque capital of 70 hectares, the pyramid tomb found in Mound 11 in 2010 with
  about 4,000 pieces of jade, pearl shell and amber, the E-Group. Chiapa de Corzo's `source_url`
  held a second URL until `2026-09-23_source-url-split-wave4` (journal row 32153):
  `https://en.wikipedia.org/wiki/Chiapa_de_Corzo_(Mesoamerican_site)` - the Zoque row's own
  `source_url` and `enwiki_title`, the article of Q4384315, the item the Zoque row carries.
* **The rules do not cover it.** Both duplicate rules - the scope lane's rule (c) and `bcases`'
  DUP (`classify_pairs`) - require both rows to carry one Wikidata item and both names to be names
  of it. (a) Chiapa de Corzo (`24aa135d-4714-47f5-96c0-d58f0bc04b6f`) carries **no** item: wave 4
  left it unlinked precisely because the Zoque row already carries Q4384315 (AUDIT_LOG, "the 20
  two-URL `source_url` values"). (b) Even linked, the pair would be PART-OF, not DUP: "Chiapa de
  Corzo" is Q4384315's English label, but "Zoque Culture Archaeological Zone" is none of its names
  (labels, aliases and sitelinks in every language, fetched today: "Zona Arqueológica de Chiapa de
  Corzo", "Chiapa de Corzo (Mesoamerican site)", "Chiapa de Corzo (lloc arqueològic)", ...).
* So it is **not added to `DUPLICATES.jsonl`**; it is recorded for the owner (HUMAN_ONLY, B1/B2,
  "Was nur du entscheiden kannst" item 7). Both survivor rules would keep the Zoque row
  (`ed186ea9-9ed1-415d-828b-97d9f21401d2`: 3 content links, 20 images, the Wikidata and enwiki ids)
  over Chiapa de Corzo (0 links, 0 images, no id) - and the survivor would then carry the name
  Wikidata does not know. Which row and which name stay is the owner's call.

### 3. Dedan: the thumbnail on the excluded hero is cleared (1 row)

The liveness lane (`img-liveness-2026-09-23-001`) excluded both image rows of the Lion Tombs of Dedan
(87351, 87352) - Commons deleted `File:Dedan tomb 1.jpg` (log 406863718) and `File:Ddan tomb 2.jpg`
(log 406863689) as copyright violations; both are still missing today - and took the hero flag off
87352 (journal 32263-32265). `unified_sites.thumbnail_url` still named 87352's local file,
`/data/images/wiki/9a9a0dca/hero.webp`, which the globe (`/api/sites/all` field `i`), the static
export and the SSR fallback go on serving (the file answers HTTP 200, 110,950 bytes).

No lane wrote `thumbnail_url` (T1 was W13's, never built; `hero_repair/` holds the flag repair only).
**`scripts/remediation/hero_repair/thumbnail.py`** (the file design entry 7 names for W13) now plans
T1 for exactly the class whose inputs are final: a curated site whose thumbnail is the local path
(`/data/images/wiki/<site_id_short>/<filename>`, `pipeline.sites_html_renderer.site_id_short`) of one
of its **own excluded** rows and of no live row. T1 is the served image's file
(`gallery_audit.worklist.served_row` - where the liveness lane's hero promotion by the hero repair's
rule already sits), or **NULL when the site serves no image**; the sealed rule table's T1 now says
so (`decide.RULES`, pin `419c4ff5...`; the applied liveness chunk cites the table before,
`2380f7a0...`). It reads production read-only (the candidates, all their image rows, the journal rows
of their excluded rows), keeps the read as `READ.json` and writes its chunk through the shared image
writer: lane `thumb-repoint`, test id `H4/thumbnail`, run stamp `thumb-repoint-2026-09-25-001`.

* **Measured** (07:40 UTC): the class is **one site, Dedan**; its own gallery has **no live row**,
  so the hero rule has no candidate and the plan clears the thumbnail: `/data/images/wiki/9a9a0dca/
  hero.webp -> NULL`, evidence wiki_images:87352, journal rows 32264 and 32265, and `served_row`
  over its 2 rows. (Of all curated sites, 1,013 serve no live image and 162 of those carry a
  thumbnail - the rest of W13, not this class.)
* `chunk_writer.py <chunk> --check`: `CHECK OK ... 1 row(s)`; **`--rehearse` on production: the
  transaction ran its guards, journalled 1 row, planned rows 1, ROLLBACK; `REHEARSAL OK: chunk 001,
  1 row(s), rolled back`** (0 journal rows kept).
* **Dedan's card moves with it**: `cultural_influence` reads "has a thumbnail". Recomputed on the
  card export: 9 -> 8, `total_power` 23 -> 22, `rarity_score` 35 -> 33, tier 3 unchanged. So the
  thumbnail goes **before** the card_stats wave (its premise holds `md5(thumbnail_url)`: the other
  order would refuse that wave).
* **Not in the database, and not this lane's**: the local files of all six rows the liveness lane
  excluded are still on the VPS and publicly served by URL (read: `hero.webp` and `Dedan_tomb_1.webp`
  under `9a9a0dca/`, the Olympia, Stoa of Eumenes and Theatre of Dionysus files; Chesterfield's name
  holds an apostrophe the check did not quote). The image lanes never delete files (design entry 7);
  whether copies of files Commons deleted as copyright violations stay on our server is the owner's
  (HUMAN_ONLY, item 8).

| file (`hero_repair/thumbnail-2026-09-25/`) | sha256 (LF text) |
|---|---|
| `READ.json` | `43d856b72fca370d6152331a80726cf050559d50cc082e7804b4ebf1e3d62a4c` |
| `chunk-001/PLAN.jsonl` (1 row) | `7d7118cfb6c4c010a27bfd77cee982fdf2d6c9a7bc80a50925492c5da1f1fe47` |
| `chunk-001/APPLY.sql` (plan sha256 `aefe53b6...70ee`) | `68906fbad98d9298c427e4e52ed71110bfe62873090a67d2660b5d8a81545687` |
| `chunk-001/ROLLBACK.sql` | `120c4423770aa4e01f0769bc907f5ea20e1722e610fd360571413c5c69d65299` |

### 4. card-stats-2026-09-23: 3,982 cells over 1,055 cards (the first wave, never applied)

The journal holds **0** `card_stats` rows: the wave planned on 2026-09-23 was never applied, so it
is re-planned under its own label (`--wave 2026-09-23`, stamp `2026-09-23_mechanical-card-stats`).

* **Plan** from the export of 2026-09-25 07:30:33 UTC (sha256 `09032380...62f6a`): the counterfactual
  put back **2,390** journalled input values and reproduced **all 60,048** stored cells (0 differ;
  the first wave's basis). **3,982 cells over 1,055 of 5,004 cards, 0 refused** (659 of the cards on
  sites with a journalled field write): antiquity 180, fortification 257, category_group 257,
  cultural_influence 0, mystery 894, legacy 27, total_power 961, rarity_score 916, rarity_tier 356,
  civilization 61, empires 37, empire_count 36. rarity_tier moves 1->2 16, 1->3 18, 2->1 10, 2->3 123,
  2->4 3, 3->1 3, 3->2 55, 3->4 71, 4->3 49, 4->5 5, 5->4 3. **Owned cards** (`card_collections`,
  read-only): 6 rows of 4 users on 6 sites change stats, 1 row (1 user, 1 site) changes rarity.
* **Phase 5.** P5 writes `card_stats.card_description` under `phase5:p5-NNNN:chunk-NNNN`
  (`phase4/write4.py`). The lane never writes it (its cells are the generator's twelve columns;
  pinned, and on production: a copy of the plan with one cell renamed to `card_description` was
  refused by guard 2, `card_stats recompute: 1 planned row(s) are not writable changes`, psql exit 3,
  0 journal rows), and neither its premise nor its export reads it, so a card text written between
  this wave's plan and its apply expires neither guard 3 nor guard 5. P5's own preflight reads the
  card row's existence and its `card_description` - neither is written here. **One conflict was
  real and is fixed** (`b14afdb`): `basis_pointer` read every `card_stats` journal row, so the first
  P5 card text would have made every later card_stats wave - the completion read-back included -
  refuse with "no card_stats wave's write or undo". It now reads the rows of the twelve columns; a
  write to one of those that no wave made still refuses, whoever made it.
* **Phase 4.** The premise holds `md5(description)` of every planned card, and `_is_unesco` reads the
  description text. A Phase-4 batch (15 sites) touches one of the 1,055 planned cards almost surely,
  so a Phase-4 write between this wave's export and its apply refuses the transaction (guard 5,
  exit 3, NOT COMMITTED): export, plan, check and apply in one pause of the Phase-4 writer. Phase 4's
  later descriptions can move `cultural_influence` again; the completion read-back will show that as
  cells, and a later wave recomputes them.
* **scope-e4 does not touch a card input**: the generator counts every curated row whatever its
  `scope_status`, and neither the export nor the premise reads a scope column. The card_stats wave
  therefore does not wait on the scope lane's owner gate - only on Dedan's thumbnail.
* **On production** (07:31-07:32 UTC): `--verify` before: tiers 525 / 1,796 / 2,310 / 353 / 20,
  **curated rows whose card_stats civilization differs from the site country 61**, total_power not
  the sum 0, curated sites without a card row 0, every journal metric 0; `--interests` 151
  (column, value) rows; **`--probe-guards` exit 0, 7 probes each refused by its own guard, 0 journal
  rows left** (guard3-foreign-old-value, guard2-no-op, guard2-foreign-column, guard2-too-long,
  guard1-other-source, guard4-not-owned, guard5-premise), plus the `card_description` probe above;
  **`--rehearse`: `NOTICE: card_stats recompute: 3982 of 3982 planned cell(s) changed and journalled
  over 1055 curated site(s)`, ROLLBACK**, 8 s end to end, journal rows for the stamp 0, temp table
  gone. On today's plan the apply leaves tiers 504 / 1,731 / 2,371 / 376 / 22 and civilization drift
  0 (computed from the plan's moves).
* gitleaks over the re-plan commit found nine guard-5 md5 premises next to "Krapina" ('api') and
  "Keynes" ('key'); triaged in `.gitleaksignore` (`e5a34d4`) like the first plan's. **The re-plan
  before the apply writes new ones: scan its commit.**

| file (`mechanical_card_stats/2026-09-23/`) | sha256 (LF text) |
|---|---|
| `PLAN.jsonl` (3,982 cells, gitignored) | `551f88e6a60d0201ed9b86eb9a7774334dea0bf8887515107d49e3b2875efd7c` |
| `APPLY.sql` (gitignored) | `3d966a36a69326eac00be47ffe368fdcc953ecb71006df7c1b1c57db5b84faf3` |
| `ROLLBACK.sql` | `6263f031cbef7bdf839f295617fe3f7ad3c6a1446d767822a1e95a105c832c9b` |
| `BASIS.json` | `f452491c301924130db174c58e0f9c7f6cb1b9a0d4a73aafc21c75cc4fe3b839` |

### The apply (the orchestrator runs it)

From the repo root, main venv, `export PYTHONIOENCODING=utf-8`,
`A=scripts/remediation/mechanical/apply.py`, `CW=scripts/remediation/gallery_audit/chunk_writer.py`.
Order: **A** (after the owner's go), **B**, **C last**; B and C do not wait for A.

**A. scope-e4** - owner gate first: HUMAN_ONLY B1/B2 item 2 (B6), the per-site go for the 19
duplicate retirements. A refused pair goes into `bcases/DUPLICATES_HELD.jsonl` before step A1.

1. **Re-plan** (the premise ages with every Phase-4 description):
   `./.venv/Scripts/python.exe scripts/remediation/mechanical/scope.py --export --collect`, then
   `./.venv/Scripts/python.exe scripts/remediation/mechanical/scope.py --write` -> read its counters
   (today `sites 109, cells 218, refused 0`); a `quote-not-in-description` refusal is a decision to
   re-read against the new description, never to apply around. Then
   `./.venv/Scripts/python.exe $A --lane scope-e4 --emit`,
   `./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical_scope.py tests/remediation/test_mechanical.py -q -m "not integration and not live_llm"`
   green, commit `mechanical_scope/`.
2. **Check.** `./.venv/Scripts/python.exe $A --check-primitive`;
   `./.venv/Scripts/python.exe $A --lane scope-e4 --verify` (outside the E3 window with no decision =
   the plan's rule-a/d count of out-of-window rows, today 75; journal rows for the stamp 0);
   `./.venv/Scripts/python.exe $A --lane scope-e4 --interests`;
   `./.venv/Scripts/python.exe $A --lane scope-e4 --probe-guards` -> exit 0, the same 6 probes.
3. **Rehearse.** `./.venv/Scripts/python.exe $A --lane scope-e4 --rehearse` -> `E4 scope decision:
   <n> of <n> planned cell(s) changed and journalled over <s> curated site(s)`, ROLLBACK, 0 rows.
4. **Apply**, right after a Phase-4 chunk has landed:
   `./.venv/Scripts/python.exe $A --lane scope-e4 --apply` -> `APPLY OK: the read-back matches the
   plan, row for row` (exit 3 NOT COMMITTED: re-plan from 1; exit 5 OUTCOME UNKNOWN: read the journal
   for the stamp first, never apply twice).
5. **Read back.** `./.venv/Scripts/python.exe $A --lane scope-e4 --verify` -> on today's plan:
   journal rows for this run stamp 218 and for this test id 218; `scope_status` retired 78, pending
   14, in_scope 17, NULL 4,895; retired as a duplicate 19; **outside the E3 window with no scope
   decision 0; without a date and no scope decision 0**; a scope_status but no scope_reason 0;
   retired duplicates whose survivor is retired or not curated 0; 0 outside the lane's cells, on
   non-curated rows or with another site's `site_id_ref`.
6. **Rehearse the rollback on the landed rows.**
   `./.venv/Scripts/python.exe $A --lane scope-e4 --rehearse-rollback` -> the NOTICE, ROLLBACK, the
   cells still holding the decisions; commit `REHEARSAL_ROLLBACK.sql`.
7. **Acceptance.** The two `verify_writes.py` runs of the "acceptance before" above, unchanged (0
   deviations; the lane writes no field they read). `/api/sites/all` serves from a 30-minute Redis
   cache: the retired sites leave the globe with it, the static data with the next export.

**B. Dedan's thumbnail** (`C=output/remediation/hero_repair/thumbnail-2026-09-25/chunk-001`):

1. `./.venv/Scripts/python.exe $CW $C --check` -> `CHECK OK ... 1 row(s)`; then read-only
   `SELECT thumbnail_url FROM unified_sites WHERE id = '9a9a0dca-52c8-44c2-94f6-adb655db17dd'` ->
   `/data/images/wiki/9a9a0dca/hero.webp` (anything else: re-plan with `thumbnail.py chunk --out`
   into a new dated directory, never over this one).
2. `./.venv/Scripts/python.exe $CW $C --rehearse` -> `REHEARSAL OK: chunk 001, 1 row(s), rolled back`.
3. `./.venv/Scripts/python.exe $CW $C --apply` -> `APPLY OK: chunk 001, the read-back matches plan
   and journal both ways` (exit 5: read the journal for `thumb-repoint-2026-09-25-001` first).
4. `./.venv/Scripts/python.exe $CW $C --readback` -> `READBACK OK: 1 row(s), plan = journal = data`.
5. `./.venv/Scripts/python.exe $CW $C --rehearse-rollback` -> `ROLLBACK REHEARSAL OK`.
6. **Acceptance**: `./.venv/Scripts/python.exe scripts/remediation/hero_repair/thumbnail.py chunk --out C:/tmp/thumbnail-2026-09-25`
   -> exit 1, `no thumbnail names an excluded row of its own site: nothing to plan` (the class is
   empty; it writes nothing), and Dedan's `thumbnail_url` reads NULL. Commit nothing new here.

**C. card-stats-2026-09-23, last** - after B, in one pause of the Phase-4 writer (steps 1-5 within
it; a Phase-4 write in between refuses step 5 with exit 3 and nothing lands):

1. **Re-plan**: `./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave 2026-09-23 --export`,
   then `--wave 2026-09-23 --write` -> `counterfactual_cells_differing 0` (it refuses otherwise) and
   `skipped 0`; expect today's 3,982 cells plus Dedan's three (`cultural_influence` 9 -> 8,
   `total_power` 23 -> 22, `rarity_score` 35 -> 33) plus whatever Phase 4 moved since. Then
   `./.venv/Scripts/python.exe $A --lane card-stats-2026-09-23 --emit`,
   `./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical_card_stats.py tests/api/test_cardgame_generator_stats.py -q -rs -m "not integration and not live_llm"`
   green with 0 skipped (the export is present), commit `PLAN.md`, `SKIPPED.jsonl`, `ROLLBACK.sql`,
   `BASIS.json`, then `gitleaks git . --config .gitleaks.toml --gitleaks-ignore-path .gitleaksignore --log-opts="HEAD~1..HEAD"`
   and triage its premise digests as in `e5a34d4`.
2. **Check.** `./.venv/Scripts/python.exe $A --lane card-stats-2026-09-23 --verify` (journal rows for
   the stamp 0; civilization drift 61 unless a country moved); `--interests`; `--probe-guards` ->
   exit 0, the same 7 probes.
3. **Rehearse.** `./.venv/Scripts/python.exe $A --lane card-stats-2026-09-23 --rehearse` -> `card_stats
   recompute: <n> of <n> planned cell(s) ... over <s> curated site(s)`, ROLLBACK, 0 rows (8 s today,
   the statement bound is 120 s).
4. **Apply.** `./.venv/Scripts/python.exe $A --lane card-stats-2026-09-23 --apply` -> `APPLY OK`.
5. **Read back, straight after.** `./.venv/Scripts/python.exe $A --lane card-stats-2026-09-23 --verify`
   -> **civilization drift 0**, total_power not the sum 0, journal rows for this run whose row is
   not a card_stats row 0, journal rows for the stamp = the plan's cells, the tier counts of the
   plan's moves (today 504 / 1,731 / 2,371 / 376 / 22 before Dedan and Phase 4).
6. `./.venv/Scripts/python.exe $A --lane card-stats-2026-09-23 --rehearse-rollback` -> the NOTICE,
   ROLLBACK (it expires at the next field write, HANDOVER section 7).
7. **Completion**: `./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave 2026-09-23b --export`,
   then `--wave 2026-09-23b --write` -> `"cells": 0` and no statement written (a read-back, not a
   wave: neither applied nor committed). Cells here after a Phase-4 description landed are the
   next wave's work, not a failure of this one.

### Tests, sweeps, gates (main checkout, branch `integrate/wave1`, main venv)

* card_stats (`test_mechanical_card_stats.py`, +4): a Phase-5 card text names no basis (the unit and
  the whole next-wave plan) - both red before `b14afdb` -, a stats cell written under a Phase-5
  stamp still refuses, and the lane neither writes nor reads `card_description`. With today's export
  on disk the three export tests run too: **57 passed, 0 skipped** (with
  `tests/api/test_cardgame_generator_stats.py`).
* thumbnail (`test_hero_thumbnail.py`, new, 14 cases; red before the module existed): the path is
  the site's short id, NULL for a site that serves no image, the served row (hero, then lead, then
  sort_order; a NULL exclusion is live) otherwise, the candidates that are not this class listed,
  the refusals, the stamp, the command over a faked production and the delivered chunk re-derived
  from its `READ.json`. `test_gallery_vision.py`'s rule-table pin moves with T1.
* scope: `test_mechanical_scope.py` and `test_mechanical.py` on the new plan: **431 passed**.
* **`mechanical/mutation_sweep.py "card_stats:"`: cases 43, fired 43** (39 before, 4 new);
  **`"img thumbnail:"`: cases 11, fired 11**; `phase3/mutation_sweep.py` on the 32 cases of
  `gallery_audit/decide.py`: **32/32 caught**. Skipped, survived, invalid, unproven, errored 0; the
  trees byte-identical afterwards, no `# mutant` left; `test_mechanical_sweep.py` green (every needle
  matches once).
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`, `-p no:cacheprovider`):
  **6,246 passed, 3 skipped, 57 deselected, 0 failed** (216 s); the skips are the two
  refactored-away article tests and the opt-in Shining Ones regen - the three card_stats export
  tests of earlier runs now run, the export being on disk.
* `ruff check` and `ruff format --check` clean on the 7 touched Python files (ruff 0.15.11);
  `ruff check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean; gitleaks over the new commits clean after the
  triage.


## 2026-09-25 - the gallery audit's C1 calibration sealed again for Opus, and its 939 questions handed off (no model called, nothing written)

Main checkout, branch `integrate/wave1`, commits `5d3e8e8` .. this one. Owner order 2026-09-23
(Martin): "no DeepSeek any more - everything with Opus". **No model was called** (no DeepSeek, Pi,
opencode gateway or MiniMax, in code or in tests) and **nothing was written to production**; one
read-only production query (the `wiki_images` journal stamps, for the G-run state below).

### What C1 measures, and its pass rule (design entry 7 `pilot_and_thresholds`; `calibrate.THRESHOLDS`, unchanged)

* **Sample** (939 questions): the gallery question (`gallery-v1`) on 889 images - (i) the 200 pilot
  tiles (`vlm_pilot/SAMPLE.jsonl`, seed 20260921, 50 per tier) with the pilot's kinds, (ii) the
  652-row labelled set (the tracked fixture; 64 foreign rows resolve), 5 images in both, (iii) all 42
  rows of the gold galleries Agri Bavnehoj, Langdale and Xcaret, of which 12 are gold-foreign and 13
  gold-correct - and the hero question (`hero-v1`) on the 50 tier-A tiles.
* **Thresholds**: T0 - every question has an in-vocabulary verdict, else nothing is admitted. T-kind
  (K1/K2 `image_kind` writes) - pilot-kind agreement >= 0.90 on (i) and non-photo precision >= 0.90
  on (ii). T-X1 (`other_site` exclusions) - >= 60 foreign rows resolve, precision >= 0.85 and recall
  >= 0.70 on (ii), all 12 gold-foreign flagged, at most 1 of 13 gold-correct flagged. T-X2 (people),
  T-X3 (other) - precision as "not this site" >= 0.85 with >= 10 flags on (ii) + (iii). T-strict
  (`HERO_PROMPT`; K2, H1) - on the 50 tier-A tiles with eye labels, precision >= 0.90 and recall
  >= 0.60.
* **Pass rule**: each trigger is admitted on its own numbers (Clopper-Pearson 95 % intervals);
  a failing trigger is dropped, never re-tuned; no threshold changes after its data is seen.
  `ADMISSION.json` is re-derived by `decide.py` before any plan and every vision-planned row cites
  its sha256. **The B4 eye labels do not exist** (`vlm_pilot/LABELS.jsonl`; only
  `LABELS.template.jsonl`): without them T-strict is not evaluable and K2 and H1 stay closed.

### The DeepSeek attempt of 2026-09-23: no verdict (commit `5d3e8e8`)

`calibration-2026-09-23/` (sealed 04:10:40Z for `deepseek-v4-flash-vision-exp`) ran four questions
at 10:26:07Z; the opencode gateway answered each of the three attempts with HTTP 401 ("Upstream
request failed: Invalid credential"), and the run stopped with exit 3: 4 failed lines, 0 verdicts,
$0. The untracked ledger moved to `calibration-2026-09-23/failed-deepseek-401/VERDICTS.jsonl`
(sha256 `23eaea0b6ebd068726eb3d9024ab396d6cca45d2f7f2b197912a59fdd673f258`, LF-pinned in
`.gitattributes`), so the sealed directory holds no ledger; its seal, thresholds and jobs are
untouched. A test pins the file and that every line is a 401 without a verdict.

### The sample in the seal, and the round through the handoff (commits `c264950`, `82f9689`)

The protocol fixes the thresholds **and the sample** before the first question; until now only the
thresholds' sha256 went into `SEAL.jsonl`, and the round ran `vision.py export|import` on whatever
`JOBS.jsonl` held.

* `calibrate.py jobs` **fixes** the sample it writes: `{jobs_sha256, jobs, fixed_at}` is appended to
  `SEAL.jsonl` beside the thresholds' line - after the seal, before any answer, once; the same
  sample again changes nothing, another is refused. `sealed_jobs` reads it back only as fixed.
* **`calibrate.py vision --run-dir C --handoff-export H | --handoff-import H`** is the calibration's
  round in the two halves the Phase-3/4 model stages take (`run4.py select --handoff-export|import`,
  `run.py judge`). Both halves read the fixed sample and call vision's own export and import - now
  `vision.command_export` / `command_import`, which `vision.py`'s CLI calls too - so the frozen
  questions, the exact JPEG (`vlm_bytes`), the answer parsing (`extract_json`, `validate`), the byte
  check and the ledger line are unchanged.
* `jobs`, `vision` and `evaluate` refuse a directory whose thresholds name another model than
  `vision.MODEL` (the DeepSeek seal among them); `evaluate` measures only the fixed sample.
* 13 new mutation cases (`GALLERY_OPUS_C1_MUTATIONS`, prefix `gallery: `); "gallery: the dry run
  exits 0 with images missing" re-anchored (its line moved into `command_export`).

### The Opus calibration directory, sealed before any question (commit `3b043a4`)

`output/remediation/gallery_audit/calibration-2026-09-25-opus/`, written by `calibrate.py seal`
(08:13:05Z) and `calibrate.py jobs` (fixed 08:13:15Z):

| file | sha256 (LF bytes) | |
|---|---|---|
| `THRESHOLDS.json` | `e65604571e5b6717a4c13982039fa94c3d5646101f36b6d53eecde3cdddc61a2` | the DeepSeek seal's thresholds except `definitions.model` = `anthropic/claude-opus-5-5 (Claude Code agent)` |
| `JOBS.jsonl` | `f0c4ccd6833f2de456e2d1ca110d2520ae6772cd9c3ebd4ec789a032de70e5c9` | 939 questions, **byte-identical** to the DeepSeek seal's sample |
| `SEAL.jsonl` | `c3f23f21ba4f54e25ce43fb2c599cbab89ee5670a80f3e69d2d669ff0c9ca45c` | the two lines above, in order |
| `README.md` | `da6c66cda1c54f27bd65b6ec5ab04f7cbf2b24386934c112e5ea3b0877d853b4` | the note: answered by Opus through the handoff (owner order 2026-09-23); the DeepSeek attempt produced no verdict |

`test_the_opus_c1_directory_was_sealed_for_opus_and_fixed_its_sample_before_any_answer` pins it (red
before the seal) and, once a ledger exists, that every line is by Opus and after the fixed sample.

### The export (no model call; `output/remediation/handoff/` is gitignored)

`calibrate.py vision --run-dir <C> --handoff-export output/remediation/handoff/gallery-calibration-opus`:
`export: 939 jobs, 0 already in the ledger, 939 handed off, 0 handed off before, 0 image(s) not found
or unreadable`. The directory holds `C1/MANIFEST.jsonl` (939 lines), `C1/vision/<id>%2F<prompt>.prompt.txt`
(939) and `images/<id>.jpg` (889 JPEGs, 245 MB, mean 279 KB, 802 at 1280 px on the long side).
`opus_handoff.py validate`: **939 questions, 0 answered, 939 missing, 0 stale, 0 malformed, 0
orphans** (exit 1, as before any answer).

### The G runs that follow a passing C1 (measured on the current state)

The state: the snapshot + the hero moves + every gallery plan the production journal shows applied
(read 2026-09-25: G0 105 `image_kind`, G0b 30 `image_kind` `gallery-verdicts-persist-07817ee0`, the
liveness chunk `img-liveness-2026-09-23-001`). Live rows by tier A 3,857 / B 9,884 / C 25,925 /
D 9,360 (49,026); 3,991 sites serve an image; 51 chunks of 100 sites.

| stage | questions | how it is known |
|---|---|---|
| G3 served image (gallery) | 3,991 | measured (3,857 heroes, 134 lead/sort-order images) |
| G3-strict (hero question) | <= 3,991, about 2,950 | the served images G3 calls `site_photo` (design estimate, pilot 74 %) |
| G2 tier B (gallery) | 9,884 | measured |
| G4 probes (gallery) | 7,840 over 3,021 sites | measured (3 per site with live C rows, seed 20260923) |
| G4-escalation (gallery) | about 3,250-3,800 net | the not-yet-asked live rows of hit sites: 27,113 if every probed site hit, x 12-14 % |
| H-reselect | up to about 6,000 | at most 3 candidates per failing site (design) |
| **total** | **about 28,000 before H-reselect; about 35,500 upper** | |

Images: G3, G2 and G4 ask about 21,646 distinct images (overlaps G3/G2 36, G3/G4 33; 402 of them
are C1 images, which the G runs' own ledgers ask again), plus the escalation's; at the export's
mean 279 KB that is about 6 GB of handoff JPEGs over the whole run, about 120 MB per chunk.
Per chunk: G3 78 / G2 194 / G4 154 questions on average (max 90 / 304 / 200). Answering volume per
question, estimated (not measured) from the exported sizes: one image read of about 1,400 tokens
(w x h / 750) plus a prompt of a few hundred tokens and a JSON answer of a few dozen - about 1.3 M
image tokens for C1, about 40-50 M for the G runs.

### The orchestrator's commands (repository root, `PY=./.venv/Scripts/python.exe`, `PYTHONIOENCODING=utf-8`)

```bash
C=output/remediation/gallery_audit/calibration-2026-09-25-opus
H=output/remediation/handoff/gallery-calibration-opus
# 1. answer: for each line of $H/C1/MANIFEST.jsonl whose answer_path does not exist, an Opus agent
#    reads $H/<prompt_path>, looks at $H/<image_path>, writes only the JSON the question asks for
#    to a file, and runs
$PY scripts/remediation/opus_handoff.py answer --dir $H --batch-id C1 --stage vision \
    --label <label> --answered-by <agent> --text-file <answer.txt>
# 2. validate: exit 0 only when all 939 are answered, in shape, by Opus, for their exact prompts
$PY scripts/remediation/opus_handoff.py validate --dir $H
# 3. import: exit 1 and nothing written while a question lacks a valid answer; exit 3 at an answer
#    that is no in-vocabulary verdict (a failed line stays; delete that answer file, answer again,
#    validate, import again - only ok lines count)
$PY scripts/remediation/gallery_audit/calibrate.py vision --run-dir $C --handoff-import $H
# 4. score against the sealed thresholds -> $C/ADMISSION.json (commit it with VERDICTS.jsonl)
$PY scripts/remediation/gallery_audit/calibrate.py evaluate --run-dir $C --no-eye-labels
#    or --eye-labels output/remediation/vlm_pilot/LABELS.jsonl once W8's B4 labels exist

# the G runs, per chunk N = 0..50, only for the triggers ADMISSION.json admitted
S=output/remediation/gallery_audit/liveness-2026-09-23
F="--kinds-from output/remediation/gallery_audit/PLAN.jsonl --kinds-from output/remediation/gallery_audit/rejected_kinds/PLAN.jsonl --applied $S/PLANNED.jsonl"
R=output/remediation/gallery_audit/run-g-chunk-NNN; HG=output/remediation/handoff/gallery-g-chunk-NNN
for G in G3 G2 G4; do
  $PY scripts/remediation/gallery_audit/worklist.py jobs --stage $G --chunk N --liveness-store $S $F --out $R/JOBS-$G.jsonl
  $PY scripts/remediation/gallery_audit/vision.py export --jobs $R/JOBS-$G.jsonl --run-dir $R --handoff $HG
done
# answer, validate, then vision.py import with the same three arguments per JOBS file; then the
# second round: --stage G3-strict --ledger $R/VERDICTS.jsonl, and --stage G4-escalation
# --hit-sites HITS.json, exported, answered, validated and imported the same way; then
$PY scripts/remediation/gallery_audit/decide.py vision --run-dir $R --calibration $C --liveness-store $S --chunk N $F
```

### Tests, sweep, gates (main checkout, branch `integrate/wave1`, main venv)

* `test_gallery_calibrate.py`: +10 tests, each red first (the failed attempt, the sample fixed in the
  seal log, never rewritten, not read once edited, fixed once and before the first answer, a
  seal-log line of neither kind, a DeepSeek-sealed copy never fixed, asked or measured, the jobs
  command, the whole round export -> answer -> validate -> import -> evaluate on real images, an
  edited sample neither asked nor measured, the versioned Opus directory); the helper and the test that
  wrote `JOBS.jsonl` directly now fix it: **39 passed**.
* Mutation sweep through the sweep's own `main` over every case on `calibrate.py` and `vision.py` or
  tested by `test_gallery_calibrate.py` (58 `gallery:`, 7 `opus handoff:`): **65/65 caught**, the
  tree byte-identical to the sweep's start for 3 files, no `# mutant` left; `test_phase3_sweep.py`
  (every anchor and test exists) green.
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`): **6,256 passed,
  3 skipped, 57 deselected, 0 failed** (231 s); the skips are the two refactored-away article tests
  and the opt-in Shining Ones regen.
* `ruff check` and `ruff format --check` clean on the 4 touched Python files (ruff 0.15.11);
  `ruff check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean; gitleaks over the new files clean.

### Open

* **Answering C1** (939 questions) is the orchestrator's; then import, evaluate, and commit
  `VERDICTS.jsonl` and `ADMISSION.json` with the seal (`.gitignore` versions `calibration-*/`).
* **B4 eye labels**: without `vlm_pilot/LABELS.jsonl` T-strict is not evaluable, so K2 (a
  `site_photo` kind) and H1 (hero moves) cannot be admitted; the owner's 40-tile spot check with it.
* **Missing links of the G runs** (none is C1's): no tool derives the G4 hit-site list
  (`worklist.py jobs --stage G4-escalation` takes `--hit-sites` as given); `decide.reselection_jobs`
  (H-reselect) has no CLI; `decide.py vision` writes `PLANNED-chunk-NNN.jsonl` but nothing emits it
  as a `chunk_writer.py` chunk (the liveness and attribution lanes have their own emitters); S13
  `accept.py` (the early gate after 300 sites, the final acceptance) is not built.
* The applied attribution write (`img-attrib-2026-09-23-001`: 72 `author`, 53 `author_url`) cannot be
  folded into the state (`--applied` reads only `decide.py` plans; `author` is not in
  `APPLIED_COLUMNS`), so H1's attribution check reads the snapshot's authors - conservative (fewer
  hero candidates), never a wrong write.

## 2026-09-25 - gallery calibration C1 with Opus: answered, scored, no trigger admitted

`calibration-2026-09-25-opus/` (sealed 08:13:05Z, thresholds `e6560457...`, jobs `f0c4ccd6...`,
identical to the DeepSeek seal except the model) was answered through the handoff by 24 Opus agents
(939 of 939, validate ok), imported through the lane's unchanged parser (`calibrate.py vision
--handoff-import`, 939 judged) and scored with `calibrate.py evaluate --no-eye-labels`
(`ADMISSION.json`, ledger `1989aba4...`):

| trigger | measured | threshold | admitted |
|---|---|---|---|
| T0 | 939 of 939 with a verdict | all | pass |
| T-kind | pilot agreement 186/200 = 0.93; non-photo precision 51/61 = 0.836 | >= 0.90 and >= 0.90 | **no** |
| T-X1 other site | precision 52/101 = 0.515, recall 52/64 = 0.81; gold foreign 12/12, gold correct flagged 2/13 | >= 0.85, >= 0.70, 12/12, <= 1/13 | **no** |
| T-X2 people | precision 1/8 = 0.125 | >= 0.85 | **no** |
| T-X3 other | precision 8/17 = 0.47 | >= 0.85 | **no** |
| T-strict | not evaluable: `vlm_pilot/LABELS.jsonl` (eye labels) does not exist | - | **no** |

Under the sealed rule a failed trigger is dropped, never re-tuned, and no threshold changes after its
data is seen: **no G run may write**. The gallery's vision stage ends here; the image fixes already
applied (rejected kinds, liveness, attribution, Dedan's thumbnail) stand. A future route needs the
eye labels (T-strict) and a model/prompt that passes the precision bars; it is recorded in
HUMAN_ONLY.md as open.


## 2026-09-25 - Phase 6 follow-through prepared: name keys, rebuild-static, the scope consumers, the shorts ledger, the sealed acceptance, and the runbook (nothing applied)

Main checkout, branch `integrate/wave1`, commits `ff9a570` .. this one. **Production was read
(SELECTs, one Qdrant `retrieve`, public GETs) and rehearsed (every statement ended in ROLLBACK, 0
journal rows left); nothing was applied, nothing deployed, no VPS file changed (two probe files
copied to `/tmp` and into the API container were deleted again), no model was called;
`opus_handoff.py`, `phase3/fetch_stage.py`, `phase3/ledger.py` and `.claude/worktrees/` are
untouched.** The Phase-4 mass run was writing throughout (journal high-water mark at 12:57 UTC:
id 45002, 9,715 rows; `phase4:` rows 1,530 at 09:55 UTC).

| commit | what |
|---|---|
| `ff9a570` | Lyra's semantic search drops retired sites, whatever the Qdrant index still holds (test-first) |
| `d8e4912` | the static export refuses root and writes nothing it cannot write in full (test-first) |
| `370babf` | Lyra's Wikidata aliases keyed by Postgres from the raw name (test-first) |
| `34606f3` | the name-key lane (`scripts/remediation/name_key/plan.py`) and the chunk writer's two key columns; 18 sweep cases |
| this one | the sealed acceptance protocol and its draw; 4 sweep cases; this record |

### Item 1 - card_stats: the sequence stands

`apply.py --lane card-stats-2026-09-23 --verify` (read-only, 13:00 UTC): journal rows for the stamp
0, tiers 525 / 1,796 / 2,310 / 353 / 20, civilization drift 61, total_power not the sum 0 - the
state the re-plan of this morning left. Dedan's thumbnail (step B) **is applied**
(`thumb-repoint-2026-09-25-001`, journal row at 07:50:51 UTC: `/data/images/wiki/9a9a0dca/hero.webp
-> NULL`), so C waits on nothing but the end of the Phase-4 writes (its premise holds
`md5(description)` of every planned card). Neither scope-e4 (applied, `be5d6c5`) nor the Phase-5
card texts touch a card_stats input or premise (`b14afdb`). The commands are section C of "The apply"
in the 2026-09-25 re-plan record above, unchanged; the re-plan (C1) is mandatory, because the
Phase-4 descriptions move `cultural_influence` and expire today's plan.

### Item 2 - name_normalized: 0 curated keys differ; the lane exists and is rehearsed

Read-only, 12:50 UTC, the key `left(lower(unaccent(name)), 500)` computed by Postgres:

* `unified_sites`: **0** rows of `ancient_nerds` (5,004) or `lyra` (24) whose key differs; 0 NULL.
  The journal holds **no** `name` or `name_normalized` row - no remediation lane ever wrote a name
  (the UK lane wrote `country`). Lyra's boot reconciles the curated site keys on every start.
* `unified_site_names`: **0** rows of `ancient_nerds` sites; **11** rows of six `lyra` sites (Yap 4,
  Charnwood Forest 2, Doggerland 2, North Sentinel Island, Roopkund Lake, Cerutti Mastodon site),
  all `wikidata_alias`, none colliding with another row of its site. Root cause: Lyra's
  `_store_wikidata_aliases` keyed them with Python's `normalize_name` (NFKD drops the Japanese
  dakuten, leaves Hangul jamo, cuts parentheses); the boot's alias UPDATE compares a key with itself
  and never repairs them. **Fixed at the source** (`370babf`): the key is computed in the INSERT,
  `ON CONFLICT ON CONSTRAINT uq_usn DO NOTHING RETURNING id` (rehearsed on production with ROLLBACK:
  new alias 1 row, the site's own name 0, repeat 0).
* **The lane** (`34606f3`): `name_key/plan.py chunk --out output/remediation/name_key/name-key-<date>`
  reads both columns, plans K1 through `gallery_audit/chunk_writer.py` (which gained guard 2b - a
  name row belongs to the planned site - and guard 2c - the planned key is the one Postgres derives
  from the row's name at write time, write only; an image chunk renders byte for byte as before).
  Run today: **exit 1, "nothing to plan", the 11 `lyra` rows listed** (the writer writes
  `ancient_nerds` rows only, guard 1). Rehearsed on production against a divergence made inside the
  transaction, then ROLLBACK (`C:/tmp/p6/name_key_probe.py`): the success path journalled 2 rows
  (one alias row, one site row) through `apply_remediation_change`, guard 2c and guard 2b each
  refused with psql exit 3, 0 journal rows and both stored keys unchanged afterwards.
* Other writers that still key in Python (not changed here; none has produced a divergent curated
  row): `site_identifier` promotion (`lyra` label/alias rows), `api/routes/radar.py` alias merge,
  `api/routes/sites.py` batch upload (curated site keys are reconciled by Lyra's boot), and the
  matching comparisons of `site_identifier._check_name_an_match` / `_check_spatial_an_match`.

### Item 3 - rebuild-static, the static export, Qdrant, IndexNow

**What is broken (plan 9.4), measured 2026-09-25 inside `ancient_nerds_api` (euid 1000, cwd `/app`):**
`sources.json(.gz)`, `sites/`, `sites/details/*`, `links.json(.gz)` and `images/index.json(.gz)` are
**root-owned, NOT-WRITABLE**, all from the export run with `docker exec -u root` on 2026-08-18;
`hubs.snapshot.json` (deploy, 2026-09-05), `content/`, `snapshots/` and `library/` are writable (10
old snapshot files are root-owned; pruning unlinks them through the writable directory).
`pipeline_heartbeats` holds no `job:rebuild-static` row: the background job (`29ad01f`) has never
run in production; it would fail at its first write. PROJECT_LESSONS' "Statik-Export braucht
`-u root`" was the cause, not the cure. **Fixed** (`d8e4912`, test-first): the export refuses to run
as root and, before any read or write, names every target it cannot write with the chown remedy;
the lesson is corrected, `docs/static-exporter.md` says so.

**Where the export runs:** on the VPS, in the API container, as its user. The export files are
**gitignored** (`.gitignore` "PUBLIC DATA - generated on VPS, never push from dev", `81ac797`): the
deploy's `git pull` does not deliver them and `git clean -fd` (no `-x`) leaves them - there is
nothing to commit and no LFS step. The globe does not read them (`/api/sites/all`); the live readers
are the frontend build (`hubs.snapshot.json`, baked into `index.html` at every deploy whose commit
differs from `dist/.built-commit`), the audit page (`snapshots/`), the library page and the public
URLs `/data/sites/...` (robots `Allow: /data/sites/`) - which still serve the 2026-08-18 state,
retired sites included (checked: a retired id is in `/data/sites/index.json`, not in
`/api/sites/all`).

**Qdrant (plan 10.7):** the duplicate nightly sync is **fixed and holds in production** - on
2026-09-25 03:00 UTC `ancient_nerds_api2` ran "Starting nightly auto-reindex", `ancient_nerds_api`
logged "skipped - running on another instance". But **all 78 retired sites were still points** of
`sites` at 12:59 UTC (read-only `retrieve`), and Lyra's `vector_search` / auto-retrieve returned
them; fixed at query time (`ff9a570`), resynced by the next index run. **IndexNow:** Lyra's hourly
step announces journal-changed and retired pages itself (2 h window; 06:29-10:29 UTC today:
156/23/229/216/139 URLs accepted, HTTP 200).

### Item 4 - the consumers of section 8.4, verified

Live probes 2026-09-25 13:00 UTC with retired `Ali Masjid Fort` (E3), `Ancient Kourion`
(duplicate), `Attock Fort` and pending `Bosnian Pyramid of Love`; `tests/api/test_scope_read_paths.py`
parses every `unified_sites` read in `api/` and `pipeline/`.

| consumer | state |
|---|---|
| globe / points, filter panel (`/api/sites/all`) | retired absent, pending present |
| SSR detail page, legacy `/site.html?id=` | 410 / 410; pending 200 |
| country hub (`/sites/pakistan`) | none of the retired Pakistani forts listed |
| `sitemap-sites.xml` | 0 of 3 retired URLs |
| site API `/api/sites/{id}`, public API `/api/v1/sites/{id}` | 410 |
| search `/api/sites/search` | retired curated row absent |
| static export | code filters (tests), **files stale since 2026-08-18: retired sites served under `/data/sites/`** - cured by the export (runbook step 3) |
| Qdrant / Lyra semantic search | **leaked: 78 of 78 retired points present and returned** - fixed at query time (`ff9a570`, ships with Push #2), resync in step 5 |
| shorts batch, single-site export, ledger | `not_retired` in the batch, a retired site refused, ledger status `withdrawn` (tests) |
| card game draws / expedition | `card_site_in_scope()` (tests, read-path scanner) |
| IndexNow | retirements announced as removed URLs (hourly step) |

### Item 5 - the `site_shorts` ledger exists

Migration `0021_site_shorts_ledger.sql` was applied on 2026-09-23 03:20 UTC (`applied_migrations`);
the table holds **0 rows**. The render step writes it (`pipeline/video/shorts_ledger.py`), and the
16 renders made before it (`video-assets/shorts/*/site.json` + mp4, workstation only) are entered by
`scripts/backfill_site_shorts_ledger.py` (plan, then `--apply`), which needs `DATABASE_URL` from
`video-assets/prod-db.env` - HUMAN_ONLY A6. No migration is needed now. The backfill belongs to the
shorts project: nothing is published, and after the Phase-5 card texts those 16 renders narrate the
old cards (the S13 gate refuses them).

### Item 6 - the acceptance protocol, sealed before any draw

`output/remediation/acceptance/PROTOCOL.md` fixes: the frame (shown `ancient_nerds` sites with a
forward journal write on a judged column; 3,342 today, before the card texts), the exclusions (9
fixed sources - the assessment's 60, the gold standard, the Phase-3 pilot, both Phase-4 pilots, the
Opus keep sample, the VLM pilot, the gallery C1 sample, the sitelink pilot: 374 of today's frame -
plus the Phase-4 audit's mid-run and final samples, required at the draw), seed **20260925**, 60
sites by `phase4.audit4.draw_sample`, 10 canaries (seed 20260926: 5 far-away countries, 5 points
moved 5 degrees), 11 judged fields with severities, stage 1 (one independent Opus judge per field,
never shown remediation evidence; verbatim quote check) and stage 2 (a second independent judge on
every WRONG, a third on UNDECIDED), deterministic checks D1-D6, and the thresholds: **VOID** unless
every question is answered, at least 9 of 10 canaries end CONFIRMED and no write touches a drawn
site after the draw; **PASS** only with 0 confirmed severe errors, at most 3 of 60 sites with any
confirmed error, and 0 D1-D6 failures. `scripts/remediation/acceptance/draw.py` is the draw
(tests: `tests/remediation/test_acceptance_draw.py`, 20; the frame read and the value read were
run read-only today to prove the SQL - not a draw).

| file | sha256 (LF bytes) |
|---|---|
| `output/remediation/acceptance/PROTOCOL.md` | `f40fac87230a26e7b1a4818e9d50d16dedfcb6936fc795b532e2cb35789f8bff` |
| `scripts/remediation/acceptance/draw.py` | `0a12beb461eb6aca6c921a4677b08472b4c8ff5068afd06af88a1baaf452515e` |
| `output/remediation/acceptance/EXCLUSIONS.sha256.json` | `dff9dd9a48a3199ebc6e7bb08bcafa31707f993f8f0a4a73c45bedbb0cf5dfb3` |
| `output/remediation/acceptance/EXCLUDE_ASSESSMENT_PILOT.txt` | `e5802a3b77728a1390f36f9dc48a3060796a43ad805581b7e591a4ea49d86e98` |
| `output/remediation/acceptance/EXCLUDE_OPUS_KEEP_SAMPLE.txt` | `09068e2942d5a536252147b73a0dbdbb5ef04d616762575ad22e25db17fc0f72` |

`SEAL.json` holds the same five digests; `test_the_seal_holds` fails on any edit.

### The runbook (the orchestrator runs it, after the last write)

Repository root, main venv, `export PYTHONIOENCODING=utf-8`, `PY=./.venv/Scripts/python.exe`,
`A=scripts/remediation/mechanical/apply.py`. "The last write" is the Phase-4 mass run's last chunk
(its own acceptance: `verify_writes4.py`, 0 deviations). Step 4 is the Phase-5 sitting, whose push is
Push #2.

1. **card_stats** - section C of the 2026-09-25 re-plan record, C1-C7, unchanged (re-plan, gitleaks
   over the plan commit, check, rehearse, apply, read back, rollback rehearsal, completion
   read-back `"cells": 0`).
2. **Name keys** - `$PY scripts/remediation/name_key/plan.py chunk --out output/remediation/name_key/name-key-<date>`
   -> expected **exit 1, "nothing to plan"**, the 11 `lyra` rows listed. Only if an
   `ancient_nerds` row is planned: `CW=scripts/remediation/gallery_audit/chunk_writer.py`,
   `$PY $CW <out>/chunk-001 --check`, `--rehearse`, `--apply`, `--readback`, `--rehearse-rollback`,
   then commit `<out>/`.
3. **Static export (VPS, before Push #2, so the next frontend build bakes the new hub list)** -
   * hand the root-owned files back (no sudo on the host):
     `ssh ancientnerds "docker exec -u root ancient_nerds_api chown -R 1000:1000 /app/public/data/sites /app/public/data/sources.json /app/public/data/sources.json.gz /app/public/data/links.json /app/public/data/links.json.gz /app/public/data/images/index.json /app/public/data/images/index.json.gz /app/public/data/snapshots"`
   * export as the container user (about 4 minutes; the deployed code already leaves retired
     sites out): `ssh ancientnerds "docker exec ancient_nerds_api python -m pipeline.static_exporter --no-library"`
     -> ends with "EXPORT SUMMARY" (after Push #2 the same command first runs the preflight, which
     names any path still unwritable)
   * check: `ssh ancientnerds "cd /var/www/ancientnerds && stat -c '%U %y %n' public/data/sources.json public/data/sites/index.json public/data/hubs.snapshot.json && grep -c 8c159d7f-d954-44fc-aab9-6b7841d68a35 public/data/sites/index.json"`
     -> owner `deploy`, today's time, **0** (Ali Masjid Fort, retired). Nothing to commit.
4. **Phase 5 and Push #2** - the P5 sitting of `docs/procedures/CARD_DESCRIPTIONS.md` (write through
   the journal, regenerate `public/data/card_descriptions.json` byte for byte, commit), then the
   push of `integrate/wave1` to `main` (the pre-push gates; CI). It deploys this record's code
   (`api/` and `pipeline/`: api, api2, lyra and ssr rebuilt) and rebuilds the frontend with the new
   `hubs.snapshot.json`. Checks: `ssh ancientnerds "curl -s localhost:8000/"` -> `commit` = HEAD;
   0 `[STARTUP] Card description overwritten` lines on `ancient_nerds_api` and `ancient_nerds_api2`.
5. **Qdrant resync** (after Push #2, outside 02:55-03:10 UTC - the CLI does not take the nightly's
   advisory lock): `ssh ancientnerds "docker exec ancient_nerds_api python scripts/build_lyra_index.py --collection sites"`
   -> logs "Deleted 78 retired sites from 'sites'" (or more, if more were retired) and "Sites to
   index (new + changed): N". Waiting for the 03:00 UTC nightly does the same. Check: the read-only
   `retrieve` of every retired id from `sites` returns **0** points.
6. **IndexNow catch-up** (the hourly Lyra step already announced each journal write within 2 h;
   this re-announces the whole write period once, which the protocol allows):
   `$PY scripts/indexnow_submit.py --all --lastmod-since 2026-09-20 --dry-run`, then without
   `--dry-run` -> "URLs accepted (HTTP 200)". Retired pages are not in the sitemap; the hourly step
   announced them as removed.
7. **Checks** - the independent acceptance, both lanes (run read-only today at 13:35 UTC: **0
   deviations** each; add `--allow-stamp` for any later lane that rewrites a phase-3 cell):
   `$PY output/remediation/tools/verify_writes.py --allow-stamp 2026-09-22_mechanical-uk-parts --allow-stamp 2026-09-22_mechanical-site-type-shape --allow-stamp 2026-09-23_mechanical-journal-reversal-1 --allow-stamp 2026-09-23_mechanical-journal-reversal-2 --allow-stamp 2026-09-25_mechanical-journal-reversal-3 --allow-stamp 2026-09-25_mechanical-wrong-both`
   and `$PY output/remediation/tools/verify_writes.py --lane gap --allow-stamp 2026-09-25_mechanical-journal-reversal-3 --allow-stamp 2026-09-25_mechanical-wrong-both`;
   `$PY $A --lane scope-e4 --verify`
   -> outside the E3 window with no decision 0; a retired site answers 410 on `/sites/...`,
   `/api/sites/{id}`, `/api/v1/sites/{id}` and is absent from `/api/sites/all`,
   `sitemap-sites.xml` and `/data/sites/index.json`; the landing page's hub list carries the new
   counts.
8. **Acceptance** - `$PY scripts/remediation/acceptance/draw.py --out output/remediation/acceptance/draw-<date> --phase4-audit-samples <the Phase-4 audit's sample id files>`,
   commit `FRAME.jsonl`, `EXCLUDED.json`, `SAMPLE.jsonl`, `DRAW.json`, then PROTOCOL.md sections 6-10.

### Tests, sweeps, gates (main checkout, branch `integrate/wave1`, main venv)

* New tests: `test_lyra_vector_search_scope.py` (5), `test_static_export_preflight.py` (8),
  `test_wikidata_alias_key.py` (5), `test_name_key_lane.py` (19), `test_acceptance_draw.py` (20);
  each fix's tests were red before its code (the planner and the draw are new modules).
* `mechanical/mutation_sweep.py "name key:"`: **cases 18, fired 18**; `"acceptance:"`: **cases 4,
  fired 4**; skipped, survived, invalid, unproven, errored 0; the swept files restored
  byte-identical; `test_mechanical_sweep.py` green (every needle matches once).
* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`, `-p no:cacheprovider`):
  **6,313 passed, 3 skipped, 57 deselected, 0 failed** (221 s; 6,256 before this work, +57 new);
  the skips are the known three. `ruff check api/ pipeline/` clean, `ruff format --check` clean on
  the 14 touched Python files (ruff 0.15.11), `lint-imports` 2 kept / 0 broken, `vulture api/
  pipeline/ .vulture_whitelist.py --min-confidence 80` clean, `semgrep --config .semgrep` clean on
  the three touched production modules, mypy reports nothing in `api/services/lyra_tools.py`, the
  Lyra-image import check (`markdown`/`nh3` absent) imports `pipeline.lyra.orchestrator`. The
  independent acceptance (`verify_writes.py`, both lanes, 13:35 UTC): **0 deviations** each.

## 2026-09-25 - Phase-4 mass run: 1,578 sites planned, 960 written in 13 accepted steps, 2 taken back, 984 live, 0 deviations

Branch `wip/p4-pilot` (worktree `.claude/worktrees/p4-pilot`), run `runs/mass-2026-09-25`, plan
`PLAN4.scope.jsonl` (`fec90379...`, unchanged since the defect-scope entry), apply root
`logs/_write_apply_p4` - all gitignored. **Production was written by the P4 group only**
(`description` and its `raw_data` provenance of defect-scope sites, stamps
`phase4:p4-NNNN:chunk-0001`), every step rehearsed, applied, read back with its inverse proof and
accepted by `verify_writes4.py`; two written sites were taken back with `revert4.py --site`. Every
model question was answered by Opus through the handoff; **no DeepSeek, Pi, opencode gateway or
MiniMax was called, and no search was made**. The short result is `phase4_runner/MASS_RESULT.md`.
The mid-run audit's hit, the reviewer fix and the single-site revert path are the entry "Phase-4 mass
run: the mid-run audit's WRONG_SITE (Roman Bath, York)" above; this entry records the whole run.

### The scope and the stages before any question

* **1,578 sites in 106 batches, `p4-0010` .. `p4-0115`**: 12 groups of 8 batches (120 sites each) and
  a last group of 10 batches (138 sites). Every `mass4.py` round printed `defect scope SCOPE4.json v1
  19a57e9fd17f5360: 0 site(s) of the open batches outside it`, every `write_gate4.py` call `120 of the
  run's 120 sites` (the last group 138 of 138): the scope refusal `outside-defect-scope` had no
  mass-run site to refuse.
* S0-S3 export for all 106 batches in one round, 2026-09-24 23:29-23:40 CEST
  (`logs/p4_mass/export.out`, `--stages prepare,sources,routes,select --searches-off --handoff-export
  handoff/p4-mass-select`, `STAGE_EXIT=0`; "searches off: every routes stage is told 0 and builds no
  MiniMax client"). Lanes at S1b (`lanes.jsonl` of every batch): **W 1,321, S 100, none 157**. The 157
  were held before any question: `search-stopped` 103 (the T, R and B3 candidates; searches off),
  `scope-pending` 35, `revision-too-fresh` 19.
* The run's ledger (`runs/mass-2026-09-25/LEDGER.jsonl`, `55b48e29...`): 4,485 lines - 2,090 fetch lines
  (2,086 ok, 4 HTTP errors), 2,395 model lines (select 1,392, review 1,003), every one
  `anthropic/claude-opus-5-5 (Claude Code agent)`, unmetered; `progress.json`: `calls 2395, cost_usd
  0.0, searches 0`.

### The Opus handoff, group by group

Each group went through the same sequence, run by the orchestrator's helper `C:/tmp/p4m_group.sh`
(its header: "orchestrator helper, not versioned"; modes `select` and `review`); every command's
header and exit line are in `logs/p4_mass/group-p4-NNNN-select.log` and `-review.log`, group 1's in
the per-batch logs:

1. the group's selector questions answered in `handoff/p4-mass-select` (`opus_handoff.py answer`),
   `opus_handoff.py validate` (answered, stale, malformed), then `mass4.py --plan PLAN4.scope.jsonl
   --run-dir runs/mass-2026-09-25 --log-dir logs/p4_mass --only <group> --searches-off --live
   --stages select --handoff-import handoff/p4-mass-select`;
2. `--stages translate --handoff-export handoff/p4-mass-translate` (lane T is closed: no question, no
   directory; the helper stops with exit 2 should one appear), then `--stages
   translate,assemble,verify --handoff-import` from it, then `--stages review --handoff-export
   handoff/p4-mass-review`;
3. the review questions answered, `validate`, `--stages review --handoff-import
   handoff/p4-mass-review`, `run4.py holds --run-dir runs/mass-2026-09-25`;
4. `write_gate4.py --group P4 --run mass-2026-09-25 --open-lanes W,S --batch <each of the group's>`:
   dry, `--rehearse` (every APPLY ending in ROLLBACK; `every open batch rehearsed`), `--apply --step
   100` - `STEP COMPLETE: <n> site(s) written in <b> batch(es)`, `WRITE_EXIT=0`;
5. `verify_writes4.py --lane p4 --plan logs/_write_apply_p4/LANE_PLAN.jsonl --run
   runs/pilot4-2026-09-24 --run runs/mass-2026-09-25 > logs/p4_mass/accept-step-NN.log`, and only on
   `ACCEPT_EXIT=0` the same gate call with `--accept` on that log (`ACCEPTED/step-00NN.json`).

**Who answered** (the `answered_by`, `answered_at` and `model` of every answer file): one Opus agent
per batch and stage. 106 selector agents (`opus-p4m-select-p4-NNNN`) wrote the 1,392 selector
answers, 2026-09-24T21:51:23Z .. 2026-09-25T11:14:32Z; 106 review agents (`opus-p4m-review-p4-NNNN`)
the 1,003 review answers, 22:36:39Z .. 11:33:23Z. Sorted by start, no agent's answering interval
overlaps the next one's: **they ran one at a time**. Group 5's 78 review answers, given under the old
reviewer pin, stay aside unimported (`handoff/p4-mass-review-stale-reviewer-89e6035d/`); its questions
were answered again under the new pin.

| group | batches | selector questions | review questions | sites written | site-held | step |
|---|---|---|---|---|---|---|
| 1 | p4-0010 .. p4-0017 | 112 | 74 | 71 | 49 | 2 |
| 2 | p4-0018 .. p4-0025 | 111 | 88 | 84 | 36 | 3 |
| 3 | p4-0026 .. p4-0033 | 108 | 80 | 76 | 44 | 4 |
| 4 | p4-0034 .. p4-0041 | 109 | 82 | 79 | 41 | 5 |
| 5 | p4-0042 .. p4-0049 | 111 | 78 | 75 | 45 | 6 |
| 6 | p4-0050 .. p4-0057 | 109 | 82 | 78 | 42 | 7 |
| 7 | p4-0058 .. p4-0065 | 110 | 78 | 72 | 48 | 8 |
| 8 | p4-0066 .. p4-0073 | 108 | 68 | 64 | 56 | 9 |
| 9 | p4-0074 .. p4-0081 | 104 | 64 | 64 | 56 | 10 |
| 10 | p4-0082 .. p4-0089 | 99 | 77 | 74 | 46 | 11 |
| 11 | p4-0090 .. p4-0097 | 98 | 67 | 63 | 57 | 12 |
| 12 | p4-0098 .. p4-0105 | 98 | 77 | 75 | 45 | 13 |
| 13 | p4-0106 .. p4-0115 | 115 | 88 | 85 | 53 | 14 |
| **all** | **106** | **1,392** | **1,003** | **960** | **618** | |

Questions from the ledger's model lines; written and site-held from each batch's `PLAN.jsonl` and
`REFUSED.jsonl` in the apply root (the gate's `refused by rule: {'site-held': n}`). 1,392 selector
questions = 1,578 less the 157 held before S3 and the 29 lane-S sites whose article offers no sentence
naming them (held `no-source`, no call bought).

### The steps and their acceptance (`logs/_write_apply_p4/ACCEPTED/`)

| step | sites | rows | planned / journal / carried / not yet written | re-verified (V1-V15) | RESULT | output sha256 |
|---|---|---|---|---|---|---|
| 1 (pilot 4, p4-0001 .. p4-0009) | 26 | 52 | 52 / 52 / 52 / 0 | 26 | 0 deviations | `6b81cfda` |
| 2 | 71 | 142 | 194 / 194 / 194 / 0 | 97 | 0 | `e206aa90` |
| 3 | 84 | 168 | 362 / 362 / 362 / 0 | 181 | 0 | `384bbfd1` |
| 4 | 76 | 152 | 514 / 514 / 514 / 0 | 257 | 0 | `3cd28706` |
| 5 | 79 | 158 | 672 / 672 / 672 / 0 | 336 | 0 | `71df707e` |
| after the Roman Bath revert (`accept-after-roman-bath.log`) | | | 672 / 672 / 670 / 2 | 335 | 0 | |
| after the Altar revert (`accept-after-reverify.log`) | | | 672 / 672 / 668 / 4 | 334 | 0 | |
| 6 | 75 | 150 | 822 / 822 / 818 / 4 | 409 | 0 | `de915ce3` |
| 7 | 78 | 156 | 978 / 978 / 974 / 4 | 487 | 0 | `4bbedbf1` |
| 8 | 72 | 144 | 1,122 / 1,122 / 1,118 / 4 | 559 | 0 | `6f04bd3a` |
| 9 | 64 | 128 | 1,250 / 1,250 / 1,246 / 4 | 623 | 0 | `e3bbec0d` |
| 10 | 64 | 128 | 1,412 / 1,378 / 1,374 / 38 | 687 | 0 | `9599bc5a` |
| 11 | 74 | 148 | 1,526 / 1,526 / 1,522 / 4 | 761 | 0 | `7283edeb` |
| 12 | 63 | 126 | 1,652 / 1,652 / 1,648 / 4 | 824 | 0 | `edc73e54` |
| 13 | 75 | 150 | 1,802 / 1,802 / 1,798 / 4 | 899 | 0 | `b06cec0e` |
| 14 | 85 | 170 | 1,972 / 1,972 / 1,968 / 4 | 984 | 0 | `2c5eaf52` |

Step 10's 38 not yet written are the 4 rows of the two reverted sites and 34 rows of p4-0082 and
p4-0083 (10 + 7 sites), still at their old value: group 10's dry gate run rendered those two batches'
`PLAN.jsonl` before it stopped on p4-0084 (their `chunks/` directories date from 11:49:22 CEST), and
the lane plan is every rendered batch's `PLAN.jsonl` (`write_gate4.write_lane_plan`), rebuilt by
group 9's apply. Step 11 wrote and carried them. **The end state, step 14 (13:35:47 CEST): 1,972 planned rows, 1,972
journal rows, 1,968 carried, 4 not yet written (the two reverted sites), 984 sites re-verified, 0
deviations** - 958 mass sites and pilot 4's 26. `LANE_PLAN.jsonl` holds the 1,972 rows
(`f3a7899e...`).

### The holds (`runs/mass-2026-09-25/HOLDS4.jsonl`, 909 lines, `3b16b3a9...`)

Site scope: 625 lines over **620 sites** - the 618 the gate refused `site-held` and the two taken back
(`audit-wrong-site`). By each site's first reason and its S1b lane:

| reason | W | S | none | sites |
|---|---|---|---|---|
| `abstained` (the selector's ABSTAIN) | 232 | 35 | | 267 |
| `search-stopped` | | | 103 | 103 |
| `V14` (T03 severe, country) | 76 | 2 | | 78 |
| `scope-pending` | | | 35 | 35 |
| `no-source` | | 29 | | 29 |
| `V9` (shorter than the stored text) | 24 | 3 | | 27 |
| `V6` (sentence 1 names no name) | 24 | | | 24 |
| `revision-too-fresh` (pinned revision younger than 48 h) | | | 19 | 19 |
| `V5` | 14 | | | 14 |
| `review-too-few-sentences` | 13 | 2 | | 15 |
| `selection-refused` | 4 | | | 4 |
| `audit-wrong-site` | 2 | | | 2 |
| `V7` | | 2 | | 2 |
| `V15` | 1 | | | 1 |
| **held** | **390** | **73** | **157** | **620** |

Five sites carry a second site hold (V5+V14 three, V5+V8, V6+V14), hence 625 lines. Card scope: 284
lines over 265 sites - `V10` 162, `card-too-short-after-review` 122, 19 sites both; 223 of the 265
carry a written description, 42 are site-held (Roman Bath and Altar of Athena Polias among them).
What those cards get is the Phase-5 sitting's.

**Coverage, T8-style - reported, not gating** (owner decision 2026-09-24, `PILOT_RESULT_3.md`):
**933 of 1,321 lane-W sites written = 70.6 %** (931 = 70.5 % after the two reverts); lane S 27 of 100.

### The audits and the re-verification

* **Mid-run audit** (after step 5): 45 of the 336 written sites (`midrun_sample.txt` `446663d5...`),
  `MIDRUN_AUDIT_VERDICTS.json` `15577da6...`: 280 sentences, 279 SUPPORTED, **1 WRONG_SITE** (Roman
  Bath, York, sentence 1: the pub); 36 cards contained, 9 sites without a card; 0 lost hedges or
  negations, flipped meanings, broken sentences, verifier false-passes or gold errors. The writes
  stopped; the reviewer's DROP line, its re-pin and the revert path are the entry above.
* **The WRONG_SITE check of every written site** (the design's consequence of a T2 hit): input
  `REVERIFY_WRONG_SITE_INPUT.jsonl` (`c5e56457...`, 336 sites, 2,046 sentences), answered by Opus
  (8 agents, per `C:/tmp/applied_today.md`), verdicts `REVERIFY_WRONG_SITE_VERDICTS.json`
  (`be5e964f...`, 336 entries): 333 without a hit, 3 flagged -
  * **Roman Bath, York** (p4-0036), sentences 1 and 2 - already taken back
    (`revert4.py --stamp-like 'phase4:p4-0036:chunk-0001' --site 70037a24-...`, 2 rows, reversals
    kept 2; `accept-after-roman-bath.log`);
  * **Altar of Athena Polias** (p4-0038, `78c18ef3-5f91-4629-bfef-37b0f13b2bef`), sentence 4: the
    Gigantomachy pediment belongs to the Archaic Temple of Athena Polias, not to the open-air altar
    (the verdict adds that sentences 2 and 3 carry the same conflation as a factual error). Held with
    `audit4.py hold` from `REVERIFY_WRONG_SITE_HOLDS.json` (`6af6a8b0...`; the `HOLDS4.jsonl` line
    cites file and digest), taken back with `revert4.py --stamp-like 'phase4:p4-0038:chunk-0001'
    --site 78c18ef3-...` (2 rows, reversals kept 2), accepted: 672 / 672 / 668 / 4, 334 re-verified,
    0 deviations (`accept-after-reverify.log`);
  * **Kit Hill** (pilot 4, p4-0003), sentence 6, subject "East Kit Hill Mine" (worked 1855-1909):
    **kept** - the mine is a later use of the hill itself, not another thing sharing its name. That
    judgement is the orchestrator's and is recorded only in `C:/tmp/applied_today.md`.
  Writes resumed with step 6.
* **The 500-site audit** (design entry [6]: "10 random written sites after every 500"): when the mass
  sites written passed 500 (step 8), 10 sites written since the first audit (`audit500_sample.txt`
  `3d050f2c...`; sheets `AUDIT500_SHEETS.md` `df5f3aba...`), verdicts `AUDIT500_VERDICTS.json`
  (`48fd22cd...`): **66 sentences, all SUPPORTED; 8 cards contained, 2 sites without a card; 0
  flags** of any kind. Group 8's write waited for it (verdicts 09:54, step 9 accepted 09:56 CEST).
  The next mark, 1,000 mass sites written, is not reached: 960.

### Fixed during the run (test-first, each with its sweep)

* `ccfb426` - `verify_writes4.py --run` repeats. The pilot's and the mass run's writes share the
  `phase4:` stamps, so a mass step's acceptance re-verifies the pilot's sites; with one `--run` it
  found them in no run and counted each as a deviation. A site two runs carry is refused. Sweep
  34/34.
* `004d522` - the acceptance reads a batch in full only when its `input.json` plans a written site
  (reading every batch stopped the first mass step's acceptance on the unassembled p4-0026); such a
  batch that cannot be read still stops it. Sweep 35/35.
* The reviewer's DROP line for a later building, business or institution sharing the site's name
  (pin `097c4589...`), `revert4.py --site`, `audit4.py hold` and the gate's re-plan without a reverted
  site: the entry above.
* `9c8f5ef`, `9f01785` - T03 reads a dot thousands separator. The review import stopped on p4-0076
  (`parse_year('35.000 BC') returned None for a digit token`, a Berbati sentence "around
  100.000-35.000 BCE") and p4-0084 (`'5.200 BC'`), and the gate's dry run stopped on the same assert
  three times (`group-p4-0074-review.log`, `group-p4-0082-review.log`): fail-closed, nothing written.
  After the fix both batches imported (p4-0076 9 assembled, 6 held; p4-0084 11 assembled, 4 held)
  and groups 9 and 10 were written. Sweep 1/1.

### Open

* **Lane L**, re-planned after step 14 as its entry requires: `LEGACY4.jsonl` `62772cac...`, 334
  batches; the gate reads live phase-4 provenance on 984 of 5,004 sites and plans **4,003 rows**
  (refused `written-by-p4` 984, `no-legacy-claim` 17 - HUMAN_ONLY D7: `same-as-snapshot` 9,
  `not-in-snapshot` 8), every batch rehearsed (`logs/p4l/rehearse-all.log`). It is being written
  now, step by step, by a background loop from this worktree: at 14:02 CEST steps 1 and 2 were
  accepted (99 and 94 sites; `lane journal rows 193 | carried 193 | not yet written 3810`, 0
  deviations) and step 3 (90 sites) was written. Its end: `verify_writes4.py --lane p4l --plan
  logs/_write_apply_p4l/LANE_PLAN.jsonl --complete`.
* **The Phase-5 sitting and Push #2** (HUMAN_ONLY D5): card texts through the journal, the card file
  regenerated byte for byte, the push. P5's plan reads this run's card holds above.
* **card_stats** (`card-stats-2026-09-23`, the main checkout's runbook step 1): its premise holds
  `md5(description)`, so it is re-planned now that the P4 writes have ended.
* **The 19 `revision-too-fresh` sites**: `mass4.py` re-queues them itself 48 h after their hold -
  "19 waiting (the first until 2026-09-26T21:30:14+00:00)" in every round's header.
* **The final acceptance of 60 sites** (`acceptance/PROTOCOL.md`, sealed on `integrate/wave1`): its
  draw takes this run's audit samples as exclusions (`logs/p4_mass/midrun_sample.txt`,
  `audit500_sample.txt`).
* **The merge into `integrate/wave1`**: `wip/merge-p4` (worktree `.claude/worktrees/merge-p4`) holds
  `wip/p4-pilot` up to `9f01785`; this entry and `MASS_RESULT.md` come after it, and it lacks
  `integrate/wave1`'s five Phase-6 commits `ff9a570` .. `a2ac917`.
* The selector's rule (8) keeps the gap the reviewer line closes (entry above): a decision for a
  later run.

## 2026-09-25 - `verify_writes4 --allow-stamp`: the two sites P4 took back and lane L then marked are superseded, not MOVED (read-only, nothing written)

After lane L was written in full, the P4 acceptance (`verify_writes4.py --lane p4 --plan
logs/_write_apply_p4/LANE_PLAN.jsonl --run runs/pilot4-2026-09-24 --run runs/mass-2026-09-25`)
reported **2 deviations**: `MOVED 70037a24-... unified_sites.raw_data` (Roman Bath, York) and `MOVED
78c18ef3-... unified_sites.raw_data` (Altar of Athena Polias). Both were written by P4, taken back
with `revert4.py --site` (own reversals kept) and held (`audit-wrong-site`); their description is the
March text again, so lane L rightly wrote its legacy provenance into their raw_data. Journal, read
only: 34910 (`phase4:p4-0036:chunk-0001`) -> 36607 (its `-rollback`) -> 65295
(`phase4l:p4l-1144:chunk-0001`), and 34982 -> 36611 -> 65572 (`phase4l:p4l-1155:chunk-0001`).
The acceptance judges an all-reverted row like one not yet written, and the raw_data no longer held
its planned old value.

**The fix** (`a9a52b0`, test-first), after Phase 3's `verify_writes --allow-stamp`:

* `--allow-stamp` is repeatable and takes SQL LIKE patterns (`write_gate4.like_matches`, imported).
* A planned row the lane did not write, or whose lane rows are all reverted, that no longer holds its
  planned old value is **superseded** (counted per allowed pattern) when its chain after the lane's
  last own link - a write or its own reversal (`reverses`, the predicate `reverted` already used) -
  runs continuously (`verify_writes.check_chain`) from the planned old value to the live value, every
  link by an allowed stamp that is not one of the lane's own or their `-rollback`. With no own link in
  the chain the whole chain must be that run, so an earlier link of another stamp leaves the row
  MOVED (the stricter reading; no such row exists today). Anything else stays MOVED, word for word.
* **Written rows, mirrored from `verify_writes`** (its docstring: "superseded when every later link
  belongs to a stamp the operator names"): a lane row after which only allowed stamps wrote is
  superseded instead of CHANGED LATER and is not carried, so its site is not re-verified as the
  lane's. A later stamp that is not allowed stays CHANGED LATER.
* The lane line gains `| superseded N`, then `allowed later:` and `superseded by <pattern>: N`.
  `write_gate4 --accept` matches the lane line by its prefix (`_ACCEPT_LANE`), so the parser is
  unchanged; a test feeds the tool's real output to `acceptance_problems`, and the gate tests'
  fixture lines carry the new field.

**Acceptance, 2026-09-25, from the main checkout, read-only** (logs in
`output/remediation/logs/p4_accept_allow/`, gitignored):

| run | planned / journal / carried / not yet written | superseded | re-verified | RESULT | sha256 |
|---|---|---|---|---|---|
| `--lane p4`, both runs, `--allow-stamp 'phase4l:%'` | 1,972 / 1,972 / 1,968 / 2 | 2 (`phase4l:%`) | 984 | **0 deviations**, `ACCEPT_EXIT=0` | `20a0d5b1` |
| the same without `--allow-stamp` | 1,972 / 1,972 / 1,968 / 2 | 0 | 984 | the 2 MOVED lines as before, `ACCEPT_EXIT=1` | |
| `--lane p4l --complete` | 4,003 / 4,003 / 4,003 / 0 | 0 | | **0 deviations** | `c8d765f3` |
| `--lane p5`, both runs, `--complete --card-check` | 1,107 / 1,107 / 1,107 / 0 | 0 | 756 | **0 deviations** | `1de10782` |

Gates: full suite 6,918 passed, 4 skipped, 57 deselected; `ruff check` and `ruff format --check` on
the touched files, `ruff check api/ pipeline/`, `lint-imports` (2 kept), `vulture` clean.
`mutation_sweep.py verify_writes4`: **50/50 caught** (35 earlier cases, two of them re-anchored
because the reversal predicate moved into `reverses`; 15 new), the tree byte-identical, no mutant
left.

## 2026-09-25 - Acceptance draw-2026-09-25 ends FAIL on A3 (D1); the D1 class measured over all curated sites, root-caused, and its repair lane `orphan-citations` (planned, checked and rehearsed on production; not applied)

### The run's result (PROTOCOL.md sections 9 and 10)

`judge.py deterministic` (15:34:43 UTC, `DETERMINISTIC.json`, commit `c546b0f`): **D1 fails on
Kuntur Amaya** (`fc514046-4f2c-42b1-a3f6-ca88404d2e18`). Its description has no `[N]` marker, but
`raw_data.description_citations` holds entry 1 (census T08 `no-markers`; the T08 docstring names
this site). D2-D6 hold. Under rule A3 the run can only end FAIL (or VOID). It is recorded as
**FAIL** under section 10: `output/remediation/acceptance/draw-2026-09-25/RESULT.md`, written by
hand because `judge.py result` scores only a finished run (commit `9c7f1eb`, with `CANARIES.jsonl`).

* **Stages 1-3 were not run.** Stage 1 was exported (653 questions, 54 batches) and got 0 answers.
  V1 and V2 were not assessed. V3 holds: at 15:51:53 UTC the journal's maximum id was still the
  draw's mark 73180.
* **No artefact of this run is reused.** The next draw uses seed 20260926, canaries 20260927 and
  excludes this draw's 60 (see "The fresh acceptance" below).

### The class over all 5,004 curated sites (read-only, 15:41 UTC, journal max 73180)

The exact D1 rule of `checks.d1` (the census's `marker_sequence` and `entries`) was run over every
`source_id = 'ancient_nerds'` row:

| subclass (T08 name) | sites | lane-L provenance | none | last writer of the description |
|---|---|---|---|---|
| no marker, entries present (`no-markers`) | **64** | 62 | 2 (Huichún, Temple of Baalshamin) | none: no journal row |
| every marker answered, entries no marker cites (`entry-never-cited`) | **5** | 5 | 0 | none |
| a marker without an entry (`marker-without-entry`) | **7** | 7 | 0 | none |
| both halves (Absalom's Tomb, Killa Mach'ay) | **2** | 2 | 0 | none |
| **D1 fails** | **78** | 76 | 2 | |

* **4,926 sites hold D1**, including every one of the 984 live Phase-4 texts. Their arrays are
  assembled by code, V8. None of the 78 is retired or pending.
* **Journal.** None of the 78 descriptions has a journal row. On `raw_data` the 76 carry lane L's
  row only and the 2 carry none. So no journalled writer (Phase 3, Phase 4, the mechanical lanes)
  touched the class.
* **The census.** On 2026-09-20 census T08 found 76 no-markers, 11 marker-without-entry and 8
  entry-never-cited (the 4 numbering-gap findings are no D1 failure). Today's class is exactly
  that set minus the 15 sites Phase 4 rewrote (12, 2 and 1). No instance is new since the census.
* **History.** Each of the 78 is byte-identical, description and array, to snapshot `e4652afe`
  (`db_snapshots`, 2026-04-24, "Before Turkey -> Türkiye backfill"). None had an array in
  `d4526691` (2026-03-05, before the March chain). The snapshots between them are the
  byte-identical replace-source copies.
* **The SQL form of D1** (`lane.CITATIONS_UNCITED` / `CITATIONS_UNANSWERED`, the census marker
  `\[(\d+)\]`) finds the same 78 ids (71 with an uncited entry, 9 with an unanswered marker). No
  curated description carries a grouped or range marker, so the plain form is every marker.

### Root cause

The March chain wrote the text and the array as two values, and nothing compared them:

* **`scripts/audit_enrich.py::merge_verification`** (`:2667`) stored the verifier's
  `verified_description` and `verified_citations` as they came. The prompt
  (`VERIFICATION_AGENT_PROMPT`, `:2420`) told the model to "remove the ENTIRE sentence
  containing the unverifiable [N]", "renumber remaining [N] citations" and "update the citations
  array to match". No code checked it. `merge_cited_descriptions` validated the entries' fields,
  not the markers.
  * The **marker-without-entry**, **entry-never-cited** and **both** rows are that renumbering
    done on one side only.
  * Absalom's Tomb: the text cites [6], [7] and [8], while the array's 4, 5 and 6 carry those
    sentences almost word for word.
  * Kinal's last sentence is marked [1][2], and entry 3's claim is that sentence.
  * Killa Mach'ay cites [4], and entry 2 ("3,400 metres") is cited by nothing.
* **`api/routes/sites.py::batch_upload_sites`** (`:1795-1822`) wrote the description, and then
  the array only if the upload carried one. It never removed an array.
  **`audit_enrich.py::sync_from_production`** (`:196`) overwrote the local description from
  production without touching `raw_data`. Either path pairs a text with the array of another
  state.
  * The **no-markers** rows are that kind of pairing. **Huichún** proves it: its description is
    byte-identical to its pre-March text, which never had a marker, and its array is the chain's.
  * For the other 63 the data cannot tell which path lost the markers. No intermediate state
    survives: the March batch files are not on this machine, and no snapshot between 03-06 and
    04-24 holds these rows.
* **Not the cause:**
  * The Phase-4 write path: none of the 78 has a `phase4:` row, and P4 fixed 15 of the census's.
  * The boot citation seed removed in Push #1: it covered 10 other sites (`52c19d4`), none of
    the 78.
  * The boot marker strip (`52c19d4`..`4cda8c3`): it removed markers only where the key was
    absent, so it cannot leave an array behind.
* **Why it survived.** The census filed every T08 finding `REVIEW`, and plan Phase 1 item 8
  ("immediately actionable") never got a lane.

### What a reader sees (`ancient-nerds-map/src`, `api/`, `pipeline/`)

* **The popup** (`SitePopup/sections/DescriptionSection.tsx:46-65, 131-152`) builds its source
  links from every entry, cited or not, grouped by domain, with the entry's `[n]` in the tooltip.
  The one exception is entries on the domain of the site's own `source_url`, which the source line
  already links. **Measured over the 69 planned sites:** 61 show the same links after the write.
  8 lose a link:
  * Carmona: artsandculture.google.com;
  * Altar of the Twelve Gods: perseus.tufts.edu, topostext.org;
  * Belören Kalesi: beloren.wordpress.com;
  * Borough Hill, Sawston: eprints.oxfordarchaeology.com;
  * Temple of Khonsuirdis: en.wikipedia.org. Its entries are the general articles "List of
    Egyptian temples", "Psamtik I" and "Luxor", and it has no `source_url`, so after the write
    its popup shows no source link;
  * Agios Georgios Hill: ledroimuseum.com;
  * Bedd Taliesin: coflein.gov.uk;
  * Agri Bavnehøj: visitaarhus.com.
* **The server-rendered body** (`pages/SitePage.tsx:114` -> `CitationText.tsx`) reaches an
  entry only through its marker. An orphan entry is invisible there, and a marker without an
  entry is a bare `<sup>[N]</sup>`. The same holds for the meta description and JSON-LD
  (`stripCitations`; `isBasedOn` comes from the provenance only) and the listing cards.
* **The library and the popup's References tab** (`pipeline/library_aggregator.py:265-316`)
  register every entry with a URL. `_flush_to_db` never deletes, and it replaces `parent_refs`
  only for the URLs a refresh sees. Measured today (read-only): **521 site references at 429
  curated sites** point at a URL the site no longer cites, almost all from Phase 4's replaced
  arrays. This lane adds its removed entries to that. It is an open item of its own, below.

### The repair, per subclass (field contract: never rewrite the text, never invent a source)

* **no-markers, 64 sites: the `description_citations` key is removed**, and every other
  `raw_data` key stays as it is. A row whose only key was the array keeps `{}`. The text cites
  nothing, so an entry cites nothing. Where the popup shows it, it presents a source of a claim
  the text does not mark. Temple of Baalshamin's one entry ("Byzantine settlements in
  northwestern Syria") is not even about the temple.
* **entry-never-cited, 5 sites: only the entries no marker cites are removed.** The cited
  entries stay byte for byte and in order. A numbering gap stays, because renumbering would
  rewrite the text.
* **marker-without-entry, 7 sites, and both halves, 2 sites: listed for a human, nothing
  written**, not even the uncited entries of the 2 (HUMAN_ONLY.md D9). The source of a marker is
  not in the data. On the two sites with both halves, the uncited entries are the evidence for
  the right array-only repair.
* The removed entries survive in the journal's `old_value`. Putting one back means putting its
  marker into the text.

### The lane (`scripts/remediation/mechanical/citations.py`, `lane.ORPHAN_CITATIONS`)

* **Cell lane `orphan-citations`.** One cell, `unified_sites.raw_data` as `jsonb`. Run stamp
  `2026-09-25_mechanical-orphan-citations`, test id `T08/orphan-citations`, the server bounds of
  the later lanes. Output: `output/remediation/mechanical_citations/`.
* **The premise** (guard 5) is `encode(sha256(convert_to(coalesce(u.description, ''), 'UTF8')),
  'hex')`: the description the markers were read from, as `_description_provenance.desc_sha256`
  pins it. It equals that pin on all 67 lane-L planned sites.
* **Residual** (post-commit and rehearsal): the SQL form of D1. The read-back adds:
  * each half of D1;
  * the rows carrying an array;
  * D4 in SQL (the description vs its provenance hash);
  * this run's journal rows that changed another `raw_data` key;
  * this run's journal rows that added an entry.
* **`citations.py --export`** reads, in one repeatable-read snapshot, every curated row (the
  description, `raw_data::text`, the premise) and the `raw_data` journal of the curated rows. The
  export is gitignored.
* **`--write`** plans from the export alone. It refuses `citations-not-readable`,
  `marker-without-entry`, a raw_data journal that does not end at the live value (compared as
  JSON with sorted keys) and a value the planner would not print as Postgres prints jsonb. Every
  planned value is read with `acceptance.checks.d1` before the plan is kept.
* **Tests:** `tests/remediation/test_mechanical_citations.py`, 26, all red before the module (a
  collection error). The registry tests of `test_mechanical.py` cover the new lane through its
  committed plan.
* **Sweep:** `mutation_sweep.py orphan-citations`: **20 cases, 20 fired**. The files come back
  byte-identical and no mutant is left.

**The plan** (`PLAN.jsonl` sha256 `86671d1a704b9732b32138421968750c21e670ab24d980be59192c273aabf372`,
export 16:00:18 UTC):

* **69 cells over 69 sites**: 64 `citations-without-markers` and 5 `uncited-entries`. 51 lose 1
  entry, 9 lose 2, 7 lose 3 and 2 lose 4.
* **9 listed**, all `marker-without-entry`: `SKIPPED.jsonl`, with the text excerpt and every entry.
* No other refusal fired.
* The first rendering had `generic-api-key` findings from gitleaks. A note ended in "...raw_data
  key stay as they are'" right before the premise hash. The note was reworded rather than the
  finding allowlisted. Scanning the staged plan now finds no leaks.

### On production (read-only, and ROLLBACK only), 2026-09-25 16:00-16:05 UTC

* `--check-primitive`: the 0022 body (t, t, t).
* **`--verify` before:**
  * curated sites 5,004;
  * **D1 fails 78**; uncited entry 71; unanswered marker 9;
  * carrying `description_citations` 2,749;
  * description not the one its provenance hashes 0;
  * every journal metric of the stamp, the test id and the rollback stamp 0.
* **`--probe-guards` exit 0**: 5 probes (guard3-foreign-old-value, guard2-no-op,
  guard2-foreign-column, guard1-other-source, guard5-premise). Each was refused by its own guard,
  and 0 journal rows were left.
* **`--rehearse`**: `orphan citation removal: 69 of 69 planned cell(s) changed and journalled over
  69 curated site(s)`, then ROLLBACK. Afterwards the stamp has 0 journal rows, D1 still fails on
  78, and the temp table is gone.
* **The write and its reversal in one transaction**, a one-off beyond the framework (the
  framework rehearses the undo only on landed rows). The script is APPLY.sql up to its COMMIT,
  reads, then ROLLBACK.sql's body, reads, then ROLLBACK (`logs/orphan_citations/WRITE_AND_UNDO.sql`
  and `write-and-undo.txt`, gitignored):

  | read | D1 fails | uncited | unanswered | carrying | provenance hash differs | journal rows (stamp / rollback) | another raw_data key changed |
  |---|---|---|---|---|---|---|---|
  | after the write | **9** | 2 | 9 | 2,685 | 0 | 69 / 0 | 0 |
  | after the reversal | 78 | 71 | 9 | 2,749 | 0 | 69 / 69 | 0 |
  | after ROLLBACK | 78 | 71 | 9 | 2,749 | 0 | 0 / 0 | 0 |

### The apply (the orchestrator runs it)

Repository root, main venv, `export PYTHONIOENCODING=utf-8`, `PY=./.venv/Scripts/python.exe`,
`A=scripts/remediation/mechanical/apply.py`, `W=.claude/worktrees/p4-pilot/output/remediation`
(where the Phase-4 lane plans live).

0. **The plan still stands.** `$PY $A --lane orphan-citations --verify` -> D1 fails 78, journal
   rows for this run stamp 0.
   * Watch for writes that touched a planned site's `raw_data` or description, above all the
     re-queue of the 19 `revision-too-fresh` sites from 2026-09-26T21:30Z. Guards 3 and 5 refuse
     them in any case.
   * If anything moved:
     `$PY scripts/remediation/mechanical/citations.py --export --write`, then
     `$PY $A --lane orphan-citations --emit`, then
     `$PY -m pytest tests/remediation/test_mechanical_citations.py tests/remediation/test_mechanical.py -q -m "not integration and not live_llm"`
     green. Run gitleaks over the staged lane directory, and commit it before going on.
1. **Check.** `$PY $A --check-primitive`, then `$PY $A --lane orphan-citations --probe-guards`
   -> exit 0, the same 5 probes, each refused by its own guard.
2. **Rehearse.** `$PY $A --lane orphan-citations --rehearse` -> `69 of 69 planned cell(s) changed
   and journalled over 69 curated site(s)`, ROLLBACK, 0 journal rows.
3. **Apply.** `$PY $A --lane orphan-citations --apply` -> `APPLY OK: the read-back matches the
   plan, row for row` (exit 0). Exit 3 is NOT COMMITTED and exit 5 OUTCOME UNKNOWN: read the
   journal for the stamp before anything else, and never apply twice.
4. **Read back.** `$PY $A --lane orphan-citations --verify` -> the expected values:
   * journal rows for this run stamp 69 and for this test id 69;
   * **D1 fails 9**; uncited entry 2; unanswered marker 9;
   * carrying `description_citations` 2,685;
   * provenance hash differs 0;
   * 0 for: another raw_data key changed, an added entry, outside `raw_data`, non-curated rows,
     another site's `site_id_ref`.
5. **Rehearse the rollback on the landed rows.** `$PY $A --lane orphan-citations
   --rehearse-rollback` -> `69 of 69`, ROLLBACK, the cells still holding the written value.
   Commit `REHEARSAL_ROLLBACK.sql`, as for the other lanes.
6. **Acceptance.**
   * (a) D1 by the acceptance's own function over every curated row:
     `$PY scripts/remediation/mechanical/citations.py --export --write --out output/remediation/logs/orphan_citations/after`
     -> `"d1_fails": 9, "marker-without-entry": 9`, no planned cell (the delivered plan stays
     untouched).
   * (b) Lane L, whose 67 rows this lane supersedes:
     `$PY output/remediation/tools/verify_writes4.py --lane p4l --plan $W/logs/_write_apply_p4l/LANE_PLAN.jsonl --complete --allow-stamp '2026-09-25_mechanical-orphan-citations'`
     -> 4,003 planned, 4,003 journal, 3,936 carried, **superseded 67**, **0 deviations**.
     Without `--allow-stamp` the same run names the 67 as changed later.
   * (c) Phase 4 and Phase 5 are unchanged, since no P4-written or P5 cell is touched:
     `$PY output/remediation/tools/verify_writes4.py --lane p4 --plan $W/logs/_write_apply_p4/LANE_PLAN.jsonl --run $W/phase4_runner/runs/pilot4-2026-09-24 --run $W/phase4_runner/runs/mass-2026-09-25 --allow-stamp 'phase4l:%'`
     -> 0 deviations, as on 2026-09-25.
7. **Static export** (the globe's popup reads `dc` from `/data/sites/index.json`; the SSR page and
   the API read the database, `/api/sites/all` through a Redis TTL):
   * the Phase-6 runbook step 3 commands (chown, then
     `ssh ancientnerds "docker exec ancient_nerds_api python -m pipeline.static_exporter --no-library"`);
   * check: `ssh ancientnerds "grep -c 'Kuntur_Amaya' /var/www/ancientnerds/public/data/sites/index.json"`
     -> 0.

### The fresh acceptance (section 10)

**`draw.py` cannot take it.** `SEED = 20260925` is a module constant (`take_draw`,
`command_draw`; the canaries use `SEED + 1`), and there is no exclusion source for a previous
draw. Passing the old `SAMPLE.jsonl` through `--phase4-audit-samples` would mislabel it and still
draw with 20260925. `draw.py` is sealed (SEAL.json, the first `DRAW.json`), so it stays byte for
byte.

**`scripts/remediation/acceptance/redraw.py`** (commit `1f08d20`, test-first) imports draw.py's
reads, exclusions, canaries and files, and adds two things:

* **The seed**: one past the highest seed of the `--after` draws, so 20260926 and canaries
  20260927.
* **The previous draws' sites** as exclusion records `previous-draw-<name>`. Each previous
  `SAMPLE.jsonl` is read only as its `DRAW.json` pins it, only once its `RESULT.md` exists, and
  only its drawn `site_id`s are excluded.
* **`DRAW.json`** keeps every key `judge.py` reads and adds `canary_seed`, `after` and
  `redraw_py_sha256`.
* **Tests:** `test_acceptance_redraw.py`, 16. The committed draw-2026-09-25 reads as 60 pinned
  sites, with seed 20260926 next.
* **Sweep:** `mutation_sweep.py acceptance-redraw`, **12 cases, 12 fired**.
  `test_the_seal_holds` is unchanged and green.

**Seal for the fresh draw** (sha256 over LF bytes; record it again at the draw if anything
changes):

* `PROTOCOL.md` `f40fac87230a26e7b1a4818e9d50d16dedfcb6936fc795b532e2cb35789f8bff` (unchanged);
* `draw.py` `0a12beb461eb6aca6c921a4677b08472b4c8ff5068afd06af88a1baaf452515e` (unchanged);
* `redraw.py` `fd12f2091066841ea46be120b81b0cc93ff98d05290326dc176d41c94d733fc9`;
* `EXCLUSIONS.sha256.json` `dff9dd9a48a3199ebc6e7bb08bcafa31707f993f8f0a4a73c45bedbb0cf5dfb3`
  (unchanged).

**When:** after the apply above, and after the 19 `revision-too-fresh` sites' re-queue has
written or held them (a P4 write on a drawn site after the draw voids the run, V3).

    $PY scripts/remediation/acceptance/redraw.py --out output/remediation/acceptance/draw-<date> \
        --after output/remediation/acceptance/draw-2026-09-25 \
        --phase4-audit-samples .claude/worktrees/p4-pilot/output/remediation/logs/p4_mass/midrun_sample.txt \
            .claude/worktrees/p4-pilot/output/remediation/logs/p4_mass/audit500_sample.txt \
            output/remediation/phase4_runner/PILOT3.jsonl output/remediation/phase4_runner/PILOT4.jsonl

These are the first draw's four Phase-4 audit sources. Then commit `FRAME.jsonl`,
`EXCLUDED.json`, `SAMPLE.jsonl` and `DRAW.json`, and run `judge.py deterministic` **first**: this
time it decided A3 before a single question was answered. Then stages 1-3 and `result`.

**The residual risk.** The 9 listed sites stay D1 failures until a human repairs them
(HUMAN_ONLY.md D9). All 9 are in the next pool: 4,194 sites, counting the first draw's frame
minus its exclusions and its 60. A sample of 60 then hits at least one with probability **12.2 %**
(`1 - C(4185,60)/C(4194,60)`). The recommended path is D9 before the draw.

### Open

* **HUMAN_ONLY.md D9**: the 9 sites with a marker without an entry.
* **The library's stale "Cited in" links.** 521 references at 429 curated sites, from Phase 4
  and after this lane from its removals. `library_aggregator._flush_to_db` never drops a site
  from a URL it no longer sees. That is a code change in `pipeline/` (prune `parent_refs` per
  refresh, like `_STRIP_RETIRED_REFS` does for retired sites). It is not made here.

### Tests, sweeps, gates (main checkout, branch `integrate/wave1`, main venv)

* Full gate suite (`-m "not integration and not live_llm"`, `--timeout 300`,
  `-p no:cacheprovider`): **7,071 passed, 4 skipped, 57 deselected, 0 failed** (221.7 s). The
  skips are the known four.
* New tests: `test_mechanical_citations.py` (26) and `test_acceptance_redraw.py` (16). Each was red
  before its module existed (a collection error). The registry tests of `test_mechanical.py` take
  the new lane from its committed plan.
* Sweeps: `mutation_sweep.py orphan-citations` **20/20 fired** and `acceptance-redraw`
  **12/12 fired**. None skipped, survived, invalid, unproven or errored. The swept files came back
  byte-identical and no mutant is left. `test_mechanical_sweep.py` is green (21).
* Linters: `ruff check` and `ruff format --check` clean on the 6 touched Python files (ruff
  0.15.11). `ruff check api/ pipeline/` clean. `lint-imports` 2 kept, 0 broken.
  `vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80` clean.
* gitleaks over the staged lane directory: no leaks.
* Not applicable: nothing under `ancient-nerds-map/`, `api/` or `pipeline/` was touched, so
  there is no frontend gate and no Lyra-image import check.

## 2026-09-25 - HUMAN_ONLY D9 into Phase 4: scope version 2, the D9 plan and run up to its select export, and lane L's order (nothing written)

Branch `wip/p4-pilot` (worktree `.claude/worktrees/p4-pilot`, fast-forwarded to `integrate/wave1`
`fe48bf0`), main venv. **Nothing was written to production**: every read was a SELECT, the lane-L
reversals were rehearsed only (ROLLBACK), and no model was called - the selector questions are
exported, not answered. Contracts: `PHASE4_CONTRACTS.md` section 11.

### The order and the recommendation taken

Owner order 2026-09-25 (Martin, "keine Fragen mehr, autonom Empfehlungen umsetzen"): the recommended
path is carried out. HUMAN_ONLY D9 lists the 9 curated sites whose description sets a `[N]` that
`raw_data.description_citations` has no entry for (the orphan-citations lane's `SKIPPED.jsonl`, entry
"Acceptance draw-2026-09-25 ends FAIL on A3 (D1)" above). Taken: option (c) - a marker without an
entry is a proven text defect, so the 9 join the Phase-4 defect scope and get a sourced description
through the same Phase-4 pipeline (pilot 4 passed T1-T7; lanes W and S open), or stay held with a
closed-list reason where the pipeline holds them.

### Scope version 2 (`phase4/scope4.py`, `phase4_runner/SCOPE4.v2.json`)

* **The file**: `SCOPE4.v2.json`, sha256
  `7256a1962ffe1b2449c7028e1174fe623d7de19fdddde2083f560790f7003173`, pinned in
  `scope4.SCOPE_SHA256`; `SCOPE_VERSION = 2`. Built by `plan4.py scope` (the current version by
  default) from version 1's inputs - `S0_ROWS.jsonl` (`2c99f96f...`) and
  `logs/_write_dry/ALL_REFUSED.jsonl` (`7b4026d0...`) - and the lane's listing
  `mechanical_citations/SKIPPED.jsonl` (`28dadb0b...`, commit `8bfa54f`, `--markers`), whose digest
  joins the file's `inputs`.
* **The lists**: `phase3-cleared-description` 322, `phase3-cleared-card` 709, `ungrounded-card` 876,
  **`d1-marker-without-entry` 9** - **1,631 sites** (1,623 + 8). The new list's source is named in the
  file's `methods` (the listing, reason `marker-without-entry`, D1 over every curated row of the
  lane's export of 16:00:18 UTC) and its decision is version 1's plus the order above
  (`scope4.ORDER_2026_09_25`).
* **No site on the listing's word**: the build reads each listed site's own S0 row with D1's reading
  (`scope4.markers_without_entry`: census T08's `marker_sequence` and `entries`, as
  `acceptance/checks.d1` reads them) and refuses one whose every marker has its entry, or that is no
  curated row. All 9 fail D1 on their S0 rows, and those rows are the live ones: their S0 and
  `LEGACY4_ROWS.jsonl` (13:36 CEST) rows are identical, and today's production values (read-only,
  journal max id 73734) are the S0 values plus lane L's `_description_provenance` (the card also
  equal, except Killa Mach'ay's, cleared by P5).
* **Version 2 refuses nothing version 1 allowed**: every version-1 site is a version-2 site whose
  lists begin with its version-1 lists (tested on the committed files). Version 2 adds the 8 listed
  sites version 1 did not hold, each in the new list alone; Killa Mach'ay (`867f08af`), a
  `phase3-cleared-card` site, gains the list as its second.
* **Version 1 stays** (`SCOPE4.json`, unchanged, now `scope4.SCOPE_V1_SHA256`): `plan4.py scope
  --version 1` rebuilds it byte for byte; `scope4.load_scope(1)` reads it at its own pin; `plan4.py
  build --pilot PILOT4.jsonl --defect-scope` builds the mass run's plan from it, and it rebuilt
  `PLAN4.scope.jsonl` byte for byte (`fec90379...`, 1,578 sites). The writers, `mass4` and the new
  list plan read version 2; a file of one version at the other's pin is refused.
* **No flag**: the list adds no `SiteFlag`. A marker without an entry says nothing about the truth
  of the text around it, so V9's 50 % floor stays for these sites (Acci's `t03-severe` waives it for
  Acci alone).

### Killa Mach'ay stays the mass run's

Killa Mach'ay was already in version 1 and in the mass run: `runs/mass-2026-09-25/p4-0042`, held
`abstained` ("no sentence can be the CARD: W1 names Peru, W2 and W4 open with It, and W3 is only 67
characters"); P5 then cleared its card (`phase5:p5-0042:chunk-0001`, journal 71871). A run never asks
its sites again, and `verify_writes4.index_runs` refuses a site two runs carry whenever both batches
hold a written site (p4-0042 does) - a D9 batch holding it would stop every later P4 acceptance. So
it is not planned again: it **stays held with a closed-list reason (`abstained`)** and stays a D1
failure. The plan reports it (`carried_by_earlier_plans`).

### The plan: 8 sites in p4-0901, not p4-0116

`mass4.requeue_lines` numbers the mass run's re-queued sites after the last ordinal of its plan and
of earlier re-queues - **p4-0116 on** - into `runs/mass-2026-09-25/REQUEUE4.jsonl`, and the 19
`revision-too-fresh` sites wait for exactly that (the first from 2026-09-26T21:30:14Z). Every run
writes into the one P4 apply root and a journal stamp names its batch (`phase4:p4-NNNN:chunk-0001`),
so a D9 batch p4-0116 would share its directory and stamp with the mass run's first re-queued batch.
The gate refuses a written batch re-planned from another plan and the preflight a stamp that
journals rows, but a dry render of either would silently replace the other's unwritten plan. The
list plan therefore has a block of its own: **p4-0901** (`plan4.LIST_PLAN_FIRST_BATCH`; lane L's
plan starts at p4-1001), and it refuses to start where an earlier plan already numbers.

    $PY scripts/remediation/phase4/plan4.py build --pilot $R4/PILOT4.jsonl \
        --scope-list d1-marker-without-entry --after $R4/PLAN4.scope.jsonl --out $R4/PLAN4.d9.jsonl

`PLAN4.d9.jsonl` (gitignored) sha256 `c38886e0...` (`logs/p4_d9/plan.out`): **1 batch, p4-0901, 8
sites** in the design's order - Acci (`t03`, `t03-severe`), Temple of Zeus (Kyrene, `t03`), Laüs,
Porth Hellick Down, Ağbulaq Necropolis, Afrodit Tapınağı, Absalom's Tomb, A Figa; listed 9, carried
by an earlier plan 1 (Killa Mach'ay), in the pilot 0. A first attempt that also named
`PLAN4.pilot4.jsonl` with `--after` was refused ("no site of the list is left to plan"): that file is
the full 5,004-site plan, of which pilot 4 ran only its 9 batches; the pilot's sites are `--pilot`'s.

### The run up to the select export (`runs/d9-2026-09-25`)

    $PY scripts/remediation/phase4/mass4.py --plan $R4/PLAN4.d9.jsonl --run-dir $R4/runs/d9-2026-09-25 \
        --log-dir $M/logs/p4_d9 --stages prepare,sources,routes,select --searches-off --live \
        --handoff-export $M/handoff/p4-d9-select

`logs/p4_d9/export.out`: `defect scope SCOPE4.v2.json v2 7256a1962ffe1b24: 0 site(s) of the open
batches outside it`, searches off (no MiniMax client), `sources phase4 6037a01ce927eb2d`, `p4-0901:
done (prepare,sources,routes,select: every stage printed STAGE_EXIT=0)`, `STAGE_EXIT=0`.

* **Lanes at S1b** (`p4-0901/lanes.jsonl`): **W 6** - Acci (rev 1365083849), Temple of Zeus
  ("Temple of Zeus, Cyrene", 1357486765), Laüs (1374837200), Porth Hellick Down (1364975097),
  Ağbulaq Necropolis ("Ağbulaq necropolis", 1364725990), Absalom's Tomb ("Tomb of Absalom",
  1369713184), each subject verdict `own`, none younger than 48 h; **none 2**, held
  `search-stopped` before any question (searches off): Afrodit Tapınağı (no `enwiki_title`, its
  `source_url` is UNESCO list 1519) and A Figa (no `enwiki_title`, no en article of that name, one
  geosearch article within 2 km). `HOLDS4.jsonl` 2 lines.
* **The ledger** (`runs/d9-2026-09-25/LEDGER.jsonl`): 13 fetch lines, every one HTTP 200, 0 model
  lines.
* **The handoff**: `handoff/p4-d9-select/p4-0901` - **6 selector questions** (`MANIFEST.jsonl`
  `f2822eb0...`). `opus_handoff.py validate --dir handoff/p4-d9-select`: questions 6, **answered 0,
  missing 6**, stale 0, malformed 0, orphans 0.

### The apply roots, the gate and the acceptance with a third run

* The D9 run writes into the same apply roots, `logs/_write_apply_p4` (write batch p4-0901) and
  `_write_apply_p5` (p5-0901), so each lane keeps one `LANE_PLAN.jsonl`, and every p4 and p5
  acceptance names all three runs (`--run` pilot 4, mass, d9). Neither root has a step awaiting its
  acceptance (P4 14 accepted, P5 13).
* **The gate over the run before its answers** (`write_gate4.py --group P4 --run d9-2026-09-25
  --open-lanes W,S`): it ended in a `FileNotFoundError` for `p4-0901/assembly.jsonl` **without its
  `WRITE_EXIT=` line**. Fixed test-first: `write4.load_batch` refuses a batch short of `lanes.jsonl`,
  `assembly.jsonl` or `holds.jsonl` as the hole it is (`PlanInputError`), and the gate now prints
  `REFUSED: p4-0901: no assembly.jsonl: the batch has not reached an outcome - the gate plans a batch
  once its review is imported` and `WRITE_EXIT=1` (`logs/p4_d9/gate-p4-dry-before-answers.log`); the
  apply root's listing is unchanged. Every finished batch of pilot 4 and the mass run carries all
  three files (115 of 115). The gate plans the batch once its review is imported - the refusal of
  an unfinished batch is the design's (a hole, not a set of refusals), not a refusal of the run.
* **A third run beside two** (`test_a_third_run_is_written_into_the_apply_root_two_runs_wrote`):
  pilot 4's and the mass run's batches written and accepted, the D9 run's p4-0901 planned, written
  and accepted in the same apply root - their records byte for byte unchanged, the step's stamp
  `phase4:p4-0901:chunk-0001`, the lane plan every run's rows.
* **The P4 acceptance with the D9 run named** (read-only, `logs/p4_d9/accept-p4-three-runs-before-d9.log`
  `b50b2e35...`): `verify_writes4.py --lane p4 --plan logs/_write_apply_p4/LANE_PLAN.jsonl` (`f3a7899e...`)
  with the three runs and `--allow-stamp 'phase4l:%'` - planned 1,972, journal 1,972, carried 1,968,
  not yet written 2, superseded 2, **984 re-verified, 0 deviations**, `ACCEPT_EXIT=0`, as without it:
  the D9 batch holds no written site and is not read (`004d522`).

### Lane L's order: its row is taken back before the P4 write (the design's way)

Lane L marked every March-AI text P4 had not written, and so all 9 listed sites (journal, read-only:
each has exactly one `raw_data` row since S0, its L row; no description row). The D9 plan names S0's
values, so **P4's preflight would refuse the batch** (`<id>/raw_data: the row no longer holds the
planned old value`): proven below.

**Decision: revert the L row first, with `revert4.py --site`, for exactly the sites the P4 dry plan
writes, after the review import - not a fresh plan read.** Contracts section 9 names this way ("the
way back is `revert4.py --stamp-like 'phase4l:...' --site <id>`"; "its L row is reverted before its P4
write"). The D9 plan then stands on the same S0 read as the mass run and the scope; the mass run's 19
re-queued sites need this order anyway (their plan lines are S0's and lane L marked them); and lane
L's gate stays consistent - a re-plan that leaves a P4-written site out is accepted only on the
proof that the site's L row is reverted (`sites_taken_back`), where a P4 write over a live L row
would leave L's gate refusing its written batch. A site P4 holds keeps its L row, so no March text
is left unmarked.

* **The proof, one transaction ending in ROLLBACK** (`logs/p4_d9/L_ORDER_PROOF.sql` `1afab084...`,
  `.out` `c72cd147...`): for the 6 lane-W sites, whether each holds the P4 plan's old values - its
  `input.json` description as text, raw_data as jsonb - before, after revert4's own reversal of its
  L row, and after the ROLLBACK:

  | read | description at the plan's old value | raw_data at the plan's old value | provenance |
  |---|---|---|---|
  | before the reversal | 6 of 6 | **0 of 6** | L |
  | after the 6 reversals (`NOTICE: revert: 1 row(s) reverted`, six times) | 6 of 6 | **6 of 6** | none |
  | after ROLLBACK | 6 of 6 | 0 of 6 | L |

  Afterwards 0 journal rows under the six stamps plus `-rollback`.
* **Rendered and rehearsed per site** (`logs/p4_d9/revert-L-<id>.sql`, `.rehearse.log`): each
  `BEGIN`, `DO`, `ROLLBACK`, then `journalled writes matched|1`, `reversals kept|0`, `WRITE_EXIT=0`.
  The two `search-stopped` sites need none.

  | site | id | L stamp |
  |---|---|---|
  | Laüs | `1c899f53-4414-4954-821d-9119802aa39a` | `phase4l:p4l-1038:chunk-0001` |
  | Porth Hellick Down | `1f66729b-c7e8-476a-b9cc-84b23a36074f` | `phase4l:p4l-1042:chunk-0001` |
  | Acci | `89f1d2b7-2579-4c33-82b3-8b58d7857c53` | `phase4l:p4l-1177:chunk-0001` |
  | Ağbulaq Necropolis | `a9c5d1bf-b6d0-4486-a507-8dddfdc57a02` | `phase4l:p4l-1218:chunk-0001` |
  | Temple of Zeus (Kyrene) | `bf538bd9-912c-471a-964a-f94842e17491` | `phase4l:p4l-1247:chunk-0001` |
  | Absalom's Tomb | `fb9e7ccb-2ffd-4bb8-a78d-1e2993881090` | `phase4l:p4l-1328:chunk-0001` |
  | (held) Afrodit Tapınağı | `c0e10d6e-fb0e-4e9c-a910-631da9e578ea` | `phase4l:p4l-1250:chunk-0001` |
  | (held) A Figa | `fe4edbed-be84-4b80-b5de-62ab3e4c88ef` | `phase4l:p4l-1331:chunk-0001` |

* **Lane L's acceptance afterwards** (tested: `test_an_l_row_taken_back_before_a_p4_write_is_superseded_and_never_complete`):
  between the reversal and the P4 write a taken-back row is not yet written, at its old value; after
  the P4 write it is superseded under `--allow-stamp 'phase4:%'` and MOVED without it; `--complete`
  names it `NOT WRITTEN`, as it names a P4 site taken back (contracts section 10). So L's acceptance
  after D9 runs without `--complete` and reads `not yet written 0`.

### The orchestrator's commands (worktree `.claude/worktrees/p4-pilot`, as `C:/tmp/p4m_group.sh`)

    cd /c/PythonProjects/AncientMap/.claude/worktrees/p4-pilot; export PYTHONIOENCODING=utf-8
    PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe; M=output/remediation; R4=$M/phase4_runner
    P4=scripts/remediation/phase4; OH=scripts/remediation/opus_handoff.py; H=$M/handoff/p4-d9
    RUN=$R4/runs/d9-2026-09-25; MAIN=C:/PythonProjects/AncientMap; L=$M/logs/p4_d9
    ROUND="--plan $R4/PLAN4.d9.jsonl --run-dir $RUN --log-dir $L --only p4-0901 --searches-off --live"
    GATE="$M/tools/write_gate4.py --run d9-2026-09-25 --batch p4-0901"
    RUNS="--run $R4/runs/pilot4-2026-09-24 --run $R4/runs/mass-2026-09-25 --run $RUN"
    P3="--phase3-run $MAIN/$M/phase3_runner/runs/mass --phase3-refused $MAIN/$M/logs/_write_dry/ALL_REFUSED.jsonl"

1. **Select.** One Opus agent (`opus-p4d9-select-p4-0901`) answers the 6 prompts
   `$H-select/p4-0901/finder/*.prompt.txt`, each with `$PY $OH answer --dir $H-select --batch-id
   p4-0901 --stage finder --label <label> --answered-by opus-p4d9-select-p4-0901 --text-file <file>`.
   `$PY $OH validate --dir $H-select` -> answered 6, missing 0, stale 0, malformed 0. Then
   `$PY $P4/mass4.py $ROUND --stages select --handoff-import $H-select` -> `STAGE_EXIT=0`.
2. **Translate, assemble, verify.** `$PY $P4/mass4.py $ROUND --stages translate --handoff-export
   $H-translate` (lane T is closed: no question, no directory - if `$H-translate` appears, stop and
   answer it first), then `$PY $P4/mass4.py $ROUND --stages translate,assemble,verify
   --handoff-import $H-translate`.
3. **Review.** `$PY $P4/mass4.py $ROUND --stages review --handoff-export $H-review`; one agent
   (`opus-p4d9-review-p4-0901`) answers `$H-review/p4-0901`; `$PY $OH validate --dir $H-review`
   clean; `$PY $P4/mass4.py $ROUND --stages review --handoff-import $H-review` (p4-0901 done: "k
   assembled, m held"); `$PY $P4/run4.py holds --run-dir $RUN`.
4. **P4 dry.** `$PY $GATE --group P4 --open-lanes W,S` -> `defect scope: SCOPE4.v2.json v2
   7256a1962ffe1b24, 1631 sites ...: 8 of the run's 8 sites`, rows planned 2k, `WRITE_EXIT=0`. The
   k sites it writes: `$PY -c "import json; print(sorted({json.loads(l)['site_id'] for l in
   open('$M/logs/_write_apply_p4/p4-0901/PLAN.jsonl', encoding='utf-8')}))"`. With k = 0 stop here:
   nothing is reverted or written, and HUMAN_ONLY D9 keeps the held sites with their reasons.
5. **The preflight's refusal (read-only proof).** `$PY $GATE --group P4 --open-lanes W,S --rehearse`
   -> `STOP at p4-0901: <id>/raw_data: the row no longer holds the planned old value` for each of
   the k sites, `WRITE_EXIT=1`; nothing is sent after the preflight and a rehearsal leaves no
   `STOPPED.json`.
6. **Lane L's rows of the k sites, and only those** (stamps in the table above): `$PY
   $P4/revert4.py --stamp-like '<L stamp>' --site <id> --out $L/revert-L-<id>.sql`, then
   `--rehearse` (`journalled writes matched|1`, `reversals kept|0`, `WRITE_EXIT=0`), then `--apply`
   (`reversals kept|1`, `WRITE_EXIT=0`). A non-zero or missing exit line: read the journal for
   `<L stamp>-rollback` before anything else, never apply twice. Then, read-only: `$PY
   $M/tools/verify_writes4.py --lane p4l --plan $M/logs/_write_apply_p4l/LANE_PLAN.jsonl
   --allow-stamp '2026-09-25_mechanical-orphan-citations' > $L/accept-p4l-after-L-revert.log` ->
   carried 3,936 - k, not yet written k, superseded 67, 0 deviations.
7. **P4 rehearse, apply, accept.** `$PY $GATE --group P4 --open-lanes W,S --rehearse` -> `every open
   batch rehearsed`, `WRITE_EXIT=0`; `$PY $GATE --group P4 --open-lanes W,S --apply --step 100` ->
   `STEP COMPLETE: k site(s) written in 1 batch(es)`, `WRITE_EXIT=0`; `$PY
   $M/tools/verify_writes4.py --lane p4 --plan $M/logs/_write_apply_p4/LANE_PLAN.jsonl $RUNS
   --allow-stamp 'phase4l:%' > $L/accept-p4-step-15.log` -> planned and journal 1,972 + 2k, carried
   1,968 + 2k, not yet written 2, superseded 2, 984 + k re-verified, 0 deviations, `ACCEPT_EXIT=0`;
   only then `$PY $GATE --group P4 --open-lanes W,S --accept $L/accept-p4-step-15.log` -> `ACCEPTED
   step 15`.
8. **Lane L after the write** (read-only): `$PY $M/tools/verify_writes4.py --lane p4l --plan
   $M/logs/_write_apply_p4l/LANE_PLAN.jsonl --allow-stamp '2026-09-25_mechanical-orphan-citations'
   --allow-stamp 'phase4:%' > $L/accept-p4l-after-d9.log` -> 4,003 / 4,003, carried 3,936 - k, not
   yet written 0, superseded 67 + k, 0 deviations (`--complete` names the k rows `NOT WRITTEN`, by
   design).
9. **P5 dry and rehearsal.** `$PY $GATE --group P5 $P3` -> `live phase-4 provenance: k of 8 planned
   sites (read-only)`, the written sites' cards planned (a card-held site has none); `$PY $GATE
   --group P5 $P3 --rehearse`.
10. **The card file, pre-rendered in the MAIN checkout** (the database first, then the file): `$PY
    $P4/card_json.py --prerender --file $MAIN/public/data/card_descriptions.json --plan4
    $R4/PLAN4.jsonl --p5-root $M/logs/_write_apply_p5` -> `pre-rendered ... cards`, `WRITE_EXIT=0`;
    commit it in the main checkout, not pushed.
11. **P5 apply and accept.** `$PY $GATE --group P5 $P3 --apply --step 100` -> `STEP COMPLETE`; `$PY
    $M/tools/verify_writes4.py --lane p5 --plan $M/logs/_write_apply_p5/LANE_PLAN.jsonl $RUNS >
    $L/accept-p5-step-14.log` -> 0 deviations; `$PY $GATE --group P5 $P3 --accept
    $L/accept-p5-step-14.log` -> `ACCEPTED step 14`.
12. **Regenerate.** `$PY $P4/card_json.py --regenerate --file $MAIN/public/data/card_descriptions.json`
    -> `REGENERATE: byte-identical with the pre-render`, `WRITE_EXIT=0` (a difference is written
    beside it as `.regenerated`: stop).
13. **Push.** In the main checkout: `wip/p4-pilot` merged into `integrate/wave1` (fast-forward), the
    card-file commit on top, the pre-push gates, `git push origin integrate/wave1:main`. After the
    deploy: the `commit` of `http://localhost:8000/` on the VPS; `verify_writes4.py --boot-logs
    --since <StartedAt>` (0 overwrite lines); `$PY $P4/card_json.py --check --file
    $MAIN/public/data/card_descriptions.json` (`ACCEPT_EXIT=0`); `verify_writes4.py --lane p5 ...
    $RUNS --complete` (0 deviations); the static export (Phase-6 runbook step 3), the Qdrant resync
    and IndexNow for the k new descriptions; and D1 again, `$PY
    scripts/remediation/mechanical/citations.py --export --write --out $M/logs/orphan_citations/after-d9`
    from the main checkout -> `"d1_fails": 9 - k`.

### Open

* **What stays a D1 failure**: Killa Mach'ay (`abstained`, the mass run's), Afrodit Tapınağı and A
  Figa (`search-stopped`, no Wikipedia article to anchor), and any lane-W site the selector or the
  reviewer holds. With 3 such sites in the next draw's pool of 4,194, a sample of 60 hits one with
  probability 4.2 % (9: 12.2 %). What remains goes back to HUMAN_ONLY D9 for options (a) or (b),
  with the reason each was held.
* **The mass run's 19 `revision-too-fresh` sites** carry lane-L rows too (all 19 are in L's lane
  plan) and their re-queued plan lines are S0's: the same order - their L rows taken back after
  their review and before their P4 write - applies when `mass4` re-queues them (p4-0116 on).
* **card_stats**: the k new descriptions move `md5(description)`; they are the next card_stats
  wave's work (HANDOVER 2.4).
* **The fresh acceptance draw** comes after these writes (a P4 write on a drawn site voids it, V3).
* The lane-L acceptance's `--complete` counts a taken-back row a later allowed lane wrote as `NOT
  WRITTEN`; reading `not yet written 0` without `--complete` is the check (recorded, not changed).

### Tests, sweep, gates (worktree `.claude/worktrees/p4-pilot`, main venv; commit `5b8edc6`)

* 17 new test functions: `test_phase4_scope.py` 13 (version 2 and version 1 as committed, each
  version at its own pin, the listing, D1's reading, the list plan, its block, its refusals and its
  command), `test_phase4_write.py` 3 (the outcome-file refusal, 3 items; the gate's exit line; a
  third run beside two in one apply root), `test_phase4_accept.py` 1 (lane L's row taken back
  before a P4 write). Rewritten, strictly as strong: the version-1 scope tests name `version=1`, the
  malformed-scope case "version" asks version 3 (version 2 is now known) and gains two cases (a
  version-1 site naming the new list, a version-1 count of it), the audit-log test asks both pins,
  the gate's scope line reads `v2`, and the mass run's plan test pins version 1 and a version 2
  that adds a site the plan must not take. Red first: the scope module's tests (a collection error,
  no `D1_MARKER_WITHOUT_ENTRY`), the gate's `v2` line, and the 4 outcome-file items (a
  `FileNotFoundError` where a `PlanInputError` was asked). The third-run gate test and the lane-L
  acceptance test pass on code that already did it; they pin the D9 path.
* Full gate suite (`-q -rs --timeout 90 -m "not integration and not live_llm"`): **6,985 passed,
  111 skipped, 57 deselected, 0 failed** (184.6 s; `logs/p4_d9/gates_pytest.log`); the 111 skips
  are the gitignored data this worktree lacks, as before.
* Sweep: 28 new cases (`P4_D9_MUTATIONS`), 3 cases re-anchored (`found != pin`, the version-2 pin
  line, the version check of `parse_scope`), 2,446 labels, all unique, every anchor and test present
  (`test_phase3_sweep.py` green). `logs/p4_d9/sweep_d9.py` - the sweep's own `main` over every case
  whose target the change touched (write4 107, plan4 52, scope4 33, AUDIT_LOG 6, mutation_sweep 3):
  **201/201 caught**, the tree byte-identical for its 5 files (and the contracts, checked by
  digest), `git status` unchanged, no `# mutant` line left (`logs/p4_d9/sweep_d9.log` `850f6e82...`).
* `ruff check` and `ruff format --check` clean on the 7 touched Python files (ruff 0.15.11); `ruff
  check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean; the Lyra import check passes; gitleaks over the
  staged commit: no leaks.
* `mass4` hashes `phase4/*.py` before every batch: the D9 export ran under `6037a01ce927eb2d`, the
  code of this commit less `write4`'s refusal, added afterwards; the next round prints the new
  digest. No `mass4` invocation was in flight.

## 2026-09-25 - HUMAN_ONLY D9 option (b): the dangling-markers lane for the 3 held sites (planned, checked and rehearsed on production; not applied), and card_stats after the D9 run: 0 cells

Main checkout, branch `integrate/wave1`, main venv. Nothing was written to production: every read
was a SELECT, and every write ran inside a transaction that ended in ROLLBACK. No model was called.

### The class, read with the orphan-citations lane's own read (19:32 CEST, journal max id 73875)

`citations.py --export --write --out output/remediation/logs/dangling_markers/orphan-read-before`
(gitignored) plans nothing and lists **3** sites, all `marker-without-entry`. The other 6 of D9's 9
have a sourced Phase-4 description from the D9 run: descriptions and provenance in journal rows
73840-73851 (`phase4:p4-0901:chunk-0001`), cards in 73870-73875 (`phase5:p5-0901:chunk-0001`).

| site | id | held by Phase 4 | the text cites | entries |
|---|---|---|---|---|
| Killa Mach'ay | `867f08af-8934-4ec0-bbcc-2c730bb2a93a` | `abstained` (mass run, p4-0042) | [1][3][4] | 1, 2, 3 (2 cited by nothing) |
| Afrodit Tapınağı | `c0e10d6e-fb0e-4e9c-a910-631da9e578ea` | `search-stopped` (D9 run) | [1] x2, [2] x3 | 1 |
| A Figa | `fe4edbed-be84-4b80-b5de-62ab3e4c88ef` | `search-stopped` (D9 run) | [1], [2], [3] x3, [4] | 1 |

Each carries lane L's `_description_provenance` (journal 65985, 67818, 69795, `P4/legacy-provenance`),
whose `desc_sha256` is the sha256 of its description, and no description journal row.

### The decision

The owner's order of 2026-09-25 takes D9's recommended option for a held site, option (b): **remove
the marker from the text**. A marker that points to no source is a false attribution. The SSR page
shows it as a bare `<sup>[N]</sup>`. The claims stay as they are: the site keeps lane L's
provenance, which marks the text as generated by the March LLM chain. No source is invented, and no
marker is renumbered to an entry. HUMAN_ONLY guessed that Killa Mach'ay's entry 2 is "probably" the
source of its [4], but the data does not say so.

**One deviation from "keep description_citations as they are", Killa Mach'ay only.** Its entry 2
("situated at a height of 3,400 metres") is cited by no marker, before and after the removal. D1
requires every entry to be cited, so "D1 holds on every curated site" and "the array unchanged" are
incompatible for this site. The lane applies the orphan-citations lane's own rule (`repaired`,
imported): an entry no marker cites goes. That lane withheld the entry only as the evidence for
option (a), which is not taken. Entries 1 and 3 carry the same URL
(`https://en.wikipedia.org/wiki/Killa_Mach%27ay`), so the popup keeps the same source link, and the
removed entry survives in the journal's `old_value`. On Afrodit Tapınağı and A Figa the array stays
byte for byte.

### The removal rule and the exact removals

**The rule** (`dangling_markers.without_dangling`): a marker is dangling when its number has no
entry, and every occurrence of it goes. Each maximal run of adjacent markers, with the horizontal
whitespace directly before it, loses exactly its dangling markers. The whitespace goes only when no
marker of the run is left. This is the frontend's own marker shape (`seo/text.ts` `stripCitations`,
`[^\S\n]*\[\d+\]`), taken as a run so that `... [4][1]` keeps its space. `removal_faults` proves on
each planned text that nothing else moved:

* the kept markers are the old ones, in order;
* with all whitespace out, the new text is the old one less exactly those tokens;
* no leading or trailing whitespace, double space, space before punctuation or empty bracket is
  added.

| site | removed | the text around it, before -> after |
|---|---|---|
| Killa Mach'ay | `[4]` x1 (no whitespace: the run keeps [1][3]) | `...in Huancavelica Region [1][3][4].` -> `...Region [1][3].` |
| Afrodit Tapınağı | ` [2]` x3 | `...Aphrodite worship [2]. The city` -> `...worship. The city`; `...the Roman Empire [2]. Major` -> `...Empire. Major`; `...around 500 AD [2].` -> `...500 AD.` |
| A Figa | ` [2]` x1, ` [3]` x3, ` [4]` x1 | `...4300-4200 BCE [2]. Excavations` -> `...BCE. Excavations`; `...resource exploitation [3].`, `...marine environment [3].`, `...occupation layers [3].` -> the same without ` [3]`; `...led by Franck Leandri [4].` -> `...Leandri.` |

The full old and new texts are in `mechanical_dangling_markers/PLAN.md`.

**`raw_data`**: `_description_provenance.desc_sha256` moves to the sha256 of the new text, and every
other key keeps its value and its place:

* Killa Mach'ay: `7cebb94d...` -> `e3af2533...`, and entry 2 removed;
* Afrodit Tapınağı: `0ce01601...` -> `889e8494...`;
* A Figa: `814e2947...` -> `c63321ec...`.

### The lane (`scripts/remediation/mechanical/dangling_markers.py`, `lane.DANGLING_MARKERS`)

* **Cell lane `dangling-markers`**, two cells per site in one transaction:
  * `unified_sites.description` as `text`, `raw_data` as `jsonb`;
  * run stamp `2026-09-25_mechanical-dangling-markers`, test id `T08/dangling-markers`;
  * the later lanes' server bounds;
  * output `output/remediation/mechanical_dangling_markers/`.
* **Guard 3** compares each cell with its full planned old value: the description as text, which
  is strictly stronger than its sha256, and `raw_data` as jsonb.
* **Guard 5, the premise**, is
  `coalesce((u.raw_data -> '_description_provenance') - 'desc_sha256', 'null'::jsonb)::text`: lane
  L's provenance less the hash the lane moves.
  * It refuses a site whose text is no longer lane L's, for example one with a live Phase-4
    provenance.
  * It holds for the write and for its reversal alike, because the reversal restores only the hash.
* **Residual**: D1 in SQL, the orphan lane's `_D1_FAILS`. The read-back adds:
  * each half of D1, and D4 in SQL (`PROVENANCE_HASH_DIFFERS`, now shared with the orphan-citations
    read-back, whose text stays byte-identical: sha256 `c1892dbe...`);
  * this run's description rows that differ in more than markers and whitespace, or gained a marker;
  * this run's raw_data rows that changed more than the citations and the hash, gained an entry,
    carry a hash that is not the description the same run wrote, or a lane other than L.
  * Each raw_data cast sits behind `CASE WHEN l.column_name = 'raw_data'`: the run's description
    rows are not JSON, and a WHERE does not fix the order its casts run in.
* **The planner refuses and lists**, first rule first:
  * `citations-not-readable`;
  * `no-dangling-marker` (the orphan-citations class);
  * `grouped-markers`;
  * `no-legacy-provenance`, `phase4-provenance`, `provenance-not-readable`,
    `provenance-hash-differs`;
  * a description or raw_data journal that does not end at the live value;
  * `raw-data-not-reprinted`;
  * `removal-not-clean`.
  * An export whose Postgres premise is not the provenance its raw_data carries is a `PlanError`.
  * `build` reads every planned site with the acceptance's own `d1` and `d4`, and refuses the plan
    unless both hold.
* **Tests**: `tests/remediation/test_mechanical_dangling_markers.py`, 47 module-level test functions.
  They were red before the module (a collection error); the one that reads the committed plan was
  red until the plan was written. The registry tests of `test_mechanical.py` take the lane from its
  committed plan.
* **Sweep**: `mutation_sweep.py dangling-markers`, **37 cases, 37 fired**. The orphan-citations
  cases, whose `lane.py` text the refactor moved into `marker_matches` and the shared predicates,
  **fire 20 of 20** again. The swept files come back byte-identical, `git status` is unchanged, and
  no mutant is left.

**The plan** (export 17:44:59 UTC, sha256 `5568ad6d...`, gitignored):

* 5,004 curated rows: D1 holds on 5,001 and fails on 3;
* **3 sites, 6 cells, 0 listed**;
* rules: `dangling-markers-removed` 3, `provenance-hash` 2, `provenance-hash-and-uncited-entries` 1.

| file (`mechanical_dangling_markers/`) | sha256 (LF text) |
|---|---|
| `PLAN.jsonl` | `943298246e9dcbd5b46cd5d7409f74022dde1ba72e2e37fd568d81670bffe87b` |
| `APPLY.sql` | `11a45635526a67572e775739260ef139041eb12351d919e699902f742c01be7f` |
| `ROLLBACK.sql` | `22fbacbe708ee0539d6b14b200db6deca785a2270d74efc84d92f7056958ac07` |

### On production (read-only, and ROLLBACK only), 2026-09-25 17:45-17:52 UTC

Logs in `output/remediation/logs/dangling_markers/` (gitignored).

* `--check-primitive`: the 0022 body (t, t, t).
* **`--verify` before**:
  * curated sites 5,004;
  * **D1 fails 3**; uncited entry 1 (Killa Mach'ay); unanswered marker 3;
  * description not the one its provenance hashes 0;
  * every journal metric of the stamp, the test id and the rollback stamp 0.
* **`--probe-guards` exit 0**: 5 probes, each refused by its own guard, 0 journal rows left:
  * guard3-foreign-old-value;
  * guard2-no-op;
  * guard2-foreign-column;
  * guard1-other-source;
  * guard5-premise.
* **`--rehearse`**: `dangling marker removal: 6 of 6 planned cell(s) changed and journalled over 3
  curated site(s)`, then ROLLBACK. Afterwards the stamp has 0 journal rows, D1 fails on 3, and the
  temp table is gone.
* **The write and its reversal in one transaction**, a one-off beyond the framework, like the
  orphan-citations lane's (`write_and_undo.py`, `WRITE_AND_UNDO.sql`, `write-and-undo.txt`,
  `write-and-undo.result.json`, all gitignored). The script is:
  * the committed APPLY.sql up to its COMMIT, each file verified against its plan pin first;
  * the lane's read-back, then a dump of every curated row that the acceptance's own `d1` and `d4`
    (Python) judge;
  * ROLLBACK.sql's body, with the same reads;
  * ROLLBACK, and the read-back again.

  | read | D1 fails (SQL / `checks.d1`) | uncited / unanswered | D4 fails (SQL / `checks.d4`) | journal rows (stamp / rollback) | the lane's own metrics |
  |---|---|---|---|---|---|
  | after the write | **0 / 0** of 5,004 | 0 / 0 | **0 / 0** | 6 / 0 | all 0 |
  | after the reversal | 3 / 3 | 1 / 3 | 0 / 0 | 6 / 6 | all 0 |
  | after ROLLBACK | 3 | 1 / 3 | 0 | 0 / 0 | all 0 |

  Provenance lanes over the curated rows: L 3,997, W 963, S 27, none 17, the same after the write.
  **D1 and D4 hold on every curated site after the write.**
* **Lane L's acceptance now** (`accept-p4l-before.log`), with the three stamps allowed:
  * 4,003 planned, 4,003 lane journal rows;
  * carried 3,930, not yet written 0;
  * superseded 73 (orphan-citations 67, `phase4:%` 6);
  * **0 deviations**, `ACCEPT_EXIT=0`.

### card_stats after the D9 run: 0 cells, and none after this lane

The last wave, `card-stats-2026-09-23`, is applied (4,106 cells, journal 56284-60389, `0d7a544`).
Since then the D9 run moved 6 descriptions, and a description is a card input: `_is_unesco` reads
its text, and `has_description` reads whether it is empty.

* **Re-plan** `card_stats.py --wave 2026-09-25 --export`, then `--write`:
  * export sha256 `7d1abf28...`, journal max id 73875;
  * the basis is wave 2026-09-23's export (horizon 51782);
  * the counterfactual put back **6** journalled input values (the D9 descriptions) and reproduced
    **all 60,048** stored cells, 0 differ;
  * the recompute plans **`"cells": 0`**, skipped 0, no statement.
  * The D9 texts move no card: none adds or drops a UNESCO or "world heritage" mention.
* **Nothing to emit, rehearse or apply.** A 0-cell wave writes no statement.
  `apply.py --lane card-stats-2026-09-25 --emit` refuses the empty plan
  (`PLAN.jsonl holds no records`, exit 1).
* **Not committed.** Like the completion read-back `2026-09-23b`, a 0-cell run is a read-back, not
  a wave. Its files are in `logs/dangling_markers/card-stats-2026-09-25/` (`BASIS.json` `2a7ee11f...`).
  The next wave's proof reads the last applied wave's `BASIS.json` (2026-09-23), because no
  card_stats row names this label.
* **This lane moves no card either** (`card_stats_after_lane.py`, read-only): the card_stats model
  on today's export, with the plan's three new descriptions substituted, recomputes all 5,004 cards
  to exactly the stored values (0 cards move, 0 cells differ). The lane removes only `[N]` tokens and
  the whitespace before them.
* `apply.py --lane card-stats-2026-09-25 --verify`:
  * tiers 504 / 1,739 / 2,383 / 357 / 21;
  * civilization drift 0; total_power not the sum 0;
  * curated sites without a card row 0;
  * journal rows for the stamp 0.

### The apply (the orchestrator runs it)

Repository root, main venv, `export PYTHONIOENCODING=utf-8`, `PY=./.venv/Scripts/python.exe`,
`A=scripts/remediation/mechanical/apply.py`, `W=.claude/worktrees/p4-pilot/output/remediation`,
`LOG=output/remediation/logs/dangling_markers`.

0. **The plan still stands.** `$PY $A --lane dangling-markers --verify` -> D1 fails 3, journal rows
   for this run stamp 0. Guards 3 and 5 refuse any write that touched a planned site's description or
   raw_data. If anything moved, re-plan:
   * `$PY scripts/remediation/mechanical/dangling_markers.py --export --write`;
   * `$PY $A --lane dangling-markers --emit`;
   * `$PY -m pytest tests/remediation/test_mechanical_dangling_markers.py tests/remediation/test_mechanical.py -q -m "not integration and not live_llm"`
     green;
   * gitleaks over the staged lane directory, and commit it before going on.
1. **Check.** `$PY $A --check-primitive`, then `$PY $A --lane dangling-markers --probe-guards` ->
   exit 0, the same 5 probes, each refused by its own guard.
2. **Rehearse.** `$PY $A --lane dangling-markers --rehearse` -> `6 of 6 planned cell(s) changed and
   journalled over 3 curated site(s)`, ROLLBACK, 0 journal rows.
3. **Apply.** `$PY $A --lane dangling-markers --apply` -> `APPLY OK: the read-back matches the plan,
   row for row` (exit 0). Exit 3 is NOT COMMITTED and exit 5 OUTCOME UNKNOWN: read the journal for
   the stamp before anything else, and never apply twice.
4. **Read back.** `$PY $A --lane dangling-markers --verify` -> the expected values:
   * journal rows for this run stamp 6 and for this test id 6;
   * **D1 fails 0**; uncited entry 0; unanswered marker 0;
   * **description not the one its provenance hashes 0**;
   * 0 for every lane-specific metric and for outside the two cells, non-curated rows and another
     site's `site_id_ref`.
5. **Rehearse the rollback on the landed rows.** `$PY $A --lane dangling-markers --rehearse-rollback`
   -> `6 of 6`, ROLLBACK, the cells still holding the written values. Commit
   `REHEARSAL_ROLLBACK.sql`, as for the other lanes.
6. **Acceptance.**
   * (a) D1 by the acceptance's own function over every curated row:
     `$PY scripts/remediation/mechanical/dangling_markers.py --export --write --out $LOG/after`
     -> `"d1_holds": 5004, "d1_fails": 0, "cells": 0` (no statement; the delivered plan stays
     untouched). The orphan-citations read `citations.py --export --write --out $LOG/orphan-after`
     then has nothing to list: it ends in `REFUSED: refusing to render a transaction with no rows`,
     exit 1, after writing an empty `PLAN.jsonl` and `SKIPPED.jsonl`, and that is its "none" today.
     D4 over every curated row is step 4's `description not the one its provenance hashes 0`.
   * (b) Lane L, whose 3 raw_data rows this lane supersedes:
     `$PY output/remediation/tools/verify_writes4.py --lane p4l --plan $W/logs/_write_apply_p4l/LANE_PLAN.jsonl --allow-stamp '2026-09-25_mechanical-orphan-citations' --allow-stamp 'phase4:%' --allow-stamp '2026-09-25_mechanical-dangling-markers' > $LOG/accept-p4l-after.log`
     -> 4,003 planned, 4,003 journal, **carried 3,927**, not yet written 0, **superseded 76**
     (orphan-citations 67, `phase4:%` 6, dangling-markers 3), **0 deviations**. Without the new
     stamp the 3 rows are CHANGED LATER.
   * (c) Phase 4 and Phase 5 are unchanged, because the lane touches no P4-written site and no card:
     * `$PY output/remediation/tools/verify_writes4.py --lane p4 --plan $W/logs/_write_apply_p4/LANE_PLAN.jsonl --run $W/phase4_runner/runs/pilot4-2026-09-24 --run $W/phase4_runner/runs/mass-2026-09-25 --run $W/phase4_runner/runs/d9-2026-09-25 --allow-stamp 'phase4l:%'`
     * `$PY output/remediation/tools/verify_writes4.py --lane p5 --plan $W/logs/_write_apply_p5/LANE_PLAN.jsonl --run $W/phase4_runner/runs/pilot4-2026-09-24 --run $W/phase4_runner/runs/mass-2026-09-25 --run $W/phase4_runner/runs/d9-2026-09-25`
     * each -> 0 deviations.
   * (d) card_stats completion read-back:
     `$PY scripts/remediation/mechanical/card_stats.py --wave 2026-09-25 --export --write --out $LOG/card-stats-after`
     -> `"cells": 0`, `counterfactual_cells_differing 0`, with 9 journalled input values put back
     (the 6 D9 descriptions and these 3). It writes no statement and is not committed. Cells there
     would mean another input moved: plan that wave in its own directory and run the runbook's
     section C.
7. **Carry the texts out** with the Phase-6 runbook steps 3, 5 and 6: the static export on the VPS,
   the Qdrant resync (the `sites` collection re-embeds changed descriptions) and IndexNow. The SSR
   page and the API read the database directly.
8. **Then the fresh acceptance draw** (`redraw.py`, entry "Acceptance draw-2026-09-25 ends FAIL on
   A3 (D1)"). With D1 at 0 on every curated row, the 12.2 % (9 sites) and 4.2 % (3 sites) risks of
   that entry are gone. This lane must land **before** the draw: a write on a drawn site after the
   draw voids the run.

### Tests, sweeps, gates (main checkout, branch `integrate/wave1`, main venv)

* Full gate suite (`-q -rs --timeout 300 -m "not integration and not live_llm"`,
  `-p no:cacheprovider`): **7,164 passed, 4 skipped, 57 deselected, 0 failed** (229 s;
  `logs/dangling_markers/gates_pytest.log`). The skips are the known four: two refactored-away
  article tests, the opt-in Shining Ones regen, and the scope test whose S0 export lives in the
  worktree.
* New tests: `test_mechanical_dangling_markers.py`, 47 module-level functions, red before the module
  (a collection error).
* Sweeps: `mutation_sweep.py dangling-markers` **37/37 fired** and `orphan-citations` **20/20 fired**
  (`logs/dangling_markers/sweep.log`, `sweep-orphan.log`). None skipped, survived, invalid, unproven
  or errored. The swept files came back byte-identical (sha256 checked before and after), `git
  status` was unchanged, and no mutant is left. `test_mechanical_sweep.py` is green (every needle
  matches once).
* Linters: `ruff check` and `ruff format --check` clean on the 4 touched Python files (ruff
  0.15.11). `ruff check api/ pipeline/` clean. `lint-imports` 2 kept, 0 broken.
  `vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80` clean.
* gitleaks over each staged commit and over the branch's new commits: no leaks.
* The Phase-4/5 acceptances, read-only, before the apply, from the main checkout with the worktree's
  plans and the three runs:
  * `--lane p4 ... --allow-stamp 'phase4l:%'`: 1,984 planned and journalled, carried 1,980, not
    yet written 2, superseded 2, 990 re-verified with V1-V15, **0 deviations**;
  * `--lane p5`: 1,113 carried, 762 re-verified, **0 deviations**.
* Not applicable: nothing under `ancient-nerds-map/`, `api/` or `pipeline/` was touched, so there is
  no frontend gate and no Lyra-image import check.

## 2026-09-25 - the fresh acceptance draw (PROTOCOL.md section 10), sealed before it runs

After the last writes of the session (the D9 run, orphan-citations, dangling-markers; D1 and D4 hold
on all 5,004 curated sites; static export, Qdrant and IndexNow done), the orchestrator seals the
re-draw before running it: `PROTOCOL.md` `f40fac87230a26e7b1a4818e9d50d16dedfcb6936fc795b532e2cb35789f8bff`
(unchanged), `draw.py` `0a12beb461eb6aca6c921a4677b08472b4c8ff5068afd06af88a1baaf452515e`
(unchanged), `redraw.py` `fd12f2091066841ea46be120b81b0cc93ff98d05290326dc176d41c94d733fc9` (as
recorded with its commit 1f08d20). Seed 20260926, canaries 20260927, excluding draw-2026-09-25's
60 and the Phase-4 audit samples (mid-run 45, 500-site 10, pilots 3 and 4), into
`draw-2026-09-25b/`.

## 2026-09-26 - draw-2026-09-25b ends as a measurement; the owner's finishing mandate

Stage 1 of `draw-2026-09-25b` ran to the end: 652 questions in 54 batches, one fresh Opus agent per
batch (six at a time), every answer recorded write-once through the handoff; `opus_handoff.py
validate`: 652 answered, 0 missing, 0 stale, 0 malformed. `judge.py import-stage1` fetched 577 cited
URLs and counted 494 verdicts (370 CORRECT, 37 UNVERIFIABLE, 87 WRONG); 158 were not counted in this
round (fetch failed 114 - Historic England, Heritage Gateway and other registers refuse plain
requests -, quote not found 41, unreadable 3). All 10 canaries were caught at stage 1.

Per field, from the recorded answers (canary questions set aside): card_description 32 CORRECT /
19 WRONG (all severe) / 4 UNVERIFIABLE; description 40 / 15 (15) / 5; period_name 30 / 22 / 8;
period_start 32 / 16 (2 severe) / 12; served_image 35 / 11 (2) / 1; site_type 50 / 8 / 2;
coordinates 52 / 7 (5) / 1; source_url 55 / 4 / 1; scope 58 / 2 (2) / 0; name 56 / 1 (cosmetic) /
3; country 60 / 0 / 0. 46 of the 60 sites carry at least one WRONG verdict, 30 a severe one. By
origin: old March cards 18 of 43 WRONG against 1 of 12 Phase-5 cards; old March descriptions 9 of 29
against 1 of 10 Phase-4 descriptions (tally before the last description batches).

**Root cause.** Phases 4/5 wrote only the owner's defect scope (2026-09-23), which rested on the
Phase-3 finder; the finder missed most defects of the March enrichment, and the structured fields
(period, type, image, point) outside Phase 3's findings were never re-derived from sources.

**The owner's decisions of 2026-09-26** (asked once, then autonomous; verbatim in
`FINISH_PLAN_2026-09-26.md` section 1): no acceptance any more - the repairs are finished and the
error rates reported (O1), so the run stops here without re-asks or stage 2, and its write freeze
on the 60 drawn sites (V3) is lifted; all cards rewritten as fact-checked teasers of 160-190
characters (O2-O4); the March descriptions Phase 4 cannot replace are checked and trimmed sentence by
sentence (O5); refuted or unverifiable single fields replaced with a sourced value or emptied (O6);
Oceania's time limit is 1500 AD like the Americas' (O7); every step ships autonomously (O8); the
HUMAN_ONLY items are decided by their recommendations (O9); AI disclosure as before (O10); up to 16
agents in parallel (O11). The plan and its progress log: `FINISH_PLAN_2026-09-26.md`.

Files: `CANARIES.jsonl`, `judging/QUESTIONS.jsonl`, `judging/ROUNDS.jsonl`, `judging/STAGE1.jsonl`,
`judging/REASK_S1.json` (committed with this entry; the fetched pages stay local).

## 2026-09-26 - Lane WA: scope version 3 (the March texts), descriptions only - built and measured, nothing written

Owner decisions of 2026-09-26 (`FINISH_PLAN_2026-09-26.md`, O1-O11) over the design
`REPAIR_TEXTS_2026-09-26.md`: every curated site still carrying 2026-03 text joins the defect scope
and goes through the unchanged Phase-4 pipeline (selector `a0b422e7...`, reviewer `097c4589...`,
lanes W and S). Changed from the design: **no Phase 5** for these plans (lane WB rewrites every
card, O2/O3), **no group C** (lanes WC and WB take the held texts), **no acceptance exclusion** (O1).
Contract: `docs/procedures/PHASE4_CONTRACTS.md` section 12; runbook:
`docs/procedures/PHASE4_V3_RUNBOOK.md`. Branch `wip/wa` (worktree `.claude/worktrees/wa`).

**The March read** (read-only; `plan4.py read-march`, the one SELECT `plan4.MARCH_SQL`): 5,004
curated rows, `march-description` (live provenance lane `L`, not retired) **3,923**, `march-card` (a
non-empty card without a live forward `phase5:` row - a row without its own reversal, revert4's
reading) **3,822**, union **4,063** - the design's counts. `MARCH4_ROWS.jsonl` (committed) sha256
`5a2949fb826fabb920ac3b8976afe21fcc8d13cf3e98c7a5197c274b03a6774b`, read first 2026-09-26 ~00:12
UTC and again at 01:17 UTC: byte-identical. The journal's high-water mark is still 73911 (2026-09-25
18:05:06 UTC): no journalled write since the design's measurement.

**Scope version 3**: `phase4_runner/SCOPE4.v3.json`, **4,954 sites**, sha256
`fb775d0e5563d9d441c7b7a33bd6e96016a5ac2f9db9524c566f10aeb84ad0ef` (pinned as `scope4.SCOPE_SHA256`).
Rebuilt from the S0 export, `ALL_REFUSED.jsonl` (`7b4026d0...`), the D1 listing and the March read:
version 1 (`19a57e9f...`, its pin) and version 2 (`7256a196...`, its pin) byte for byte from the
same inputs, version 3 byte for byte **when the March read is named `MARCH4_ROWS.jsonl`** (the input's
file name is part of the scope's `inputs`; a check file of another name hashes differently).

**The plan, measured offline** from a fresh `plan4.py read` (5,004 rows, sha256 `55b2ece1...`,
byte-identical at 00:12 and 01:18 UTC), `S0_ITEM_NAMES.json` (the 76 shared QIDs of the fresh read
are exactly its 76), pilot 4 as `--pilot`, `--after PLAN4.scope.jsonl --after PLAN4.d9.jsonl`,
`--first-batch 2001`: **3,238 sites in 216 batches, p4-2001 .. p4-2216**, every batch `pass:
phase4-descriptions-only`, plan sha256 `4276f5d0...` (for that read; the run's plan is built from its
own fresh read). Of the 4,063 listed sites 721 are carried by the mass and D9 plans and 104 are
pilot 4's (825, the design's "already asked"); 8 planned sites carry a March card beside an unmarked
description (D7). Flags: t03 535 (99 severe), shared-title 125, shared-qid 106, scope-pending 20,
duplicate-pair 6.

**The mass run's 19 `revision-too-fresh` sites** (latest batch holds, `mass4.deferred_sites`): due
2026-09-26T21:30:14Z .. 21:40:06Z (48 h after the answers that held them); the run never re-queued
one (no `REQUEUE4.jsonl`). They were held, not written, so they are not "new": the v3 plan leaves
them to `PLAN4.scope.jsonl` (carried), and a follow-up plan of the same lists takes them over after
21:40:06Z (`build --take-deferred runs/mass-2026-09-25 --after ... --after PLAN4.v3.jsonl
--first-batch 2501`): simulated at 21:41Z, **19 sites in 2 batches, p4-2501 .. p4-2502**, run
`runs/v3d-<date>`. `verify_writes4.index_runs` reads such a site from the run that assembled it.

**Expected questions** (the census run `runs/census-2026-09-24`, S0 ids, searches off; S3's own
`site_pool` over the census's pinned texts): the v3 plan's sites are census lane W 2,477, S 246, 0
515 (search-stopped 442, revision-too-fresh 49, scope-pending 24). Selector questions: W 2,477 + the
128 S sites whose article offers a naming sentence (118 get none, `no-source`) = **2,605**, up to
**2,654** with the 49 held too fresh on 09-24. Review questions at the mass run's measured ratio
(1,003 per 1,392 selector questions): **~1,877-1,912**. v3d: 10-18 selector, 7-13 review. Handoff
batches: 216 select + <= 216 review (every v3 batch has 9-15 census W/S sites) + 2 + 2 for v3d.

**`handoff4.py check-answer` on real answers** (read-only, `C:/tmp/wa2/check_real.py`): over the
mass run's 1,392 recorded selector answers, 1,388 pass and the 4 it names are exactly the mass run's
4 `selection-refused` holds (`span-not-offered`, p4-0031, p4-0034, p4-0059, p4-0113) - the check
would have caught them before recording. D9: 6 of 6 selector and 6 of 6 review answers pass. The
mass run's reviews can be checked only where the import left the batch as exported (650 pass); for
the others the import moved the batch (308 prompts no longer rebuilt, 45 sites held after the
review), which the check refuses by design - an agent checks before the import.

**Tests, sweep, gates** (worktree `.claude/worktrees/wa`, main venv, 2026-09-26 ~01:30-01:55 UTC):

* Full gate suite (`-q -rs --timeout 90 -m "not integration and not live_llm"`, `-p no:cacheprovider`):
  **7,152 passed, 119 skipped, 57 deselected, 0 failed** (461 s). The skips are gitignored working
  data this worktree does not hold (Natural Earth caches 76, the production snapshot 14, the
  phase-3 worklist 4, card_stats export 3, T10 data 3, bcases caches 3, design file 2, brand fonts
  and shorts 4, the S0 export and Phase 3's refusals 2, and others of the same kind) plus the known
  three (two refactored-away article tests, the opt-in Shining Ones regen). The lane's two skipped
  byte-rebuild tests (`test_the_committed_scope_is_rebuilt_byte_for_byte_from_its_inputs`,
  `test_the_committed_version_3_rebuilds_from_the_committed_march_read`) were run with the p4-pilot
  worktree's `S0_ROWS.jsonl` and `ALL_REFUSED.jsonl` copied in and then removed: 2 passed (versions
  1, 2 and 3 byte for byte).
* New and changed tests: `tests/remediation/test_phase4_v3.py` (44), `test_phase4_scope.py`,
  `test_phase4_accept.py` (the deferred site read from the run that wrote it; WB's
  `_card_provenance` on a descriptions-only site superseded under `wb-teaser-prov-%`),
  `test_phase4_write.py`.
* Sweep: `mutation_sweep.py "p4 v3" "p4 d9" "p4 scope4: the pin" "p4 write4: a held card" "p4
  verify_writes4: a site two runs"` 86/87 - the miss was `p4 d9 scope: the audit log loses scope
  version 2's digest`, because this entry first quoted the v2 pin in full a second time; the
  entry now abbreviates the earlier pins, and `mutation_sweep.py "the audit log loses"` is **7/7
  caught**. The tree came back byte-identical after both.
* `ruff check` and `ruff format --check` clean on the 12 touched Python files (ruff 0.15.11);
  `ruff check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/ pipeline/
  .vulture_whitelist.py --min-confidence 80` clean. Nothing under `api/`, `pipeline/` or
  `ancient-nerds-map/` was touched: no Lyra import check, no frontend gate.

### Lane WA: the independent review's findings and their fixes (2026-09-26, branch `wip/wa`)

An independent review of `wip/wa` (verdict "fix": 2 major, 4 minor) - each finding fixed, tests
first:

* **Major - the mass run's 19 rested on documentation alone.** HANDOVER still said `mass4`
  re-queues them itself from 21:30Z; a live round of `runs/mass-2026-09-25` after that would have
  re-queued them into the mass run's plan (p4-0116: S0's old values, an L revert first, and P5
  planning their extractive card against owner decision O2/O3), after which v3d's
  `--take-deferred` refuses, or - after v3d was built - both runs assemble them. Fixed in code:
  `mass4.descriptions_only_claims` - a plan without a pass (scope versions 1 and 2) re-queues no
  site a descriptions-only list names; `drive` refuses such a live round before `REQUEUE4.jsonl`
  is written, the dry run prints `hand over`. This covers both windows (before and after the v3d
  build) without a hand-over file. All 19 of the mass run's `revision-too-fresh` holds are
  `march-description` sites of the pinned `SCOPE4.v3.json` (15 also `march-card`; read offline
  from the p4-pilot worktree's `HOLDS4.jsonl`), so from 21:30:14Z on every live round of the mass
  run is refused. A descriptions-only plan re-queues its own sites as before. HANDOVER (resume
  point, 2.4 item 2, section 6), contracts sections 11 and 12, the runbook (0.2, section 8) and
  REPAIR_TEXTS 2.4 (b) / 5.2 now say: the 19 are v3d's, the mass run is never driven live again.
* **Major - L5 before the plan's read.** Runbook 0.3 (and contracts section 12): the link and name
  pass L5 (HUMAN_ONLY_DECISIONS B1-L, B1-N) is applied and accepted before step 2's `plan4.py
  read`, and no link or name lane writes while v3 runs - or L5's candidates are `--exclude`d and
  planned after L5 in their own list plan. Measured offline against the plan of the 00:12 UTC fresh
  read (`C:/tmp/wa2/PLAN4.v3.jsonl`, 3,238 sites): **43 of the 72 `link_suspect` sites** of
  `bcases/names.jsonl` and 34 of its 46 N7 names are v3 sites (the reviewer's 43 confirmed).
* **Minor - `ready` and a batch that asked nothing.** `handoff4.ready` now takes `--run-dir`: a
  named batch of the run without a folder in the handoff directory (every site held before the
  stage) is listed as `named_without_questions` and no longer keeps `ok` false; its import asks
  nothing, and had its export not run, its import stops at the first question (no answer file). A
  name that is no batch of the run is refused (exit 2), so a typo cannot pass as such a batch.
  Runbook sections 5 and 6 updated.
* **Minor - the E3 rule the plan is built with.** Runbook 0.4: merge WD2 (O7) before step 3 if
  ready, and record which commit's `dates.py` fixed the flags. Measured with `wip/wd2`'s
  `pipeline/normalizers/dates.py` (`git show wip/wd2:...`, loaded from a scratch file) over the same
  plan and read: **0 of the plan's 20 `scope-pending` flags change** - the v3 sites in Oceania dated
  after 500 AD (5, all on Easter Island, country Chile) already lie in the Americas' longitude
  window.
* **Minor - stale texts.** `scope4`'s docstring names version 2's pin `SCOPE_V2_SHA256`; contracts
  section 9 and 11 name the renamed pins; contracts section 11's p4-0116 re-queue and its
  "lane-L-first for the 19" are marked superseded with a pointer to section 12;
  `write_gate4._defect_scope`'s docstring names the current version's pinned file; REPAIR_TEXTS
  2.4 (b) and 5.2 are marked superseded.
* **Minor - the item-name reads.** `V3_ITEM_NAMES.json` / `V3D_ITEM_NAMES.json` are committed with
  the plan's AUDIT_LOG seal (runbook steps 2, 3 and section 8), as `S0_ITEM_NAMES.json` is; the
  `.gitignore` comment says so (`V3*_ROWS.jsonl` stays ignored).

Tests: `test_a_plan_without_the_pass_re_queues_no_site_a_descriptions_only_list_names`,
`test_a_named_batch_that_asked_nothing_is_ready_and_a_stray_name_is_refused`, and the `ready` test
with `--run-dir` (`tests/remediation/test_phase4_v3.py`). Six new mutation cases in
`P4_V3_MUTATIONS` (four for the re-queue guard, two for `ready`).

Gates (worktree `.claude/worktrees/wa`, main venv, 2026-09-26 ~02:30-02:50 UTC): the full suite
(`-q -rs --timeout 90 -m "not integration and not live_llm"`, `-p no:cacheprovider`) **7,155
passed, 119 skipped, 57 deselected, 0 failed** (434 s; the skips are the same gitignored working
data as above plus the known three). Sweep: every `p4 v3` case and every case whose target is
`mass4.py` or `handoff4.py` - **112/112 caught**, the tree byte-identical for its 8 files
afterwards. `ruff check` and `ruff format --check` clean on the six touched Python files (ruff
0.15.11); `ruff check api/ pipeline/` clean; `lint-imports` 2 kept, 0 broken; `vulture api/
pipeline/ .vulture_whitelist.py --min-confidence 80` clean. Nothing under `api/`, `pipeline/` or
`ancient-nerds-map/` was touched: no Lyra import check, no frontend gate.

## 2026-09-26 - A7: `mypy api/` from 93 errors to 0 (WE2, branch `wip/we2`; code only, nothing written to production, not pushed)

**What A7 names.** HUMAN_ONLY A7 ("`mypy api/` Altbestand") is `./.venv/Scripts/python.exe -m mypy
api/` in the repo venv: the project's dependencies installed, mypy 1.19.1, the `[tool.mypy]` section
of `pyproject.toml`. CI's `lint-backend` job runs a different configuration: it installs only
`ruff mypy import-linter==2.13 vulture==2.16` (`ci.yml:118`, mypy unpinned, today 2.3.1) and runs
`mypy api/ --no-error-summary` (`ci.yml:136`). Without the dependencies `ignore_missing_imports`
makes every SQLAlchemy, discord.py, pydantic and LangChain type `Any`, so CI's run exits 0 before
and after this work. A7's "CI-Gate kann dadurch rot sein" never held.

**Measured** (80 source files each run; the base on a `git archive 7b6c736 api pipeline
pyproject.toml` export):

| run | base `7b6c736` | head of `wip/we2` |
|---|---|---|
| repo venv, mypy 1.19.1, with dependencies (A7) | 93 errors in 14 files | **0** |
| mypy 2.3.1 (`PYTHONPATH=/tmp/mypy2`), with dependencies | 95 errors in 15 files | **0** |
| CI's install in a throwaway venv (mypy 2.3.1, no dependencies), `--no-error-summary` | exit 0 | exit 0 |

**Two real bugs**, each fixed with a test written first:

* `52d37fa` - remove-image answered 500 after it had stored the exclusion when the image had no
  cached row.
* `c6b58ff` - `/ask` in a thread (Lyra's follow-up threads included) or a voice channel's chat
  called `create_thread` on a channel without it: the player got "Something went wrong" after Lyra
  had written the answer and charged the credit. The thread is opened only in a text channel now.

And one test-suite fix: `7e6d0e5` - `tests/api/lyra/conftest.py` put a `MagicMock` under
`sys.modules["discord"]`, and pytest 9 collects that package first, so in every full run the
Discord bot and the card game's views ran against the mock whatever the tests asserted.

**The rest are typed spellings with the same behaviour**, each commit tagged `(A7)` with its own
tests: `605d7aa` and `95c9432` (`pipeline.database.affected_rows` for every `rowcount` of a
data-changing `Session.execute`; none is read directly in `api/` any more), `b19b61b` (`.one()` for
card-game rows re-read `FOR UPDATE`), `925c309` (`true()` for the empty "not owned" filter),
`b7e80c9` (the public API's `scalar_one()` counts, `dict(result.tuples())` breakdowns,
`Field(default=...)`), `95daac4` (`any_()` array membership in the library search), `0e586f2`
(`list[BaseMessage]` for Lyra's marker injection), `68f24e7` and `904d460` (the Discord views'
`_CallbackButton`, `_disable_buttons`, `_component_message`; `register_commands(bot: LyraBot)`),
`7a7a531` (the homepage cache's body typed as Starlette's `bytes | memoryview`, found by mypy 2.3.1).

**The independent review** (verdict ship, three minor findings) and what was done:

1. The status edits were uncommitted and pointed to this entry, which did not exist: written now,
   committed with them; the `HANDOVER.md` and `HUMAN_ONLY.md` edits are limited to the A7 lines.
2. The view tests pinned the new helpers and all failed against the base: rewritten
   (`904d460`). They read `View.to_components()` and click through `item.callback`; with
   `7b6c736`'s `discord_commands.py` swapped in, 7 of 8 pass, and the eighth, which pins the helpers,
   fails with `AttributeError: ... '_CallbackButton'` as it must (file restored, `git diff` empty).
3. Five `.rowcount` reads stayed direct because their sessions are `Any`: routed (`95c9432`).
   Annotating `get_session() -> Iterator[Session]` was tried and not kept: it surfaces 29 more
   errors in 3 files (25 `discord_commands.py`, 3 `vector_sync.py`, 1 `theo.py`), a follow-up
   beyond A7 recorded in the runbook.

**Runbook:** `docs/procedures/CODE_AUDIT.md`, "Type check: `mypy api/` in two configurations"
(both commands, the typed spellings, how to try a newer mypy without touching the venv, the
`get_session` measurement, and the gate gap below).

**Open.** (a) No gate enforces the dependency-aware run: `.githooks/pre-push` runs no mypy, and CI
installs neither the dependencies nor a pinned mypy. Moving the run into the hook or into CI is a
gate change, so it waits for the owner (HUMAN_ONLY A7); until then the runbook is run after every
merge that touches `api/` or the models in `pipeline/database.py`. (b) The `get_session`
annotation and its 29 errors, among them `DuelView.accept_button` reading `c_deck_row.card_ids`
before the line that treats the deck as possibly `None`. (c) Deploy effect of merging: the api
image rebuilds, and because of `pipeline/database.py` the Lyra image too (Lyra import check green).

**Gates** (worktree `.claude/worktrees/we2`, main venv, head `904d460` plus this entry): pytest
`-q -rs --timeout 90 -m "not integration and not live_llm"` **7,150 passed, 118 skipped, 57
deselected, 0 failed** (379 s; the skips are the gitignored remediation inputs, fonts and Natural
Earth cache this worktree does not carry); `ruff check api/ pipeline/` clean and `ruff format
--check` clean on the 31 touched Python files (ruff 0.15.11); `lint-imports` 2 kept, 0 broken;
`vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80` clean; the three mypy runs in the
table above; the Lyra-image import check (`markdown`/`nh3` blocked) imports
`pipeline.lyra.orchestrator`.
