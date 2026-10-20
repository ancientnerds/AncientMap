"""pipeline.lyra.story_site_matcher: the curated site a story names, or none.

The production keyer folds words in Postgres (site_key_sql); these tests pass a
Python fold, which agrees with unaccent on the plain Latin names used here.
"""

import inspect
import unicodedata
from types import SimpleNamespace

import pytest

from pipeline.lyra import story_site_matcher as ssm
from pipeline.lyra.story_site_matcher import StoryText, build_lexicon, match_story
from pipeline.utils.public_sites import curated_page


def fold(words):
    return {
        w: "".join(
            c for c in unicodedata.normalize("NFKD", w.lower()) if not unicodedata.combining(c)
        )
        for w in words
    }


def _site(site_id, name, country, *aliases):
    rows = [(site_id, name, country, name, "site"), (site_id, name, country, name, "label")]
    rows += [(site_id, name, country, alias, kind) for alias, kind in aliases]
    return rows


def _fillers():
    """Enough sites to make "el", "castillo" and "temple" generic words."""
    rows = []
    countries = ["Spain", "Mexico", "Peru", "Italy", "Greece"]
    for i in range(ssm.GENERIC_SITE_COUNT):
        country = countries[i % len(countries)]
        rows += _site(f"c{i}", f"Castillo de Filler{i}", country, (f"El Filler{i}", "label"))
        rows += _site(f"t{i}", f"Temple of Filler{i}", country)
    return rows


ROWS = [
    *_site("giza-gp", "The Great Pyramid of Giza", "Egypt"),
    *_site("giza-n", "Giza Temple", "Egypt", ("Giza", "wikidata_alias")),
    *_site("gobekli", "Göbekli Tepe", "Türkiye"),
    *_site("karahan", "Karahan Tepe", "Türkiye"),
    *_site("apollo-gr", "Temple of Apollo (Delphi)", "Greece", ("Temple of Apollo", "label")),
    *_site("apollo-it", "Temple of Apollo, Pompeii", "Italy", ("Temple of Apollo", "label")),
    *_site("pons", "Pons Aelius", "England", ("Newcastle", "wikidata_alias")),
    *_site("cave", "Cave of El Castillo", "Spain", ("El Castillo", "wikidata_alias")),
    *_site("sweet", "Sweet Track", "England"),
    *_site("stonehenge", "Stonehenge", "England"),
    *_site("deir", "Deir el-Bahari", "Egypt"),
    *_site("abydos", "Osiris Temple, Abydos.", "Egypt", ("Abydos", "wikidata_alias")),
    *_site("cromagnon", "Cro-Magnon Rock Shelter", "France", ("Abri", "wikidata_alias")),
    *_site("sparta", "Ancient Sparta", "Greece", ("Sparta", "wikidata_alias")),
    *_site("herc", "Herculaneum", "Italy"),
    *_site("pompeii-a", "Pompeii", "Italy"),
    *_site("pompeii-b", "Pompeii Ruins", "Italy", ("Pompeii", "wikidata_alias")),
    *_site("mexico-site", "Teotihuacan", "Mexico", ("Tollan", "wikidata_alias")),
    *_site("bath", "Bath", "England"),
    *_site("rome-cjk", "Colosseum", "Italy", ("コロッセオ", "wikidata_alias")),
    *_fillers(),
]


@pytest.fixture(scope="module")
def lex():
    return build_lexicon(ROWS, fold)


def _match(lex, **fields):
    return match_story(StoryText(**fields), lex, fold)


def _site_of(found):
    return found.site_id if found else None


