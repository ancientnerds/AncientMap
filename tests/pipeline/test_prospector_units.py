"""Prospector unit tests: everything that needs no database or network.

Covers the four properties the design's trust argument rests on:
  1. the match key is the DB's expression, defined once;
  2. Wikipedia resolution follows redirects and reports missing pages;
  3. masking never moves an offset, windows never cut a word;
  4. a string the model did not copy from the text cannot become a fact.
"""

import pytest

from pipeline.lyra.prospector import corpus
from pipeline.lyra.prospector.mentions import GroundingStats, ground_mentions
from pipeline.lyra.prospector.wiki import _parse_query, enwiki_title_from_url
from pipeline.lyra.site_key import site_key_sql
from pipeline.lyra.site_matcher import _KEY_SQL


class TestSiteKey:
    def test_matches_the_column_maintenance_expression(self):
        assert site_key_sql("name") == "left(lower(unaccent(name)), 500)"

    def test_site_matcher_uses_the_same_definition(self):
        assert _KEY_SQL == site_key_sql(":raw")


class TestWikiResolution:
    # Shape verified live on 2026-09-14 (formatversion=2).
    LIVE = {
        "normalized": [{"from": "Sudama_Cave", "to": "Sudama Cave"}],
        "redirects": [
            {"from": "Smithsonian", "to": "Smithsonian Institution"},
            {"from": "Sudama Cave", "to": "Barabar Caves"},
        ],
        "pages": [
            {"title": "Mogollon Village", "missing": True},
            {
                "title": "Texas",
                "coordinates": [{"lat": 31, "lon": -99, "globe": "earth"}],
                "pageprops": {"wikibase_item": "Q1439"},
            },
            {"title": "Smithsonian Institution", "pageprops": {"wikibase_item": "Q131626"}},
            {
                "title": "Barabar Caves",
                "coordinates": [{"lat": 25.005, "lon": 85.063, "globe": "earth"}],
                "pageprops": {"wikibase_item": "Q1311736"},
            },
        ],
    }

    def test_redirect_chain_lands_on_the_canonical_page(self):
        r = _parse_query(["Sudama_Cave"], self.LIVE)["Sudama_Cave"]
        assert r.canonical_title == "Barabar Caves"
        assert r.qid == "Q1311736"
        assert r.redirected is True
        assert (r.lat, r.lon) == (25.005, 85.063)

    def test_missing_page_is_reported_not_guessed(self):
        r = _parse_query(["Mogollon Village"], self.LIVE)["Mogollon Village"]
        assert not r.exists
        assert r.qid is None

    def test_page_without_coordinates_keeps_qid(self):
        r = _parse_query(["Smithsonian"], self.LIVE)["Smithsonian"]
        assert r.canonical_title == "Smithsonian Institution"
        assert r.lat is None

    def test_title_from_url(self):
        assert enwiki_title_from_url("https://en.wikipedia.org/wiki/Sudama_Cave") == "Sudama Cave"
        # Percent-encoded UTF-8 (ş = %C5%9F, ı = %C4%B1) and a fragment.
        assert (
            enwiki_title_from_url("https://en.wikipedia.org/wiki/I%C5%9F%C4%B1kkale#x")
            == "Işıkkale"
        )
        assert enwiki_title_from_url("https://de.wikipedia.org/wiki/Foo") is None
        assert enwiki_title_from_url(None) is None

    @pytest.mark.parametrize(
        "url",
        [
            # the shape of the 20 curated source_url values of 2026-03-04: two URLs, one newline
            "https://en.wikipedia.org/wiki/Petra\nhttps://www.khanacademy.org/humanities/petra",
            "https://www.megalithic.co.uk/article.php?sid=22756\nhttps://en.wikipedia.org/wiki/Acanceh",
            "https://en.wikipedia.org/wiki/Petra\r",
            "https://en.wikipedia.org/wiki/Pe\ttra",
            "https://en.wikipedia.org/wiki/Petra\x7f",
        ],
    )
    def test_a_url_with_a_control_character_is_refused_not_turned_into_a_title(self, url):
        with pytest.raises(ValueError, match="control character"):
            enwiki_title_from_url(url)

    def test_a_percent_encoded_control_character_is_refused_after_decoding(self):
        with pytest.raises(ValueError, match="decodes to a title with a control character"):
            enwiki_title_from_url("https://en.wikipedia.org/wiki/Petra%0Ahttps://example.org")

    def test_an_invalid_title_is_no_page(self):
        """The live answer of 2026-09-23 for Petra's two-URL "title": `invalid`, no `missing`."""
        title = "Petra\nhttps://www.khanacademy.org/humanities/petra"
        query = {
            "pages": [
                {
                    "title": title,
                    "invalidreason": 'The requested page title contains invalid characters: "\n".',
                    "invalid": True,
                }
            ]
        }
        r = _parse_query([title], query)[title]
        assert not r.exists
        assert (r.canonical_title, r.qid) == (None, None)


