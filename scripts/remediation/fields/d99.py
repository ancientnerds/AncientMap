"""Owner decision D99 (2026-11-06): the undated shown sites are dated by a Claude researcher.

The deterministic extractor of D70 failed its sealed gold (0.7034; three independent spot checks
found 26, 29 and more of 30 cells wrong). D99 asks a Sonnet `field_researcher` per site for the
start of the site itself, checked by the calibrated `adversarial` role - the lane wd5 machinery,
not a parallel one: the run is a wd5 run built with `population.py build --stage wd5 --sites FILE
--d99` (reason `d99-undated`, whose question text is `handoff.D99_OPEN_TEXT`), exported, answered,
imported and re-checked by `handoff.py` and `adversarial.py` like every wd5 run. This module adds
only the two things the lane lacked:

    d99.py draw --undated U.jsonl --sites SITES.jsonl --owner OWNER.jsonl --seed S --out FILE
        the pilot's listed sites: a seeded, stratified draw (`STRATA`), written as the
        `{"site_id", "reason"}` lines `population.py build --sites` reads
    d99.py sources --label SITE_ID [--harvest DIR]
        what is on disk for a site, for the agent to read before the web: the Wikipedia cache
        (`wiki.py`), the item's other-language articles and its Wikidata date claims (the wd5x
        harvest, `harvest.py fetch-dating`), its Pleiades record (through P1584) and the
        non-Wikipedia pages earlier field runs cited (`harvest.cited_page_refs`)

Nothing here fetches, decides or writes production.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from fields import dating as DT  # noqa: E402
from fields import harvest as H  # noqa: E402
from fields import wiki as W  # noqa: E402

FIELDS_DIR = REPO / "output" / "remediation" / "fields"
HARVEST = FIELDS_DIR / "wd5x" / "harvest"
PLEIADES_CSV = REPO / "data" / "raw" / "pleiades" / "pleiades-places.csv"

#: The pilot's strata, drawn in this order, each from the sites no earlier stratum took (D99: Peru
#: stubs, England, Greece/Türkiye, the earlier adversarial conflicts, the others).
CONFLICTS, PERU, ENGLAND, AEGEAN, OTHERS = "conflict", "peru", "england", "greece-turkiye", "other"
STRATA: tuple[tuple[str, int], ...] = (
    (CONFLICTS, 10),
    (PERU, 10),
    (ENGLAND, 10),
    (AEGEAN, 10),
    (OTHERS, 10),
)
_COUNTRIES = {PERU: {"Peru"}, ENGLAND: {"England"}, AEGEAN: {"Greece", "Türkiye"}}
REASON = {
    CONFLICTS: "an earlier wd5 answer was rejected by the adversarial check (sources disagree)",
    PERU: "a site in Peru (mostly stub articles)",
    ENGLAND: "a site in England",
    AEGEAN: "a site in Greece or Türkiye",
    OTHERS: "a site of another country",
}
#: Wikidata properties whose values the agent sees as leads (dates and periods of the item).
LEAD_PROPS = ("P571", "P580", "P1249", "P575", "P2348", "P793")


class D99Error(RuntimeError):
    """An input of the draw or the source printer is not what it should be."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise D99Error(f"{path} is missing")
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines() if raw.strip()]


