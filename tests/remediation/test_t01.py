"""Do the T01 comparisons actually fire?

A check that reports zero findings is indistinguishable from a check that is broken, and
"Wikidata agrees with the stored name/country/coordinate" is only a result if the same
code reports a disagreement when one is present. These tests therefore build a synthetic
snapshot, a synthetic entity cache in `tmp_path` **through the module's own writer and
extractor**, and assert on the findings.

They are deliberately not end-to-end: no network, no real snapshot, no real cache. The
entity dicts are shaped like the `wbgetentities` answer, so a change in how the module
reads P625/P17/labels shows up here instead of quietly shrinking the flag list.

The reference for the shape and the standard is `TestT04SiteType` in
tests/remediation/test_census_checks.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from census import model as M  # noqa: E402
from census.run import Context  # noqa: E402
from census.tests import t01_wikidata_claims as t01  # noqa: E402

RETRIEVED = "2026-09-20T20:28:00+0200"


# --------------------------------------------------------------------------- fixtures
def _site(sid: str = "s1", name: str = "Site", country: str = "Greece",
          lat: float | None = 37.0, lon: float | None = 22.0) -> dict[str, Any]:
    return {"id": sid, "source_id": "ancient_nerds", "name": name, "country": country,
            "lat": lat, "lon": lon}


def _entity(label: str | None = None, lat: float | None = None, lon: float | None = None,
            precision: float = 1e-06, globe: str = "Q2", country_qids: tuple[str, ...] = (),
            missing: bool = False) -> dict[str, Any]:
    """A `wbgetentities` entity, with only the parts T01 reads."""
    entity: dict[str, Any] = {}
    if missing:
        entity["missing"] = ""
    if label:
        entity["labels"] = {"en": {"language": "en", "value": label}}
    claims: dict[str, Any] = {}
    if lat is not None and lon is not None:
        claims["P625"] = [{"mainsnak": {"datavalue": {"value": {
            "latitude": lat, "longitude": lon, "altitude": None, "precision": precision,
            "globe": f"http://www.wikidata.org/entity/{globe}"}}}}]
    if country_qids:
        claims["P17"] = [{"mainsnak": {"datavalue": {"value": {"id": q}}}}
                         for q in country_qids]
    if claims:
        entity["claims"] = claims
    return entity


class _Snap:
    """The three snapshot accessors T01 uses, over an in-memory site list."""

    def __init__(self, sites: list[dict[str, Any]],
                 external: dict[str, dict[str, str]]) -> None:
        self.sites = sites
        self._external = external

    def ids_of_kind(self, kind: str) -> dict[str, str]:
        return {sid: ext[kind] for sid, ext in self._external.items() if ext.get(kind)}

    def by(self, table: str, key: str | None = None) -> dict[str, list[dict[str, Any]]]:
        assert table == "site_external_ids", table
        return {sid: [{"kind": k, "value": v} for k, v in ext.items() if v]
                for sid, ext in self._external.items()}


def _write_cache(tmp_path: Path, entities: dict[str, dict[str, Any]],
                 labels: dict[str, str | None]) -> None:
    """Write one entity batch (and the label batch it needs) the way collect() does."""
    out = tmp_path / "cache" / t01.CACHE_DIRNAME
    out.mkdir(parents=True, exist_ok=True)
    ids = sorted(entities)
    records = {q: t01._site_claims(entities[q], RETRIEVED) for q in ids}
    t01._write_batch(out / t01._batch_name("entities", 0), "entities", 0, ids, records,
                     RETRIEVED)
    targets = sorted({q for e in entities.values()
                      for statement in (e.get("claims", {}).get("P17") or [])
                      for q in [statement["mainsnak"]["datavalue"]["value"]["id"]]})
    if targets:
        t01._write_batch(
            out / t01._batch_name("labels", 0), "labels", 0, targets,
            {q: {"label": labels.get(q), "retrieved_at": RETRIEVED} for q in targets},
            RETRIEVED)


def _context(sites: list[dict[str, Any]], external: dict[str, dict[str, str]],
             tmp_path: Path, cache: Path | None = None) -> Context:
    """The parts of `Context` T01 reads, and nothing else.

    `cast` because a test double is not a `Context` - the annotation keeps mypy honest
    about every call the module makes with it.
    """
    return cast(Context, SimpleNamespace(
        snap=_Snap(sites, external), sites=sites, cache=cache or tmp_path / "cache",
        out=tmp_path))


def _findings(tmp_path: Path, site: dict[str, Any], entity: dict[str, Any],
              labels: dict[str, str | None] | None = None,
              enwiki: str | None = None, qid: str = "Q1") -> list[M.Finding]:
    _write_cache(tmp_path, {qid: entity}, labels or {})
    external = {str(site["id"]): {"wikidata_qid": qid,
                                  **({"enwiki_title": enwiki} if enwiki else {})}}
    return t01.run(_context([site], external, tmp_path))


# ------------------------------------------------------------------------- coordinates
class TestT01Coordinates:
    def test_a_few_km_off_is_flagged_for_review(self, tmp_path):
        """~2.2 km north of the stored point: the plan's own 1 km criterion."""
        got = _findings(tmp_path, _site(lat=48.0, lon=2.0), _entity(lat=48.02, lon=2.0))
        assert len(got) == 1
        f = got[0]
        assert f.test_id == "T01/coords"
        assert f.field == "lat/lon"
        assert f.severity is M.Severity.MODERATE
        assert f.proposal is M.Proposal.REVIEW
        assert f.proposed_value is None, "a coordinate disagreement is never a proposed value"
        assert not f.applicable, "anti-pattern 4: coordinates are never auto-fixed"
        assert len(f.evidence) >= 2

    def test_a_tens_of_km_off_is_severe(self, tmp_path):
        got = _findings(tmp_path, _site(lat=48.0, lon=2.0), _entity(lat=48.2, lon=2.0))
        assert [f.severity for f in got] == [M.Severity.SEVERE]

    def test_agreement_produces_nothing(self, tmp_path):
        """~11 m off: the same point, not a disagreement."""
        assert _findings(tmp_path, _site(lat=48.0, lon=2.0),
                         _entity(lat=48.0001, lon=2.0)) == []

    def test_wikidatas_own_coarse_precision_absorbs_the_disagreement(self, tmp_path):
        """A P625 rounded to a whole degree is a region centroid, not a site pin.

        The point is 5.5 km away, which would otherwise be a moderate finding; Wikidata
        itself says it is only accurate to +/- 55 km.
        """
        assert _findings(tmp_path, _site(lat=48.0, lon=2.0),
                         _entity(lat=48.05, lon=2.0, precision=1.0)) == []

    def test_an_off_globe_coordinate_is_reported_not_compared(self, tmp_path):
        got = _findings(tmp_path, _site(lat=48.0, lon=2.0),
                        _entity(lat=0.0, lon=0.0, globe="Q111"))
        assert [f.test_id for f in got] == ["T01/coords-globe"]
        assert got[0].severity is M.Severity.COSMETIC

    def test_an_entity_without_p625_is_not_a_disagreement(self, tmp_path):
        """Nothing to compare is not 'clean', but it is also not a coordinate claim."""
        assert _findings(tmp_path, _site(name="Something"),
                         _entity(label="Something")) == []


