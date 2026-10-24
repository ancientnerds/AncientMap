"""The five dead card_stats columns, filled from the Wikidata ids (`mechanical/card_stats_ext.py`, D25).

DB-less and offline: production is a fixture export, Wikidata a fake `Fetcher`, the harvest a
temporary directory in `fields/harvest.py`'s layout. Each refusal is asserted by the refusal it
produces (`mechanical/mutation_sweep.py "d25-ext:"`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from fields import harvest as H  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import card_stats as CS  # noqa: E402
from mechanical import card_stats_ext as X  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical.plan import SNAPSHOT_KIND, PlanError  # noqa: E402

SITE = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
OTHER = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
QID = "Q6904806"
WAVE = "2026-10-25"
LABELS = {"Q219538": "scheduled monument", "Q9259": "World Heritage Site", "Q404": None}
NONE_REFUSED: frozenset[tuple[str, int]] = frozenset()
#: Monte Lazzu (Sardinia): an Old-World site dated -1800 .. -900.
PLACE = {"lat": 40.95, "lon": 8.68, "country": "Italy", "period_start": -1800, "period_end": -900}


def statement(value: Any, rank: str = "normal") -> dict[str, Any]:
    return {"rank": rank, "mainsnak": {"datavalue": {"value": value}}}


def time_value(year: int, precision: int = 9) -> dict[str, Any]:
    sign = "-" if year < 0 else "+"
    return {"time": f"{sign}{abs(year):04d}-00-00T00:00:00Z", "precision": precision}


def entity(qid: str = QID, **claims: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": qid, "claims": claims}


def full_entity() -> dict[str, Any]:
    return entity(
        P18=[statement("Monte Lazzu.jpg")],
        P1435=[statement({"id": "Q219538"})],
        P571=[statement(time_value(-1500))],
    )


def live(**over: Any) -> X.Live:
    base: dict[str, Any] = {
        "site_id": SITE,
        "name": "Monte Lazzu",
        "source_id": "ancient_nerds",
        "scope_status": None,
        "qid": QID,
        "enwiki_title": "Monte Lazzu",
        "has_card": True,
        "stored": dict.fromkeys(X.COLUMNS),
        "premise": f"{QID}|Monte Lazzu",
        **PLACE,
    }
    base.update(over)
    return X.Live(**base)


def inception(e: dict[str, Any], refused: frozenset = NONE_REFUSED, **over: Any) -> Any:
    return X.inception_year(e, live(**over), refused)


def p571(year: int, precision: int = 9) -> dict[str, Any]:
    return entity(P571=[statement(time_value(year, precision))])


def cells(verdicts: list[Any]) -> dict[str, Any]:
    return {v.column: v.new_value for v in verdicts if v.ok}


def reasons(verdicts: list[Any]) -> dict[str, str]:
    return {str(v.column): v.reason for v in verdicts if not v.ok}


# ------------------------------------------------------------------------------ the lanes
class TestTheLane:
    def test_the_lane_fills_exactly_the_five_dead_columns(self) -> None:
        lane = X.ext_lane(WAVE, 3)
        assert lane.columns == (
            "wikidata_qid",
            "best_wiki_url",
            "heritage_designation",
            "inception_year",
            "commons_image",
        )
        assert all(cell.fills_null and not cell.clears for cell in lane.cells)
        assert lane.target is L.CARD_STATS and lane.premise_sql == X.PREMISE_SQL
        assert lane.name == "card-stats-ext-2026-10-25-s003" == lane.key_prefix
        assert lane.run_stamp == "2026-10-25_mechanical-card-stats-ext-s003"
        assert lane.out_dir_name == "mechanical_card_stats_ext/2026-10-25/s003"

    def test_civilization_and_source_language_are_never_touched(self) -> None:
        """`civilization` is the recompute's; `source_language` gates the page's wiki link
        (plans/fields.md item 9) - neither is a cell of this lane."""
        lane = X.ext_lane(WAVE, 1)
        assert "civilization" not in lane.columns and "source_language" not in lane.columns
        assert "source_language" not in X.site_sql([SITE])

    def test_the_columns_are_neither_input_nor_cell_of_the_recompute(self) -> None:
        """So an ext step and a card_stats wave never void each other's proof."""
        assert not set(X.COLUMNS) & set(CS.COLUMNS)
        assert not set(X.COLUMNS) & set(CS.INPUT_COLUMNS)
        assert all(c not in CS.PREMISE_SQL for c in X.COLUMNS)

    def test_the_name_resolves_through_the_registry_and_its_readback(self) -> None:
        lane = L.resolve_lane("card-stats-ext-2026-10-25b-s012")
        assert lane == X.ext_lane("2026-10-25b", 12)
        assert A.readback_for(lane) == X.readback(lane)
        assert f"'{lane.run_stamp}'" in X.readback(lane)
        # a card_stats wave is still a card_stats wave
        assert L.resolve_lane("card-stats-2026-10-25") == CS.card_stats_lane("2026-10-25")

    @pytest.mark.parametrize(
        "name",
        ["card-stats-ext-2026-10-25", "card-stats-ext-x-s001", "card-stats-ext-2026-10-25-s1"],
    )
    def test_a_malformed_name_is_no_lane(self, name: str) -> None:
        with pytest.raises(KeyError):
            L.resolve_lane(name)


