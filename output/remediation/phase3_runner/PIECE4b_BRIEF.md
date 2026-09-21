# Piece 4b — probe a host once per run instead of hammering it thirty-nine times

**Status:** brief for a lane. Extends piece 4.
**Written:** 2026-09-21 by the supervisor, from measurements recorded in `AUDIT_LOG.md`.

## 1. The measured problem

The first successful live batch (`batch-0001`, 15 sites, ledger rows on disk) made its 15 model calls
in **39 seconds** (06:55:25 → 06:56:04) and spent **38 minutes** (06:17:36 → 06:55:21) getting the
evidence ready. From the ledger, grouped by host and by the outcome of each target's last attempt:

| host | outcome | count |
| --- | --- | --- |
| `overpass-api.de` | `transport_failure` | **113** |
| `overpass-api.de` | `http_error` | 4 |
| `en.wikipedia.org` | `ok` | 14 |
| `en.wikipedia.org` | (no outcome field, legacy row) | 1 |
| `www.wikidata.org` | `ok` | 8 |

**Every single failure is one host.** The 117 Overpass attempts are 39 distinct targets ×
`MAX_ATTEMPTS = 3`, each waiting `OVERPASS_TIMEOUT = 20.0` seconds — which is the 38 minutes.

Measured with `curl` from this workstation (2026-09-21), same User-Agent the runner sends:

```text
overpass-api.de         http=000 time=0.077s   curl: (35) Recv failure: Connection was reset
overpass.kumi.systems   http=000 time=25.02s   curl: (28) Operation timed out
overpass.osm.ch         http=400 time=0.41s    (an HTTP answer: the host is reachable)
en.wikipedia.org        http=301 time=0.16s    (control: the network is otherwise fine)
```

The reset is at TLS level with **0 bytes**, for the bare host URL as well as for a query, and it is
**not** an address-family problem: `overpass-api.de` resolves to IPv4 only here
(`162.55.144.139`, `65.109.112.52`, no AAAA) and `curl -4` is reset just the same. From the **VPS** the
same host answers in 0.35 s, so this is a property of this workstation's network path, not of Overpass.

At 38 minutes per batch the plan is not viable: ~121 batches for the 1,813-site worklist is **~77
hours**, and all 5,004 sites would be **~211 hours**. The money is not the constraint ($2.43 for 5,004
sites at the measured $0.000486/site); the wall clock is, and all of it is one host that is not
answering this machine.

## 2. What to build

**One reachability probe per host per run, before any target on that host is asked.** If a host does not
answer, record every target on it as *not attempted*, with the reason, and continue with the other
hosts. When a host is up, nothing about today's behaviour changes.

Requirements, in the order they matter:

1. `ledger.py`: add `FetchOutcome.HOST_UNREACHABLE = "host_unreachable"`. It counts as a **fetch
   failure** in `StageTotals` exactly like `transport_failure` does.
2. **The probe is itself a request, so it writes its own ledger line** — `kind="fetch"`,
   `label="host_probe:<host>"`, the probed URL, its outcome and its reason. The ledger still records
   every request that left the machine; that is the property piece 4 established and it does not bend.
   One line, one request, per host per run.
3. A probe that receives **any HTTP response** (200, 400, 404, 429, 500 — anything) means the host is
   **reachable**. Only a `TransportFailure` means it is down. Do not treat a 4xx as "down".
4. For a host that is down, each pending target on it gets **exactly one ledger line** with
   `attempt=0` (no attempt was made), `outcome=host_unreachable`, `error=<the probe's reason>`, and no
   request is sent to it. The batch continues; other hosts are fetched normally.
5. `fetch.json` must carry the probe decision (per host: reachable, reason) **and** each un-attempted
   target must show up where the judge looks for failures. **Read `model_stage.read_fetch_failures`
   and the prompt builder before assuming this works**: if `host_unreachable` does not reach the
   prompt's `<failed_targets>` block, fix that too, and add a test asserting the reason appears in the
   built prompt text.
6. The reason must keep two facts apart that are not the same fact: *"this host did not answer a probe,
   so the target was not attempted"* versus *"this target was attempted and failed"*. The prompt and
   the report must both say which one happened.
7. **No host rotation and no fallback endpoint.** Which endpoint to ask stays a decision for the
   operator. Picking `overpass.osm.ch` because it answers is the operator's call, not the retry loop's.
8. Determinism is unchanged: same input, same plan, same bytes.

## 3. Tests (each one mutation-proven — say which mutation and which assertion failed)

In `tests/remediation/test_phase3_fetch.py` (and `test_phase3_model.py` if the prompt changes):

* probe unreachable → all targets on that host are `host_unreachable`, **zero requests** to their URLs
  (assert with a counting fake fetcher), one ledger line each with the reason, and a target on another
  host is still fetched normally in the same run.
* probe reachable → normal path, and **exactly one** probe request was made for that host.
* the probe writes its own ledger line.
* the reason reaches the prompt (`<failed_targets>`), and the two facts in item 6 stay distinct.
* a re-run skips already-stored evidence exactly as before.

## 4. Gates to run, and the one live command that proves the point

Report the verbatim output of:

```bash
./.venv/Scripts/python.exe -m pytest tests/remediation/ -q -rs
./.venv/Scripts/python.exe -m ruff check scripts/remediation/phase3/ tests/remediation/
./.venv/Scripts/python.exe -m ruff format --check scripts/remediation/phase3/ tests/remediation/
./.venv/Scripts/python.exe -m mypy scripts/remediation/phase3/
```

Then this **one** live command, because "the wall clock improved" is a claim that needs the artefact,
not an argument — it re-attempts nothing that is already on disk:

```bash
./.venv/Scripts/python.exe scripts/remediation/phase3/run.py fetch --batch-id batch-0001 --stage finder --live
```

Report **its wall-clock seconds** and the new ledger rows it wrote. Before the change this fetch stage
took ~38 minutes; the fix is worth nothing if it does not show up here.

## 5. Do not touch

* `output/remediation/AUDIT_LOG.md` — the supervisor is writing the entry for this measurement.
* The database, git history, `LEDGER.jsonl`'s existing rows (append only), or any file outside
  `scripts/remediation/phase3/` and `tests/remediation/`.
* Do not commit. The supervisor verifies first.