# ----------------------------------------------------------------------------- country
class TestT01Country:
    def test_a_different_country_is_flagged(self, tmp_path):
        got = _findings(tmp_path, _site(country="Greece"), _entity(country_qids=("Q38",)),
                        labels={"Q38": "Italy"})
        assert len(got) == 1
        f = got[0]
        assert (f.test_id, f.field, f.severity) == ("T01/country", "country",
                                                    M.Severity.MODERATE)
        assert f.proposal is M.Proposal.REVIEW and not f.applicable
        assert any("Italy" in (e.quote or "") for e in f.evidence)

    def test_a_constituent_country_matches_its_sovereign(self, tmp_path):
        """Section 4.3: England vs United Kingdom is deliberate project design."""
        assert _findings(tmp_path, _site(country="England"), _entity(country_qids=("Q145",)),
                         labels={"Q145": "United Kingdom"}) == []

    def test_ireland_against_the_united_kingdom_is_flagged(self, tmp_path):
        """The 21-site cohort the real snapshot produces - not an alias form."""
        got = _findings(tmp_path, _site(country="Ireland"), _entity(country_qids=("Q145",)),
                        labels={"Q145": "United Kingdom"})
        assert [f.test_id for f in got] == ["T01/country"]

    def test_any_of_several_p17_values_may_match(self, tmp_path):
        entity = _entity(country_qids=("Q38", "Q41"))
        assert _findings(tmp_path, _site(country="Greece"), entity,
                         labels={"Q38": "Italy", "Q41": "Greece"}) == []

    def test_a_p17_target_without_an_english_label_is_reported(self, tmp_path):
        """Uncomparable must not read as confirmed (model.py: never a silent pass)."""
        got = _findings(tmp_path, _site(country="Greece"),
                        _entity(country_qids=("Q99999999",)), labels={"Q99999999": None})
        assert [f.test_id for f in got] == ["T01/country-unlabelled"]
        assert got[0].severity is M.Severity.COSMETIC

    def test_an_entity_without_p17_is_not_a_country_claim(self, tmp_path):
        assert _findings(tmp_path, _site(country="Greece", name="X"),
                         _entity(label="X")) == []