# ------------------------------------------------------------------------------ the values
class TestTheValues:
    def test_the_best_rank_is_preferred_else_normal_and_never_deprecated(self) -> None:
        e = entity(
            P18=[
                statement("old.jpg", "deprecated"),
                statement("normal.jpg"),
                statement("chosen.jpg", "preferred"),
            ]
        )
        assert X.commons_image(e).value == "chosen.jpg"
        assert X.commons_image(entity(P18=[statement("old.jpg", "deprecated")])).reason == "no-p18"

    def test_several_normal_images_take_wikidata_s_first_and_say_so(self) -> None:
        found = X.commons_image(entity(P18=[statement("a.jpg"), statement("b.jpg")]))
        assert found.value == "a.jpg" and "first of 2" in found.note

    def test_the_designations_are_their_english_labels_in_order(self) -> None:
        e = entity(P1435=[statement({"id": "Q9259"}), statement({"id": "Q219538"})])
        assert X.heritage_designation(e, LABELS).value == "World Heritage Site; scheduled monument"
        assert X.heritage_designation(entity(), LABELS).reason == "no-p1435"

    def test_a_designation_without_an_english_label_is_never_guessed(self) -> None:
        e = entity(P1435=[statement({"id": "Q219538"}), statement({"id": "Q404"})])
        found = X.heritage_designation(e, LABELS)
        assert found.value is None and found.reason == "designation-without-label"
        unknown = entity(P1435=[statement({"id": "Q1"})])
        assert X.heritage_designation(unknown, LABELS).reason == "designation-without-label"

    def test_an_ended_designation_is_not_in_force(self) -> None:
        """A tentative-list entry the inscription superseded carries an end time (P582): the card
        names only the designation in force, and the note names the ended one."""
        tentative = {**statement({"id": "Q9259"}), "qualifiers": {"P582": [
            {"snaktype": "value", "property": "P582", "datavalue": {"value": time_value(1987)}}]}}  # fmt: skip
        e = entity(P1435=[tentative, statement({"id": "Q219538"})])
        found = X.heritage_designation(e, LABELS)
        assert found.value == "scheduled monument"
        assert "ended (P582), not read: ['Q9259']" in found.note
        assert X.designation_ids([e]) == ["Q219538"]
        gone = X.heritage_designation(entity(P1435=[tentative]), LABELS)
        assert (gone.value, gone.reason) == (None, "designation-ended")
        unknown_end = {**statement({"id": "Q9259"}),
                       "qualifiers": {"P582": [{"snaktype": "somevalue", "property": "P582"}]}}  # fmt: skip
        assert X.heritage_designation(entity(P1435=[unknown_end]), LABELS).reason == (
            "designation-ended"
        )

    def test_a_designation_whose_end_is_novalue_is_in_force(self) -> None:
        never = {**statement({"id": "Q9259"}),
                 "qualifiers": {"P582": [{"snaktype": "novalue", "property": "P582"}]}}  # fmt: skip
        assert X.heritage_designation(entity(P1435=[never]), LABELS).value == "World Heritage Site"

    def test_an_inception_is_a_year_within_the_site_s_dating(self) -> None:
        assert inception(p571(-1500)).value == "-1500"
        assert inception(p571(120, 11), period_start=-50, period_end=300).value == "120"
        # a year on the period's end is still within it
        assert inception(p571(-900)).value == "-900"

    def test_an_inception_coarser_than_a_year_states_none(self) -> None:
        found = inception(p571(-3000, 7))
        assert found.value is None and found.reason == "inception-not-a-year"
        assert inception(entity()).reason == "no-p571"

    def test_a_modern_inception_is_the_park_not_the_site(self) -> None:
        found = inception(p571(1927))
        assert found.value is None and found.reason == "inception-modern"
        americas = {"lat": 17.2, "lon": -89.6, "country": "Guatemala", "period_end": 1500}
        assert inception(p571(1499), **americas).value == "1499"
        assert inception(p571(1500), **americas).reason == "inception-modern"

    def test_two_inception_years_are_a_conflict(self) -> None:
        e = entity(P571=[statement(time_value(-1500)), statement(time_value(-1450))])
        assert inception(e).reason == "inception-conflict"
        same = entity(P571=[statement(time_value(-1500)), statement(time_value(-1500, 10))])
        assert inception(same).value == "-1500"

    def test_a_medieval_charter_of_a_roman_city_is_no_start(self) -> None:
        """Tarragona (Tarraco): Wikidata's P571 1165 at year precision is the town's medieval
        charter; the site is Roman and the Old World's E3 cutoff is 500 AD."""
        tarraco = {"lat": 41.12, "lon": 1.25, "country": "Spain", "period_start": -218,
                   "period_end": 476}  # fmt: skip
        found = inception(entity("Q15088", P571=[statement(time_value(1165))]), qid="Q15088",
                          **tarraco)  # fmt: skip
        assert found.value is None and found.reason == "inception-past-scope"
        assert "500 AD" in found.note
        # the same holds without a stored period end: the scope alone refuses it
        assert inception(p571(1192), period_end=None).reason == "inception-past-scope"
        # 500 AD itself is inside the window (passes_date_cutoff's `<=`)
        assert inception(p571(500), period_end=500).value == "500"

    def test_the_americas_and_oceania_run_to_1500(self) -> None:
        maya = {"lat": 17.2, "lon": -89.6, "country": "Guatemala", "period_end": 1200}
        assert inception(p571(900), **maya).value == "900"
        maori = {"lat": -36.9, "lon": 174.8, "country": "New Zealand", "period_end": 1450}
        assert inception(p571(1300), **maori).value == "1300"
        # the same year on an Old-World site is past its window
        assert inception(p571(900), period_end=1200).reason == "inception-past-scope"

    def test_a_year_the_period_wave_refused_is_no_start(self) -> None:
        refused = frozenset({(QID, -1500)})
        found = inception(p571(-1500), refused)
        assert found.value is None and found.reason == "inception-refused-by-period-wave"
        assert inception(p571(-1500), frozenset({("Q1", -1500), (QID, -1400)})).value == "-1500"

    def test_a_site_without_a_longitude_has_no_window(self) -> None:
        assert inception(p571(-1500), lon=None).reason == "inception-region-unknown"

    def test_a_year_after_the_band_of_the_stored_period_is_a_later_phase(self) -> None:
        # dated -900, the band "1500 - 500 BC": -500 is the next band's first year
        found = inception(p571(-500))
        assert found.value is None and found.reason == "inception-after-period"
        assert "'1500 - 500 BC'" in found.note
        assert inception(p571(-501)).value == "-501"

    def test_a_band_edge_period_admits_its_whole_band(self) -> None:
        """Pyramid of Amenemhat I: period_start -3000 is the edge of "3000 - 1500 BC"
        (`bucket_edge`), P571 -1990 lies inside that band."""
        edge = {"period_start": -3000, "period_end": None}
        assert inception(p571(-1990), **edge).value == "-1990"
        assert inception(p571(-1500), **edge).reason == "inception-after-period"

    def test_the_period_is_end_or_start(self) -> None:
        # `period_end or period_start`: a missing or 0 end falls through to the start (-1800,
        # the band "3000 - 1500 BC")
        assert inception(p571(-1600), period_end=0).value == "-1600"
        assert inception(p571(-1500), period_end=0).reason == "inception-after-period"
        assert inception(p571(-1500), period_end=None).reason == "inception-after-period"

    def test_the_readback_counts_every_inception_the_rule_refuses(self) -> None:
        sql = X.readback(X.ext_lane(WAVE, 1))
        assert "inception_year lies past the site''s E3 cutoff" in sql
        assert "inception_year lies after the band of the site''s period" in sql
        assert L.e3_cutoff_sql("u.") in sql and X._BAND_END in sql

    def test_the_band_end_in_sql_is_the_python_band_end(self) -> None:
        import sqlite3

        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE u (period_start INTEGER, period_end INTEGER)")
        rows = [(-6500, None), (-3000, None), (-1800, 0), (-1800, -900), (1, 300), (1000, 1700)]
        db.executemany("INSERT INTO u VALUES (?, ?)", rows)
        got = [r[0] for r in db.execute(f"SELECT {X._BAND_END} FROM u ORDER BY rowid")]
        assert got == [X.band_end(end or start) for start, end in rows]

    def test_the_band_end_is_the_bucket_table_s(self) -> None:
        assert [X.band_end(y) for y in (-6500, -4500, -1, 1, 499, 1000, 1700)] == [
            -4500, -3000, 1, 500, 500, 1500, 999999,
        ]  # fmt: skip

    def test_a_site_without_a_period_states_no_year(self) -> None:
        found = inception(p571(-1500), period_start=None, period_end=None)
        assert found.value is None and found.reason == "inception-without-period"

    def test_the_ids_give_the_qid_and_the_english_article(self) -> None:
        got = X.derive(live(enwiki_title="Heraclea (Lucania)"), full_entity(), LABELS, NONE_REFUSED)
        assert got["wikidata_qid"].value == QID
        assert got["best_wiki_url"].value == "https://en.wikipedia.org/wiki/Heraclea_(Lucania)"

    def test_without_a_qid_no_item_cell_is_derived(self) -> None:
        got = X.derive(
            live(qid=None, premise="<NULL>|Monte Lazzu"), full_entity(), LABELS, NONE_REFUSED
        )
        assert got["wikidata_qid"].reason == "no-qid"
        assert {got[c].reason for c in X.ITEM_COLUMNS} == {"no-qid"}
        assert got["best_wiki_url"].value is not None

    def test_an_item_missing_from_the_harvest_is_named(self) -> None:
        got = X.derive(live(), None, LABELS, NONE_REFUSED)
        assert {got[c].reason for c in X.ITEM_COLUMNS} == {"entity-not-harvested"}

    def test_a_merged_item_refuses_every_item_cell(self) -> None:
        got = X.derive(live(), {**full_entity(), "id": "Q1"}, LABELS, NONE_REFUSED)
        assert {got[c].reason for c in X.ITEM_COLUMNS} == {"qid-redirects"}
        assert got["wikidata_qid"].value == QID


