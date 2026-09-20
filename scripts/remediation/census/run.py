"""Driver for the deterministic census.

The audit's acceptance criterion is per SITE, not per test: after the census every one of
the 5,004 curated sites must be, for every test, exactly one of

    pass            the test applied to this site and found nothing
    flagged         the test applied and produced at least one Finding
    not_applicable  the test does not apply (e.g. T01 on a site with no Wikidata QID)
    error           the test crashed - the hole is visible, never silently a "pass"

so a test module declares

    TEST_ID, NAME, DIMENSION          metadata
    applies_to(site, ctx) -> bool     optional; default is "all sites"
    collect(ctx) -> None              optional; the only part that touches the network
    run(ctx) -> list[Finding]         the census itself

`census.jsonl` carries one TestResult per (site, test) - 5004 x len(tests) rows - and the
run asserts that the four statuses sum back to the site count for every test. A test that
silently checks fewer sites than exist is the failure mode this file exists to prevent.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

# Dual use: `python -m census.run` and `python scripts/remediation/census/run.py`.
# The package is not installed; when run as a file, its parent must be importable first.
# (Loaded by path rather than `scripts.remediation...` because a dependency installs a
# top-level package named `scripts` that shadows this repo's scripts/ directory.)
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from census import model as M  # noqa: E402
from census.fetch import Fetcher  # noqa: E402
from census.snapshot import Snapshot, SnapshotError  # noqa: E402

log = logging.getLogger("census")

#: test id -> module name under census.tests
REGISTRY: dict[str, str] = {
    "T01": "t01_wikidata_claims",
    "T02": "t02_admin_country",
    "T03": "t03_years_in_text",
    "T04": "t04_site_type",
    "T05": "t05_country_values",
    "T06": "t06_url_shape",
    "T07": "t07_link_sweep",
    "T08": "t08_citation_markers",
    "T09": "t09_commons_dimensions",
    "T10": "t10_gallery_tiers",
}


class TestModule(Protocol):
    TEST_ID: str
    NAME: str
    DIMENSION: str

    def run(self, ctx: Context) -> list[M.Finding]: ...
    def applies_to(self, site: dict[str, Any], ctx: Context) -> bool: ...


@dataclass
class Context:
    """Everything a test may read. Deliberately no database handle."""

    snap: Snapshot
    cache: Path
    out: Path
    fetch: Fetcher | None = None
    sites: list[dict[str, Any]] = field(default_factory=list)

    def net(self) -> Fetcher:
        """The HTTP client, or a clear failure.

        A test that needs the network must fail loudly when it is absent instead of
        quietly reporting "no findings" - that would turn "could not check" into
        "checked and fine", the exact inversion this audit exists to prevent.
        """
        if self.fetch is None:
            raise RuntimeError("this test needs the network but no Fetcher was provided")
        return self.fetch


def _load(test_id: str) -> TestModule:
    mod = importlib.import_module(f"census.tests.{REGISTRY[test_id]}")
    if not hasattr(mod, "run"):
        raise AttributeError(f"{mod.__name__} has no run(ctx)")
    return mod  # type: ignore[return-value]


def _aggregate(
    tid: str, mod: TestModule, findings: list[M.Finding], ctx: Context, error: str | None = None
) -> list[M.TestResult]:
    """Build the per-site outcome rows for one test, with no gaps."""
    applies = getattr(mod, "applies_to", None)
    by_site: dict[str, list[M.Finding]] = {}
    for f in findings:
        by_site.setdefault(f.site_id, []).append(f)

    rows: list[M.TestResult] = []
    for site in ctx.sites:
        sid = str(site["id"])
        if error is not None:
            rows.append(M.TestResult(site_id=sid, test_id=tid, status="error", detail=error))
            continue
        if applies is not None and not applies(site, ctx):
            rows.append(M.TestResult(site_id=sid, test_id=tid, status="not_applicable"))
            continue
        hits = by_site.get(sid, [])
        if not hits:
            rows.append(M.TestResult(site_id=sid, test_id=tid, status="pass"))
        else:
            detail = "; ".join(f"{h.field}:{h.proposal.value}" for h in hits[:5])
            rows.append(
                M.TestResult(
                    site_id=sid,
                    test_id=tid,
                    status="flagged",
                    detail=detail[:500],
                    checked=len(hits),
                )
            )
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic census over the curated sites")
    ap.add_argument("--snapshot", default="output/remediation/snapshot")
    ap.add_argument("--cache", default="output/remediation/cache")
    ap.add_argument("--out", default="output/remediation")
    ap.add_argument(
        "--tests", default=",".join(REGISTRY), help="comma-separated test ids, e.g. T01,T04"
    )
    ap.add_argument(
        "--collect-only", action="store_true", help="fill the network cache and stop (resumable)"
    )
    ap.add_argument(
        "--no-collect",
        action="store_true",
        help="do not fetch - for a fully offline re-run against a warm cache",
    )
    ap.add_argument(
        "--skip-verify",
        action="store_true",
        help="do not re-check sha256 (only for a quick local iteration)",
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    snap = Snapshot(args.snapshot)
    try:
        manifest = {} if args.skip_verify else snap.verify()
    except SnapshotError as exc:
        log.error("snapshot unusable: %s", exc)
        return 2
    log.info("snapshot verified: %s", manifest or "(skipped)")
    log.info("sites in snapshot: %d", len(snap.sites))

    wanted = [t.strip() for t in args.tests.split(",") if t.strip()]
    unknown = [t for t in wanted if t not in REGISTRY]
    if unknown:
        log.error("unknown test id(s): %s", ", ".join(unknown))
        return 2

    mods = {t: _load(t) for t in wanted}

    fetcher: Fetcher | None = Fetcher(cache)
    ctx = Context(snap=snap, cache=cache, out=out, fetch=fetcher, sites=snap.sites)

    # ---------------------------------------------------------------- collectors
    if not args.no_collect:
        for tid, mod in mods.items():
            if not hasattr(mod, "collect"):
                continue
            t0 = time.time()
            log.info("%s: collecting ...", tid)
            try:
                mod.collect(ctx)
            except Exception:
                log.exception("%s: collector failed", tid)
                if fetcher is not None:
                    fetcher.close()
                return 1
            log.info("%s: collected in %.1fs", tid, time.time() - t0)
    if args.collect_only:
        log.info("collect-only done; cache stats %s", fetcher.stats if fetcher else {})
        if fetcher is not None:
            fetcher.close()
        return 0

    # ---------------------------------------------------------------- census
    rows: list[M.TestResult] = []
    findings: list[M.Finding] = []
    summary: list[dict[str, Any]] = []
    n_sites = len(ctx.sites)

    for tid, mod in mods.items():
        t0 = time.time()
        log.info("%s: running", tid)
        error: str | None = None
        try:
            got = mod.run(ctx) or []
        except Exception as exc:
            log.exception("%s: failed", tid)
            got, error = [], f"{type(exc).__name__}: {exc}"
        findings.extend(got)
        test_rows = _aggregate(tid, mod, got, ctx, error)
        rows.extend(test_rows)
        tally = {
            s: sum(1 for r in test_rows if r.status == s)
            for s in ("pass", "flagged", "not_applicable", "error")
        }
        if sum(tally.values()) != n_sites:
            # A hole in the matrix is a bug in _aggregate, not a data problem.
            raise AssertionError(
                f"{tid}: statuses sum to {sum(tally.values())}, expected {n_sites}"
            )
        summary.append(
            {
                "test_id": tid,
                "name": getattr(mod, "NAME", REGISTRY[tid]),
                "dimension": getattr(mod, "DIMENSION", ""),
                "sites": n_sites,
                "findings": len(got),
                "applicable": tally["pass"] + tally["flagged"],
                "flagged": tally["flagged"],
                "not_applicable": tally["not_applicable"],
                "errors": tally["error"],
                "elapsed_s": round(time.time() - t0, 2),
                "applicable_findings": sum(1 for f in got if f.applicable),
            }
        )
        log.info(
            "%s: %d findings (%d applicable), %d/%d sites flagged, %.1fs",
            tid,
            len(got),
            sum(1 for f in got if f.applicable),
            tally["flagged"],
            n_sites,
            time.time() - t0,
        )

    if fetcher is not None:
        fetcher.close()

    # ---------------------------------------------------------------- output
    (out / "findings.jsonl").write_text(
        "".join(f.to_json() + "\n" for f in findings), encoding="utf-8"
    )
    (out / "census.jsonl").write_text("".join(r.to_json() + "\n" for r in rows), encoding="utf-8")
    (out / "CENSUS.md").write_text(_report(summary, findings, snap), encoding="utf-8")

    bad = [s["test_id"] for s in summary if s["errors"]]
    log.info("wrote %s: %d findings, %d census rows", out, len(findings), len(rows))
    # Printed, not just logged: a run that writes files but says nothing is indistinguishable
    # from a run that did nothing, and this is the one line that shows the shape of the result.
    print(
        f"[census] {len(snap.sites)} sites x {len(summary)} tests -> {len(rows)} rows, "
        f"{len(findings)} findings; wrote {out}/CENSUS.md",
        flush=True,
    )
    if bad:
        log.error("tests that crashed: %s", ", ".join(bad))
        return 1
    return 0


def _report(summary: list[dict[str, Any]], findings: list[M.Finding], snap: Snapshot) -> str:
    lines = [
        "# Census of the curated sites",
        "",
        f"Snapshot `{snap.dir}`, exported {snap.exported_at()} - `{len(snap.sites)}` sites.",
        "",
        "Every site is accounted for in every test: `applicable = pass + flagged`, and",
        "`applicable + not_applicable + errors = sites`. A non-zero `errors` column means",
        "that test's result is unknown, not clean.",
        "",
        "## Tests",
        "",
        "| test | dimension | sites | applicable | flagged | n/a | errors | findings "
        "| applicable findings | elapsed_s |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summary:
        lines.append(
            f"| {s['test_id']} {s['name']} | {s['dimension']} | {s['sites']} "
            f"| {s['applicable']} | {s['flagged']} | {s['not_applicable']} | {s['errors']} "
            f"| {s['findings']} | {s['applicable_findings']} | {s['elapsed_s']} |"
        )

    # The column was headed `s`, which reads like a score. It is wall-clock seconds, so it
    # changes between runs (whichever test runs first pays the snapshot-load cost). Say so,
    # and name the artifacts that ARE reproducible, so nobody hashes this file.
    lines += [
        "",
        "`elapsed_s` is wall-clock seconds and varies between runs: it is a timing note, not a"
        " quality score, and it is not part of the reproducible output. `census.jsonl` and"
        " `findings.jsonl` are the byte-reproducible artifacts.",
    ]

    lines += [
        "",
        "## Findings by severity, field and proposal",
        "",
        "| severity | field | proposal | count |",
        "|---|---|---|---|",
    ]
    tally: dict[tuple[str, str, str], int] = {}
    for f in findings:
        k = (f.severity.value, f.field, f.proposal.value)
        tally[k] = tally.get(k, 0) + 1
    for (sev, fld, prop), n in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {sev} | {fld} | {prop} | {n} |")

    lines += [
        "",
        "## Provenance",
        "",
        "Reproducible from the snapshot plus the HTTP cache; no test reads the",
        "database. `applicable findings` carry the evidence their confidence",
        "demands - the rest are proposals for human review.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
