"""T01 - what Wikidata itself claims about a site, next to what the database says.

Four comparisons, all driven by the 4,618 QIDs the snapshot already carries in
`site_external_ids.kind = 'wikidata_qid'`, so nothing is reconciled again here:

    coordinates  P625 vs `unified_sites.lat`/`lon`
    country      P17's English label vs `unified_sites.country`
    name         the entity's English label - or, when it has none, the site's
                 `enwiki_title` - vs `unified_sites.name`
    the QID      whether it resolves to an entity at all

Periods are deliberately NOT compared, and that is a finding of the plan rather than a
simplification. Section 9.5 measured it on 300 random production QIDs: P571 covers 10.3 %,
P580/P582 exactly 0 %, and of the 25 dates that do exist 6 agree within 100 years - 6 of
the 11 deviations being designation dates (museum 1971, historical park 1989) that say
when a site became protected, not when it was in use. Wikidata cannot verify a period
here, so a period comparison would only manufacture findings.

**Every finding is `Proposal.REVIEW`, and `applicable_findings` for this test is 0 by
construction.** That is the point, not an oversight:

* ENRICHMENT_AUDIT.md anti-pattern 4: *"Do NOT auto-fix coordinates. Flag for manual
  review unless the error is extreme (wrong continent, in the ocean)."*
* The plan's own sample (section 4.1) confirmed 2 of 11 claimed `name` errors, 2 of 3
  `country` claims and 2 of 3 `coordinates` claims. A disagreement is a lead, not a
  correction.
* Wikidata is a wiki. Its entity for a site can carry the class instead of the instance
  (anti-pattern 17: "Roman aqueduct" rather than *this* aqueduct), and section 4.3 records
  that the form "Archaeological Site of Olympia" (34 sites) is the official UNESCO title
  and that England/Scotland/Wales instead of United Kingdom is deliberate project design.
  Writing Wikidata's answer over ours would be a wrong value on purpose, and a wrong value
  is worse than no value (anti-pattern 5, ENRICHMENT_AUDIT.md).

So T01 produces a review queue with its evidence attached; it never writes.

## What had to be decided

**1000 m before a coordinate disagreement is reported.** Not invented: section 9.5
measured exactly these 4,618 QID pairs with "within 1 km" as its criterion and reports
88.0 % agreement. Reusing the plan's own yardstick keeps this census comparable with the
measurement it is meant to reproduce, instead of introducing a second, incompatible
tolerance. Above 10 000 m the finding is `severe`: the one confirmed severe coordinate
error of the 60-site sample (El Tintal, section 4.2) lies 11-12 km off, and model.py
defines `severe` as "moves the pin".

**That tolerance is floored by Wikidata's own P625 `precision`.** `extract_claims()` drops
the field; it is kept here because it is the only signal that separates a site pin
(precision 1e-06 deg) from a region centroid (precision 1 deg) - the same distinction
`pipeline/lyra/site_identifier.py:1259-1262` uses it for. Wikidata rounds its value to
`precision` degrees, so its uncertainty is half of that; converted at 111 320 m per degree
of latitude. A point Wikidata itself calls a region cannot contradict a site pin, and
without this term every Texas site pinned to its real location would be flagged against
Wikidata's centroid of Texas.

**A name is the same name when its token set matches, contains, or is contained in the
other's, and when the two are the same tokens with different word breaks.** Those three
forms carry the aliases section 4.3 documents as correct - Wikidata's "Olympia" against
our "Archaeological Site of Olympia" (the official UNESCO title), "Cumbemayo" against
"Cumbe Mayo". What is left over is split by one structural rule, with no similarity
score involved: a difference of one token on each side ("Hattusa"/"Hattusas",
"Meare Lake Village"/"Meare Lake Villages", Wikidata's own typo "Mehirs"/"Menhirs") is
recorded as `cosmetic`, a difference of more as `moderate`. Neither class is dropped,
because a misspelt site name is precisely what a high string-similarity score looks like.

**Every country disagreement is `moderate`, including the ones that are our own project
design.** 67 of 4,473 comparisons disagree (98.5 % agreement, against section 9.5's
96.6 %), and the cohort splits into three kinds a reviewer must tell apart by hand:
21 sites whose `country` is "Ireland" while P17 says United Kingdom, 8 long forms
("China" against "People's Republic of China"), and a tail whose P17 value is a
historical polity rather than a modern state (Ancient Rome, Gaul, Roman Britain, Kingdom
of Kush) - anti-pattern 7 forbids using those, so Wikidata is the wrong side there. A
tolerance that guessed between them would have to contain "Niger" in "Nigeria"; it is
not worth the false negatives.

## Evidence, cache and purity

`collect()` fetches claims in `wbgetentities` batches of 50 (the API's own limit) through
`census.fetch.Fetcher`, one derived JSON file per batch below
`<cache>/t01_wikidata_claims/`, plus a second, much smaller sweep that resolves the P17
target QIDs to English labels. A batch whose file exists is never refetched, so a run
interrupted after batch 40 resumes at 41 and a re-run is free; `run()` is a pure function
of (snapshot, cache) and reads nothing else.

The extraction itself is `extract_claims()` from `scripts/audit_wikidata_batch.py`, loaded
by file path because an installed dependency ships a top-level `scripts` package that
shadows this repository's directory (`run.py` carries the same warning). Its neighbour
`fetch_json()` is deliberately unused: it prints a warning and returns `None` when a
request fails, which is the "could not ask" -> "checked and clean" inversion this census
exists to prevent. Every failure raises; `run()` raises when the cache cannot cover the
snapshot's QIDs rather than reporting passes it did not earn.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from census.fetch import chunked
from census.model import Confidence, Evidence, Finding, Proposal, Severity

if TYPE_CHECKING:
    from census.run import Context

TEST_ID = "T01"
NAME = "Wikidata label/P17/P625 vs name, country and coordinates"
DIMENSION = "D3-LOCATION / D4-NAME"

REPO = Path(__file__).resolve().parents[4]
AUDIT_MODULE = REPO / "scripts" / "audit_wikidata_batch.py"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
ENTITY_URL = "https://www.wikidata.org/wiki/"
CACHE_DIRNAME = "t01_wikidata_claims"

#: wbgetentities accepts at most 50 ids per call.
BATCH = 50
#: Section 9.5's own criterion for "the coordinates agree" (88.0 % of the QID pairs).
TOLERANCE_M = 1000.0
#: The one confirmed severe coordinate error (El Tintal, section 4.2) is 11-12 km out.
SEVERE_M = 10_000.0
#: Metres per degree of latitude, for turning P625's precision into a tolerance.
METRES_PER_DEGREE = 111_320.0
#: Wikidata's globe for Earth. Any other globe is not a WGS84 lon/lat.
EARTH_GLOBE = "Q2"

#: Apostrophes are elided rather than treated as word breaks, because transliterated
#: names vary on exactly that character ("Beit She'arim" / "Beit Shearim").
_APOSTROPHES = str.maketrans("", "", "'\u2019")
_WORD_SPLIT = re.compile(r"[^0-9a-z]+")

log = logging.getLogger("census.t01")


# --------------------------------------------------------------------------- helpers
def _project_root() -> None:
    """Make the repository root importable, so `pipeline.*` resolves.

    `run.py` puts `scripts/remediation` on the path (as a file, that is all it needs) but
    not the repository root, so `from pipeline.utils.geo import haversine_distance` fails
    until this runs. Appended rather than prepended, deliberately: the repo's own
    `scripts/` directory would otherwise shadow the top-level `scripts` package whose
    existence `run.py` warns about. t04_site_type.py does the same for its normalizer.
    """
    if str(REPO) not in sys.path:
        sys.path.append(str(REPO))


def _audit_helper() -> Any:
    """`extract_claims` from scripts/audit_wikidata_batch.py, loaded by file path.

    By path, not by import: a dependency installs a top-level package named `scripts`
    which shadows this repository's directory (run.py's own note). The module is left in
    `sys.modules` so a second call reuses it instead of re-executing it.
    """
    if "audit_wikidata_batch" in sys.modules:
        return sys.modules["audit_wikidata_batch"]
    spec = importlib.util.spec_from_file_location("audit_wikidata_batch", AUDIT_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{TEST_ID}: cannot load {AUDIT_MODULE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_wikidata_batch"] = module
    spec.loader.exec_module(module)
    return module


def _p625_extras(entity: dict[str, Any]) -> tuple[float | None, str | None] | None:
    """The two P625 companions `extract_claims()` drops: precision and globe.

    Same snak `extract_claims()` reads (P625 statement 0, not rank-filtered), so the
    coordinate compared is the coordinate whose precision is reported.
    """
    statements = (entity.get("claims") or {}).get("P625") or []
    if not statements:
        return None
    value = statements[0].get("mainsnak", {}).get("datavalue", {}).get("value") or {}
    precision = value.get("precision")
    globe = value.get("globe")
    return (
        float(precision) if isinstance(precision, int | float) else None,
        str(globe).rsplit("/", 1)[-1] if globe else None,
    )


def _site_claims(entity: dict[str, Any], retrieved_at: str | None) -> dict[str, Any]:
    """One entity's claims, as the JSON a batch file stores."""
    record: dict[str, Any] = dict(_audit_helper().extract_claims(entity))
    extras = _p625_extras(entity)
    if extras is not None:
        record["coord_precision"], record["coord_globe"] = extras
    if "missing" in entity:
        record["missing"] = True  # the QID resolves to nothing
    record["retrieved_at"] = retrieved_at
    return record