# ------------------------------------------------------------------------------ a site
class TestClassify:
    def test_every_empty_cell_with_a_value_is_filled(self) -> None:
        verdicts = X.classify(
            SITE, live(), full_entity(), LABELS, NONE_REFUSED, entity_sha="s" * 64
        )
        assert cells(verdicts) == {
            "wikidata_qid": QID,
            "best_wiki_url": "https://en.wikipedia.org/wiki/Monte_Lazzu",
            "heritage_designation": "scheduled monument",
            "inception_year": "-1500",
            "commons_image": "Monte Lazzu.jpg",
        }
        assert all(v.premise == f"{QID}|Monte Lazzu" and v.old_value is None for v in verdicts)
        item = next(v for v in verdicts if v.column == "commons_image")
        assert "s" * 64 in item.evidence[0]["source"]

    def test_a_filled_cell_is_never_overwritten(self) -> None:
        stored = {**dict.fromkeys(X.COLUMNS), "commons_image": "Other.jpg", "wikidata_qid": QID}
        verdicts = X.classify(
            SITE, live(stored=stored), full_entity(), LABELS, NONE_REFUSED, entity_sha="s"
        )
        assert "commons_image" not in cells(verdicts) and "wikidata_qid" not in cells(verdicts)
        assert reasons(verdicts) == {"commons_image": "stored-differs"}

    def test_a_value_longer_than_its_column_is_refused(self) -> None:
        long = entity(P18=[statement("x" * 501 + ".jpg")])
        verdicts = X.classify(SITE, live(), long, LABELS, NONE_REFUSED, entity_sha="s")
        assert reasons(verdicts)["commons_image"] == "value-too-long"

    @pytest.mark.parametrize(
        ("over", "reason"),
        [
            ({"scope_status": "retired"}, "retired"),
            ({"has_card": False}, "no-card-stats-row"),
            ({"source_id": "lyra"}, "row-not-in-curated-source"),
        ],
    )
    def test_a_site_whose_card_is_not_this_lane_s_is_listed(self, over: dict, reason: str) -> None:
        verdicts = X.classify(
            SITE, live(**over), full_entity(), LABELS, NONE_REFUSED, entity_sha="s"
        )
        assert [(v.ok, v.column, v.reason) for v in verdicts] == [(False, None, reason)]

    def test_a_site_that_is_gone_is_listed(self) -> None:
        gone = X.classify(SITE, None, None, LABELS, NONE_REFUSED, entity_sha=None)
        assert gone[0].reason == "site-gone"

    def test_a_step_holds_at_most_a_hundred_sites(self) -> None:
        many = [f"00000000-0000-4000-8000-{n:012d}" for n in range(101)]
        with pytest.raises(PlanError, match="at most 100"):
            X.build_step(WAVE, 1, many, {}, {}, {}, LABELS, NONE_REFUSED, built_at="t")

    def test_the_counters_name_the_columns_and_the_reasons(self) -> None:
        built = X.build_step(
            WAVE,
            1,
            [SITE, OTHER],
            {SITE: live(), OTHER: live(site_id=OTHER, qid=None, enwiki_title=None)},
            {SITE: full_entity(), OTHER: None},
            {SITE: "s", OTHER: None},
            LABELS,
            NONE_REFUSED,
            built_at="t",
        )
        c = built.plan.counters
        assert c["cells"] == 5 and c["sites"] == 1 and c["cells:commons_image"] == 1
        assert c["skip:wikidata_qid:no-qid"] == 1 and c["skip:best_wiki_url:no-enwiki-title"] == 1