class TestTolerance:
    def test_a_missing_leading_article_still_names_the_site(self, lex):
        """54 public stories sat on a Wikidata copy of the Great Pyramid for want of "The"."""
        found = _match(lex, extracted="Great Pyramid of Giza", headline="Shafts found")
        assert _site_of(found) == "giza-gp"
        assert found.reason == "extracted_name"

    def test_hyphens_and_apostrophes_fold_away(self, lex):
        found = _match(lex, headline="New pillar found at Göbekli-Tepe's eastern enclosure")
        assert _site_of(found) == "gobekli"
        assert found.reason == "headline"

    def test_accents_fold_like_the_name_column(self, lex):
        found = _match(lex, headline="Gobekli Tepe pillars were cut with flint tools")
        assert _site_of(found) == "gobekli"

    def test_a_lower_case_word_the_name_itself_writes_lower_case(self, lex):
        found = _match(lex, headline="Hatshepsut's terraced temple at Deir el-Bahari")
        assert _site_of(found) == "deir"

    def test_a_non_latin_alias_is_never_a_key(self, lex):
        assert all(ssm._latin(key) for key in lex.by_key)


class TestRatherNoLinkThanAWrongOne:
    def test_a_shared_name_needs_the_country_of_exactly_one_site(self, lex):
        assert _match(lex, headline="Excavators reopen the Temple of Apollo") is None
        found = _match(lex, headline="Excavators reopen the Temple of Apollo in Greece")
        assert _site_of(found) == "apollo-gr"
        assert found.country_confirmed

    def test_a_name_of_generic_words_needs_the_country(self, lex):
        """ "El Castillo" is a Wikidata alias of a cave in Spain; the story is Chichén Itzá."""
        story = {"headline": "Serpent shadow descends El Castillo pyramid at the equinox"}
        assert _match(lex, **story) is None

    def test_a_one_word_wikidata_alias_needs_the_country(self, lex):
        story = {
            "summary": "Researcher Brendan Burhan in Newcastle studies narcotics.",
            "facts": ["Samples were analysed in Newcastle by the team."],
        }
        assert _match(lex, **story) is None

    def test_the_distinctive_word_of_the_site_name_needs_no_country(self, lex):
        found = _match(lex, headline="Massive bedrock shafts discovered near Giza's causeway")
        assert _site_of(found) == "giza-n"
        assert not found.country_confirmed

    def test_a_word_the_story_writes_in_lower_case_is_a_common_word(self, lex):
        story = {"post_text": "Romans built it at Bath. Later the bath was rebuilt."}
        assert _match(lex, **story) is None

    def test_a_one_word_name_in_a_title_case_headline_only_proves_nothing(self, lex):
        assert _match(lex, headline="Mysterious Ancient Stonehenge Builders Revealed Today") is None
        found = _match(
            lex,
            headline="Mysterious Ancient Stonehenge Builders Revealed Today",
            post_text="New dating at Stonehenge moves the builders back.",
        )
        assert _site_of(found) == "stonehenge"

    def test_a_country_name_inside_a_sub_national_name_confirms_nothing(self, lex):
        story = {"headline": "Tollan legends retold by a historian from New Mexico"}
        assert _match(lex, **story) is None