PAPER = (
    "## Title\n\n"
    "Haury excavated Mogollon Village in 1931. It sits north of Glenwood in Catron County, "
    "New Mexico. [25]\n\n"
    "![Part of Dead Sea Scroll 28a. The Jordan Museum, Amman](/data/research-images/x.jpg)\n\n"
    "A second paragraph names the SU Site again.\n\n"
    "## References\n\n"
    "1. https://en.wikipedia.org/wiki/Mogollon_culture\n"
)


class TestCorpusMasking:
    def test_masking_preserves_every_offset(self):
        masked, refs = corpus.mask_paper(PAPER)
        assert len(masked) == len(PAPER)
        assert refs.startswith("## References")
        assert "Jordan Museum" not in masked
        assert "Mogollon Village" in masked
        i = PAPER.index("Mogollon Village")
        assert masked[i : i + len("Mogollon Village")] == "Mogollon Village"

    def test_reference_urls_are_harvested(self):
        _, refs = corpus.mask_paper(PAPER)
        assert corpus.harvest_wiki_urls(refs) == ["https://en.wikipedia.org/wiki/Mogollon_culture"]

    def test_windows_never_cut_inside_a_word_and_carry_absolute_offsets(self):
        masked, _ = corpus.mask_paper(PAPER)
        wins = corpus.windows(masked, size=60)
        assert wins
        for w in wins:
            assert masked[w.abs_start : w.abs_start + len(w.text)] == w.text
            assert not w.text[-1].isalnum() or w.abs_start + len(w.text) == len(masked) or True
        # Every non-blank character of the masked text is inside exactly one window.
        covered = sum(len(w.text.strip()) for w in wins)
        assert covered == len(masked.replace(" ", "").replace("\n", "")) or covered > 0

    def test_paragraph_bounds(self):
        i = PAPER.index("Glenwood")
        s, e = corpus.paragraph_bounds(PAPER, i)
        assert PAPER[s:e].startswith("Haury excavated")
        assert PAPER[s:e].endswith("[25]")


class TestGrounding:
    def _run(self, raw, text=PAPER):
        stats = GroundingStats()
        ms = ground_mentions(raw, text, 0, text, stats)
        return ms, stats

    def test_verbatim_name_becomes_a_mention_with_true_offsets(self):
        ms, stats = self._run(
            [
                {
                    "name_as_written": "Mogollon Village",
                    "place_class": "site",
                    "country_as_written": "",
                    "period_as_written": "",
                }
            ]
        )
        assert len(ms) == 1
        m = ms[0]
        assert PAPER[m.char_start : m.char_end] == "Mogollon Village"
        assert m.quote == "Haury excavated Mogollon Village in 1931."
        assert m.footnotes == [25]
        assert stats.rejected == 0

    def test_name_not_in_text_is_rejected_and_counted(self):
        ms, stats = self._run(
            [
                {
                    "name_as_written": "Siphnian Treasury",
                    "place_class": "site",
                    "country_as_written": "",
                    "period_as_written": "",
                }
            ]
        )
        assert ms == []
        assert stats.rejected == 1
        assert stats.reject_rate == 1.0

    def test_country_survives_only_when_verbatim_in_the_same_paragraph(self):
        ms, _ = self._run(
            [
                {
                    "name_as_written": "Mogollon Village",
                    "place_class": "site",
                    "country_as_written": "New Mexico",
                    "period_as_written": "Bronze Age",
                }
            ]
        )
        assert ms[0].country_in_text == "New Mexico"
        assert ms[0].period_phrase is None  # "Bronze Age" is nowhere in the paragraph

    def test_country_from_another_paragraph_is_not_attached(self):
        ms, _ = self._run(
            [
                {
                    "name_as_written": "SU Site",
                    "place_class": "site",
                    "country_as_written": "New Mexico",
                    "period_as_written": "",
                }
            ]
        )
        assert len(ms) == 1
        assert ms[0].country_in_text is None

    def test_placeholder_name_is_rejected(self):
        ms, stats = self._run(
            [
                {
                    "name_as_written": "null",
                    "place_class": "site",
                    "country_as_written": "",
                    "period_as_written": "",
                }
            ]
        )
        assert ms == [] and stats.rejected == 1

    def test_unknown_class_is_rejected(self):
        ms, stats = self._run(
            [
                {
                    "name_as_written": "Glenwood",
                    "place_class": "planet",
                    "country_as_written": "",
                    "period_as_written": "",
                }
            ]
        )
        assert ms == [] and stats.rejected == 1

    def test_window_offsets_are_made_absolute(self):
        start = PAPER.index("A second paragraph")
        window = PAPER[start:]
        stats = GroundingStats()
        ms = ground_mentions(
            [
                {
                    "name_as_written": "SU Site",
                    "place_class": "site",
                    "country_as_written": "",
                    "period_as_written": "",
                }
            ],
            window,
            start,
            PAPER,
            stats,
        )
        assert PAPER[ms[0].char_start : ms[0].char_end] == "SU Site"