# ------------------------------------------------------------------------------ the steps
def tagged(rows: dict[str, list[dict[str, Any]]]) -> str:
    lines = [json.dumps({"kind": kind, "row": r}) for kind, items in rows.items() for r in items]
    lines.append(
        json.dumps({"kind": SNAPSHOT_KIND, "row": {"exported_at": "2026-10-25 10:00:00+00"}})
    )
    return "\n".join(lines) + "\n"


def site_row(site: str = SITE, **over: Any) -> dict[str, Any]:
    base = {"site_id": site, "name": "Monte Lazzu", "source_id": "ancient_nerds",
            "scope_status": None, "qid": QID, "enwiki_title": "Monte Lazzu", "has_card": True,
            **{f"stored_{c}": None for c in X.COLUMNS}, "premise": f"{QID}|Monte Lazzu",
            **PLACE}  # fmt: skip
    return {**base, **over}


def reader(candidates: list[dict[str, Any]], rows: list[dict[str, Any]] | None = None,
           journal: list[dict[str, Any]] | None = None):  # type: ignore[no-untyped-def]  # fmt: skip
    def read(script: str) -> str:
        if "AS qid FROM unified_sites u JOIN card_stats" in script:
            return tagged({"site": candidates})
        return tagged(
            {"site": rows if rows is not None else [site_row()], "journal": journal or []}
        )

    return read


