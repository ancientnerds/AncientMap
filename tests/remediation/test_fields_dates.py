"""Lane wd5 (2026-10-09): the dates a quote states, in the language the page prints them
(`scripts/remediation/fields/dates.py`, read through `answers.states_year`).

The WD5 pilot's Opus spot check found four of ten `unresolved` fields where a source plainly stated
the value and only a machine reader failed - among them the Hungarian Wikipedia's "már az i. e. 7.
században is lakták a várost". The phrasings below are real ones: the pilot's, and the sentences of
the earlier lanes' accepted answers (`output/remediation/fields/wd1*`, `wd3*`, `wd4`, written out
because `output/` is a gitignored snapshot). Every parametrised case names the language.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from fields import answers as A  # noqa: E402
from fields import dates as D  # noqa: E402
from fields import rule as R  # noqa: E402

from tests.remediation import test_fields_answers as TA  # noqa: E402

# (language, quote, year the quote states) - every row must state the year
STATED = (
    # the pilot's Hungarian sentence: inhabited already in the 7th century BC
    ("hu", "már az i. e. 7. században is lakták a várost", -700),
    ("hu", "már az i. e. 7. században is lakták a várost", -650),
    ("hu", "Kr. e. 776-ban rendezték az első olimpiát", -776),
    ("hu", "i. e. 776-ban alapították", -776),
    ("hu", "a Kr. u. 3. században épült", 250),
    ("en", "the 5th or 4th century BC", -449),
    ("en", "the 5th century B.C.", -449),
    ("en", "in 449 BC", -449),
    ("en", "around 700 bc", -700),
    ("en", "AD 449", 449),
    ("en", "449 CE", 449),
    ("en", "the 2nd century AD", 101),
    ("en", "it dates to the third millennium BC", -3000),
    ("en", "a village of the 30th century BC", -3000),
    ("en", "from the 1st to the 4th centuries.", 1),
    ("en", "the late first and early second centuries AD", 150),
    ("en", "From the eighth century to the seventh century BC", -800),
    ("en", "dating to the 5th Millennium to early 4th Millennium BC", -5000),
    ("en", "between 3990-3640 cal BCE", -3990),
    ("en", "(3316–2921 cal. BC)", -3316),
    ("en", "c. 3300 - c. 1900 BC", -3300),
    ("en", "(c.30,000 BCE)", -30000),
    ("en", "20,000 years BC", -20000),
    ("en", "14,000 or 15,000 years before the current era (BCE)", -15000),
    ("en", "the 50s BCE", -55),
    ("en", "the 30s BC", -35),
    ("en", "the early AD 70s", 70),
    ("en", "during the early AD1600s", 1650),
    ("en", "start date -330 end date 300", -330),
    ("en", "the last century BC", -50),
    ("en", "4-3 millennium of BC", -3500),
    ("en", "Excavated in 1958", 1958),
    ("en", "7th century−3rd century BCE", -700),
    ("de", "gegründet um 3.000 v. Chr.", -3000),
    ("de", "im 5. Jahrhundert v. Chr.", -450),
    ("de", "im 5. oder 4. Jahrhundert v. Chr.", -350),
    ("de", "aus dem 3. Jahrtausend v. Chr.", -2500),
    ("de", "im 5. Jahrhundert n. Chr.", 450),
    ("de", "ein Durchschnittsalter von 45.180 ±910 Jahren v. Chr.", -45180),
    ("de", "im Jahr 776 vor Christus", -776),
    ("fr", "fondé au IIIe millénaire av. J.-C.", -2500),
    ("fr", "au Ve siècle av. J.-C.", -450),
    ("fr", "un tesson attique du ve siècle av. J.-C.", -450),
    ("fr", "en 449 avant notre ère", -449),
    ("fr", "du IVe millénaire avant JC", -3500),
    ("fr", "d'environ 80 000 à 10 000 ans avant notre ère", -80000),
    ("fr", "au IIe siècle ap. J.-C.", 150),
    ("es", "siglo V a.C.", -449),
    ("es", "entre los siglos VII y V antes de Cristo", -650),
    ("es", "habitado entre los séculos VIII-IV a. C.", -750),
    ("es", "hacia 800 años a. C.", -800),
    ("es", "su antigüedad data aproximadamente de 6,000 a 5,000 a.C.", -6000),
    ("es", "entre el siglo VIII y III antes de nuestra era", -750),
    ("es", "el siglo II d. C.", 150),
    ("ca", "al segle V aC", -450),
    ("it", "IV secolo a.C.", -350),
    ("it", "(secoli XV-XIV a.C.)", -1450),
    ("it", "tra il XIII e il X secolo a.C.", -1250),
    ("it", "realizzato fra il 31 e il 25 a.C.", -31),
    ("it", "nel IV sec. a.C.", -350),
    ("it", "nel II secolo d.C.", 150),
    ("pt", "século V a.C.", -450),
    ("pt", "do III milénio a.C.", -2500),
    ("nl", "in de 5e eeuw v.Chr.", -450),
    ("nl", "in de 3e eeuw na Christus", 250),
    ("pl", "w V wieku p.n.e.", -450),
    ("pl", "w V w. p.n.e.", -450),
    ("pl", "w V i IV wieku p.n.e.", -450),
    ("pl", "w III wieku n.e.", 250),
    ("cs", "v 5. století př. n. l.", -450),
    ("cs", "ve 3. tisíciletí př. n. l.", -2500),
    ("hr", "u 5. stoljeću pr. Kr.", -450),
    ("sr", "у V веку пре нове ере", -450),
    ("ru", "в V веке до н. э.", -450),
    ("ru", "в V в. до н. э.", -450),
    ("ru", "в 776 г. до н. э.", -776),
    ("ru", "IV тыс. до н. э.", -3500),
    ("uk", "IV тис. до н. е.", -3500),
    ("uk", "у V столітті до н. е.", -450),
    ("bg", "през V век пр. н. е.", -450),
    ("mk", "6000 и 5200 г. п.н.е.", -6000),
    ("el", "τον 5ο αιώνα π.Χ.", -450),
    ("el", "5ος αιώνας π.Χ.", -450),
    ("tr", "MÖ 7. yüzyıl", -650),
    ("tr", "M.Ö. 6. binyıl", -5500),
    ("tr", "M.S. 5. yüzyıl", 450),
    ("sv", "från 1000 före Kristus till 1050 efter Kristus", -1000),
    ("sv", "cirka 500 f.Kr. till 1050 e.Kr.", -500),
    ("sv", "under 600-talet före Kristus", -650),
    ("da", "ca. 2400‑2000 f.Kr.", -2400),
    ("da", "omkring 3200 f. v.t.", -3200),
    ("da", "cirka 200 år før vor tidsregning", -200),
    ("no", "fra eldre steinalder (4000–5.600 f.Kr.)", -5600),
    ("fi", "noin 5000–500 eaa.", -5000),
    ("id", "(2500–1500 SM)", -2500),
    # an AD abbreviation after a "before" word is a BC phrase, in every language that has one
    ("pl", "450 przed n. e.", -450),
    ("pl", "450 pr. n. e.", -450),
    ("cs", "v roce 450 před n. l.", -450),
    ("cs", "ve 3. století před Kristem", -250),
    ("sk", "roku 450 pred n. l.", -450),
    ("sk", "roku 450 pred Kr.", -450),
    ("hr", "450. godine prije n. e.", -450),
    ("hr", "450. godine prije Kr.", -450),
    ("sr", "450. године пре н. е.", -450),
    ("sr", "450. године пре нове ере", -450),
    ("mk", "450 г. пред н. е.", -450),
    ("bg", "450 г. преди н. е.", -450),
    ("pt", "em 450 antes de J.C.", -450),
    ("pt", "em 450 antes da nossa era", -450),
    ("fr", "en 450 avant l'ère chrétienne", -450),
    # a modern year before an ancient date is its own statement
    ("en", "In 1998 the 3rd century BC walls were found.", -250),
    ("en", "Excavated in 1998 and 1999; the 4th century BC wall", -350),
    ("en", "Excavated in 1998 and 1999; the 4th century BC wall", 1999),
    ("en", "from 800 to the 7th century BC", -800),
    ("en", "the 8th century and the 7th century BC", -750),
    ("sh", "u V veku pre nove ere", -450),
    ("sh", "450 prije n. l.", -450),
)


@pytest.mark.parametrize(("language", "quote", "year"), STATED)
def test_a_quote_states_the_year_it_prints(language: str, quote: str, year: int) -> None:
    assert A.states_year(quote, year), (language, quote, D.statements(quote))


def test_a_century_is_the_hundred_years_with_the_prompt_s_edges() -> None:
    # the n-th century BC from n x 100 BC (the prompt's "8th century BC -> -800") to (n-1) x 100 + 1
    assert D.span("century", 8, "BC") == (-800, -701)
    assert D.span("century", 2, "AD") == (101, 200)
    assert D.span("millennium", 3, "BC") == (-3000, -2001)
    assert D.span("millennium", 1, "AD") == (1, 1000)
    assert A.states_year("the 8th century BC", -800)
    assert A.states_year("the 8th century BC", -701)
    assert not A.states_year("the 8th century BC", -700)
    assert not A.states_year("the 8th century BC", -801)


# (language, quote, year the quote must NOT state)
NOT_STATED = (
    # a year or a century with no marker is AD: a modern event never states an ancient year
    ("hu", "2009-ben ásatták a lelőhelyet", -2009),
    ("de", "Im Jahr 1958 wurde die Anlage ausgegraben", -1958),
    ("ru", "в 1958 году провели раскопки", -1958),
    ("es", "El 5 de mayo de 2009 se inauguró el museo", -2009),
    ("fr", "fouillé en 1958", -1958),
    ("sv", "grävdes ut 1958", -1958),
    ("en", "the 5th century", -450),
    ("tr", "5. yüzyıl", -450),
    ("it", "nel V secolo", -450),
    ("pl", "w V wieku", -450),
    ("en", "the third millennium", -3000),
    ("en", "Assurnasirpal II (883-859) founded the temple", -883),
    # an explicit AD marker is not a BC year, and the other way round
    ("en", "AD 449", -449),
    ("en", "449 AD", -449),
    ("en", "449 BC", 449),
    ("de", "im 5. Jahrhundert n. Chr.", -450),
    ("de", "im 5. Jahrhundert v. Chr.", 450),
    ("es", "siglo V d. C.", -450),
    ("ru", "в V веке н. э.", -450),
    ("hu", "Kr. u. 776-ban", -776),
    # a century or millennium is the one it names
    ("en", "the 6th century BC", -449),
    ("de", "im 4. Jahrhundert v. Chr.", -449),
    ("fr", "au IVe siècle av. J.-C.", -449),
    ("en", "the 3rd millennium BC", -4000),
    # a number below 100 beside no marker is no year ("Table 12", "5 W")
    ("en", "Table 12 lists the pieces", 12),
    ("en", "a 5 W lamp", 5),
    # an abbreviated unit counts only with a marker after it
    ("en", "mentioned during the 4th c. in the Periplus", -400),
    ("en", "mentioned during the 4th c. in the Periplus", 350),
    ("en", "the 30s BC", -2950),
    ("en", "in 12 the 5th century BC", -1150),
    ("en", "the i.e. 776-fold increase", -776),
    ("en", "a lot of 2500 sm", -2500),
    ("pl", "5 w", 5),
    ("pl", "5 w", 450),
    # a fraction is not the number: the first half of the 5th century is the 5th
    ("en", "in the first half of the 5th century BC", -50),
    # the idiom needs its marker
    ("en", "the last century AD", -50),
    ("en", "the last century AD", 50),
    # a truncated unit word or marker is not one
    ("en", "The chronology ranges from the 1st to the 5th centu", -400),
    ("es", "mitad del siglo IV a.", -350),
    # the Hungarian BC marker is English "that is" before anything but a Hungarian date
    ("en", "i.e. 7th century", -650),
    ("en", "the temple, i.e. 776 pieces", -776),
    # "ad" and "ce" are words in lower case, and "ce" is French "this"
    ("en", "an ad of 449", -449),
    ("fr", "ce siècle 5", -450),
    # a lone I is a Roman one beside a unit word only
    ("pl", "I tak dalej", -50),
    # a hyphenated sentence end is no minus
    ("en", "built between 1500-1000", -1000),
    # an AD abbreviation after a "before" word is never AD, whether the phrase is in the table or not
    ("pl", "450 przed n. e.", 450),
    ("cs", "v roce 450 před n. l.", 450),
    ("sk", "roku 450 pred n. l.", 450),
    ("hr", "450. godine prije n. e.", 450),
    ("sr", "450. године пре н. е.", 450),
    ("bg", "450 г. преди н. е.", 450),
    ("mk", "450 г. пред н. е.", 450),
    ("sh", "450 prije n. l.", 450),
    ("pt", "em 450 antes de J.C.", 450),
    ("pt", "em 450 antes da nossa era", 450),
    ("fr", "en 450 avant l'ère chrétienne", 450),
    ("cs", "ve 3. století před Kristem", 250),
    # a modern year does not borrow the era of an ancient date after it: a determiner, a comma, a
    # semicolon, a bracket or a full stop between them is no range
    ("en", "In 1998 the 3rd century BC walls were found.", -1998),
    ("en", "Since 1962 the 5th century BC temple was studied.", -1962),
    ("en", "In 2009 the 300 BC temple was restored.", -2009),
    ("en", "In 1962, a 300 BC temple was found.", -1962),
    ("en", "Excavated in 1998 and 1999; the 4th century BC wall", -1998),
    ("en", "Excavated in 1998 and 1999; the 4th century BC wall", -1999),
    ("en", "Excavated in 1998 (the 4th century BC wall)", -1998),
    ("en", "Excavated in 1998. The 4th century BC wall", -1998),
    ("en", "In 1998 and the 3rd century BC walls", -1998),
    # Czech and Slovak věk is an age, Serbian vek a century only against a number and a marker
    ("cs", "bronzový věk 5", -450),
)


@pytest.mark.parametrize(("language", "quote", "year"), NOT_STATED)
def test_a_quote_does_not_state_what_it_does_not_say(language: str, quote: str, year: int) -> None:
    assert not A.states_year(quote, year), (language, quote, D.statements(quote))


def test_a_bare_year_is_ad_and_a_marked_one_has_its_era() -> None:
    assert [(s.era, s.lo) for s in D.statements("excavated in 1958")] == [(None, 1958)]
    assert [(s.era, s.lo) for s in D.statements("in 449 BC")] == [("BC", -449)]
    assert [(s.era, s.lo) for s in D.statements("AD 449")] == [("AD", 449)]
    assert A.states_year("Excavated in 1958", 1958)
    assert not A.states_year("Excavated in 1958", -1958)


def test_year_zero_is_stated_by_nothing() -> None:
    assert not A.states_year("the year 0 or 000 BC", 0)


def test_a_marker_goes_with_the_statement_before_it_not_the_number_after_it() -> None:
    quote = "Período Preclásico Medio (600 a. C. - 1000 d. C.)"
    assert A.states_year(quote, -600)
    assert A.states_year(quote, 1000)
    assert not A.states_year(quote, -1000)
    quote = "ocupado entre el siglo I a.C. y el VI d.C."
    assert A.states_year(quote, -50)
    assert A.states_year(quote, 550)
    assert not A.states_year(quote, 50)
    assert not A.states_year(quote, -550)


def test_ranges_share_the_marker_of_their_end() -> None:
    for year in (-2100, -2000, -1800):
        assert A.states_year("around 2100-c.1800 BCE", year) == (year in (-2100, -1800)), year


def test_a_thousands_separator_is_not_a_second_number() -> None:
    assert D.group_thousands("45.180 ±910 und 3,000 und 12 000 und 1958 120") == (
        "45180 ±910 und 3000 und 12000 und 1958 120"
    )
    assert D.group_thousands("c.30,000 BCE") == "c.30000 BCE"
    assert D.group_thousands("1.5 Ma") == "1.5 Ma"


# ------------------------------------------------------------------------------ in an answer
WIKI_HU = "https://hu.wikipedia.org/wiki/Olümpé"
WIKI_EN = "https://en.wikipedia.org/wiki/Olympe"


def checked(field: str, answer: dict[str, Any], rule: R.Rule = R.RECHECK, **stored: Any) -> Any:
    return A.check_shape(TA.text(**{field: answer}), [field], TA.line(**stored), rule)[field]


def test_the_hungarian_olympe_sentence_carries_an_answer() -> None:
    """The WD5 pilot: Olympe, stored -1500 (a band rule, bucket "1500 - 500 BC"), answered
    `unresolved` because the 7th century BC was quotable only in Hungarian. Now the quote states
    -700, which lies in the stored bucket: a keep that sources the stored band."""
    quotes = [(WIKI_HU, "már az i. e. 7. században is lakták a várost")]
    answer = checked("period_start", TA.block("keep", "-700", quotes), period_start=-1500)
    assert answer.decision == "keep" and answer.value == "-700"
    # a replace into another bucket needs a quote of that bucket: this one is the 7th century
    refused = checked("period_start", TA.block("replace", "-3000", quotes), period_start=-1500)
    assert "no quote states -3000" in refused
    other = checked("period_start", TA.block("replace", "-450", quotes), period_start=-1500)
    assert "no quote states -450" in other


def test_a_foreign_quote_without_a_digit_is_a_date_through_its_unit_word() -> None:
    quote = "в V веке до н. э."
    assert not any(c.isdigit() for c in quote)
    assert A.dated(quote)
    answer = checked(
        "period_start",
        TA.block("keep", "-500", [("https://ru.wikipedia.org/wiki/X", quote)]),
        period_start=-449,
    )
    assert answer.decision == "keep"


def test_a_marker_less_quote_no_longer_carries_a_bc_value() -> None:
    quotes = [(WIKI_EN, "the 5th century"), (TA.REGISTER, "built in 1958")]
    refused = checked("period_start", TA.block("replace", "-450", quotes), period_start=None)
    assert isinstance(refused, str) and "no quote states -450" in refused


# ------------------------------------------------------------------------------ the BP phrases
@pytest.mark.parametrize(
    ("language", "quote", "year", "tolerance"),
    [
        ("de", "vor 12.000 Jahren", -10050, 1000),
        ("de", "vor etwa 12.000 Jahren", -10050, 1000),
        ("de", "vor 1,2 Millionen Jahren", -1_198_050, 100_000),
        ("de", "vor 1,2 Mio. Jahren", -1_198_050, 100_000),
        ("de", "12.000 Jahre vor heute", -10050, 1000),
        ("de", "12.000 v. h.", -10050, 1000),
        ("fr", "il y a 12 000 ans", -10050, 1000),
        ("fr", "il y a environ 40 000 ans", -38050, 4000),
        ("fr", "il y a 2 millions d'années", -1_998_050, 200_000),
        ("fr", "12 000 ans AP", -10050, 1000),
        ("fr", "12 000 cal AP", -10050, 1000),
        ("fr", "12 000 ans avant le présent", -10050, 1000),
        ("es", "hace 12.000 años", -10050, 1000),
        ("es", "hace unos 40 mil años", -38050, 4000),
        ("es", "hace 2 millones de años", -1_998_050, 200_000),
        ("es", "12.000 años antes del presente", -10050, 1000),
        ("es", "12 000 años atrás", -10050, 1000),
        ("it", "12.000 anni fa", -10050, 1000),
        ("it", "40 mila anni fa", -38050, 4000),
        ("it", "2 milioni di anni fa", -1_998_050, 200_000),
        ("pt", "há 12 mil anos", -10050, 1000),
        ("pt", "há 2 milhões de anos", -1_998_050, 200_000),
        ("nl", "12.000 jaar geleden", -10050, 1000),
        ("pl", "12 tysięcy lat temu", -10050, 1000),
        ("ru", "12 000 лет назад", -10050, 1000),
        ("ru", "40 тыс. лет назад", -38050, 4000),
        ("ru", "2 млн лет назад", -1_998_050, 200_000),
    ],
)
def test_years_before_the_present_are_read_in_other_languages(
    language: str, quote: str, year: int, tolerance: int
) -> None:
    assert (year, tolerance) in A.bp_dates(quote), (language, quote, A.bp_dates(quote))
    assert A.states_year(quote, year)
    assert not A.states_year(quote, year + tolerance + 1)


def test_a_range_in_another_language_states_each_end() -> None:
    quote = "vor 12.000 bis 10.000 Jahren"
    assert A.states_year(quote, -10050) and A.states_year(quote, -8050)
    assert A.states_year("il y a 12 000 à 10 000 ans", -8050)


@pytest.mark.parametrize(
    "quote",
    [
        "vor 12 Tagen",
        "hace tiempo",
        "il y a des ans",
        "12.000 Jahre alt",
        "ans 12.000 AP news",
        "12 000 anos de idade",
        "12 000 ans ap",  # AP in capitals only
        "Hace 12 años",  # 12 years ago is 1938, the year it states, not a BP year
    ],
)
def test_a_phrase_without_both_number_and_unit_states_no_far_year(quote: str) -> None:
    assert not A.states_year(quote, -10050)


# ------------------------------------------------------------------------------ the tokens
def test_digits_and_letters_are_tokens_of_their_own() -> None:
    assert [t.low for t in D.tokens("449BC and 5th, Ve siècle")] == [
        "449", "bc", "and", "5", "th", "ve", "siecle",
    ]  # fmt: skip
    assert [t.low for t in D.tokens("př. n. l.")] == ["pr", "n", "l"]
    assert [t.low for t in D.tokens("αιώνα")] == ["αιωνα"]


def test_a_minus_sign_is_the_marker_of_a_table_value() -> None:
    assert D.tokens("start date -330")[-1].minus
    assert D.tokens("(−330)")[0].minus
    assert not D.tokens("883-859")[-1].minus  # a range hyphen
    assert not A.states_year("built 1500-500", -500)


def test_an_ad_abbreviation_after_a_before_word_is_a_bc_marker() -> None:
    # not phrases of the table: a "before" word and an AD abbreviation are BC all the same
    for quote in ("450 prije n. l.", "450 pred n. e.", "450 vor n. Chr.", "450 godine pre n. l."):
        assert [(s.era, s.lo) for s in D.statements(quote)] == [("BC", -450)], quote
    assert [(s.era, s.lo) for s in D.statements("5. století před n. e.")] == [("BC", -500)]
    assert [(s.era, s.lo) for s in D.statements("450 n. l.")] == [("AD", 450)]
    assert [(s.era, s.lo) for s in D.statements("450 prije")] == [(None, 450)]


def test_a_marker_made_of_joint_words_ends_a_run_of_years() -> None:
    quote = "Periodo 600 a C y 1000 d C"
    assert A.states_year(quote, -600) and not A.states_year(quote, 600)
    assert A.states_year(quote, 1000) and not A.states_year(quote, -1000)


def test_a_range_of_a_year_and_a_century_needs_a_range_word() -> None:
    assert [s.era for s in D.statements("In 1998 the 3rd century BC walls")] == [None, "BC"]
    assert [s.era for s in D.statements("from 800 to the 7th century BC")] == ["BC", "BC"]
    assert [s.era for s in D.statements("the 8th century - the 7th century BC")] == ["BC", "BC"]
    assert [s.era for s in D.statements("the 8th century, the 7th century BC")] == [None, "BC"]


def test_czech_and_slovak_age_is_no_century_word() -> None:
    assert not D.has_unit_word("bronzový věk")
    assert not A.dated("bronzový věk")
    assert not A.dated("doba kamenná, železný věk a vek")
    assert A.states_year("u V veku pre nove ere", -450)  # Serbian: against a number and a marker
    assert not A.states_year("u V veku", -450)


def test_an_unknown_word_is_no_unit_word() -> None:
    assert not D.has_unit_word("większy kamień")
    assert not D.has_unit_word("an eternal flame, αιώνιος")
    assert D.has_unit_word("в V веке")
    assert D.has_unit_word("III milénio")
    assert D.has_unit_word("MÖ 7. yüzyılda")
    assert not D.has_unit_word("5th c.")  # an abbreviation is no unit word on its own
