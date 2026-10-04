# SPDX-License-Identifier: AGPL-3.0-only
"""The optional result_json keys of a Claude-written paper, validated for the page.

Studio spec 2026-09-26 §2.7/§3.7: evidence[], videos[], corrections[] and writer
sit next to the report. The paper page, the public API and the publish gate read
them through these parsers, so a malformed value fails loudly in one place
instead of rendering half a disclosure or a dead anchor. A paper without the
keys (all 31 papers published before the studio) parses to "nothing to add".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pipeline.research_html_renderer import (
    PAPER_EXTRAS_COLUMNS,
    PaperExtras,
    PaperPageError,
    VideoMoment,
    evidence_video_moments,
    format_references_md,
    page_extras_payload,
    paper_extras,
    paper_markdown,
    parse_corrections,
    parse_evidence,
    parse_videos,
    parse_writer,
    strip_leading_title_heading,
)

WRITER = {
    "model": "claude-opus-5-5",
    "tool": "claude-code",
    "research_model": "MiniMax-M3",
    "published": "automatic",
    "human_review": False,
}
# The request id as PAPER_SUMMARY_COLUMNS selects it (r.id::text). A video's
# poster is our own studio thumbnail at exactly this path (owner decision #13,
# spec §2.7: theo_publishing.poster_web_path).
REQ = "7f00aa00-0000-4000-8000-000000000000"
POSTER = f"/data/research-images/{REQ}/video_dQw4w9WgXcQ.jpg"


def _evidence(ev_id: str = "ev-01", **overrides) -> dict:
    entry = {
        "id": ev_id,
        "anchor_text": "The stone weighs about 1,000 tonnes",
        "claim": "The Stone of the Pregnant Woman weighs about 1,000 t.",
        "source_ids": ["S12"],
        "quote": "about 1,000 tonnes",
        "quote_source_id": "S12",
        "verdict": "supported",
    }
    entry.update(overrides)
    return entry


def _video(**overrides) -> dict:
    video = {
        "youtube_id": "dQw4w9WgXcQ",
        "title": "Baalbek: the 1,000-tonne question",
        "published_at": "2026-10-01T15:00:00+00:00",
        "evidence_timestamps": {"ev-01": 312},
    }
    video.update(overrides)
    return video


def _row(**overrides) -> SimpleNamespace:
    row = {"id": REQ, "evidence": None, "videos": None, "corrections": None, "writer": None}
    row.update(overrides)
    return SimpleNamespace(**row)


class TestPaperMarkdown:
    def test_is_the_title_strip_followed_by_the_reference_reflow(self):
        report = (
            "# Baalbek\n\n## Findings\n\nText [1].\n\n## References\n\n[1] A. https://a.org\n[2] B."
        )
        assert paper_markdown(report, "Baalbek") == format_references_md(
            strip_leading_title_heading(report, "Baalbek")
        )
        assert not paper_markdown(report, "Baalbek").startswith("# Baalbek")


class TestExtrasColumns:
    def test_selects_the_four_keys_as_jsonb(self):
        for key in ("evidence", "videos", "corrections", "writer"):
            assert f"r.result_json::jsonb->'{key}' AS {key}" in PAPER_EXTRAS_COLUMNS


class TestParseEvidence:
    def test_absent_key_means_no_evidence(self):
        assert parse_evidence(None) == []

    def test_keeps_id_anchor_and_claim(self):
        assert parse_evidence([_evidence()]) == [
            {
                "id": "ev-01",
                "anchor_text": "The stone weighs about 1,000 tonnes",
                "claim": "The Stone of the Pregnant Woman weighs about 1,000 t.",
            }
        ]

    # "ev-\u0661\u0662" is ev- plus Arabic-Indic digits: EVIDENCE_ID_RE is ASCII-only
    # (ev-[0-9]{2,}), like the page's PAPER_HASH_RE, so the page never injects
    # an id that the deep-link handler cannot match.
    @pytest.mark.parametrize(
        "bad_id", ["ev-1", "ev-01a", "EV-01", "evidence-01", "ev-\u0661\u0662", 3, None]
    )
    def test_rejects_ids_that_are_not_ev_nn(self, bad_id):
        with pytest.raises(PaperPageError, match="ev-NN"):
            parse_evidence([_evidence(bad_id)])

    def test_rejects_a_duplicate_id(self):
        with pytest.raises(PaperPageError, match="ev-01 appears twice"):
            parse_evidence([_evidence(), _evidence()])

    def test_rejects_an_empty_anchor_text(self):
        with pytest.raises(PaperPageError, match="ev-01.anchor_text"):
            parse_evidence([_evidence(anchor_text="  ")])

    def test_rejects_a_value_that_is_not_a_list_of_objects(self):
        with pytest.raises(PaperPageError, match="result_json.evidence"):
            parse_evidence({"id": "ev-01"})


class TestParseCorrections:
    def test_a_current_evidence_id_is_a_link_not_an_anchor(self):
        got = parse_corrections(
            [{"date": "2026-10-02", "text": "Quarry date re-sourced.", "evidence_id": "ev-01"}],
            {"ev-01"},
        )
        assert got == [
            {
                "date": "2026-10-02",
                "text": "Quarry date re-sourced.",
                "evidence_id": "ev-01",
                "holds_anchor": False,
            }
        ]

    def test_a_retired_id_is_held_by_the_correction_that_retired_it(self):
        # The publish gate lets an entry name an id while it is current
        # ("concerns this paragraph") and never once it is retired, so the
        # retiring entry is the last one naming it.
        got = parse_corrections(
            [
                {"date": "2026-10-02", "text": "Wording fixed.", "evidence_id": "ev-05"},
                {"date": "2026-10-04", "text": "Claim removed.", "evidence_id": "ev-05"},
            ],
            {"ev-01"},
        )
        assert [c["holds_anchor"] for c in got] == [False, True]

    def test_evidence_id_may_be_absent(self):
        got = parse_corrections([{"date": "2026-10-02", "text": "Typo in a date."}], set())
        assert got[0]["evidence_id"] is None
        assert got[0]["holds_anchor"] is False

    @pytest.mark.parametrize("day", ["2026-10-2", "02.10.2026", "2026-10-02T10:00:00", None])
    def test_rejects_a_date_that_is_not_yyyy_mm_dd(self, day):
        with pytest.raises(PaperPageError, match="YYYY-MM-DD"):
            parse_corrections([{"date": day, "text": "x"}], set())

    def test_rejects_an_impossible_day(self):
        with pytest.raises(PaperPageError, match="not a calendar day"):
            parse_corrections([{"date": "2026-02-30", "text": "x"}], set())

    def test_rejects_a_malformed_evidence_id(self):
        with pytest.raises(PaperPageError, match="evidence_id must look like ev-NN"):
            parse_corrections([{"date": "2026-10-02", "text": "x", "evidence_id": "5"}], set())

    def test_rejects_an_empty_text(self):
        with pytest.raises(PaperPageError, match=r"corrections\[0\].text"):
            parse_corrections([{"date": "2026-10-02", "text": ""}], set())


class TestParseVideos:
    def test_keeps_the_fields_the_page_and_api_need(self):
        got = parse_videos([_video()], {"ev-01"}, REQ)
        assert got == [
            {
                "youtube_id": "dQw4w9WgXcQ",
                "title": "Baalbek: the 1,000-tonne question",
                "published_at": "2026-10-01T15:00:00+00:00",
                "evidence_timestamps": {"ev-01": 312},
                # Registered without a poster: a valid state, the page then
                # shows the posterless player (owner decision #13).
                "poster": None,
            }
        ]

    def test_keeps_our_own_poster(self):
        got = parse_videos([_video(poster=POSTER)], {"ev-01"}, REQ)
        assert got[0]["poster"] == POSTER

    @pytest.mark.parametrize(
        "poster",
        [
            "/data/research-images/99999999-8888-7777-6666-555555555555/video_dQw4w9WgXcQ.jpg",
            f"/data/research-images/{REQ}/video_aaaaaaaaaaa.jpg",
            f"/data/research-images/{REQ}/thumbnail_1.jpg",
            f"/data/research-images/{REQ}/video_dQw4w9WgXcQ.png",
            f"https://ancientnerds.com/data/research-images/{REQ}/video_dQw4w9WgXcQ.jpg",
            "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            "",
            None,
        ],
    )
    def test_rejects_any_poster_but_the_video_path(self, poster):
        with pytest.raises(PaperPageError, match=r"videos\[0\]\.poster must be " + POSTER):
            parse_videos([_video(poster=poster)], {"ev-01"}, REQ)

    @pytest.mark.parametrize("youtube_id", ["dQw4w9WgXc", "dQw4w9WgXcQQ", "dQw4w9WgX<Q", None])
    def test_rejects_a_malformed_youtube_id(self, youtube_id):
        with pytest.raises(PaperPageError, match="youtube_id"):
            parse_videos([_video(youtube_id=youtube_id)], {"ev-01"}, REQ)

    def test_rejects_a_timestamp_for_an_unknown_evidence_id(self):
        with pytest.raises(PaperPageError, match="neither an evidence id nor retired"):
            parse_videos([_video(evidence_timestamps={"ev-09": 10})], {"ev-01"}, REQ)

    @pytest.mark.parametrize("seconds", [-1, 1.5, "312", True])
    def test_rejects_a_timestamp_that_is_not_whole_seconds(self, seconds):
        with pytest.raises(PaperPageError, match="whole seconds"):
            parse_videos([_video(evidence_timestamps={"ev-01": seconds})], {"ev-01"}, REQ)

    def test_rejects_a_published_at_that_is_not_iso(self):
        with pytest.raises(PaperPageError, match="ISO 8601"):
            parse_videos([_video(published_at="1 Oct 2026")], {"ev-01"}, REQ)

    def test_rejects_missing_evidence_timestamps(self):
        video = _video()
        del video["evidence_timestamps"]
        with pytest.raises(PaperPageError, match="evidence_timestamps"):
            parse_videos([video], {"ev-01"}, REQ)


class TestParseWriter:
    def test_absent_key_means_an_older_paper(self):
        assert parse_writer(None) is None

    def test_keeps_exactly_the_five_disclosure_fields(self):
        assert parse_writer({**WRITER, "brief_version": 3}) == WRITER

    def test_rejects_an_unknown_publication_mode(self):
        with pytest.raises(PaperPageError, match="writer.published"):
            parse_writer({**WRITER, "published": "auto"})

    def test_rejects_a_human_review_that_is_not_a_boolean(self):
        with pytest.raises(PaperPageError, match="human_review"):
            parse_writer({**WRITER, "human_review": "no"})

    def test_rejects_a_missing_model(self):
        with pytest.raises(PaperPageError, match="writer.model"):
            parse_writer({k: v for k, v in WRITER.items() if k != "model"})

    def test_the_publication_modes_are_the_publish_gates_one_definition(self, monkeypatch):
        """The page knows exactly the modes theo_publishing.check_writer lets through."""
        from pipeline.lyra import theo_publishing

        monkeypatch.setattr(theo_publishing, "WRITER_PUBLISHED", ("automatic", "manual", "x"))
        assert parse_writer({**WRITER, "published": "x"})["published"] == "x"


class TestPaperExtras:
    def test_an_older_paper_has_nothing_to_add(self):
        assert paper_extras(_row()) == PaperExtras([], [], [], None)

    def test_a_video_may_keep_the_timestamp_of_a_retired_id(self):
        extras = paper_extras(
            _row(
                evidence=[_evidence("ev-01")],
                corrections=[{"date": "2026-10-04", "text": "Removed.", "evidence_id": "ev-05"}],
                videos=[_video(evidence_timestamps={"ev-01": 312, "ev-05": 400})],
            )
        )
        assert extras.corrections[0]["holds_anchor"] is True
        assert extras.videos[0]["evidence_timestamps"] == {"ev-01": 312, "ev-05": 400}

    def test_a_video_timing_an_id_nobody_knows_fails(self):
        with pytest.raises(PaperPageError, match="ev-05"):
            paper_extras(
                _row(
                    evidence=[_evidence("ev-01")],
                    videos=[_video(evidence_timestamps={"ev-05": 400})],
                )
            )

    def test_the_poster_path_is_the_rows_own_request_id(self):
        row = _row(evidence=[_evidence()], videos=[_video(poster=POSTER)])
        assert paper_extras(row).videos[0]["poster"] == POSTER
        other = "99999999-8888-7777-6666-555555555555"
        with pytest.raises(PaperPageError, match=r"videos\[0\]\.poster"):
            paper_extras(_row(id=other, evidence=[_evidence()], videos=[_video(poster=POSTER)]))


class TestEvidenceVideoMoments:
    def test_links_only_current_evidence_in_video_order(self):
        extras = paper_extras(
            _row(
                evidence=[_evidence("ev-01"), _evidence("ev-02", anchor_text="Other text")],
                corrections=[{"date": "2026-10-04", "text": "Removed.", "evidence_id": "ev-05"}],
                videos=[
                    _video(evidence_timestamps={"ev-01": 312, "ev-05": 400}),
                    _video(
                        youtube_id="aaaaaaaaaaa",
                        title="Short",
                        evidence_timestamps={"ev-01": 20, "ev-02": 45},
                    ),
                ],
            )
        )
        assert evidence_video_moments(extras) == {
            "ev-01": [
                VideoMoment("dQw4w9WgXcQ", 312, "Baalbek: the 1,000-tonne question"),
                VideoMoment("aaaaaaaaaaa", 20, "Short"),
            ],
            "ev-02": [VideoMoment("aaaaaaaaaaa", 45, "Short")],
        }


class TestPageExtrasPayload:
    def test_an_older_paper_adds_no_key(self):
        assert page_extras_payload(PaperExtras([], [], [], None)) == {}

    def test_each_key_appears_only_when_present(self):
        only_writer = page_extras_payload(PaperExtras([], [], [], dict(WRITER)))
        assert only_writer == {"writer": WRITER}

    def test_the_video_payload_carries_no_timestamps(self):
        extras = paper_extras(_row(evidence=[_evidence()], videos=[_video()]))
        assert page_extras_payload(extras) == {
            "videos": [
                {
                    "youtube_id": "dQw4w9WgXcQ",
                    "title": "Baalbek: the 1,000-tonne question",
                    "published_at": "2026-10-01T15:00:00+00:00",
                    "poster": None,
                }
            ]
        }

    def test_the_video_payload_carries_our_poster(self):
        extras = paper_extras(_row(evidence=[_evidence()], videos=[_video(poster=POSTER)]))
        assert page_extras_payload(extras)["videos"][0]["poster"] == POSTER