class FakeNet:
    """`census.fetch.Fetcher.get_json`, answered from a dict of entities."""

    def __init__(self, entities: dict[str, dict[str, Any]]) -> None:
        self.entities, self.asked = entities, []

    def get_json(self, url: str, *, params: dict, ns: str, force: bool = False) -> dict:
        ids = params["ids"].split("|")
        self.asked.append((params.get("props"), ids))
        return {"json": {"entities": {q: self.entities[q] for q in ids}}}


@pytest.fixture
def harvest(tmp_path: Path) -> Path:
    root = tmp_path / "harvest"
    (root / H.ENTITIES).mkdir(parents=True)
    return root


#: Two records in `period_wave/structured_refused.json`'s form: a refused P571 and a refused P2348.
REFUSED_RECORDS = [
    {"site_id": SITE, "name": "Monte Lazzu", "qid": QID, "property": "P571", "year": -1500,
     "usable_as_period": False, "tier": "refused"},
    {"site_id": OTHER, "name": "Other", "qid": "Q2978", "property": "P2348", "year": 1245,
     "usable_as_period": False, "tier": "refused"},
    {"site_id": OTHER, "name": "Other", "qid": "Q3", "property": "P571", "year": 300,
     "usable_as_period": True, "tier": "structured"},
]  # fmt: skip


