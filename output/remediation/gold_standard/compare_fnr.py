#!/usr/bin/env python3
"""Unblinding: compare the blinded gold-standard verdicts against the machine census.

The GOLD lane wrote its 36 per-site records (540 field verdicts) before its run was cut
short, and never got to the comparison step. This script performs that comparison.

The comparison must be FIELD-level, not site-level. T10 alone flags 4,010 of the 5,004
sites and T09 flags all 5,004, so "the site was mentioned somewhere by some check" would
read as a catch rate near 100% and measure nothing. A blinded error counts as CAUGHT only
if a census finding names the same site AND the same field.

Run:  ./.venv/Scripts/python.exe output/remediation/gold_standard/compare_fnr.py
"""

from __future__ import annotations

import collections
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
RUNS = sorted(ROOT.glob("output/remediation/run_t0*/findings.jsonl"))
RUNS.append(ROOT / "output/remediation/run_t10/findings.jsonl")
RECORDS = sorted(ROOT.glob("output/remediation/gold_scratch/records/*.json"))
SITES = json.loads((ROOT / "output/remediation/gold_standard/sites.json").read_text("utf-8"))

# Design weights from DRAW.md / GOLD_STANDARD.md section 3 (N_h / n_h per rarity tier).
WEIGHT = {1: 175.0, 2: 179.6, 3: 165.0, 4: 50.4, 5: 10.0}

# Which census finding-field would catch which blinded field. A blinded error is CAUGHT only
# if a census finding for the SAME site carries one of these fields.
#   - period_start: T03 is the only period check and it reaches the period through prose
#     (its findings carry field description / card_description), so those are its proxies.
#   - site_type: T04 is the check; it ran and flagged 0 sites.
#   - scope: no census check covers the E3 cutoff at all (grep: 0 modules).
FIELD_MAP: dict[str, set[str]] = {
    "description": {"description"},
    "card_description": {"card_description"},
    "period_start": {"description", "card_description"},
    "period_name": {"description", "card_description"},
    "hero_image": {"wiki_images.is_hero", "wiki_images.width", "wiki_images.original_url", "wiki_images"},
    "gallery_images": {"wiki_images.is_hero", "wiki_images.width", "wiki_images.original_url", "wiki_images"},
    "thumbnail_url": {"unified_sites.thumbnail_url", "wiki_images.original_url"},
    "source_url": {"unified_sites.source_url", "site_content_links.content_url"},
    "name": {"name"},
    "coordinates": {"lat/lon"},
    "country": {"country"},
    "site_type": {"site_type"},
    "scope": set(),  # structural: no check exists
    "civilization": set(),
    "heritage_designation": set(),
}