class TestOneSitePerStory:
    def test_two_sites_in_the_headline_give_no_link(self, lex):
        story = {"headline": "Bull symbolism links Karahan Tepe and Gobekli Tepe"}
        assert _match(lex, **story) is None

    def test_a_headline_yardstick_is_not_the_subject(self, lex):
        story = {"headline": "Neolithic trackway in Somerset is older than Sweet Track"}
        assert _match(lex, **story) is None
        story = {"headline": "Nabta Playa circle pre-dating Stonehenge by 1,000 years"}
        assert _match(lex, **story) is None

    def test_an_unsettled_name_blocks_the_other_site(self, lex):
        """ "Pompeii" is shared here: the story is no Herculaneum story."""
        story = {"headline": "1,500 bodies found in Pompeii and Herculaneum"}
        assert _match(lex, **story) is None

    def test_the_extracted_name_decides_first(self, lex):
        found = _match(
            lex, extracted="Karahan Tepe", headline="Karahan Tepe is older than Gobekli Tepe"
        )
        assert _site_of(found) == "karahan"

    def test_another_named_place_takes_the_site_from_its_headline(self, lex):
        found = _match(
            lex,
            extracted="Wadi Cemetery",
            headline="Wadi Cemetery: 77 tombs discovered at Deir el-Bahari",
        )
        assert _site_of(found) == "deir"
        assert found.reason == "headline"

    def test_another_named_place_never_takes_a_bare_wikidata_alias(self, lex):
        story = {
            "extracted": "Saka Republic",
            "headline": "Cave lion cub named Sparta found in Siberian permafrost",
        }
        assert _match(lex, **story) is None

    def test_another_named_place_never_takes_a_site_from_the_body(self, lex):
        story = {
            "extracted": "Coffin Rock",
            "headline": "Elongated skulls of the Pacific Northwest",
            "post_text": "He compared them to finds at Stonehenge. Stonehenge has none.",
        }
        assert _match(lex, **story) is None

    def test_the_body_counts_for_the_one_site_it_names_in_two_sentences(self, lex):
        story = {
            "headline": "Pillar 43 may commemorate a comet impact",
            "post_text": "Pillar 43 stands at Göbekli Tepe. Göbekli Tepe dates to 9,600 BC.",
        }
        found = _match(lex, **story)
        assert _site_of(found) == "gobekli"
        assert found.reason == "repeated"

    def test_the_summary_repeating_a_fact_is_one_sentence(self, lex):
        fact = "A limestone quarry sits northwest of Göbekli Tepe"
        story = {
            "headline": "An unfinished T-pillar in the quarry",
            "summary": fact,
            "facts": [fact],
        }
        assert _match(lex, **story) is None

    def test_a_body_that_lists_several_sites_gives_no_link(self, lex):
        story = {
            "headline": "Shared symbols across continents",
            "post_text": "Found at Stonehenge, Göbekli Tepe and Karahan Tepe. Stonehenge too.",
        }
        assert _match(lex, **story) is None


class TestTheExtractedName:
    def test_a_part_set_off_by_a_connector_is_a_place(self, lex):
        found = _match(lex, extracted="Pyramid of Ahmose I at Abydos", headline="Cenotaph")
        assert _site_of(found) is None  # Abydos is a bare alias: Egypt is not named
        found = _match(
            lex, extracted="Pyramid of Ahmose I at Abydos", headline="Cenotaph found in Egypt"
        )
        assert _site_of(found) == "abydos"
        assert found.reason == "extracted_name_part"

    def test_a_part_glued_to_another_proper_name_is_a_modifier(self, lex):
        story = {"extracted": "Abri Lartet", "headline": "Lunar notation on a bone from France"}
        assert _match(lex, **story) is None

    def test_a_lower_case_part_is_no_name(self, lex):
        story = {"extracted": "Roman temple near Rossett", "headline": "A villa in Wales"}
        assert _match(lex, **story) is None


class TestPostgresSide:
    def test_the_keyer_folds_in_postgres(self):
        src = inspect.getsource(ssm.postgres_keyer)
        assert "site_key_sql('w')" in src
        assert "pipeline.utils.text" not in inspect.getsource(ssm)

    def test_the_lexicon_holds_the_curated_sites_with_a_page(self):
        """public_sites.curated_page(): curated, with a country, not retired. A
        curated site without a country has no /sites page to link to."""
        assert ssm.LEXICON_SQL.count(curated_page("u")) == 2
        assert ssm.LEXICON_SQL.count("u.country IS NOT NULL AND u.country != ''") == 2
        assert ssm.LEXICON_SQL.count("u.scope_status IS DISTINCT FROM 'retired'") == 2

    def test_the_keyer_batches_and_caches(self):
        calls = []

        class Session:
            def execute(self, _sql, params):
                calls.append(list(params["words"]))
                return SimpleNamespace(fetchall=lambda: [(w, w.lower()) for w in params["words"]])

        key = ssm.postgres_keyer(Session())
        assert key(["Giza", "Tepe"]) == {"Giza": "giza", "Tepe": "tepe"}
        key(["Giza"])
        assert calls == [["Giza", "Tepe"]]