@pytest.fixture
def refused(tmp_path: Path) -> Path:
    path = tmp_path / "structured_refused.json"
    path.write_text(json.dumps(REFUSED_RECORDS[1:]), encoding="utf-8")
    return path


def put(harvest: Path, e: dict[str, Any], qid: str = QID) -> None:
    H.entity_path(harvest, qid).write_text(json.dumps(e), encoding="utf-8")


class TestTheFetchTheWaveAndTheSteps:
    def test_the_fetch_brings_the_missing_items_and_the_labels(
        self, tmp_path: Path, harvest: Path
    ) -> None:
        net = FakeNet(
            {
                QID: full_entity(),
                "Q219538": {"id": "Q219538", "labels": {"en": {"value": "scheduled monument"}}},
            }
        )
        result = X.fetch(WAVE, harvest, read=reader([{"site_id": SITE, "qid": QID}]),
                         net=net, root=tmp_path)  # type: ignore[arg-type]  # fmt: skip
        assert result["items"]["fetched"] == 1 and result["designations"] == 1
        assert H.entity_path(harvest, QID).exists()
        assert X.read_labels(WAVE, tmp_path) == {"Q219538": "scheduled monument"}
        assert net.asked[-1] == ("labels", ["Q219538"])

    def test_a_fetch_for_a_planned_wave_is_refused(self, tmp_path: Path, harvest: Path) -> None:
        """WAVE.json pins LABELS.json: a second fetch would rewrite it and void the wave's steps."""
        (tmp_path / WAVE).mkdir(parents=True)
        (tmp_path / WAVE / X.WAVE_FILE).write_text("{}", encoding="utf-8")
        (tmp_path / WAVE / X.LABELS_FILE).write_text('{"labels": {}}', encoding="utf-8")
        net = FakeNet({QID: full_entity()})
        with pytest.raises(PlanError, match="the wave pinned its labels and items"):
            X.fetch(WAVE, harvest, read=reader([{"site_id": SITE, "qid": QID}]),
                    net=net, root=tmp_path)  # type: ignore[arg-type]  # fmt: skip
        assert (tmp_path / WAVE / X.LABELS_FILE).read_text(encoding="utf-8") == '{"labels": {}}'
        assert net.asked == []

    def test_the_fetch_needs_a_harvest(self, tmp_path: Path) -> None:
        with pytest.raises(PlanError, match="no harvest's entity directory"):
            X.fetch(WAVE, tmp_path / "none", read=reader([]), net=FakeNet({}), root=tmp_path)  # type: ignore[arg-type]

    def labelled(self, root: Path) -> None:
        (root / WAVE).mkdir(parents=True, exist_ok=True)
        (root / WAVE / X.LABELS_FILE).write_text(json.dumps({"labels": LABELS}), encoding="utf-8")

    def test_a_wave_needs_its_labels_and_every_item(
        self, tmp_path: Path, harvest: Path, refused: Path
    ) -> None:
        candidates = [{"site_id": SITE, "qid": QID}]
        with pytest.raises(PlanError, match="LABELS.json is missing"):
            X.build_wave(WAVE, harvest, refused, read=reader(candidates), root=tmp_path)
        self.labelled(tmp_path)
        with pytest.raises(PlanError, match="are not in"):
            X.build_wave(WAVE, harvest, refused, read=reader(candidates), root=tmp_path)

    def test_the_wave_pins_the_items_and_the_labels_in_steps_of_100(
        self, tmp_path: Path, harvest: Path, refused: Path
    ) -> None:
        put(harvest, full_entity())
        self.labelled(tmp_path)
        sites = [f"00000000-0000-4000-8000-{n:012d}" for n in range(150)]
        candidates = [{"site_id": s, "qid": QID if s == sites[0] else None} for s in sites]
        assert X.build_wave(WAVE, harvest, refused, read=reader(candidates), root=tmp_path) == {
            "wave": WAVE,
            "sites": 150,
            "steps": 2,
        }
        record = X.read_wave(WAVE, tmp_path)
        assert record["entity_sha256"][sites[0]] == X.sha256_file(H.entity_path(harvest, QID))
        assert record["entity_sha256"][sites[1]] is None
        with pytest.raises(PlanError, match="planned once"):
            X.build_wave(WAVE, harvest, refused, read=reader(candidates), root=tmp_path)

    def plan(self, tmp_path: Path, harvest: Path, refused: Path) -> Path:
        put(harvest, full_entity())
        self.labelled(tmp_path)
        X.build_wave(
            WAVE, harvest, refused, read=reader([{"site_id": SITE, "qid": QID}]), root=tmp_path
        )
        X.plan_step(WAVE, 1, read=reader([]), root=tmp_path)
        return tmp_path / WAVE / "s001"

    def test_a_step_is_planned_from_a_fresh_read_and_renders(
        self, tmp_path: Path, harvest: Path, refused: Path
    ) -> None:
        out = self.plan(tmp_path, harvest, refused)
        lines = [
            json.loads(x) for x in (out / "PLAN.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert {r["column"] for r in lines} == set(X.COLUMNS)
        assert all(r["table"] == "card_stats" and r["old_value"] is None for r in lines)
        lane = X.ext_lane(WAVE, 1)
        records = A.load_records(out / "PLAN.jsonl")
        A.validate_records(records, lane=lane)
        sql = A.render_transaction(records, site_ids={SITE}, lane=lane)
        assert "'card_stats'" in sql and "scope guard 5" in sql
        assert lane.rollback_run_stamp in (out / "ROLLBACK.sql").read_text(encoding="utf-8")
        with pytest.raises(PlanError, match="exists"):
            X.plan_step(WAVE, 1, read=reader([]), root=tmp_path)

    def test_an_item_that_moved_since_the_wave_refuses_the_step(
        self, tmp_path: Path, harvest: Path, refused: Path
    ) -> None:
        put(harvest, full_entity())
        self.labelled(tmp_path)
        X.build_wave(
            WAVE, harvest, refused, read=reader([{"site_id": SITE, "qid": QID}]), root=tmp_path
        )
        put(harvest, entity(P18=[statement("New.jpg")]))
        with pytest.raises(PlanError, match="not the one wave 2026-10-25 pinned"):
            X.plan_step(WAVE, 1, read=reader([]), root=tmp_path)

    def test_labels_that_moved_since_the_wave_refuse_the_step(
        self, tmp_path: Path, harvest: Path, refused: Path
    ) -> None:
        put(harvest, full_entity())
        self.labelled(tmp_path)
        X.build_wave(
            WAVE, harvest, refused, read=reader([{"site_id": SITE, "qid": QID}]), root=tmp_path
        )
        (tmp_path / WAVE / X.LABELS_FILE).write_text(json.dumps({"labels": {}}), encoding="utf-8")
        with pytest.raises(PlanError, match="is not the file wave"):
            X.plan_step(WAVE, 1, read=reader([]), root=tmp_path)

    def test_the_refused_dates_are_the_period_wave_s_refused_p571s(self, tmp_path: Path) -> None:
        path = tmp_path / "refused.json"
        path.write_text(json.dumps(REFUSED_RECORDS), encoding="utf-8")
        assert X.read_refused(path) == frozenset({(QID, -1500)})

    def test_a_refused_dates_file_is_read_whole(self, tmp_path: Path) -> None:
        path = tmp_path / "refused.json"
        with pytest.raises(PlanError, match="is missing"):
            X.read_refused(path)
        path.write_text(json.dumps([{"qid": QID, "property": "P571"}]), encoding="utf-8")
        with pytest.raises(PlanError, match="record 0 lacks"):
            X.read_refused(path)
        path.write_text(json.dumps([]), encoding="utf-8")
        with pytest.raises(PlanError, match="non-empty list"):
            X.read_refused(path)

    def test_a_refused_p571_refuses_the_cell_in_the_step(
        self, tmp_path: Path, harvest: Path
    ) -> None:
        path = tmp_path / "refused.json"
        path.write_text(json.dumps(REFUSED_RECORDS), encoding="utf-8")
        out = self.plan(tmp_path, harvest, path)
        planned = {
            json.loads(x)["column"]
            for x in (out / "PLAN.jsonl").read_text(encoding="utf-8").splitlines()
        }
        assert planned == set(X.COLUMNS) - {"inception_year"}
        skipped = [json.loads(x) for x in (out / "SKIPPED.jsonl").read_text("utf-8").splitlines()]
        assert any(r["reason"] == "inception-refused-by-period-wave" for r in skipped)

    def test_a_refused_dates_file_that_moved_refuses_the_step(
        self, tmp_path: Path, harvest: Path, refused: Path
    ) -> None:
        put(harvest, full_entity())
        self.labelled(tmp_path)
        X.build_wave(WAVE, harvest, refused, read=reader([{"site_id": SITE, "qid": QID}]),
                     root=tmp_path)  # fmt: skip
        assert X.read_wave(WAVE, tmp_path)["refused_sha256"] == X.sha256_file(refused)
        refused.write_text(json.dumps(REFUSED_RECORDS), encoding="utf-8")
        with pytest.raises(PlanError, match="not the refused-dates file"):
            X.plan_step(WAVE, 1, read=reader([]), root=tmp_path)

    def test_the_default_refused_dates_are_the_main_checkout_s(self) -> None:
        from identity.common import main_checkout

        assert X.default_refused() == main_checkout() / X.REFUSED_PATH

    def test_a_step_waits_for_the_one_before_it(
        self, tmp_path: Path, harvest: Path, refused: Path
    ) -> None:
        self.labelled(tmp_path)
        sites = [{"site_id": f"00000000-0000-4000-8000-{n:012d}", "qid": None} for n in range(101)]
        X.build_wave(WAVE, harvest, refused, read=reader(sites), root=tmp_path)
        with pytest.raises(PlanError, match="step 1 is not accepted"):
            X.plan_step(WAVE, 2, read=reader([]), root=tmp_path)

    def test_the_acceptance_reads_production_back_and_records_it_once(
        self, tmp_path: Path, harvest: Path, refused: Path
    ) -> None:
        out = self.plan(tmp_path, harvest, refused)
        lane = X.ext_lane(WAVE, 1)
        plan = [
            json.loads(x) for x in (out / "PLAN.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        filled = site_row(**{f"stored_{r['column']}": r["new_value"] for r in plan})
        journal = [{"row_pk": SITE, "column_name": r["column"], "run_stamp": lane.run_stamp,
                    "old_value": None, "new_value": r["new_value"]} for r in plan]  # fmt: skip
        assert X.accept_step(WAVE, 1, read=reader([], [filled], journal), root=tmp_path) == (0, [])
        assert (out / X.ACCEPTED_FILE).exists()
        code, found = X.accept_step(WAVE, 1, read=reader([], [site_row()], journal), root=tmp_path)
        assert code == 1 and all("does not hold the planned value" in f for f in found)

    def test_the_acceptance_names_what_production_lacks(self) -> None:
        lane = X.ext_lane(WAVE, 1)
        planned = [{"site_id": SITE, "column": "wikidata_qid", "new_value": QID}]
        found = X.deviations(lane, planned, {SITE: live()}, [])
        assert any("0 journal row(s) for 1 planned" in f for f in found)
        assert any("journal row is not the plan's" in f for f in found)
        undone = [
            {"row_pk": SITE, "column_name": "wikidata_qid", "run_stamp": lane.rollback_run_stamp}
        ]
        assert any(
            "rollback journal row" in f for f in X.deviations(lane, planned, {SITE: live()}, undone)
        )


def test_the_cli_takes_each_command_s_own_arguments(tmp_path: Path) -> None:
    """`fetch` and `wave` take a harvest, `step` and `accept` a step, `wave` also `--refused`."""
    assert X.main(["fetch", "--wave", WAVE, "--harvest", str(tmp_path / "none")]) == 1
    wave = ["wave", "--wave", "2026-10-25x", "--harvest", str(tmp_path)]
    assert X.main([*wave, "--refused", str(tmp_path / "none.json")]) == 1
    for bad in (
        ["fetch", "--wave", WAVE, "--harvest", "h", "--step", "1"],
        ["step", "--wave", WAVE],
    ):
        with pytest.raises(SystemExit) as exc:
            X.main(bad)
        assert exc.value.code == 2
