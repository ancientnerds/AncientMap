"""Does T06 have teeth?

A check that reports nothing is indistinguishable from a check that is broken, so each test
feeds a synthetic row carrying the defect T06 exists to find and asserts that it fires - and,
just as important, feeds the *accepted* shapes (`/data/images/wiki/<id8>/…` paths, fragments
inside a page URL, an already-https URL) and asserts silence.

Offline by construction: the tests build the only thing `run()` reads, `ctx.snap.rows(table)`,
out of plain dicts. No snapshot, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from census import model as M  # noqa: E402

SITE = "d953e9b3-de33-4c7d-9357-bbc5d94d2a16"
OTHER_SITE = "0000aa11-2222-3333-4444-555566667777"


def _ctx(rows: dict[str, list[dict[str, Any]]]) -> SimpleNamespace:
    """The only part of Context T06 reads: `snap.rows(table)`."""
    return SimpleNamespace(
        sites=[],
        snap=SimpleNamespace(rows=lambda table: rows.get(table, []), by=lambda *a, **k: {}),
    )


def _sites(**over: Any) -> dict[str, list[dict[str, Any]]]:
    """A snapshot holding one unified_sites row with an intact source_url."""
    row = {"id": SITE, "source_id": "ancient_nerds", "source_url": "https://example.org/reference"}
    row.update(over)
    return {"unified_sites": [row]}


#: an image row that is intact: correct md5 directories, own Commons file page
VALID_ORIGINAL = "https://upload.wikimedia.org/wikipedia/commons/8/80/Cornish_midsummer_bonfire.jpg"
VALID_PAGE = "https://commons.wikimedia.org/wiki/File%3ACornish_midsummer_bonfire.jpg"


def _image(**over: Any) -> dict[str, list[dict[str, Any]]]:
    """A snapshot holding one intact wiki_images row, with `over` applied."""
    row = {
        "site_id": SITE,
        "source_type": "wikimedia",
        "original_url": VALID_ORIGINAL,
        "commons_page_url": VALID_PAGE,
    }
    row.update(over)
    return {"wiki_images": [row]}


@pytest.fixture(scope="module")
def t06() -> Any:
    import importlib

    return importlib.import_module("census.tests.t06_url_shape")


def _one(t06: Any, rows: dict[str, list[dict[str, Any]]]) -> M.Finding:
    got = t06.run(_ctx(rows))
    assert len(got) == 1, f"expected exactly one finding, got {got}"
    return got[0]


def _none(t06: Any, rows: dict[str, list[dict[str, Any]]]) -> None:
    got = t06.run(_ctx(rows))
    assert got == [], f"expected no finding, got {[(f.test_id, f.current_value) for f in got]}"


# --------------------------------------------------------------- presence


class TestPresence:
    """An empty value is a defect only where a consumer needs the field."""

    def test_missing_source_url_is_reviewed_not_guessed(self, t06):
        f = _one(t06, _sites(source_url=""))
        assert f.test_id == "T06/empty"
        assert f.field == "unified_sites.source_url"
        assert (f.proposal, f.confidence) == (M.Proposal.REVIEW, M.Confidence.UNVERIFIABLE)
        assert f.proposed_value is None, "REVIEW must not carry a value"
        assert f.severity is M.Severity.MODERATE

    def test_missing_optional_thumbnail_is_not_a_shape_defect(self, t06):
        _none(t06, _sites(thumbnail_url=""))

    def test_never_populated_columns_are_not_reported(self, t06):
        """card_stats/site_content_links.thumbnail_url are NULL everywhere - Phase 2, not T06."""
        _none(t06, {"card_stats": [{"site_id": SITE, "best_wiki_url": None, "commons_image": ""}]})
        _none(
            t06,
            {
                "site_content_links": [
                    {
                        "site_id": SITE,
                        "content_url": "https://example.org/ref",
                        "thumbnail_url": None,
                    }
                ]
            },
        )

    def test_missing_commons_page_for_a_remote_original_is_set(self, t06):
        f = _one(
            t06,
            {
                "wiki_images": [
                    {
                        "site_id": SITE,
                        "commons_page_url": None,
                        "source_type": "wikimedia",
                        "original_url": VALID_ORIGINAL,
                    }
                ]
            },
        )
        assert f.test_id == "T06/empty"
        assert f.proposal is M.Proposal.SET
        assert f.confidence is M.Confidence.AUTHORITATIVE
        assert (
            f.proposed_value
            == "https://commons.wikimedia.org/wiki/File%3ACornish_midsummer_bonfire.jpg"
        )

    def test_missing_commons_page_for_a_disk_original_is_not_decidable(self, t06):
        """The reindexed rows kept only a .webp path - the Commons filename is gone."""
        _none(
            t06,
            {
                "wiki_images": [
                    {
                        "site_id": SITE,
                        "commons_page_url": "",
                        "source_type": "manual",
                        "original_url": f"/data/images/wiki/{SITE[:8]}/hero.webp",
                    }
                ]
            },
        )


# --------------------------------------------------------------- scheme


class TestScheme:
    def test_missing_scheme_without_host_evidence_is_proposed_weakly(self, t06):
        f = _one(t06, _sites(source_url="www.historyhit.com/locations/dougga/"))
        assert f.test_id == "T06/missing-scheme"
        assert f.proposal is M.Proposal.SET
        assert f.confidence is M.Confidence.WEAK, "no stored URL corroborates the host"
        assert f.proposed_value == "https://www.historyhit.com/locations/dougga/"
        assert not f.applicable

    def test_missing_scheme_with_host_evidence_is_authoritative(self, t06):
        rows = _sites(source_url="example.org/place")
        rows["wiki_images"] = [
            dict(_image()["wiki_images"][0], license_url="https://example.org/licence")
        ]
        f = _one(t06, rows)
        assert (f.test_id, f.confidence) == ("T06/missing-scheme", M.Confidence.AUTHORITATIVE)
        assert f.proposed_value == "https://example.org/place"
        assert f.applicable

    def test_http_upgrade_needs_an_https_url_for_the_same_host(self, t06):
        rows = _sites(source_url="http://example.org/place")
        rows["wiki_images"] = [
            dict(_image()["wiki_images"][0], license_url="https://example.org/licence")
        ]
        f = _one(t06, rows)
        assert (f.test_id, f.confidence) == ("T06/http-scheme", M.Confidence.AUTHORITATIVE)
        assert f.proposed_value == "https://example.org/place"
        assert f.applicable

    def test_http_without_evidence_is_reviewed(self, t06):
        f = _one(t06, _sites(source_url="http://nobody-else-has-this-host.example/place"))
        assert f.test_id == "T06/http-scheme"
        assert (f.proposal, f.confidence) == (M.Proposal.REVIEW, M.Confidence.UNVERIFIABLE)
        assert f.proposed_value is None

    def test_protocol_relative_author_url_gets_the_project_scheme(self, t06):
        f = _one(t06, _image(author_url="//commons.wikimedia.org/wiki/User:Foo"))
        assert (f.test_id, f.confidence) == ("T06/protocol-relative", M.Confidence.AUTHORITATIVE)
        assert f.proposed_value == "https://commons.wikimedia.org/wiki/User:Foo"

    def test_a_file_page_in_license_url_is_wrong_field_not_a_scheme_fix(self, t06):
        """The mechanical https: prefix would be the wrong repair for the wrong kind of URL."""
        f = _one(
            t06,
            _image(license_url="//commons.wikimedia.org/wiki/File:S10.08_Gizeh,_image_9936.jpg"),
        )
        assert f.test_id == "T06/wrong-field"
        assert (f.proposal, f.confidence) == (M.Proposal.REVIEW, M.Confidence.UNVERIFIABLE)
        assert f.proposed_value is None

    def test_non_http_scheme_is_reviewed(self, t06):
        f = _one(t06, _sites(source_url="ftp://example.org/place"))
        assert f.test_id == "T06/non-http-scheme"
        assert f.proposal is M.Proposal.REVIEW


# --------------------------------------------------------------- not a locator


class TestNotALocator:
    def test_javascript_url_is_cleared(self, t06):
        f = _one(t06, _sites(source_url="javascript:void(0)"))
        assert f.test_id == "T06/javascript-scheme"
        assert f.proposal is M.Proposal.CLEAR
        assert f.confidence is M.Confidence.AUTHORITATIVE
        assert f.severity is M.Severity.MODERATE, "a scriptable href is not cosmetic"
        assert f.proposed_value is None

    def test_bare_fragment_is_cleared(self, t06):
        f = _one(t06, _image(author_url="#cite_note-bl-1"))
        assert f.test_id == "T06/fragment-only"
        assert f.proposal is M.Proposal.CLEAR and f.applicable

    def test_unsubstituted_template_placeholder_is_cleared(self, t06):
        f = _one(t06, _image(license_url="{{{tos_url}}}"))
        assert f.test_id == "T06/not-a-url"
        assert f.proposal is M.Proposal.CLEAR

    def test_a_plain_word_cannot_be_cleared_against_its_field_contract(self, t06):
        f = _one(t06, _sites(source_url="British Museum"))
        assert f.test_id == "T06/not-a-url"
        assert f.proposal is M.Proposal.CLEAR and f.confidence is M.Confidence.AUTHORITATIVE

    def test_a_fragment_inside_a_page_url_is_fine(self, t06):
        _none(t06, _sites(source_url="https://en.wikipedia.org/wiki/Paphos#Odeon"))


# --------------------------------------------------------------- encoding


class TestEncoding:
    def test_html_entity_is_decoded_but_not_auto_applied(self, t06):
        value = "https://commons.wikimedia.org/w/index.php?title=User:Fn&amp;action=edit"
        f = _one(t06, _image(author_url=value))
        assert f.test_id == "T06/html-entities"
        assert f.proposal is M.Proposal.SET and f.confidence is M.Confidence.WEAK
        assert f.proposed_value == value.replace("&amp;", "&")
        assert not f.applicable, "decoding changes which query the server sees"

    def test_two_urls_joined_by_a_newline_are_reviewed(self, t06):
        f = _one(t06, _sites(source_url="https://a.example/x\nhttps://b.example/y"))
        assert f.test_id == "T06/control-characters"
        assert (f.proposal, f.confidence) == (M.Proposal.REVIEW, M.Confidence.UNVERIFIABLE)
        assert f.severity is M.Severity.MODERATE

    def test_surrounding_whitespace_is_stripped(self, t06):
        f = _one(t06, _sites(source_url=" https://example.org/x "))
        assert f.test_id == "T06/control-characters"
        assert f.proposal is M.Proposal.SET and f.proposed_value == "https://example.org/x"

    def test_broken_percent_escape_is_repaired(self, t06):
        f = _one(t06, _sites(source_url="https://example.org/x%2y"))
        assert f.test_id == "T06/bad-percent-encoding"
        assert f.proposal is M.Proposal.SET and f.confidence is M.Confidence.WEAK
        assert f.proposed_value == "https://example.org/x%252y"

    def test_inner_double_slash_is_collapsed(self, t06):
        f = _one(
            t06,
            {
                "site_content_links": [
                    {
                        "site_id": SITE,
                        "content_url": "https://wuw.pl/data/include/cms//SI_2021_89.pdf",
                    }
                ]
            },
        )
        assert f.test_id == "T06/double-slash"
        assert f.proposed_value == "https://wuw.pl/data/include/cms/SI_2021_89.pdf"

    def test_double_slash_of_an_embedded_url_is_kept(self, t06):
        """1,261 author_urls are archive.org snapshots with a second URL inside the path."""
        _none(t06, _image(author_url="https://web.archive.org/web/2016/https://example.org/x"))

    def test_dangling_query_is_reviewed(self, t06):
        f = _one(
            t06,
            {
                "site_content_links": [
                    {
                        "site_id": SITE,
                        "content_url": "https://www.tandfonline.com/doi/full/10.1080/x?src=",
                    }
                ]
            },
        )
        assert f.test_id == "T06/truncated"
        assert f.proposal is M.Proposal.REVIEW and f.proposed_value is None

    def test_trailing_separator_is_reviewed_not_cut(self, t06):
        f = _one(
            t06,
            {
                "site_content_links": [
                    {
                        "site_id": SITE,
                        "content_url": "https://www.academia.edu/123/BARGALA_english_",
                    }
                ]
            },
        )
        assert f.test_id == "T06/truncated-tail"
        assert f.proposal is M.Proposal.REVIEW, "a trailing _ is legal in a slug"


# --------------------------------------------------------------- wikimedia shapes


class TestWikimediaShape:
    def test_hash_directory_is_corrected_from_the_filename(self, t06):
        f = _one(
            t06,
            _image(
                original_url=(
                    "https://upload.wikimedia.org/wikipedia/commons/4/4d/"
                    "Earliest_carbon_14_dates_for_G%C3%B6bekli_Tepe_as_of_2013.jpg"
                )
            ),
        )
        assert f.test_id == "T06/wikimedia-path"
        assert f.proposal is M.Proposal.SET and f.confidence is M.Confidence.AUTHORITATIVE
        assert f.proposed_value == (
            "https://upload.wikimedia.org/wikipedia/commons/e/ec/"
            "Earliest_carbon_14_dates_for_G%C3%B6bekli_Tepe_as_of_2013.jpg"
        )

    def test_correct_hash_directory_is_left_alone(self, t06):
        _none(t06, _image())

    def test_thumbnail_stored_as_the_original_is_stripped(self, t06):
        f = _one(
            t06,
            _image(
                original_url=(
                    "https://upload.wikimedia.org/wikipedia/commons/thumb/8/80/"
                    "Cornish_midsummer_bonfire.jpg/440px-Cornish_midsummer_bonfire.jpg"
                )
            ),
        )
        assert f.test_id == "T06/wikimedia-path"
        assert f.proposed_value == (
            "https://upload.wikimedia.org/wikipedia/commons/8/80/Cornish_midsummer_bonfire.jpg"
        )

    def test_thumbnail_with_wrong_directories_is_stripped_and_corrected(self, t06):
        f = _one(
            t06,
            _image(
                original_url=(
                    "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/"
                    "Cauria-stantari_alignement.jpg/640px-Cauria-stantari_alignement.jpg"
                )
            ),
        )
        assert f.proposed_value == (
            "https://upload.wikimedia.org/wikipedia/commons/7/71/Cauria-stantari_alignement.jpg"
        )

    def test_wiki_page_url_as_a_card_thumbnail_is_reviewed(self, t06):
        f = _one(
            t06,
            _sites(
                thumbnail_url="https://en.wikipedia.org/wiki/Nabataean_architecture#/media/File:X.jpg"
            ),
        )
        assert f.test_id == "T06/page-as-image"
        assert f.field == "unified_sites.thumbnail_url"
        assert (f.proposal, f.confidence) == (M.Proposal.REVIEW, M.Confidence.UNVERIFIABLE)

    def test_wrong_field_original_from_another_host_is_reviewed(self, t06):
        f = _one(
            t06,
            {
                "wiki_images": [
                    {
                        "site_id": SITE,
                        "source_type": "manual",
                        "original_url": "https://www.butterfield.com/_next/image",
                    }
                ]
            },
        )
        assert f.test_id == "T06/wrong-field"
        assert f.proposal is M.Proposal.REVIEW

    def test_local_image_path_of_another_site_is_reviewed(self, t06):
        f = _one(
            t06,
            {
                "wiki_images": [
                    {
                        "site_id": SITE,
                        "source_type": "manual",
                        "original_url": f"/data/images/wiki/{OTHER_SITE[:8]}/hero.webp",
                    }
                ]
            },
        )
        assert f.test_id == "T06/local-path-mismatch"
        assert f.proposal is M.Proposal.REVIEW

    def test_own_local_image_path_is_accepted(self, t06):
        """static_exporter.py:363 writes exactly this shape - not a defect."""
        _none(
            t06,
            {
                "wiki_images": [
                    {
                        "site_id": SITE,
                        "source_type": "manual",
                        "original_url": f"/data/images/wiki/{SITE[:8]}/hero.webp",
                    }
                ]
            },
        )
        _none(t06, _sites(thumbnail_url=f"/data/images/wiki/{SITE[:8]}/hero.webp"))


# --------------------------------------------------------------- citations


class TestCitations:
    def test_nested_citation_url_is_checked_and_labelled(self, t06):
        rows = _sites(raw_data={"description_citations": [{"url": "http://example.org/paper"}]})
        rows["wiki_images"] = [
            dict(_image()["wiki_images"][0], license_url="https://example.org/licence")
        ]
        f = _one(t06, rows)
        assert f.test_id == "T06/http-scheme"
        assert f.field == "raw_data.description_citations[].url"
        assert f.proposed_value == "https://example.org/paper"
        assert f.applicable

    def test_row_without_citations_is_untouched(self, t06):
        _none(t06, _sites(raw_data={"description_citations": []}))


# --------------------------------------------------------------- invariants


class TestInvariants:
    """Properties that must hold for every finding, shape-checked on a batch of defects."""

    @pytest.fixture(scope="class")
    def findings(self, t06: Any) -> list[M.Finding]:
        rows = {
            "unified_sites": [
                {"id": SITE, "source_id": "ancient_nerds", "source_url": ""},
                {
                    "id": OTHER_SITE,
                    "source_id": "ancient_nerds",
                    "source_url": "http://nobody-else-has-this-host.example/place",
                },
            ],
            "wiki_images": [
                _image(author_url="#cite_note-x", license_url="{{{tos_url}}}")["wiki_images"][0],
                _image(
                    author_url="https://commons.wikimedia.org/w/index.php?title=U&amp;action=edit"
                )["wiki_images"][0],
            ],
            "site_content_links": [
                {"site_id": SITE, "content_url": "https://www.academia.edu/1/Slug_"}
            ],
        }
        return t06.run(_ctx(rows))

    def test_batch_is_not_empty(self, findings):
        assert len(findings) >= 6

    def test_set_carries_a_value_and_review_does_not(self, findings):
        for f in findings:
            if f.proposal is M.Proposal.SET:
                assert f.proposed_value, f"{f.test_id} proposes SET without a value"
                assert f.proposed_value != f.current_value, f"{f.test_id} proposes no change"
            if f.proposal is M.Proposal.REVIEW:
                assert f.proposed_value is None, f"{f.test_id} REVIEW must not carry a value"
            if f.proposal is M.Proposal.CLEAR:
                assert f.proposed_value is None

    def test_every_finding_has_evidence(self, findings):
        for f in findings:
            assert f.evidence, f"{f.test_id} has no evidence"
            assert all(e.source for e in f.evidence)

    def test_applicable_findings_are_strong_and_never_weak(self, findings):
        for f in findings:
            if f.applicable:
                assert f.proposal in (M.Proposal.SET, M.Proposal.CLEAR)
                assert f.confidence in (M.Confidence.TWO_SOURCE, M.Confidence.AUTHORITATIVE)

    def test_test_id_carries_the_class_and_dimension_is_set(self, findings):
        for f in findings:
            assert f.test_id.startswith("T06/")
            assert f.dimension == "URL"
            assert f.severity in (M.Severity.COSMETIC, M.Severity.MODERATE, M.Severity.SEVERE)


class TestModuleContract:
    def test_module_declares_its_identity(self, t06):
        assert t06.TEST_ID == "T06"
        assert t06.NAME == "URL shapes"
        assert t06.DIMENSION == "URL"

    def test_module_is_offline(self, t06):
        """T07 does the reachability sweep; T06 must never reach for the network."""
        import inspect

        assert not hasattr(t06, "collect"), "T06 must not need a collect() phase"
        source = inspect.getsource(t06)
        assert "ctx.net(" not in source
        assert "requests." not in source and "urllib.request" not in source

    def test_every_url_column_of_the_snapshot_is_enumerated(self, t06):
        """A new URL column must not slip past the census unnoticed."""
        listed = {(f.table, f.column) for f in t06.FIELDS}
        assert listed == {
            ("unified_sites", "source_url"),
            ("unified_sites", "thumbnail_url"),
            ("unified_sites", "raw_data"),
            ("card_stats", "best_wiki_url"),
            ("card_stats", "commons_image"),
            ("wiki_images", "original_url"),
            ("wiki_images", "commons_page_url"),
            ("wiki_images", "author_url"),
            ("wiki_images", "license_url"),
            ("site_content_links", "content_url"),
            ("site_content_links", "thumbnail_url"),
        }
