"""Stage 3: is this place already ours? Set-based SQL, zero LLM.

The ladder (design doc, "Dedup-Entscheidungstabelle"):

  R0  hard identifier  — QID or redirect-resolved enwiki title in
                          site_external_ids. Decisive only if exactly ONE
                          curated site matches AND _is_same_name holds.
  R1  exact name key   — K(name) on the curated set's names and aliases,
                          with the country gate (750 curated names have a
                          same-named site in a different country).
  R2  recall nets      — trigram (word_similarity >= 0.5), levenshtein
                          (spaceless <= 2), proximity (3 km); each hit passes
                          gates G1 country / G2 distance / G3 rare shared
                          token before it is even shown. Auto-skip only when
                          ALL of: _is_same_name, countries agree or unknown,
                          distance <= 250 m or unknown.
  R3  external sources — never blocks; annotates and, under a guard, enriches.

An LLM is never asked "are these the same site?" — that question produced
Great Zimbabwe -> Great Ziggurat of Ur.

Every comparison uses the DB's own key (pipeline.lyra.site_key) computed in
Postgres. A "new" verdict always carries the trace of what was checked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import text as sql

from pipeline.lyra.site_key import site_key_sql
from pipeline.lyra.site_matcher import _is_same_name
from pipeline.utils.country_lookup import normalize_country

logger = logging.getLogger(__name__)

TRGM_THRESHOLD = 0.5
LEVENSHTEIN_MAX = 2
PROXIMITY_NET_M = 3000
G2_MAX_KM = 50.0
AUTO_SKIP_MAX_M = 250.0
G3_RARE_DF = 300


@dataclass
class Candidate:
    idx: int
    name: str
    qid: str | None = None
    enwiki_title: str | None = None
    country: str | None = None
    lat: float | None = None
    lon: float | None = None


@dataclass
class Hit:
    rung: str  # R0 | R1 | N1_trgm | N2_lev | N3_geo
    site_id: str
    site_name: str
    site_country: str | None
    source_id: str
    distance_m: float | None
    signal: float | None
    same_name: bool
    killed_by: str | None = None
    detail: dict = field(default_factory=dict)

    def trace(self) -> dict:
        return {
            "rung": self.rung,
            "site": self.site_name,
            "site_id": self.site_id,
            "source": self.source_id,
            "site_country": self.site_country,
            "distance_m": None if self.distance_m is None else round(self.distance_m),
            "signal": self.signal,
            "same_name": self.same_name,
            "killed_by": self.killed_by,
            **self.detail,
        }


@dataclass
class Verdict:
    verdict: str  # have_it | needs_decision | new
    an_site_id: str | None = None
    an_site_name: str | None = None
    trace: list[dict] = field(default_factory=list)
    external: dict | None = None  # {site_id, source_id, name, lat, lon, site_type, enrich}


# --------------------------------------------------------------------------
# SQL: every rung is ONE statement over the whole batch (VALUES + joins).
# --------------------------------------------------------------------------


def _values(cands: list[Candidate]) -> tuple[str, dict]:
    frags, params = [], {}
    for c in cands:
        i = c.idx
        frags.append(
            f"(:i{i}, :n{i}, :q{i}, :t{i}, :c{i}, CAST(:la{i} AS float8), CAST(:lo{i} AS float8))"
        )
        params.update(
            {
                f"i{i}": i,
                f"n{i}": c.name,
                f"q{i}": c.qid,
                f"t{i}": c.enwiki_title,
                f"c{i}": c.country,
                f"la{i}": c.lat,
                f"lo{i}": c.lon,
            }
        )
    return ", ".join(frags), params


_CAND_CTE = """
WITH cand(idx, name, qid, enwiki, country, lat, lon) AS (VALUES {values}),
ck AS (
    SELECT idx, name, qid, enwiki, country, lat, lon,
           {key} AS key,
           replace({key}, ' ', '') AS key_spaceless,
           CASE WHEN lat IS NOT NULL AND lon IS NOT NULL
                THEN ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography END AS g
    FROM cand
)
"""


def _cte(cands: list[Candidate]) -> tuple[str, dict]:
    values, params = _values(cands)
    return _CAND_CTE.format(values=values, key=site_key_sql("name")), params


def _site_cols(alias: str = "us") -> str:
    return (
        f"{alias}.id::text AS site_id, {alias}.name AS site_name, {alias}.country AS site_country, "
        f"{alias}.source_id, {alias}.site_type, {alias}.lat AS site_lat, {alias}.lon AS site_lon"
    )


def _dist_expr(alias: str = "us") -> str:
    return f"CASE WHEN ck.g IS NOT NULL AND {alias}.geom IS NOT NULL THEN ST_Distance(ck.g, {alias}.geom::geography) END AS distance_m"


def _r0(session, cands) -> list[tuple[int, dict]]:
    cte, params = _cte(cands)
    rows = session.execute(
        sql(
            cte
            + f"""
        SELECT DISTINCT ON (ck.idx, us.id) ck.idx, e.kind, {_site_cols()}, {_dist_expr()}
        FROM ck
        JOIN site_external_ids e
          ON (ck.qid IS NOT NULL AND e.kind = 'wikidata_qid' AND e.value = ck.qid)
          OR (ck.enwiki IS NOT NULL AND e.kind = 'enwiki_title' AND e.value = ck.enwiki)
        JOIN unified_sites us ON us.id = e.site_id AND us.source_id = 'ancient_nerds'
        """
        ),
        params,
    ).fetchall()
    return [(r.idx, dict(r._mapping)) for r in rows]


# Every curated rung works on the 5,004 ancient_nerds rows and THEIR aliases
# only, materialised once per statement. The first version joined the full
# 1.76M-row alias table through an OR of correlated predicates and hit the
# 5-minute statement timeout on a 10-candidate batch (probe 2026-09-15).
# Restricting to the curated subset makes replace()/word_similarity()/
# levenshtein() plain filters over ~15k rows — no functional index needed.
_AN_CTE = """
, an AS (
    SELECT id, name, country, source_id, site_type, lat, lon, geom, name_normalized,
           replace(name_normalized, ' ', '') AS spaceless
    FROM unified_sites WHERE source_id = 'ancient_nerds'
),
an_names AS (
    SELECT an.id AS site_id, usn.name_normalized,
           replace(usn.name_normalized, ' ', '') AS spaceless
    FROM unified_site_names usn JOIN an ON an.id = usn.site_id
)
"""


def _r1(session, cands) -> list[tuple[int, dict]]:
    cte, params = _cte(cands)
    rows = session.execute(
        sql(
            cte
            + _AN_CTE
            + f"""
        SELECT DISTINCT ON (ck.idx, us.id) ck.idx, {_site_cols()}, {_dist_expr()}
        FROM ck
        JOIN (
            SELECT ck2.idx, an.id
            FROM ck ck2 JOIN an ON an.name_normalized = ck2.key
                                OR an.spaceless = ck2.key_spaceless
            UNION
            SELECT ck2.idx, n.site_id
            FROM ck ck2 JOIN an_names n ON n.name_normalized = ck2.key
                                       OR n.spaceless = ck2.key_spaceless
        ) m ON m.idx = ck.idx
        JOIN an us ON us.id = m.id
        """
        ),
        params,
    ).fetchall()
    return [(r.idx, dict(r._mapping)) for r in rows]


def _r2(session, cands) -> list[tuple[int, dict]]:
    cte, params = _cte(cands)
    params["thr"] = TRGM_THRESHOLD
    params["lev"] = LEVENSHTEIN_MAX
    params["prox"] = PROXIMITY_NET_M
    rows = session.execute(
        sql(
            cte
            + _AN_CTE
            + f"""
        SELECT * FROM (
            SELECT DISTINCT ON (ck.idx, us.id) ck.idx, 'N1_trgm' AS net,
                   word_similarity(ck.key, n.name_normalized) AS signal,
                   {_site_cols()}, {_dist_expr()}
            FROM ck
            JOIN an_names n ON word_similarity(ck.key, n.name_normalized) >= :thr
            JOIN an us ON us.id = n.site_id
            ORDER BY ck.idx, us.id, signal DESC
        ) n1
        UNION ALL
        SELECT ck.idx, 'N2_lev' AS net,
               levenshtein(ck.key_spaceless, us.spaceless)::float8 AS signal,
               {_site_cols()}, {_dist_expr()}
        FROM ck JOIN an us
          ON length(ck.key_spaceless) BETWEEN 4 AND 60
         AND abs(length(us.spaceless) - length(ck.key_spaceless)) <= :lev
         AND levenshtein(ck.key_spaceless, us.spaceless) <= :lev
        UNION ALL
        SELECT ck.idx, 'N3_geo' AS net,
               ST_Distance(ck.g, us.geom::geography) AS signal,
               {_site_cols()}, {_dist_expr()}
        FROM ck JOIN an us
          ON ck.g IS NOT NULL AND us.geom IS NOT NULL
         AND ST_DWithin(ck.g, us.geom::geography, :prox)
        """
        ),
        params,
    ).fetchall()
    return [(r.idx, dict(r._mapping)) for r in rows]


def _r3(session, cands) -> list[tuple[int, dict]]:
    """External (non-curated) rows by QID or exact key. Annotation only."""
    cte, params = _cte(cands)
    rows = session.execute(
        sql(
            cte
            + f"""
        SELECT DISTINCT ON (ck.idx, us.id) ck.idx, {_site_cols()}, {_dist_expr()},
               CASE WHEN ck.qid IS NOT NULL AND us.source_id = 'wikidata'
                         AND us.source_record_id = ck.qid THEN 'qid' ELSE 'key' END AS via
        FROM ck
        JOIN unified_sites us
          ON us.source_id NOT IN ('ancient_nerds', 'lyra')
         AND ((ck.qid IS NOT NULL AND us.source_id = 'wikidata' AND us.source_record_id = ck.qid)
              OR us.name_normalized = ck.key)
        ORDER BY ck.idx, us.id,
                 CASE WHEN us.lat IS NOT NULL THEN 0 ELSE 1 END
        """
        ),
        params,
    ).fetchall()
    return [(r.idx, dict(r._mapping)) for r in rows]


def _token_df(session, names: list[str]) -> dict[str, int]:
    tokens: set[str] = set()
    for n in names:
        tokens.update(t for t in n.lower().split() if t)
    if not tokens:
        return {}
    rows = session.execute(
        sql("SELECT token, df FROM site_name_token_df WHERE token = ANY(:t)"),
        {"t": list(tokens)},
    ).fetchall()
    return {r.token: r.df for r in rows}


# --------------------------------------------------------------------------
# Gates and verdicts (Python; all inputs are already measured in SQL)
# --------------------------------------------------------------------------


def _countries_disagree(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return normalize_country(a) != normalize_country(b)


def gate_country(resolved: str | None, in_text: str | None) -> str | None:
    """The country a candidate is GATED on.

    A resolved (Wikidata P17 / reverse-geocoded) country always wins. A
    phrase from the text counts only if normalize_country() maps it to a real
    country: "New Mexico" or "Catron County" would otherwise disagree with a
    curated site's "USA" and kill a legitimate match at G1. The phrase itself
    stays on the card as country_in_text; it just does not vote.
    """
    if resolved:
        return resolved
    if not in_text:
        return None
    code = normalize_country(in_text)
    return in_text if len(code) == 2 and code.isupper() else None


def _keyed_names(name: str) -> set[str]:
    return {t for t in name.lower().replace("-", " ").split() if t}


def _gate(hit: Hit, cand: Candidate, df: dict[str, int]) -> None:
    """Apply G1/G2/G3 in order; the first failure is recorded on the hit."""
    if _countries_disagree(cand.country, hit.site_country):
        hit.killed_by = "G1_country"
        hit.detail["candidate_country"] = cand.country
        return
    if hit.distance_m is not None and hit.distance_m > G2_MAX_KM * 1000:
        hit.killed_by = "G2_distance"
        return
    shared = _keyed_names(cand.name) & _keyed_names(hit.site_name)
    rare = [t for t in shared if df.get(t, 0) <= G3_RARE_DF]
    hit.detail["shared_tokens"] = sorted(shared)
    hit.detail["shared_df"] = {t: df.get(t) for t in sorted(shared)}
    # G3 applies to EVERY net, proximity included: 1,748 ordered pairs of
    # curated sites sit within 100 m of each other, so a neighbour that shares
    # no rare token is context (kept in the trace), not a candidate identity.
    # KV62 next to Deir el-Bahari must be "new", not "needs_decision".
    if not rare and hit.rung != "N2_lev":
        hit.killed_by = "G3_rare_token"


def _auto_skip(hit: Hit, cand: Candidate) -> bool:
    if not hit.same_name:
        return False
    if _countries_disagree(cand.country, hit.site_country):
        return False
    return hit.distance_m is None or hit.distance_m <= AUTO_SKIP_MAX_M


def adjudicate(session, cands: list[Candidate]) -> dict[int, Verdict]:
    """Run the ladder for a batch. Returns {candidate.idx: Verdict}."""
    if not cands:
        return {}
    by_idx = {c.idx: c for c in cands}
    r0 = _r0(session, cands)
    r1 = _r1(session, cands)
    r2 = _r2(session, cands)
    r3 = _r3(session, cands)
    df = _token_df(session, [c.name for c in cands] + [r["site_name"] for _, r in r2])

    hits: dict[int, list[Hit]] = {c.idx: [] for c in cands}

    def mk(rung: str, idx: int, r: dict, signal: float | None) -> Hit:
        return Hit(
            rung=rung,
            site_id=r["site_id"],
            site_name=r["site_name"],
            site_country=r["site_country"],
            source_id=r["source_id"],
            distance_m=r.get("distance_m"),
            signal=None if signal is None else round(float(signal), 3),
            same_name=_is_same_name(by_idx[idx].name, r["site_name"]),
        )

    for idx, r in r0:
        h = mk("R0", idx, r, None)
        h.detail["key"] = r["kind"]
        hits[idx].append(h)
    for idx, r in r1:
        hits[idx].append(mk("R1", idx, r, None))
    for idx, r in r2:
        h = mk(r["net"], idx, r, r["signal"])
        _gate(h, by_idx[idx], df)
        hits[idx].append(h)

    external: dict[int, dict] = {}
    for idx, r in r3:
        if idx in external:
            continue
        cand = by_idx[idx]
        near = r.get("distance_m") is not None and r["distance_m"] <= G2_MAX_KM * 1000
        country_ok = bool(cand.country) and not _countries_disagree(cand.country, r["site_country"])
        external[idx] = {
            "site_id": r["site_id"],
            "source_id": r["source_id"],
            "name": r["site_name"],
            "country": r["site_country"],
            "lat": r["site_lat"],
            "lon": r["site_lon"],
            "site_type": r["site_type"],
            "via": r["via"],
            "enrich": bool(near or country_ok or r["via"] == "qid"),
        }

    out: dict[int, Verdict] = {}
    for c in cands:
        hs = hits[c.idx]
        trace = [h.trace() for h in hs]
        ext = external.get(c.idx)

        # R0: exactly one curated site with a same-name confirmation.
        r0_sites = {h.site_id: h for h in hs if h.rung == "R0"}
        if len(r0_sites) == 1:
            h = next(iter(r0_sites.values()))
            if h.same_name or (c.enwiki_title and _is_same_name(c.enwiki_title, h.site_name)):
                out[c.idx] = Verdict("have_it", h.site_id, h.site_name, trace, ext)
                continue
            out[c.idx] = Verdict("needs_decision", h.site_id, h.site_name, trace, ext)
            continue
        if len(r0_sites) > 1:
            out[c.idx] = Verdict("needs_decision", None, None, trace, ext)
            continue

        # R1: exact key, country-gated.
        r1_hits = [h for h in hs if h.rung == "R1"]
        if r1_hits:
            h = r1_hits[0]
            if not _countries_disagree(c.country, h.site_country):
                out[c.idx] = Verdict("have_it", h.site_id, h.site_name, trace, ext)
            else:
                h.killed_by = "G1_country"
                out[c.idx] = Verdict("needs_decision", h.site_id, h.site_name, trace, ext)
            continue

        # R2: surviving net hits, best first — same name, then nearest,
        # then strongest signal.
        alive = sorted(
            (h for h in hs if h.rung.startswith("N") and h.killed_by is None),
            key=lambda x: (
                not x.same_name,
                x.distance_m is None,
                x.distance_m or 0,
                -(x.signal or 0),
            ),
        )
        skip = [h for h in alive if _auto_skip(h, c)]
        if skip:
            h = skip[0]
            out[c.idx] = Verdict("have_it", h.site_id, h.site_name, trace, ext)
        elif alive:
            h = alive[0]
            out[c.idx] = Verdict("needs_decision", h.site_id, h.site_name, trace, ext)
        else:
            out[c.idx] = Verdict("new", None, None, trace, ext)
    return out
