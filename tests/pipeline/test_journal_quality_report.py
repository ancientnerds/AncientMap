"""Regressions from the 2026-09-14 journal (article 75).

Four defects, all visible in the published article and its quality report:

* cluster names rendered as 30-char heartbeat step keys
* paragraphs cited only with [VN] scored as uncited, dragging the judge's
  double-weighted D1 dimension down on correctly attributed prose
* the claim stripper amputated a sentence at the period in "Kevin C. Nolan"
* a screenshot shipped for a cluster that produced no prose, and filler words
  let screenshots match unrelated paragraphs
"""

from pipeline.lyra.article_generator import _build_research_scores, _inject_screenshots
from pipeline.lyra.research_stages import _strip_unsupported_claims
from pipeline.lyra.theo_citations import CitationRegistry, audit_citations


class TestResearchScoreLabels:
    def test_full_headline_is_used_as_the_cluster_name(self):
        step_data = {
            "research_Barabar Caves feature unique t": {
                "label": "Barabar Caves feature unique trapezoidal architecture",
                "score": 66,
                "count": 8,
                "elapsed": 349.1,
                "status": "partial",
            }
        }
        scores = _build_research_scores(step_data)
        assert list(scores) == ["Barabar Caves feature unique trapezoidal architecture"]
        assert scores["Barabar Caves feature unique trapezoidal architecture"] == {
            "score": 66,
            "sources": 8,
            "elapsed": 349.1,
            "status": "partial",
        }

    def test_falls_back_to_the_step_key_when_no_label_was_recorded(self):
        scores = _build_research_scores({"research_Old run without a label": {"score": 70}})
        assert list(scores) == ["Old run without a label"]

    def test_non_research_steps_are_ignored(self):
        assert _build_research_scores({"polish": {"score": 1}, "assemble": {}}) == {}


class TestVideoCitationsCountAsCitations:
    def _registry(self):
        registry = CitationRegistry()
        sid = registry.register_source(url="https://example.org/a", title="A", snippet="s")
        registry.assign_reference_number(sid)
        return registry

    def test_paragraph_cited_only_by_a_video_marker_is_not_uncited(self):
        paper = (
            "# Report\n\n"
            "The preservation of the skeleton and its grave goods is uncommon in "
            "northern Scotland, where acidic soils typically destroy bone [V2].\n\n"
            "A second finding is documented in the record [1].\n"
        )
        result = audit_citations(paper, self._registry())
        assert result["uncited_paragraphs"] == 0

    def test_paragraph_without_any_marker_is_still_uncited(self):
        paper = (
            "# Report\n\n"
            "The lower walls were bonded with a viscous clay that may have been "
            "designed to hold liquid across the whole structure.\n\n"
            "A second finding is documented in the record [1].\n"
        )
        result = audit_citations(paper, self._registry())
        assert result["uncited_paragraphs"] == 1

    def test_video_marker_is_not_reported_as_a_debug_token(self):
        paper = "# Report\n\nThe tomb was entered by divers [V3] and recorded [1].\n"
        result = audit_citations(paper, self._registry())
        assert result["non_numeric_markers"] == []

    def test_real_debug_tokens_are_still_reported(self):
        paper = "# Report\n\nThe tomb was entered by divers [N1] and recorded [1].\n"
        result = audit_citations(paper, self._registry())
        assert "N1" in result["non_numeric_markers"]


class TestStripUnsupportedClaims:
    def test_initial_in_a_name_does_not_amputate_the_sentence(self):
        prose = (
            "A landmark 2023 study by Mark F. Seeman (Kent State) and Kevin C. Nolan "
            "(Ball State) has redrawn Ohio Hopewell chronology. "
            "Peak construction occurred approximately 2,000 years ago."
        )
        problems = [{"claim": "Peak construction occurred approximately 2,000 years ago"}]
        out, removed = _strip_unsupported_claims(prose, problems)

        assert removed == 1
        assert out == (
            "A landmark 2023 study by Mark F. Seeman (Kent State) and Kevin C. Nolan "
            "(Ball State) has redrawn Ohio Hopewell chronology."
        )

    def test_claim_spanning_an_initial_removes_the_whole_sentence(self):
        prose = (
            "A landmark 2023 study by Mark F. Seeman (Kent State) and Kevin C. Nolan "
            "(Ball State) has redrawn Ohio Hopewell chronology. "
            "The dates came from six sites."
        )
        problems = [{"claim": "Nolan (Ball State) has redrawn Ohio Hopewell chronology"}]
        out, removed = _strip_unsupported_claims(prose, problems)

        assert removed == 1
        # The surviving text is a whole sentence, not the head of a cut one.
        assert out == "The dates came from six sites."
        assert "Kevin C.," not in out

    def test_reports_how_many_claims_actually_matched(self):
        prose = "The wall is built of granite. The roof has collapsed."
        problems = [
            {"claim": "The wall is built of granite"},
            {"claim": "a claim the judge invented that appears nowhere"},
        ]
        out, removed = _strip_unsupported_claims(prose, problems)
        assert removed == 1
        assert out == "The roof has collapsed."

    def test_paragraph_structure_is_preserved(self):
        prose = "First para sentence one. Bad claim here.\n\nSecond para stays intact."
        out, removed = _strip_unsupported_claims(prose, [{"claim": "Bad claim here"}])
        assert removed == 1
        assert out == "First para sentence one.\n\nSecond para stays intact."

    def test_no_problems_is_a_noop(self):
        prose = "Nothing to remove here."
        assert _strip_unsupported_claims(prose, []) == (prose, 0)


class TestScreenshotInjection:
    def test_screenshot_is_placed_under_its_own_paragraph(self):
        body = (
            "Archaeologists announced the discovery of a previously unknown fourth "
            "talayot at the Son Fornes archaeological site in Montuiri, Mallorca, "
            "bringing the total number of known monuments at the site to four."
        )
        items = [
            {
                "headline": "Fourth talayot discovered at Son Fornes site in Mallorca",
                "screenshot_url": "/data/talayot.webp",
            }
        ]
        assert (
            "![Fourth talayot discovered at Son Fornes site in Mallorca](/data/talayot.webp)"
            in (_inject_screenshots(body, items))
        )

    def test_filler_words_alone_do_not_place_a_screenshot(self):
        # Shares only "from", "with" and "made" with the headline - all filler.
        body = (
            "The lower walls were bonded with a viscous clay that may have been made "
            "to hold liquid, yet the steep staircase and narrow entrance argue against "
            "a simple storage function from any period."
        )
        items = [
            {
                "headline": "Dacite sarcophagus in Osiris Shaft made from volcanic rock "
                "with no African source",
                "screenshot_url": "/data/osiris.webp",
            }
        ]
        assert _inject_screenshots(body, items) == body

    def test_item_without_prose_contributes_no_screenshot(self):
        # generate_weekly_article now passes only clusters that produced prose,
        # so an empty item list must leave the body untouched.
        body = "A paragraph long enough to be a candidate for a screenshot insertion point."
        assert _inject_screenshots(body, []) == body
