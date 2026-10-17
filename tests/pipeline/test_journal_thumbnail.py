"""journal_thumbnail: das Bild, das eine Journal-Ausgabe auf dem Hub vertritt."""

from pipeline.article_html_renderer import journal_thumbnail, reading_minutes


class TestJournalThumbnail:
    def test_picks_the_image_whose_alt_shares_a_word_with_the_headline(self):
        content = (
            "![A medieval abbey tower](https://a.example/1.webp)\n\n"
            "![Harbin cranium reconstruction](https://a.example/2.webp)\n"
        )

        assert journal_thumbnail(content, "Week of October 5: Harbin Cranium Confirmed") == (
            "https://a.example/2.webp"
        )

    def test_falls_back_to_the_first_image_when_no_alt_matches(self):
        content = "![A tower](https://a.example/1.webp)\n\n![A bridge](https://a.example/2.webp)\n"

        assert journal_thumbnail(content, "Week of October 5: Harbin Cranium") == (
            "https://a.example/1.webp"
        )

    def test_short_title_words_do_not_count(self):
        # "the" has three letters and would match every alt text containing it;
        # the bound is "longer than four", exactly like the SPA's w.length > 4.
        content = "![The harbour](https://a.example/1.webp)\n\n![Harbin cranium](https://a.example/2.webp)\n"

        assert (
            journal_thumbnail(content, "The Week 42 Harbin Cranium") == "https://a.example/2.webp"
        )

    def test_a_five_letter_headline_word_counts(self):
        # Boundary of the "longer than four" rule: "Göbek" is five letters.
        content = "![A harbour](https://a.example/1.webp)\n\n![Göbekli pillar](https://a.example/2.webp)\n"

        assert (
            journal_thumbnail(content, "Week 5: Göbekli Pillars Traced")
            == "https://a.example/2.webp"
        )

    def test_article_without_an_image_has_no_thumbnail(self):
        assert journal_thumbnail("Just prose, no pictures.", "Week 42: Something") is None

    def test_empty_content_has_no_thumbnail(self):
        assert journal_thumbnail("", "Week 42: Something") is None

    def test_site_relative_screenshot_paths_are_kept_as_written(self):
        content = "![Sayburç floor]( /data/news/screenshots/abc_1.webp )"

        assert journal_thumbnail(
            content.replace("( ", "(").replace(" )", ")"), "Sayburç floor"
        ) == ("/data/news/screenshots/abc_1.webp")


class TestReadingMinutes:
    def test_counts_two_hundred_words_to_one_minute(self):
        assert reading_minutes("word " * 200) == 1

    def test_rounds_up(self):
        assert reading_minutes("word " * 201) == 2

    def test_never_below_one(self):
        assert reading_minutes("") == 1
        assert reading_minutes("three short words") == 1
