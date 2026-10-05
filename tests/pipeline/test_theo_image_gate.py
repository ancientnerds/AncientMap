"""The mechanical image rules of pipeline/lyra/theo_image_gate.py, against real defects.

Every literal in this file is copied out of a paper that shipped on
ancientnerds.com in the 31-paper audit of 2026-10-04
(docs/reports/theo-paper-defects-2026-10-04.md, section G). The paper is named above
each literal. Nothing here reads C:\tmp or the network: the tests carry the snippets
with them, so they fail on the code, not on a missing audit directory.

The defects they reproduce, one per test:
  * `verified:no` images ship (52 of the 235 gallery-marked images in the corpus),
    the caption even admitting it - "Illustration: Hesiod ...".
  * the 7 dead image references of `the-enuma-elish-...` (404 of 511 corpus-wide).
  * `cargo-cults`: eight image credits for seven pictures, the eighth credit pointing
    at a file the site answers 404 for.
  * a hero image of another paper's folder reaching a `web_path` that is not this
    paper's (the audit found two such dead stored images).
  * the attribution rules, which the studio's own gate already applies to its
    workspace but which the production path never ran.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.lyra.theo_image_gate import (
    ImageIssue,
    check_image_entries,
    check_image_report,
    parse_figures,
)

# cyclical-world-ages-in-comparative-mythology (1d0053d4-...), the same picture in
# two states: the second entry of the paper's first gallery was never opened.
CYC = "1d0053d4-c28b-45db-a30c-20c6501d6147"
VERIFIED_NO_ALT = "gallery:7a93594c|verified:no|Hesiod (Daktyliothek, Zweites Historisches Tausend)"
VERIFIED_NO_BLOCK = f"""![{VERIFIED_NO_ALT}](/data/research-images/{CYC}/p0_Hesiod_1.jpg)

