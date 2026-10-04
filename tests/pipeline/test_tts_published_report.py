"""Paper audio narrates what the page shows: published_report (memory project-theo-published-report-trap)."""

from pipeline.lyra.tts_generator import report_for_audio


def test_a_published_paper_narrates_the_published_text():
    assert report_for_audio({"report": "draft", "published_report": "published"}) == "published"


def test_an_unpublished_paper_narrates_its_report():
    assert report_for_audio({"report": "draft"}) == "draft"


def test_an_empty_published_text_is_not_swapped_for_the_draft():
    assert report_for_audio({"report": "draft", "published_report": ""}) == ""