# -------------------------------------------------------------------------------- name
class TestT01Name:
    def test_a_reworded_title_is_flagged(self, tmp_path):
        """The plan's own known pair (section 3), same site under two names."""
        got = _findings(tmp_path, _site(name="Templos de Tarxien"),
                        _entity(label="Tarxien Temples"))
        assert [f.test_id for f in got] == ["T01/name"]
        f = got[0]
        assert f.severity is M.Severity.MODERATE
        assert f.proposal is M.Proposal.REVIEW and f.proposed_value is None
        assert any(e.source == "snapshot:unified_sites.name" for e in f.evidence)

    def test_a_qid_pointing_at_a_different_subject_is_flagged(self, tmp_path):
        """Tikal carrying the QID of the Mundo Perdido complex."""
        got = _findings(tmp_path, _site(name="Tikal"), _entity(label="Mundo Perdido"))
        assert [f.test_id for f in got] == ["T01/name"]

    def test_the_official_long_title_is_tolerated(self, tmp_path):
        assert _findings(tmp_path, _site(name="Archaeological Site of Olympia"),
                         _entity(label="Olympia")) == []

    def test_word_order_and_stopwords_are_tolerated(self, tmp_path):
        assert _findings(tmp_path, _site(name="Temple of Apollo"),
                         _entity(label="Apollo Temple")) == []

    def test_a_different_word_break_is_tolerated(self, tmp_path):
        assert _findings(tmp_path, _site(name="Cumbemayo"), _entity(label="Cumbe Mayo")) == []

    def test_a_single_token_difference_is_a_cosmetic_variant(self, tmp_path):
        """"Hattusa"/"Hattusas" is a real difference and a cheap one to dismiss."""
        got = _findings(tmp_path, _site(name="Hattusas"), _entity(label="Hattusa"))
        assert [f.test_id for f in got] == ["T01/name-variant"]
        assert got[0].severity is M.Severity.COSMETIC
        assert got[0].proposal is M.Proposal.REVIEW

    def test_a_misspelling_is_not_silenced_by_looking_similar(self, tmp_path):
        """The typo class must survive: it is one token, so it stays a finding."""
        got = _findings(tmp_path, _site(name="Menhirs of Lavajo"),
                        _entity(label="Mehirs of Lavajo"))
        assert len(got) == 1, "a near-miss name is recorded, never treated as agreement"

    def test_the_enwiki_title_stands_in_when_the_entity_has_no_label(self, tmp_path):
        got = _findings(tmp_path, _site(name="Stadium at Nemea"), _entity(),
                        enwiki="Ancient Stadium of Nemea")
        assert [f.test_id for f in got] == ["T01/name"]
        assert any(e.source == "wikidata:enwiki title" for e in got[0].evidence)

    def test_case_and_punctuation_alone_are_tolerated(self, tmp_path):
        assert _findings(tmp_path, _site(name="Giants' Graves"),
                         _entity(label="giants' graves")) == []

    def test_the_enwiki_title_is_shown_when_it_disagrees_with_the_label(self, tmp_path):
        got = _findings(tmp_path, _site(name="Avdat National Park"),
                        _entity(label="Abdah"), enwiki="Avdat")
        assert any(e.source == "snapshot:site_external_ids:enwiki_title"
                   for e in got[0].evidence)