def _as_float(value: Any) -> float | None:
    """A JSON number as a float; anything else - including bool - is `None`."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _batch_name(prefix: str, index: int) -> str:
    return f"{prefix}_{index:04d}.json"


def _write_batch(
    path: Path,
    kind: str,
    index: int,
    ids: list[str],
    records: dict[str, dict[str, Any]],
    fetched_at: str | None,
) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "kind": kind,
                "index": index,
                "ids": ids,
                "fetched_at": fetched_at,
                "records": records,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp.replace(path)  # atomic: an interrupted collect leaves no half batch


def _load_batch(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, dict):
        raise RuntimeError(f"{TEST_ID}: {path} is not a batch file (no `records` map)")
    return records


def _batch_files(directory: Path, prefix: str) -> list[Path]:
    return sorted(directory.glob(f"{prefix}_*.json"))


def _expected_batches(n_items: int) -> int:
    return (n_items + BATCH - 1) // BATCH


# --------------------------------------------------------------------------- collect
def _fetch_entities(ctx: Context, out: Path, index: int, ids: list[str]) -> None:
    payload = ctx.net().get_json(
        WIKIDATA_API,
        params={
            "action": "wbgetentities",
            "ids": "|".join(ids),
            "props": "claims|labels",
            "languages": "en",
            "format": "json",
        },
        ns="t01_wikidata",
    )
    body = payload.get("json") or {}
    if not isinstance(body, dict):
        raise RuntimeError(f"{TEST_ID}: batch {index} answered with a non-JSON body")
    if body.get("error"):
        raise RuntimeError(f"{TEST_ID}: wbgetentities refused batch {index}: {body['error']}")
    entities = body.get("entities")
    if not isinstance(entities, dict):
        raise RuntimeError(f"{TEST_ID}: batch {index} answered without an `entities` map")
    # The API echoes every requested id, using {"missing": ...} for one that does not
    # exist. An id that is absent entirely means the response is not about our request,
    # which must not be recorded as "this entity has no claims".
    absent = [q for q in ids if q not in entities]
    if absent:
        raise RuntimeError(f"{TEST_ID}: batch {index} did not answer for {absent[:3]}")
    records = {q: _site_claims(entities[q], payload.get("fetched_at")) for q in ids}
    _write_batch(
        out / _batch_name("entities", index),
        "entities",
        index,
        ids,
        records,
        payload.get("fetched_at"),
    )


def _fetch_labels(ctx: Context, out: Path, index: int, ids: list[str]) -> None:
    payload = ctx.net().get_json(
        WIKIDATA_API,
        params={
            "action": "wbgetentities",
            "ids": "|".join(ids),
            "props": "labels",
            "languages": "en",
            "format": "json",
        },
        ns="t01_wikidata",
    )
    body = payload.get("json") or {}
    if not isinstance(body, dict):
        raise RuntimeError(f"{TEST_ID}: label batch {index} answered with a non-JSON body")
    if body.get("error"):
        raise RuntimeError(f"{TEST_ID}: label batch {index} refused: {body['error']}")
    entities = body.get("entities")
    if not isinstance(entities, dict):
        raise RuntimeError(f"{TEST_ID}: label batch {index} answered without an `entities` map")
    records: dict[str, dict[str, Any]] = {}
    for qid in ids:
        entity = entities.get(qid) or {}
        label = (entity.get("labels") or {}).get("en", {}).get("value")
        # Keyed for every requested id, so `run()` can tell "no English label" (a value)
        # from "this batch was never fetched" (an error).
        records[qid] = {"label": label, "retrieved_at": payload.get("fetched_at")}
    _write_batch(
        out / _batch_name("labels", index), "labels", index, ids, records, payload.get("fetched_at")
    )


def _collect_batches(
    ctx: Context,
    out: Path,
    prefix: str,
    what: str,
    ids: list[str],
    fetch: Callable[[Context, Path, int, list[str]], None],
) -> None:
    batches = list(enumerate(chunked(ids, BATCH)))
    pending = [(i, batch) for i, batch in batches if not (out / _batch_name(prefix, i)).exists()]
    log.info(
        "%s: %d/%d %s batches cached, fetching %d",
        TEST_ID,
        len(batches) - len(pending),
        len(batches),
        what,
        len(pending),
    )
    if not pending:
        return
    # ctx.net() raises when there is no fetcher; Fetcher.map returns the exception of a
    # failed item instead of propagating it, so the result is inspected and re-raised.
    results = ctx.net().map(
        lambda item: fetch(ctx, out, item[0], item[1]), pending, desc=f"{TEST_ID} {what}"
    )
    for result in results:
        if isinstance(result, Exception):
            raise result


def _country_qids(directory: Path) -> set[str]:
    """Every P17 target any cached entity names - the union the label sweep must cover."""
    targets: set[str] = set()
    for path in _batch_files(directory, "entities"):
        for record in _load_batch(path).values():
            targets.update(record.get("country_qids") or [])
    return targets


def collect(ctx: Context) -> None:
    """Fill the cache. Resumable: a batch already on disk is never refetched."""
    _project_root()
    out = ctx.cache / CACHE_DIRNAME
    out.mkdir(parents=True, exist_ok=True)
    qids = sorted(set(ctx.snap.ids_of_kind("wikidata_qid").values()))
    if not qids:
        raise RuntimeError(f"{TEST_ID}: the snapshot carries no wikidata_qid values")
    _collect_batches(ctx, out, "entities", "entity", qids, _fetch_entities)
    country_qids = sorted(_country_qids(out))
    _collect_batches(ctx, out, "labels", "country label", country_qids, _fetch_labels)


# ------------------------------------------------------------------------------ read
def _read_entities(directory: Path, qids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """The cached claims, or a refusal - never a short dict that would read as clean."""
    wanted = set(qids)
    files = _batch_files(directory, "entities")
    expected = _expected_batches(len(wanted))
    if len(files) != expected:
        raise RuntimeError(
            f"{TEST_ID}: {len(files)} entity batches in {directory}, expected {expected} "
            f"for {len(wanted)} QIDs - delete {directory} and run "
            f"`run.py --tests {TEST_ID} --collect-only`"
        )
    entities: dict[str, dict[str, Any]] = {}
    for path in files:
        entities.update(_load_batch(path))
    missing = sorted(wanted - set(entities))
    if missing:
        raise RuntimeError(
            f"{TEST_ID}: the entity cache does not cover {len(missing)} "
            f"QIDs, e.g. {missing[:3]} - delete {directory} and run "
            f"`run.py --tests {TEST_ID} --collect-only`"
        )
    return entities


def _read_labels(directory: Path, qids: Iterable[str]) -> dict[str, dict[str, Any]]:
    wanted = set(qids)
    files = _batch_files(directory, "labels")
    expected = _expected_batches(len(wanted))
    if len(files) != expected:
        raise RuntimeError(
            f"{TEST_ID}: {len(files)} label batches in {directory}, expected {expected} "
            f"for {len(wanted)} P17 targets - delete {directory} and run "
            f"`run.py --tests {TEST_ID} --collect-only`"
        )
    labels: dict[str, dict[str, Any]] = {}
    for path in files:
        labels.update(_load_batch(path))
    missing = sorted(wanted - set(labels))
    if missing:
        raise RuntimeError(
            f"{TEST_ID}: the label cache does not cover {missing[:3]} - "
            f"delete {directory} and run "
            f"`run.py --tests {TEST_ID} --collect-only`"
        )
    return labels


# ------------------------------------------------------------------- name agreement
def _name_tokens(name: str) -> set[str]:
    """Tokens of a site name, through the project's own `normalize_name()`.

    `normalize_name()` (pipeline/utils/text.py) is what the project already uses to match
    names for deduplication: NFKD, diacritics stripped, bracketed and parenthesised parts
    dropped, lowercased. On top of that, punctuation and hyphens become word breaks and
    apostrophes vanish, so that "Umm-el-Qanatir", "Umm el Qanatir" and "Umm el Qanatir's"
    are not three names.
    """
    from pipeline.utils.text import normalize_name

    return {t for t in _WORD_SPLIT.split(normalize_name(name).translate(_APOSTROPHES)) if t}


def _names_agree(ours: str, theirs: str) -> bool:
    """Whether two names are the same site's name in different clothes.

    Equal tokens, one token set contained in the other, or the same tokens written with
    different word breaks. Containment is what carries the alias forms the plan documents
    as correct: Wikidata's "Olympia" against our "Archaeological Site of Olympia" (the
    official UNESCO title, section 4.3), or its "Great Sphinx" against our "Great Sphinx
    of Giza". Word order and stopwords are therefore not decisive. Word breaks carry
    "Cumbemayo" / "Cumbe Mayo" and "Bojjannakonda" / "Bojjanna Konda", which are one
    name typed two ways. Two names that are none of the three are reported, never
    resolved - section 3 records real pairs like "Templos de Tarxien" / "Tarxien
    Temples" that are the same site under two names, and only a human can say which name
    to keep (anti-pattern 18: confirm that name *and* coordinate mean the same place).
    """
    a, b = _name_tokens(ours), _name_tokens(theirs)
    if not a or not b:
        return False
    if a == b or a <= b or b <= a:
        return True
    return "".join(sorted(a)) == "".join(sorted(b))


def _is_name_variant(ours: str, theirs: str) -> bool:
    """Whether the two names differ in form only - one token on each side.

    "Hattusas" / "Hattusa", "Meare Lake Village" / "Meare Lake Villages", "Mehirs" /
    "Menhirs" (where the typo is Wikidata's, not ours), "Giants' Graves" / "giants'
    grave". These are real differences in the stored name and are therefore recorded, but
    as `cosmetic`: the finding costs one glance to dismiss, and Phase 3 spends ~40 000
    tokens per reviewed site, so the two classes must not share a queue.

    Deliberately structural rather than a string-similarity score: the set difference
    needs no threshold to justify, and a similarity threshold would start silencing
    genuine defects - a misspelt site name is exactly what a high similarity score looks
    like.
    """
    return len(_name_tokens(ours) ^ _name_tokens(theirs)) <= 2


def _distance_m(site: dict[str, Any], entity: dict[str, Any]) -> float | None:
    """Stored-to-Wikidata distance in metres, or None when either side has no point."""
    lat, lon = _as_float(site.get("lat")), _as_float(site.get("lon"))
    wlat, wlon = _as_float(entity.get("lat")), _as_float(entity.get("lon"))
    if lat is None or lon is None or wlat is None or wlon is None:
        return None
    from pipeline.utils.geo import haversine_distance

    return haversine_distance(lat, lon, wlat, wlon) * 1000.0


# ------------------------------------------------------------------ the comparisons
def _finding(
    sid: str,
    suffix: str,
    field: str,
    severity: Severity,
    qid: str,
    current: Any,
    note: str,
    evidence: list[Evidence],
) -> Finding:
    return Finding(
        site_id=sid,
        test_id=f"{TEST_ID}/{suffix}",
        field=field,
        severity=severity,
        dimension=DIMENSION,
        current_value=current,
        proposal=Proposal.REVIEW,
        confidence=Confidence.UNVERIFIABLE,
        note=note,
        evidence=evidence,
    )


def _compare_coordinates(
    site: dict[str, Any], sid: str, qid: str, entity: dict[str, Any], stats: dict[str, int]
) -> list[Finding]:
    lat, lon = _as_float(site.get("lat")), _as_float(site.get("lon"))
    wlat, wlon = _as_float(entity.get("lat")), _as_float(entity.get("lon"))
    if lat is None or lon is None or wlat is None or wlon is None:
        return []  # one side holds no comparable point; there is nothing to weigh
    globe = entity.get("coord_globe")
    if globe not in (None, EARTH_GLOBE):
        # A P625 on the Moon or Mars is a real (if odd) Wikidata statement; comparing it
        # to a WGS84 lon/lat would be a category error, so it is reported as such.
        return [
            _finding(
                sid,
                "coords-globe",
                "lat/lon",
                Severity.COSMETIC,
                qid,
                [lat, lon],
                f"Wikidata P625 sits on globe {globe}, not Earth - not comparable to a WGS84 point",
                [
                    Evidence(
                        source="wikidata:P625",
                        url=f"{ENTITY_URL}{qid}",
                        quote=f"globe = {globe}",
                        retrieved_at=entity.get("retrieved_at"),
                    ),
                    Evidence(
                        source="snapshot:unified_sites.lat/lon",
                        quote=f"stored = {lat:.6f}, {lon:.6f}",
                    ),
                ],
            )
        ]

    stats["coordinates"] += 1
    distance = _distance_m(site, entity)
    assert distance is not None  # both sides were checked above
    precision = entity.get("coord_precision")
    precision_m = (
        float(precision) * METRES_PER_DEGREE / 2.0 if isinstance(precision, int | float) else 0.0
    )
    tolerance = max(TOLERANCE_M, precision_m)
    if distance <= tolerance:
        if precision_m > TOLERANCE_M:
            stats["coords-tolerant"] += 1
        return []

    severity = Severity.SEVERE if distance > SEVERE_M else Severity.MODERATE
    wd_quote = f"P625 = {wlat:.6f}, {wlon:.6f}"
    if isinstance(precision, int | float):
        wd_quote += f" (precision {precision} deg = +/-{precision_m:.0f} m)"
    return [
        _finding(
            sid,
            "coords",
            "lat/lon",
            severity,
            qid,
            [lat, lon],
            f"Wikidata P625 is {distance / 1000.0:.2f} km from the stored point "
            f"(review threshold {tolerance:.0f} m) - section 4.3: decide this by hand, "
            "never write it automatically (anti-pattern 4)",
            [
                Evidence(
                    source="wikidata:P625",
                    url=f"{ENTITY_URL}{qid}",
                    quote=wd_quote,
                    retrieved_at=entity.get("retrieved_at"),
                ),
                Evidence(
                    source="snapshot:unified_sites.lat/lon", quote=f"stored = {lat:.6f}, {lon:.6f}"
                ),
            ],
        )
    ]


def _compare_country(
    site: dict[str, Any],
    sid: str,
    qid: str,
    entity: dict[str, Any],
    labels: dict[str, dict[str, Any]],
    stats: dict[str, int],
) -> list[Finding]:
    ours = site.get("country")
    targets = [q for q in (entity.get("country_qids") or []) if q]
    if not ours or not targets:
        return []  # no P17 on the entity, or no stored country: nothing to weigh
    stats["country"] += 1

    from pipeline.utils.country_lookup import normalize_country

    ours_code = normalize_country(ours)
    matched: list[str] = []
    unlabelled: list[str] = []
    labelled: list[tuple[str, str]] = []
    for target in targets:
        label: str | None = labels[target].get("label")
        if not label:
            unlabelled.append(target)
            continue
        labelled.append((target, label))
        if normalize_country(label) == ours_code:
            matched.append(target)
    if matched:
        return []
    if not labelled:
        qids = ", ".join(unlabelled)
        return [
            _finding(
                sid,
                "country-unlabelled",
                "country",
                Severity.COSMETIC,
                qid,
                ours,
                f"Wikidata P17 target(s) {qids} carry no English label, so the country could "
                "not be compared - the country is unverified, not confirmed",
                [
                    Evidence(
                        source="wikidata:P17",
                        url=f"{ENTITY_URL}{qid}",
                        quote=f"P17 = {qids} (no en label)",
                        retrieved_at=entity.get("retrieved_at"),
                    ),
                    Evidence(source="snapshot:unified_sites.country", quote=f"stored = {ours!r}"),
                ],
            )
        ]

    wd_codes = sorted({normalize_country(label) for _, label in labelled})
    wd = ", ".join(f"{label} ({target})" for target, label in labelled)
    return [
        _finding(
            sid,
            "country",
            "country",
            Severity.MODERATE,
            qid,
            ours,
            f"stored country normalises to {ours_code!r}, Wikidata P17 to {wd_codes!r}. "
            "Read both before deciding: constituent countries (England/Scotland/Wales), "
            'contested territories and long forms ("People\'s Republic of China") are '
            "project design or naming, while P17 itself sometimes carries a historical "
            "polity (Ancient Rome, Gaul, Kingdom of Kush) that anti-pattern 7 forbids us to "
            "use",
            [
                Evidence(
                    source="wikidata:P17",
                    url=f"{ENTITY_URL}{qid}",
                    quote=f"P17 = {wd}",
                    retrieved_at=entity.get("retrieved_at"),
                ),
                Evidence(source="snapshot:unified_sites.country", quote=f"stored = {ours!r}"),
                Evidence(
                    source="pipeline/utils/country_lookup.py:normalize_country",
                    quote=f"normalize_country({ours!r}) = {ours_code!r}",
                ),
            ],
        )
    ]


def _compare_name(
    site: dict[str, Any],
    sid: str,
    qid: str,
    entity: dict[str, Any],
    enwiki: str | None,
    stats: dict[str, int],
) -> list[Finding]:
    ours = site.get("name")
    label = entity.get("en_label")
    candidate = label or enwiki
    if not ours or not candidate:
        return []  # no label and no enwiki title, or no stored name
    stats["name"] += 1
    if _names_agree(ours, candidate):
        return []

    distance = _distance_m(site, entity)
    where = (
        f"; Wikidata's point is {distance / 1000.0:.2f} km away, so check that both "
        "refer to the same site before any verdict (section 4.3)"
        if distance is not None and distance > TOLERANCE_M
        else ""
    )
    source = "en label" if label else "enwiki title"
    evidence = [
        Evidence(
            source=f"wikidata:{source}",
            url=f"{ENTITY_URL}{qid}",
            quote=f"{source} = {candidate!r}",
            retrieved_at=entity.get("retrieved_at"),
        ),
        Evidence(source="snapshot:unified_sites.name", quote=f"name = {ours!r}"),
    ]
    if label and enwiki and enwiki != label:
        evidence.append(
            Evidence(
                source="snapshot:site_external_ids:enwiki_title", quote=f"enwiki_title = {enwiki!r}"
            )
        )
    variant = _is_name_variant(ours, candidate)
    stats["name-variant" if variant else "name-differ"] += 1
    return [
        _finding(
            sid,
            "name-variant" if variant else "name",
            "name",
            Severity.COSMETIC if variant else Severity.MODERATE,
            qid,
            ours,
            (
                f"stored name {ours!r} differs from the {source} {candidate!r} by one token - a "
                "spelling, number or word-break difference, recorded for completeness"
                if variant
                else f"stored name {ours!r} vs the {source} {candidate!r}: the two names share no full "
                f"token set and differ by more than one token, so one of them - or the QID "
                f"itself (anti-pattern 17) - is wrong{where}"
            ),
            evidence,
        )
    ]


def _dead_qid(sid: str, qid: str, entity: dict[str, Any]) -> Finding:
    return _finding(
        sid,
        "qid",
        "site_external_ids",
        Severity.MODERATE,
        qid,
        qid,
        "the stored QID resolves to no Wikidata entity, so nothing about this site is "
        "verifiable against Wikidata - the identifier needs replacing or clearing",
        [
            Evidence(
                source="wikidata:wbgetentities",
                url=f"{ENTITY_URL}{qid}",
                quote="entity is marked missing (deleted or never existed)",
                retrieved_at=entity.get("retrieved_at"),
            )
        ],
    )


# ------------------------------------------------------------------------------- run
def applies_to(site: dict[str, Any], ctx: Context) -> bool:
    """Only sites that carry a Wikidata QID. The other 386 have nothing to compare."""
    rows = ctx.snap.by("site_external_ids").get(str(site["id"]), [])
    return any(r.get("kind") == "wikidata_qid" for r in rows)


def run(ctx: Context) -> list[Finding]:
    _project_root()
    directory = ctx.cache / CACHE_DIRNAME
    qid_by_site = ctx.snap.ids_of_kind("wikidata_qid")
    enwiki_by_site = ctx.snap.ids_of_kind("enwiki_title")
    entities = _read_entities(directory, set(qid_by_site.values()))
    country_qids = {q for e in entities.values() for q in (e.get("country_qids") or [])}
    labels = _read_labels(directory, country_qids)

    findings: list[Finding] = []
    stats = {
        "coordinates": 0,
        "coords-tolerant": 0,
        "country": 0,
        "name": 0,
        "name-variant": 0,
        "name-differ": 0,
        "deads": 0,
    }
    for site in ctx.sites:
        sid = str(site["id"])
        qid = qid_by_site.get(sid)
        if not qid:
            continue  # applies_to() marks this site not_applicable
        entity = entities.get(qid)
        if entity is None:
            raise RuntimeError(f"{TEST_ID}: site {sid} cites {qid}, which no batch covers")
        if entity.get("missing"):
            stats["deads"] += 1
            findings.append(_dead_qid(sid, qid, entity))
            continue
        findings += _compare_coordinates(site, sid, qid, entity, stats)
        findings += _compare_country(site, sid, qid, entity, labels, stats)
        findings += _compare_name(site, sid, qid, entity, enwiki_by_site.get(sid), stats)

    log.info(
        "%s: compared %d coordinates (%d disagreements absorbed by Wikidata's own "
        "precision), %d countries, %d names (%d mismatches: %d differing, %d "
        "single-token variants); %d QIDs resolve to nothing",
        TEST_ID,
        stats["coordinates"],
        stats["coords-tolerant"],
        stats["country"],
        stats["name"],
        stats["name-differ"] + stats["name-variant"],
        stats["name-differ"],
        stats["name-variant"],
        stats["deads"],
    )
    return findings
