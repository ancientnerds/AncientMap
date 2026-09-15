"""Increment 2: stories, the radar backlog and the legacy entities vein.

All pure logic — the DB-touching parts are exercised against prod by the
CLI runs; what is pinned here is the offset arithmetic and the decisions
that decide whether a name enters the queue at all.
"""

import inspect

from pipeline.lyra.prospector import extract_stories as es
from pipeline.lyra.prospector.corpus import StoryUnit, story_text
from pipeline.lyra.prospector.extract_radar import RadarUnit, mentions_for, prefill_for
from pipeline.lyra.prospector.mentions import GroundingStats, ground_mentions


def unit(i: int, text: str) -> StoryUnit:
    return StoryUnit(i, f"vid{i}", 120, text)


class TestStoryText:
    def test_joiner_is_a_single_newline_and_blank_parts_are_dropped(self):
        assert story_text("H", "", ["f1", "", "f2"]) == "H\nf1\nf2"

    def test_locator_carries_the_timestamp(self):
        assert unit(1, "x").locator == "https://www.youtube.com/watch?v=vid1&t=120s"
        assert StoryUnit(2, "v", None, "x").locator == "https://www.youtube.com/watch?v=v"


class TestBatching:
    def test_six_items_per_call(self):
        units = [unit(i, "short") for i in range(14)]
        sizes = [len(b) for b in es.batches(units)]
        assert sizes == [6, 6, 2]

    def test_window_char_cap_splits_early(self):
        units = [unit(i, "x" * 4000) for i in range(4)]
        assert [len(b) for b in es.batches(units)] == [2, 2]


class TestRemap:
    def test_offsets_map_back_into_the_owning_item(self):
        a = unit(1, "Digging at Tell Brak resumed.\nA second line.")
        b = unit(2, "Nothing here.\nExcept Göbekli Tepe in Turkey.")
        window = a.text + es.SEPARATOR + b.text
        starts = [0, len(a.text) + len(es.SEPARATOR)]
        stats = GroundingStats()
        grounded = ground_mentions(
            [
                {
                    "name_as_written": "Tell Brak",
                    "place_class": "site",
                    "country_as_written": "",
                    "period_as_written": "",
                },
                {
                    "name_as_written": "Göbekli Tepe",
                    "place_class": "site",
                    "country_as_written": "Turkey",
                    "period_as_written": "",
                },
            ],
            window,
            0,
            window,
            stats,
        )
        mapped = es.remap_to_units(grounded, [a, b], starts)
        assert [(u.item_id, m.name) for u, m in mapped] == [(1, "Tell Brak"), (2, "Göbekli Tepe")]
        for u, m in mapped:
            assert u.text[m.char_start : m.char_end] == m.name
            assert m.quote in u.text
            assert u.text[m.quote_start : m.quote_start + len(m.quote)] == m.quote
        assert mapped[1][1].country_in_text == "Turkey"


def radar_unit(**kw) -> RadarUnit:
    base = {
        "contribution_id": "c1",
        "name": "Ho-Bar Site",
        "status": "enriched",
        "wikidata_id": None,
        "lat": None,
        "lon": None,
        "country": None,
        "site_type": None,
        "period_start": None,
        "period_end": None,
        "description": None,
        "thumbnail_url": None,
        "wikipedia_url": None,
        "items": [],
    }
    base.update(kw)
    return RadarUnit(**base)


class TestRadarBacklog:
    def test_enriched_coordinates_become_a_prefilled_resolution(self):
        pre = prefill_for(
            radar_unit(lat=33.4, lon=-108.9, country="United States", wikidata_id="Q1")
        )
        assert pre.resolution is not None
        assert pre.resolution.path == "contribution"
        assert pre.resolution.verdict == "resolved"
        assert pre.resolution.has_point
        assert pre.contribution_id == "c1"
        assert pre.prior_verdict is None

    def test_without_coordinates_the_normal_resolver_runs(self):
        assert prefill_for(radar_unit()).resolution is None

    def test_llm_rejection_is_a_prior_verdict_not_a_hide(self):
        assert prefill_for(radar_unit(status="rejected")).prior_verdict == "llm_match_rejected"

    def test_medieval_contribution_is_out_of_scope_but_still_resolved(self):
        pre = prefill_for(radar_unit(lat=50.9, lon=6.95, period_start=1248))
        assert pre.resolution.in_scope is False

    def test_evidence_is_the_headline_with_the_name_located(self):
        u = radar_unit(items=[unit(7, "New dates for the Ho-Bar Site\nsummary\nfact")])
        ((m, ref),) = mentions_for(u)
        assert (m.char_start, m.char_end) == (18, 29)
        assert m.quote == "New dates for the Ho-Bar Site"
        assert ref.corpus == "radar" and ref.source_pk == "7"
        assert ref.locator.endswith("&t=120s")

    def test_contribution_without_items_still_has_a_source(self):
        ((m, ref),) = mentions_for(radar_unit())
        assert ref.source_table == "user_contributions" and ref.source_pk == "c1"


class TestOnePipeline:
    def test_every_corpus_goes_through_prepare_and_write(self):
        from pipeline.lyra import prospector

        for fn in (
            prospector.process_paper,
            prospector.run_stories,
            prospector.run_radar_backlog,
            prospector.run_entities_legacy,
        ):
            body = inspect.getsource(fn)
            assert "prepare(" in body and "write(session, prepared)" in body, fn.__name__

    def test_no_session_is_held_across_the_resolve_phase(self):
        """prepare() (network, minutes) must run OUTSIDE any `with get_session()`.

        Prod closes a connection idle in a transaction after 15 minutes; the
        first entities run died on the first dedup statement that way.
        """
        from pipeline.lyra import prospector

        for fn in (
            prospector.run_stories,
            prospector.run_radar_backlog,
            prospector.run_entities_legacy,
        ):
            lines = inspect.getsource(fn).splitlines()
            call = next(i for i, l in enumerate(lines) if "prepared = prepare(" in l)
            indent = len(lines[call]) - len(lines[call].lstrip())
            # Walk upwards: the nearest enclosing block opener must not be a session.
            for j in range(call - 1, -1, -1):
                line = lines[j]
                if line.strip() and (len(line) - len(line.lstrip())) < indent:
                    assert "get_session()" not in line, fn.__name__
                    break

    def test_stories_are_marked_read_even_without_mentions(self):
        from pipeline.lyra import prospector

        body = inspect.getsource(prospector.run_stories)
        assert "mark_prospected(session, [u.item_id for u in units])" in body