# ------------------------------------------------------------------------------- cache
class TestT01CacheContract:
    def test_a_missing_entity_batch_raises_instead_of_passing_everything(self, tmp_path):
        site = _site()
        _write_cache(tmp_path, {"Q1": _entity(label="Site")}, {})
        (tmp_path / "cache" / t01.CACHE_DIRNAME / t01._batch_name("entities", 0)).unlink()
        ctx = _context([site], {"s1": {"wikidata_qid": "Q1"}}, tmp_path)
        with pytest.raises(RuntimeError, match="collect-only"):
            t01.run(ctx)

    def test_a_missing_label_batch_raises(self, tmp_path):
        site = _site(country="Greece")
        _write_cache(tmp_path, {"Q1": _entity(country_qids=("Q41",))}, {"Q41": "Greece"})
        (tmp_path / "cache" / t01.CACHE_DIRNAME / t01._batch_name("labels", 0)).unlink()
        ctx = _context([site], {"s1": {"wikidata_qid": "Q1"}}, tmp_path)
        with pytest.raises(RuntimeError, match="label batches"):
            t01.run(ctx)

    def test_a_qid_marked_missing_is_reported(self, tmp_path):
        got = _findings(tmp_path, _site(), _entity(missing=True))
        assert [f.test_id for f in got] == ["T01/qid"]
        assert got[0].field == "site_external_ids"

    def test_a_site_without_a_qid_is_not_applicable(self, tmp_path):
        site = _site()
        with_qid = _context([site], {"s1": {"wikidata_qid": "Q1"}}, tmp_path)
        without = _context([site], {"s1": {"enwiki_title": "Something"}}, tmp_path)
        assert t01.applies_to(site, with_qid) is True
        assert t01.applies_to(site, without) is False


# ---------------------------------------------------------------------------- contract
class TestT01FindingContract:
    def test_nothing_t01_reports_is_auto_applicable(self, tmp_path):
        """Wikidata is not automatically right: every finding stays a human decision."""
        sites = [_site("s1", name="Templos de Tarxien", country="Greece", lat=48.0, lon=2.0),
                 _site("s2", name="Hattusas", country="Ireland", lat=48.0, lon=2.0)]
        entities = {"Q1": _entity(label="Tarxien Temples", country_qids=("Q38",),
                                  lat=48.02, lon=2.0),
                    "Q2": _entity(label="Hattusa", country_qids=("Q145",),
                                  lat=48.2, lon=2.0)}
        labels = {"Q38": "Italy", "Q145": "United Kingdom"}
        out = tmp_path / "cache"
        out.mkdir(parents=True, exist_ok=True)
        cache = out / t01.CACHE_DIRNAME
        cache.mkdir(parents=True, exist_ok=True)
        ids = sorted(entities)
        t01._write_batch(cache / t01._batch_name("entities", 0), "entities", 0, ids,
                         {q: t01._site_claims(entities[q], RETRIEVED) for q in ids}, RETRIEVED)
        t01._write_batch(cache / t01._batch_name("labels", 0), "labels", 0, sorted(labels),
                         {q: {"label": v, "retrieved_at": RETRIEVED}
                          for q, v in labels.items()}, RETRIEVED)
        external = {"s1": {"wikidata_qid": "Q1"}, "s2": {"wikidata_qid": "Q2"}}
        ctx = _context(sites, external, tmp_path, cache=out)

        findings = t01.run(ctx)
        assert findings, "sanity: the synthetic defects must produce findings"
        assert [f.proposal for f in findings] == [M.Proposal.REVIEW] * len(findings)
        assert all(f.confidence is M.Confidence.UNVERIFIABLE for f in findings)
        assert all(f.evidence for f in findings), "a finding without evidence is not one"
        assert not any(f.applicable for f in findings)
        assert {f.site_id for f in findings} == {"s1", "s2"}

    def test_the_same_cache_yields_the_same_findings(self, tmp_path):
        site = _site(name="Templos de Tarxien", lat=48.0, lon=2.0)
        entity = _entity(label="Tarxien Temples", lat=48.02, lon=2.0)
        first = _findings(tmp_path, site, entity)
        second = _findings(tmp_path, site, entity)
        assert [f.change_key for f in first] == [f.change_key for f in second]
        assert len(first) == 2  # name + coordinates