def conflict_sites(owner_rows: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    """The sites whose `period_start` the wd5 adversarial check rejected (`adv/OWNER.jsonl`)."""
    return frozenset(
        str(r["site_id"])
        for r in owner_rows
        if r["field"] == "period_start" and r["state"] == "reject"
    )


def stratum(site_id: str, country: str | None, conflicts: frozenset[str]) -> str:
    if site_id in conflicts:
        return CONFLICTS
    for name, countries in _COUNTRIES.items():
        if country in countries:
            return name
    return OTHERS


def draw(
    undated: Sequence[str],
    countries: Mapping[str, str | None],
    conflicts: frozenset[str],
    seed: int,
    strata: Sequence[tuple[str, int]] = STRATA,
) -> list[dict[str, str]]:
    """The pilot: per stratum, `n` sites drawn with `seed` from the undated sites of that stratum
    (sorted first, so the draw depends on the set and the seed only). A stratum smaller than its
    `n` is refused by name: a pilot that silently shrinks measures less than it claims."""
    missing = sorted(s for s in undated if s not in countries)
    if missing:
        raise D99Error(f"{len(missing)} undated site(s) have no harvest row, e.g. {missing[0]}")
    by_stratum: dict[str, list[str]] = {}
    for site in sorted(set(undated)):
        by_stratum.setdefault(stratum(site, countries[site], conflicts), []).append(site)
    rng = random.Random(seed)  # noqa: S311 - a reproducible draw, not a secret
    out = []
    for name, n in strata:
        pool = by_stratum.get(name, [])
        if len(pool) < n:
            raise D99Error(f"stratum {name} holds {len(pool)} site(s), fewer than {n}")
        for site in sorted(rng.sample(pool, n)):
            out.append(
                {
                    "site_id": site,
                    "reason": f"D99 pilot (seed {seed}), stratum {name}: {REASON[name]}",
                }
            )
    return out


# ------------------------------------------------------------------------------ the sources
def article_url(lang: str, title: str) -> str:
    """An article's own address (the one the import's quote check reads live)."""
    return f"https://{lang}.wikipedia.org/wiki/{url_quote(title.replace(' ', '_'), safe='/:@!$&()*+,;=-._~')}"


def wikidata_leads(entity: Mapping[str, Any], item_labels: Mapping[str, Any]) -> list[str]:
    """The item's date and period claims as one line each, the item labels resolved where the
    harvest holds them. Leads only: the agent quotes a page that states the value."""
    out = []
    for prop in LEAD_PROPS:
        for claim in (entity.get("claims") or {}).get(prop, []):
            value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if isinstance(value, dict) and "time" in value:
                shown = f"{value['time']} (precision {value.get('precision')})"
            elif isinstance(value, dict) and "id" in value:
                label = (item_labels.get(value["id"]) or {}).get("label")
                shown = f"{value['id']}" + (f" ({label})" if label else "")
            else:
                shown = json.dumps(value, ensure_ascii=False)
            qualifiers = []
            for qprop, qvalues in (claim.get("qualifiers") or {}).items():
                for q in qvalues:
                    qv = (q.get("datavalue") or {}).get("value")
                    if isinstance(qv, dict) and "time" in qv:
                        qualifiers.append(f"{qprop} {qv['time']}")
            out.append(
                f"  - {prop}: {shown}" + (f" [{'; '.join(qualifiers)}]" if qualifiers else "")
            )
    return out


def pleiades_lines(row: Mapping[str, Any]) -> list[str]:
    return [
        f"URL: {DT.PLEIADES_URL.format(id=row['id'])}",
        f"title: {row.get('title')}",
        f"description: {row.get('description')}",
        f"time periods: {row.get('timePeriodsKeys')} (minDate {row.get('minDate')}, maxDate "
        f"{row.get('maxDate')}) - the periods a source attests the place in, not a dated start",
    ]


def render_sources(
    site_id: str,
    *,
    harvest: Path,
    wiki: W.WikiCache,
    pages: Mapping[str, list[dict[str, Any]]],
    pleiades: Callable[[str], Mapping[str, Any] | None],
) -> str:
    """Everything on disk for one site, as the agent reads it: each source under a heading with the
    URL to cite."""
    sites = {s["site_id"]: s for s in H.read_sites(harvest)}
    site = sites.get(site_id)
    if site is None:
        raise D99Error(f"{site_id} is not a site of {harvest / H.SITES_FILE}")
    qid = site["qid"]
    entity = H.load_entity(harvest, qid) if qid else {}
    labels_path = harvest / H.ITEM_LABELS_FILE
    item_labels = (
        json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else {}
    )
    out = [
        f"# {site['name']} ({site['country']}), site {site_id}",
        f"Wikidata item: {'https://www.wikidata.org/wiki/' + qid if qid else 'none'}",
        "",
        "## 1. The cached Wikipedia article(s) - quote the live article at the URL given",
        "",
        W.render(site_id, wiki.pages(site_id)),
    ]
    cached = frozenset(str(p["lang"]) for p in wiki.pages(site_id))
    out.append("## 2. The item's articles in other languages")
    out.append("")
    others = H.load_wikis(harvest, qid, entity, skip=cached) if qid else []
    shown = 0
    for lang, record in others:
        if record.get("missing"):
            continue
        shown += 1
        title = str(record["title"])
        out.append(f"### {lang}.wikipedia.org: {title} (revision {record.get('revid')})")
        out.append(f"URL: {article_url(lang, title)}")
        out.append(str(record["text"]))
        out.append("")
    if not shown:
        out.append("(none on disk)\n")
    out.append("## 3. Wikidata date and period claims (leads, never a quote)")
    out.append("")
    leads = wikidata_leads(entity, item_labels) if entity else []
    out.extend(leads or ["  (none)"])
    out.append("")
    out.append("## 4. Pleiades (through the item's P1584)")
    out.append("")
    rows = [pleiades(pid) for pid in DT._string_values(entity, "P1584")] if entity else []
    rows = [r for r in rows if r is not None]
    for row in rows:
        out.extend(pleiades_lines(row))
        out.append("")
    if not rows:
        out.append("(none)\n")
    out.append("## 5. Pages earlier field passes cited (as fetched then; quote the live page)")
    out.append("")
    cited = pages.get(site_id, [])
    for ref in cited:
        text = H.page_text(ref)
        out.append(f"### {ref['url']}")
        out.append(text if text is not None else "(not readable as text)")
        out.append("")
    if not cited:
        out.append("(none)\n")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("draw", help="the pilot's listed sites (seeded, stratified)")
    d.add_argument("--undated", type=Path, required=True, help='JSON lines with "site_id"')
    d.add_argument("--sites", type=Path, default=HARVEST / H.SITES_FILE)
    d.add_argument("--owner", type=Path, default=FIELDS_DIR / "wd5" / "adv" / "OWNER.jsonl")
    d.add_argument("--seed", type=int, required=True)
    d.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("sources", help="what is on disk for one site, for the agent")
    s.add_argument("--label", required=True, help="the question's label: the site id")
    s.add_argument("--harvest", type=Path, default=HARVEST)
    s.add_argument("--wiki-cache", type=Path, default=W.WIKI_CACHE)
    s.add_argument("--fields-dir", type=Path, default=FIELDS_DIR)
    s.add_argument("--pleiades", type=Path, default=PLEIADES_CSV)
    args = parser.parse_args(argv)
    try:
        if args.command == "draw":
            undated = [str(r["site_id"]) for r in _read_jsonl(args.undated)]
            countries = {r["site_id"]: r["country"] for r in _read_jsonl(args.sites)}
            rows = draw(undated, countries, conflict_sites(_read_jsonl(args.owner)), args.seed)
            if args.out.exists():
                raise D99Error(f"{args.out} exists: a draw is written once")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                encoding="utf-8",
                newline="\n",
            )
            counts: dict[str, int] = {}
            for r in rows:
                name = r["reason"].split("stratum ")[1].split(":")[0]
                counts[name] = counts.get(name, 0) + 1
            print(json.dumps({"out": str(args.out), "sites": len(rows), "strata": counts}))
            return 0
        table = DT.read_pleiades(args.pleiades)
        print(
            render_sources(
                args.label,
                harvest=args.harvest,
                wiki=W.WikiCache(args.wiki_cache),
                pages=H.cited_page_refs(args.fields_dir),
                pleiades=lambda pid: table.get(str(pid)),
            )
        )
        return 0
    except (D99Error, H.HarvestError, W.WikiCacheError, DT.DatingError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