*Illustration: Hesiod (Daktyliothek, Zweites Historisches Tausend). Photo: \
http://data.europeana.eu/agent/165163 / Europeana.*
[Source](https://www.europeana.eu/item/669/item_GDKRGEQL4Z32Y2CB5BNWX2ETWXWSEFYM)\
"""

VERIFIED_YES_BLOCK = f"""![gallery:7a93594c|verified:yes|Seneca](/data/research-images/{CYC}/p0_Hesiod.jpg)

*Seneca. Photo: Massimo Finizio / Wikimedia Commons.*
[Source](https://commons.wikimedia.org/wiki/File:Seneca.JPG)
"""

# the-enuma-elish-tiamat-and-the-sitchin-nibiru-controversy
# (30dfca0b-0ce9-4ab5-b093-05a0240758bc): one of the seven references that 404. The
# image step wrote the block and never wrote the file.
ENUMA = "30dfca0b-0ce9-4ab5-b093-05a0240758bc"
ENUMA_DEAD_BLOCK = f"""![Mesopotamian cylinder seal impression](/data/research-images/{ENUMA}\
/writer_img_2.jpg)

*Mesopotamian cylinder seal impression. Photo: The original uploader was IronyWrit at \
English Wikipedia. / Wikimedia Commons. Image placed by the paper writer as visual \
evidence for this passage.*
[Source](https://commons.wikimedia.org/wiki/File:Mesopotamian_cylinder_seal_impression.jpg)\
"""

# cargo-cults-and-uncontacted-peoples-in-comparative-perspective
# (a00c4ee2-0162-4bfe-997f-72f7ac3457fc): seven pictures, eight credits. Blocks 2, 3
# and 5 are the shape the writer produced - the image sits at the end of a prose
# paragraph, its caption and credit on the lines after it. The last credit belongs to
# no picture at all: `NorthSentinel_Island_ISS006-E-33376_sat.jpg` returns HTTP 404
# and the paper has no `![]()` embed for it. `p14_Manus_Island.jpg` is North Sentinel
# Island - the filename is the only thing that lies.
CARGO = "a00c4ee2-0162-4bfe-997f-72f7ac3457fc"
CARGO_REPORT = f"""\
![Aerial view of Henderson Field, Guadalcanal, in late August 1942](/data/research-images/\
{CARGO}/writer_img_0.jpg)

*Aerial view of Henderson Field, Guadalcanal, in late August 1942. Photo: U.S. Navy \
(photographed from a USS Saratoga (CV-3) plane) / Wikimedia Commons.*
[Source](https://commons.wikimedia.org/wiki/File:Aerial_view_of_Henderson_Field,_Guadalcanal,\
_in_late_August_1942.jpg)

Chief Isaak Wan Nikiau, current leader, frames John Frum as 'our God, our Jesus'. \
![John Frum flag raising](/data/research-images/{CARGO}/writer_img_1.jpg) [5]

*John Frum flag raising. Photo: Flickr user Charmaine Tham / Wikimedia Commons. John Frum \
"cargo" cult and their ceremonial flag raising.*
[Source](https://commons.wikimedia.org/wiki/File:John_Frum_flag_raising.jpg)

The Prince Philip Movement venerated the Duke of Edinburgh as 'a recycled descendant of a \
very powerful spirit or god'. ![John Frum effigy 1960](/data/research-images/{CARGO}\
/writer_img_2.jpg) [6] [7]

*John Frum effigy 1960. Photo: David Attenborough / Wikimedia Commons. Cargo cult effigy \
of John Frum, 1960.*
[Source](https://commons.wikimedia.org/wiki/File:John_Frum_effigy_1960.jpg)

![Reconstructed Viking longship Havhingsten fra Glendalough under construction showing part \
of the inside2](/data/research-images/{CARGO}/p6_Norse_longship.jpg)

*Reconstructed Viking longship Havhingsten fra Glendalough under construction showing part of \
the inside2. Photo: Sonty / Wikimedia Commons.*
[Source](https://commons.wikimedia.org/wiki/File:Reconstructed_Viking_longship_Havvingsten\
_fra_Glendalough_under_construction_showing_part_of_the_inside2.jpg)

![General History of the Things of New Spain by Fray Bernardino de Sahagún- The Florentine \
Codex WDL10096](/data/research-images/{CARGO}/writer_img_3.jpg) [12]

*General History of the Things of New Spain by Fray Bernardino de Sahagún- The Florentine \
Codex WDL10096. Photo: Sahagún, Bernardino de, 1499-1590 / Wikimedia Commons.*
[Source](https://commons.wikimedia.org/wiki/File:General_History_of_the_Things_of_New_Spain\
_by_Fray_Bernardino_de_Sahag%C3%BAn-_The_Florentine_Codex_WDL10096.jpg)

*NorthSentinel Island ISS006-E-33376 sat. Photo: Wikimedia Commons.*
[Source](https://commons.wikimedia.org/wiki/File:NorthSentinel_Island_ISS006-E-33376_sat.jpg)

![North Sentinel Island](/data/research-images/{CARGO}/p14_Manus_Island.jpg)

*North Sentinel Island. Photo: NASA Earth Observatory image created by Jesse Allen, using \
data provided by the NASA EO-1 team. / Wikimedia Commons.*
[Source](https://commons.wikimedia.org/wiki/File:North_Sentinel_Island.jpg)

![Mount Yasur eruption 2006, Tanna Island, Vanuatu, VAN 0516](/data/research-images/{CARGO}\
/p21_Mount_Yasur_volcano_Tanna.jpg)

*Mount Yasur eruption 2006, Tanna Island, Vanuatu, VAN 0516. Photo: Rolf Cosar / Wikimedia \
Commons. Eruption of Yasur.*
[Source](https://commons.wikimedia.org/wiki/File:Mount_Yasur_eruption_2006,_Tanna_Island,\
_Vanuatu,_VAN_0516.jpg)
"""


def _served(tmp_path: Path, request_id: str, *names: str) -> Path:
    """A served root (the directory served as /data/) holding the named files."""
    for name in names:
        target = tmp_path / "research-images" / request_id / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"jpeg")
    return tmp_path


def _entry(request_id: str, name: str, **overrides) -> dict:
    """One probative_images record, complete except for what a test wants to break.

    The shape is the one the studio writes (pipeline/studio/paper/images.py) and the
    one handlers/probative_images.py embeds; the values are the ones a Wikimedia or
    Europeana candidate carries, and Europeana is 59 % of the corpus.
    """
    entry = {
        "web_path": f"/data/research-images/{request_id}/{name}",
        "image_path": f"/app/public/data/research-images/{request_id}/{name}",
        "section_heading": "How Heavy Is Heavy",
        "paragraph_index": 12,
        "paragraph_text": "The paragraph the picture sits under.",
        "title": "Seneca",
        "artist": "Massimo Finizio",
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "source_url": "https://commons.wikimedia.org/wiki/File:Seneca.JPG",
        "source_name": "wikimedia",
        "description": "Seneca. Photo: Massimo Finizio / Wikimedia Commons.",
        "search_query": "Seneca",
        "keyword": "seneca",
        "rationale": "The bust is the Seneca of the text.",
        "verified": True,
    }
    entry.update(overrides)
    return entry


def _rules(issues: list[ImageIssue]) -> list[str]:
    return [issue.rule for issue in issues]


# --- unverified: the picture nobody opened -------------------------------


def test_alt_with_verified_no_is_exactly_one_unverified_issue(tmp_path):
    """cyclical-world-ages: the image the embed marked verified:no must not ship."""
    issues = check_image_report(
        VERIFIED_NO_BLOCK,
        [],
        request_id=CYC,
        served_root=_served(tmp_path, CYC, "p0_Hesiod_1.jpg"),
    )
    assert _rules(issues) == ["unverified"]
    assert issues[0].image == f"/data/research-images/{CYC}/p0_Hesiod_1.jpg"
    assert "p0_Hesiod_1.jpg" in issues[0].detail


def test_alt_with_verified_yes_is_not_unverified(tmp_path):
    """The same gallery, one image further: the opened picture passes."""
    issues = check_image_report(
        VERIFIED_YES_BLOCK, [], request_id=CYC, served_root=_served(tmp_path, CYC)
    )
    assert "unverified" not in _rules(issues)


def test_entry_flagged_false_is_unverified_even_without_a_marker(tmp_path):
    """A record whose own verified field is false is refused, marker or no marker."""
    entry = _entry(CYC, "p3_Road.jpg", verified=False)
    issues = check_image_report(
        "", [entry], request_id=CYC, served_root=_served(tmp_path, CYC, "p3_Road.jpg")
    )
    assert _rules(issues) == ["unverified"]


def test_unverified_picture_is_named_once_not_twice(tmp_path):
    """The same picture reached as a record and as a figure is one issue, not two."""
    entry = _entry(CYC, "p0_Hesiod_1.jpg", verified=False)
    issues = check_image_report(
        VERIFIED_NO_BLOCK, [entry], request_id=CYC, served_root=_served(tmp_path, CYC)
    )
    assert _rules(issues).count("unverified") == 1


# --- not_served: the file the site does not serve -------------------------


def test_reference_missing_under_the_served_root_is_not_served(tmp_path):
    """The reference is a real file nowhere: the served root has no such file."""
    _served(tmp_path, CYC, "p0_Hesiod.jpg")  # the served root exists, the file does not
    issues = check_image_report(
        VERIFIED_YES_BLOCK.replace("p0_Hesiod.jpg", "p3_Road.jpg"),
        [],
        request_id=CYC,
        served_root=tmp_path,
    )
    assert _rules(issues) == ["not_served"]
    assert "research-images" in issues[0].detail


def test_real_enuma_elish_reference_is_not_served(tmp_path):
    """the-enuma-elish-...: all seven of its image references 404; this is one.

    The block is the stored shape of writer_img_2.jpg - the caption even says
    "Image placed by the paper writer as visual evidence for this passage" - and the
    file was never written, in the container or anywhere else.
    """
    issues = check_image_report(ENUMA_DEAD_BLOCK, [], request_id=ENUMA, served_root=tmp_path)
    assert "not_served" in _rules(issues)
    served = next(i for i in issues if i.rule == "not_served")
    assert served.image == f"/data/research-images/{ENUMA}/writer_img_2.jpg"
    assert "writer_img_2.jpg" in served.detail


def test_missing_served_root_is_reported_not_passed(tmp_path):
    """A caller that cannot read the filesystem must not pass by default."""
    issues = check_image_report(VERIFIED_YES_BLOCK, [], request_id=CYC, served_root=None)
    assert _rules(issues) == ["not_served"]
    assert "no served root given" in issues[0].detail


def test_hero_image_outside_the_papers_folder_is_not_in_paper_dir(tmp_path):
    """A web_path from another paper's folder is refused by the folder rule.

    Real shape: the stored hero of
    the-squatter-man-petroglyph-and-auroral-sky-mythology named
    p4_Teymareh_rock_art_site.jpg, which the audit found answering 404 while the
    paper's other 24 images were fine.
    """
    foreign = _entry(CYC, "p4_Teymareh_rock_art_site.jpg")
    foreign["web_path"] = (
        "/data/research-images/27ec3538-258c-4960-9493-2bf6c0dc1a3b/p4_Teymareh_rock_art_site.jpg"
    )
    issues = check_image_entries([foreign], request_id=CYC)
    assert "not_in_paper_dir" in _rules(issues)
    detail = next(i for i in issues if i.rule == "not_in_paper_dir").detail
    assert CYC in detail


def test_web_path_outside_research_images_is_not_in_paper_dir():
    """A path that is not under /data/research-images/<request_id>/ at all."""
    entry = _entry(CYC, "p0_Hesiod.jpg", web_path="/data/images/wiki/abc123/hero.jpg")
    issues = check_image_entries([entry], request_id=CYC)
    assert _rules(issues) == ["not_in_paper_dir"]


# --- credit_picture_mismatch ---------------------------------------------


def test_cargo_cults_ships_eight_credits_for_seven_pictures(tmp_path):
    """cargo-cults, measured: 8 image credits, 7 pictures, one credit 404.

    The detail has to name both counts, because "a credit has no picture" is only
    actionable next to the numbers.
    """
    _served(
        tmp_path,
        CARGO,
        "writer_img_0.jpg",
        "writer_img_1.jpg",
        "writer_img_2.jpg",
        "writer_img_3.jpg",
        "p6_Norse_longship.jpg",
        "p14_Manus_Island.jpg",
        "p21_Mount_Yasur_volcano_Tanna.jpg",
    )
    issues = check_image_report(CARGO_REPORT, [], request_id=CARGO, served_root=tmp_path)
    assert "credit_picture_mismatch" in _rules(issues)
    mismatch = next(i for i in issues if i.rule == "credit_picture_mismatch")
    assert "8 image credits for 7 pictures" in mismatch.detail
    assert mismatch.image.endswith("NorthSentinel_Island_ISS006-E-33376_sat.jpg")
    assert len(parse_figures(CARGO_REPORT)) == 7


# --- attribution ----------------------------------------------------------


def test_no_artist_and_no_source_name_is_no_credit():
    """CC BY attribution is a licence condition, so both names absent is a defect."""
    entry = _entry(CYC, "p0_Hesiod.jpg", artist="", source_name="")
    assert "no_credit" in _rules(check_image_entries([entry], request_id=CYC))


def test_either_artist_or_source_name_is_enough():
    """The guard: one name present and the rule stays quiet."""
    for entry in (
        _entry(CYC, "p0_Hesiod.jpg", artist="Massimo Finizio", source_name=""),
        _entry(CYC, "p0_Hesiod.jpg", artist="", source_name="wikimedia"),
    ):
        assert "no_credit" not in _rules(check_image_entries([entry], request_id=CYC))


def test_missing_licence_source_url_and_caption_are_each_reported():
    entry = _entry(CYC, "p0_Hesiod.jpg", license="", license_url="", source_url="", description="")
    assert _rules(check_image_entries([entry], request_id=CYC)) == [
        "no_licence",
        "no_source_url",
        "no_caption",
    ]


def test_two_images_with_the_same_source_url_are_a_duplicate_credit():
    """The same Commons file credited to two different pictures in one paper."""
    entries = [
        _entry(CYC, "p0_Hesiod.jpg"),
        _entry(
            CYC,
            "p4_Maya_Long_Count_calendar.jpg",
            source_url="https://commons.wikimedia.org/wiki/File:Seneca.JPG",
        ),
    ]
    issues = check_image_entries(entries, request_id=CYC)
    duplicates = [i for i in issues if i.rule == "duplicate_credit"]
    assert len(duplicates) == 1
    assert "p4_Maya_Long_Count_calendar.jpg" in duplicates[0].image
    assert "p0_Hesiod.jpg" in duplicates[0].detail


# --- the clean case, and the machine marker ------------------------------


def test_one_clean_picture_raises_no_issue_at_all(tmp_path):
    """The floor this gate exists to keep: a complete, opened, served picture."""
    entry = _entry(CYC, "p0_Hesiod.jpg")
    served = _served(tmp_path, CYC, "p0_Hesiod.jpg")
    assert check_image_report(VERIFIED_YES_BLOCK, [entry], request_id=CYC, served_root=served) == []


def test_gallery_marker_never_reaches_a_detail(tmp_path):
    """The marker is machine data: `gallery:` must not survive into any detail.

    The unverified picture here has no record of its own, so its detail is the one built
    from the alt text - the only detail that quotes the title at all.
    """
    entries = [_entry(CYC, "p0_Hesiod.jpg", description="")]
    issues = check_image_report(
        VERIFIED_NO_BLOCK + "\n" + VERIFIED_YES_BLOCK,
        entries,
        request_id=CYC,
        served_root=_served(tmp_path, CYC, "p0_Hesiod_1.jpg", "p0_Hesiod.jpg"),
    )
    unverified = next(i for i in issues if i.rule == "unverified")
    assert "Hesiod (Daktyliothek, Zweites Historisches Tausend)" in unverified.detail
    assert {i.rule for i in issues} == {"unverified", "no_caption"}
    for issue in issues:
        assert "gallery:" not in issue.detail
        assert VERIFIED_NO_ALT not in issue.detail
    # The detail names the flag in prose ("carries verified:no") - that is the rule
    # speaking, not the marker. What must not survive is the marker itself.
    assert "carries verified:no" in unverified.detail
