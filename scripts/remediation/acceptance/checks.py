"""Phase 6 acceptance, section 8: the deterministic checks D1-D6 - no judge.

D1-D5 run on the frozen values of the drawn sites (`SAMPLE.jsonl`), each with the project's own
definition, imported rather than copied:

* D1 - every `[N]` marker has an entry in `description_citations` and every entry is cited: the
  census's T08 reading (`census.tests.t08_citation_markers.marker_sequence` / `entries`, the
  pipeline's grouped-marker expander first);
* D2 - `period_name` is `pipeline.utils.text.categorize_period(period_start)`;
* D3 - `card_stats.civilization` equals `country`;
* D4 - where `_description_provenance` is carried, it parses (`phase4.model4.provenance_from_dict`),
  its `desc_sha256` is the sha256 of the description, and a card it names hashes to
  `card.text_sha256` (`model4.text_sha256`);
* D5 - `name_normalized` is Postgres's `left(lower(unaccent(name)), 500)` of the frozen name
  (`pipeline.lyra.site_key.site_key_sql`, computed by Postgres, never in Python).

D6 is production now: no curated site outside the E3 window without a scope decision (the scope
lane's own residual, `mechanical.lane.SCOPE.post_commit_residual`) and no retired site in
`/api/sites/all`. The database is read in one read-only repeatable-read transaction of SELECTs
(`export_script`, `mechanical.plan.tagged_export_script`); the API with a plain GET of the public
endpoint for each source that has a retired site.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from census.fetch import USER_AGENT
from census.tests.t08_citation_markers import entries, marker_sequence
from mechanical.lane import SCOPE, sql_literal
from mechanical.plan import tagged_export_script
from phase4.model4 import Provenance, provenance_from_dict, text_sha256

from pipeline.lyra.site_key import site_key_sql
from pipeline.utils.text import categorize_period

CHECKS = ("D1", "D2", "D3", "D4", "D5", "D6")
EXPORT_KINDS = ("name_key", "outside_window", "retired")
SITES_ALL = "https://ancientnerds.com/api/sites/all"


def d1(site: Mapping[str, Any]) -> str | None:
    markers = set(marker_sequence(site.get("description") or ""))
    try:
        numbers = {e["n"] for e in entries(site.get("description_citations"), site["site_id"])}
    except ValueError as exc:
        return str(exc)
    missing, uncited = sorted(markers - numbers), sorted(numbers - markers)
    if missing or uncited:
        return (
            f"markers without an entry {[f'[{n}]' for n in missing]}, entries never cited {uncited}"
        )
    return None


def d2(site: Mapping[str, Any]) -> str | None:
    expected = categorize_period(site.get("period_start"))
    if site.get("period_name") != expected:
        return (
            f"period_name {site.get('period_name')!r} is not "
            f"categorize_period({site.get('period_start')}) = {expected!r}"
        )
    return None


def d3(site: Mapping[str, Any]) -> str | None:
    if site.get("civilization") != site.get("country"):
        return f"civilization {site.get('civilization')!r} is not country {site.get('country')!r}"
    return None


def d4(site: Mapping[str, Any]) -> str | None:
    data = site.get("description_provenance")
    if data is None:
        return None
    try:
        provenance = provenance_from_dict(data)
    except ValueError as exc:
        return f"the provenance does not parse: {exc}"
    description = site.get("description")
    if description is None or text_sha256(description) != provenance.desc_sha256:
        return "desc_sha256 is not the sha256 of the served description"
    if isinstance(provenance, Provenance) and provenance.card is not None:
        card = site.get("card_description")
        if card is None or text_sha256(card) != provenance.card.text_sha256:
            return "card.text_sha256 is not the sha256 of the served card text"
    return None


def d5(site: Mapping[str, Any], key: str) -> str | None:
    if site.get("name_normalized") != key:
        return f"name_normalized {site.get('name_normalized')!r} is not Postgres's key {key!r}"
    return None


def d6(outside: int, retired: Mapping[str, str], served: set[str]) -> list[str]:
    failures = []
    if outside:
        failures.append(f"{outside} curated site(s) outside the E3 window without a decision")
    for site_id in sorted(set(retired) & served):
        failures.append(f"retired site {site_id} ({retired[site_id]}) is in /api/sites/all")
    return failures


# ------------------------------------------------------------------------------ production
def export_script(sample: Sequence[Mapping[str, Any]]) -> str:
    """One read-only transaction: Postgres's key of every frozen name, the scope residual, and the
    retired ids."""
    values = ", ".join(
        f"({sql_literal(str(site['site_id']))}, {sql_literal(str(site['name']))})"
        for site in sample
    )
    parts = (
        (
            "name_key",
            f"SELECT v.site_id, {site_key_sql('v.name')} AS sql_key "
            f"FROM (VALUES {values}) AS v(site_id, name)",
        ),
        (
            "outside_window",
            "SELECT count(*) AS n FROM unified_sites WHERE source_id = 'ancient_nerds' AND "
            + SCOPE.post_commit_residual.predicate,
        ),
        (
            "retired",
            "SELECT id::text AS site_id, source_id FROM unified_sites "
            "WHERE scope_status = 'retired'",
        ),
    )
    return tagged_export_script(parts)


def served_ids(sources: set[str]) -> tuple[set[str], dict[str, Any]]:
    """Every site id `/api/sites/all` serves for these sources - a plain public GET, nothing else."""
    ids: set[str] = set()
    counts: dict[str, int] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120.0) as client:
        for source in sorted(sources):
            response = client.get(SITES_ALL, params={"source": source, "fields": "globe"})
            response.raise_for_status()
            sites = response.json()["sites"]
            counts[source] = len(sites)
            ids |= {str(site["id"]) for site in sites}
    return ids, {"url": SITES_ALL, "fields": "globe", "sites_served": counts}


def evaluate(
    sample: Sequence[Mapping[str, Any]],
    rows: Mapping[str, list[dict[str, Any]]],
    served: set[str],
) -> dict[str, Any]:
    """D1-D6 over the frozen values and the production read."""
    keys = {str(row["site_id"]): str(row["sql_key"]) for row in rows["name_key"]}
    missing = sorted({str(site["site_id"]) for site in sample} - set(keys))
    if missing:
        raise ValueError(f"the name_key read lacks {missing}")
    per_site: dict[str, list[dict[str, Any]]] = {check: [] for check in CHECKS[:5]}
    for site in sample:
        site_id = str(site["site_id"])
        for check, detail in (
            ("D1", d1(site)),
            ("D2", d2(site)),
            ("D3", d3(site)),
            ("D4", d4(site)),
            ("D5", d5(site, keys[site_id])),
        ):
            if detail is not None:
                per_site[check].append({"site_id": site_id, "name": site["name"], "detail": detail})
    (outside,) = rows["outside_window"]
    retired = {str(row["site_id"]): str(row["source_id"]) for row in rows["retired"]}
    result: dict[str, Any] = {
        check: {"holds": not failures, "failures": failures} for check, failures in per_site.items()
    }
    d6_failures = d6(int(outside["n"]), retired, served)
    result["D6"] = {
        "holds": not d6_failures,
        "failures": d6_failures,
        "outside_e3_without_decision": int(outside["n"]),
        "retired": len(retired),
    }
    result["all_hold"] = all(result[check]["holds"] for check in CHECKS)
    return result
