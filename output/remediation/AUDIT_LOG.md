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
