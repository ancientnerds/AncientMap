"""Read-only probe of the dedup ladder and the resolver against prod data.

Creates the two lookup tables migration 0015 adds as TEMP tables (session
scoped, nothing persists), populates token_df from the real name table, then
runs adjudicate() on the design's acceptance pairs and a few known cases.
Also runs resolve_names() on a handful of names with the LLM tiebreak
budget at 0, so the only cost is Wikipedia/Wikidata calls.

    ssh ancientnerds "docker exec -i ancient_nerds_api python -u -" < scripts/probe_prospector_dedup.py
"""

import json

from sqlalchemy import text

from pipeline.database import get_session
from pipeline.lyra.prospector.dedup import Candidate, adjudicate
from pipeline.lyra.prospector.resolve import ResolverBudget, resolve_names

CANDS = [
    Candidate(0, "Great Zimbabwe", country="Zimbabwe", lat=-20.2675, lon=30.9333),
    Candidate(1, "Lake Van", country="Turkey", lat=38.63, lon=42.83),
    Candidate(2, "Derinkuyu", country="Turkey", lat=38.3733, lon=34.7344),
    Candidate(3, "Meadowcroft Rockshelter", country="United States", lat=40.287, lon=-80.491),
    Candidate(4, "Osireion", country="Egypt", lat=26.1847, lon=31.9192),
    Candidate(5, "Ayşepınar"),
    Candidate(6, "Mogollon Village", country="United States", lat=33.4, lon=-108.9),
    Candidate(7, "KV62", country="Egypt", lat=25.7402, lon=32.6014),
    Candidate(8, "Cahokia", country="United States", lat=38.655, lon=-90.062),
    Candidate(9, "Rollright Stone Circle", country="England"),
]

with get_session() as s:
    s.execute(
        text("""CREATE TEMP TABLE site_external_ids (
                    site_id uuid NOT NULL, kind text NOT NULL, value text NOT NULL,
                    resolved_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (site_id, kind, value))""")
    )
    s.execute(
        text("""CREATE TEMP TABLE site_name_token_df AS
                SELECT t AS token, COUNT(*)::int AS df
                FROM unified_site_names, unnest(string_to_array(name_normalized, ' ')) AS t
                WHERE t <> '' GROUP BY t""")
    )
    print("temp tables ready", flush=True)

    verdicts = adjudicate(s, CANDS)
    for c in CANDS:
        v = verdicts[c.idx]
        print(f"\n{c.name:26s} -> {v.verdict:15s} an={v.an_site_name}")
        for t in v.trace[:6]:
            print("   ", json.dumps(t, ensure_ascii=False, default=str)[:220])
        if v.external:
            print("    external:", {k: v.external[k] for k in ("source_id", "name", "via", "enrich")})

    print("\n=== resolver (no LLM tiebreaks) ===", flush=True)
    budget = ResolverBudget(0)
    res = resolve_names(
        ["Mogollon Village", "Sicyonian Treasury", "Smithsonian", "Texas", "Derinkuyu", "Harris Village"],
        cited_titles=["https://en.wikipedia.org/wiki/Mogollon_culture"],
        budget=budget,
    )
    for name, r in res.items():
        print(
            f"{name:22s} {r.verdict:14s} via={r.path:9s} label={r.label!r:34s} "
            f"qid={r.qid} pt=({r.lat},{r.lon}) prec={r.coord_precision} scope={r.in_scope} "
            f"country={r.country} type={r.site_type} note={r.note}"
        )
    s.rollback()
    print("\nrolled back (temp tables dropped with the session)")
