"""The Commons page URL has one spelling (`pipeline/commons_urls.py`), imported everywhere it is
written - the downloader, the attribution backfill - so no copy can drift from it."""

from pipeline import commons_urls, image_attribution_backfill, wiki_image_downloader


def test_a_file_title_keeps_its_spaces_and_is_quoted_whole() -> None:
    assert (
        commons_urls.commons_page_url_for("File:Forum Romanum - panoramio (3).jpg")
        == "https://commons.wikimedia.org/wiki/File%3AForum%20Romanum%20-%20panoramio%20%283%29.jpg"
    )


def test_the_writers_use_the_one_function() -> None:
    assert wiki_image_downloader.commons_page_url_for is commons_urls.commons_page_url_for
    assert image_attribution_backfill.commons_page_url_for is commons_urls.commons_page_url_for