def census_fields_by_site() -> dict[str, set[str]]:
    """site_id -> every field any of the ten checks flagged for it."""
    out: dict[str, set[str]] = collections.defaultdict(set)
    for fn in RUNS:
        if not fn.exists():
            continue
        with fn.open(encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                sid = d.get("site_id")
                fld = d.get("field")
                if not sid:
                    continue
                out[str(sid)].add(str(fld))
                # T10 stores the per-image field as "wiki_images:<id>"; normalise the prefix so
                # an image-level finding still counts as an image-dimension finding.
                if fld and str(fld).startswith("wiki_images:"):
                    out[str(sid)].add("wiki_images")
    return out


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact binomial interval, computed by bisection on the exact binomial CDF (no scipy)."""
    if n == 0:
        return (0.0, 1.0)
    if k == 0:
        lo = 0.0
    else:
        # P(X >= k | p) is INCREASING in p. Find p where it equals alpha/2:
        # below that p the tail is smaller, so we must raise p.
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            tail = sum(math.comb(n, i) * mid**i * (1 - mid) ** (n - i) for i in range(k, n + 1))
            if tail < alpha / 2:
                lo = mid
            else:
                hi = mid
        lo = (lo + hi) / 2
    if k == n:
        hi = 1.0
    else:
        # P(X <= k | p) is DECREASING in p. Find p where it equals alpha/2:
        # above that p the lower tail is smaller, so we must raise p when it is still large.
        lo2, hi2 = 0.0, 1.0
        for _ in range(200):
            mid = (lo2 + hi2) / 2
            tail = sum(math.comb(n, i) * mid**i * (1 - mid) ** (n - i) for i in range(0, k + 1))
            if tail > alpha / 2:
                lo2 = mid
            else:
                hi2 = mid
        hi = (lo2 + hi2) / 2
    # A confidence interval that does not contain the point estimate is a bug, not a result.
    assert lo <= k / n <= hi, f"Clopper-Pearson interval [{lo}, {hi}] excludes p_hat={k / n}"
    assert 0.0 <= lo <= hi <= 1.0, f"interval out of range: [{lo}, {hi}]"
    return (lo, hi)


def main() -> None:
    covered = census_fields_by_site()

    blinds = []
    for p in RECORDS:
        r = json.loads(p.read_text(encoding="utf-8"))
        for v in r["verdicts"]:
            if v["verdict"] != "WRONG":
                continue
            blinds.append(
                {
                    "site_id": r["site_id"],
                    "site_name": r["site_name"],
                    "tier": r["rarity_tier"],
                    "field": v["field"],
                    "correct_value": v.get("correct_value"),
                    "note": v.get("note", ""),
                }
            )

    for b in blinds:
        want = FIELD_MAP.get(b["field"], set())
        have = covered.get(b["site_id"], set())
        hits = want & have
        b["caught"] = bool(hits)
        b["caught_by"] = sorted(hits)
        b["site_flagged_anyway"] = bool(have)
        b["site_fields"] = sorted(have)

    n = len(blinds)
    uncaught = [b for b in blinds if not b["caught"]]
    k = len(uncaught)
    fnr = k / n if n else 0.0
    lo, hi = clopper_pearson(k, n)

    print("=" * 78)
    print(f"GOLD -> census comparison   (errors found by the blinded check: {n})")
    print("=" * 78)

    print("\nper blinded field:")
    print(f"  {'field':20s} {'wrong':>5s} {'caught':>7s} {'MISSED':>7s}")
    by_field: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for b in blinds:
        by_field[b["field"]][0] += 1
        if b["caught"]:
            by_field[b["field"]][1] += 1
    for fld, (tot, cau) in sorted(by_field.items(), key=lambda x: -x[1][0]):
        print(f"  {fld:20s} {tot:5d} {cau:7d} {tot - cau:7d}")

    print(f"\nFALSE-NEGATIVE RATE (unweighted): {k}/{n} = {fnr:.1%}")
    print(f"  95% Clopper-Pearson interval : [{lo:.1%}, {hi:.1%}]")

    # Tier-weighted ratio estimate, as GOLD_STANDARD.md section 3 promises.
    num = sum(WEIGHT.get(b["tier"], 1.0) for b in uncaught)
    den = sum(WEIGHT.get(b["tier"], 1.0) for b in blinds)
    print(f"\nFALSE-NEGATIVE RATE (inverse-probability weighted): {num / den:.1%}")
    print("  (weights N_h/n_h per tier: " + ", ".join(f"t{k}={v}" for k, v in WEIGHT.items()) + ")")

    print("\n" + "=" * 78)
    print("THE ERRORS THE CENSUS DID NOT FLAG (the point of the measurement)")
    print("=" * 78)
    for b in uncaught:
        anyf = "site WAS flagged by other checks: " + ", ".join(b["site_fields"]) if b["site_flagged_anyway"] else "site NOT flagged by any check"
        print(f"\n  [{b['field']}] tier {b['tier']}  {b['site_name']}")
        print(f"      {anyf}")
        note = " ".join(str(b["note"]).split())
        print(f"      {note[:300]}")

    print("\n" + "=" * 78)
    print("CAUGHT, for contrast (the census flagged the same field)")
    print("=" * 78)
    for b in blinds:
        if b["caught"]:
            print(f"  [{b['field']:20s}] tier {b['tier']}  {b['site_name'][:44]:44s} via {b['caught_by']}")

    out = {
        "blinded_errors": n,
        "caught": n - k,
        "missed": k,
        "fnr_unweighted": fnr,
        "fnr_ci95": [lo, hi],
        "fnr_weighted": num / den,
        "per_field": {f: {"wrong": t, "caught": c} for f, (t, c) in by_field.items()},
        "missed_errors": uncaught,
    }
    dest = ROOT / "output/remediation/gold_standard/fnr_result.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
