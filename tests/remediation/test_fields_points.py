"""Lane wd5 (2026-10-09): the point a coordinate quote holds, in the form the page prints it
(`scripts/remediation/fields/points.py`, read through `answers.quote_point_km`).

The WD5 pilot's Opus spot check found two `unresolved` coordinates where a source printed the point
and only the reader failed: a PLOS ONE appendix table with the header `Long. Lat.` and the row
`K001 Said Qala Tepe 65.5795897 31.5520628 mound`, and the Russian Wikipedia's `16°15′30″ ю. ш.
46°44′27″ з. д.` for the Gruta do Gentio.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from bcases.web_witness import Rejected  # noqa: E402
from fields import answers as A  # noqa: E402
from fields import points as PT  # noqa: E402
from fields import rule as R  # noqa: E402

from tests.remediation import test_fields_answers as TA  # noqa: E402

RU = "https://ru.wikipedia.org/wiki/Жентиу"


def dms(d: int, m: int, s: float = 0.0) -> float:
    return d + m / 60 + s / 3600


# (quote, url, (lat, lon))
READ = (
    # the pilot's two
    (
        "Long. Lat. K001 Said Qala Tepe 65.5795897 31.5520628 mound",
        "https://journals.plos.org/plosone/article/file?type=supplementary",
        (31.5520628, 65.5795897),
    ),
    (
        "16°15′30″\xa0ю.\xa0ш. 46°44′27″\xa0з.\xa0д.",
        RU,
        (-dms(16, 15, 30), -dms(46, 44, 27)),
    ),
    # labelled axes, longitude first
    ("lon 65.5795897, lat 31.5520628", "", (31.5520628, 65.5795897)),
    ("Lon: 65.5795897 Lat: 31.5520628", "", (31.5520628, 65.5795897)),
    ("65.5795897 (lon), 31.5520628 (lat)", "", (31.5520628, 65.5795897)),
    ("Longitude 65.5795897 Latitude 31.5520628", "", (31.5520628, 65.5795897)),
    ("(lon, lat) 65.5795897, 31.5520628", "", (31.5520628, 65.5795897)),
    ("Lng 65.5795897 Lat 31.5520628 Nagara", "", (31.5520628, 65.5795897)),
    # labelled axes, latitude first, with a table row's words around the numbers
    ("Lat. Long. K001 Said Qala Tepe 31.5520628 65.5795897 mound", "", (31.5520628, 65.5795897)),
    ("lat 31.5520628, lon 65.5795897", "", (31.5520628, 65.5795897)),
    ("Latitud 31.5520628 Longitud 65.5795897", "", (31.5520628, 65.5795897)),
    # a bare pair is latitude first, as before
    ("31.5520628, 65.5795897", "", (31.5520628, 65.5795897)),
    ("51.1789, -1.8262", "", (51.1789, -1.8262)),
    # English letters, as before
    ("51°10′44″N 1°49′34″W", "", (dms(51, 10, 44), -dms(1, 49, 34))),
    # Cyrillic hemispheres
    ("55°45′21″ с. ш. 37°37′02″ в. д.", "", (dms(55, 45, 21), dms(37, 37, 2))),
    ("55°45′ с.ш. 37°37′ в.д.", "", (dms(55, 45), dms(37, 37))),
    ("33°52′ ю. ш. 151°12′ в. д.", "", (-dms(33, 52), dms(151, 12))),
    ("40°43′ с. ш. 74°00′ з. д.", "", (dms(40, 43), -dms(74, 0))),
    ("55,7558° с. ш. 37,6173° в. д.", "", (55.7558, 37.6173)),
    ("50°27′ пн. ш. 30°31′ сх. д.", "", (dms(50, 27), dms(30, 31))),
    ("34°30′ пд. ш. 58°24′ зх. д.", "", (-dms(34, 30), -dms(58, 24))),
    ("42°41′ с. ш. 23°19′ и. д.", "", (dms(42, 41), dms(23, 19))),
    ("44°49′ с. г. ш. 20°27′ и. г. д.", "", (dms(44, 49), dms(20, 27))),
    # Czech/Slovak and Hungarian
    ("50°05′ s. š. 14°25′ v. d.", "", (dms(50, 5), dms(14, 25))),
    ("33°52′ j. š. 71°12′ z. d.", "", (-dms(33, 52), -dms(71, 12))),
    ("47° 29′ 56″ é. sz., 19° 02′ 25″ k. h.", "", (dms(47, 29, 56), dms(19, 2, 25))),
    ("34° 36′ d. sz. 58° 24′ ny. h.", "", (-dms(34, 36), -dms(58, 24))),
    # the one-letter hemispheres that differ, by the language of the page
    (
        "48°51′24″ N 2°21′08″ O",
        "https://de.wikipedia.org/wiki/Paris",
        (dms(48, 51, 24), dms(2, 21, 8)),
    ),
    ("52° 31′ N 13° 24′ O", "https://www.beispiel.de/berlin", (dms(52, 31), dms(13, 24))),
    (
        "48°51′24″ N 2°21′08″ O",
        "https://fr.wikipedia.org/wiki/X",
        (dms(48, 51, 24), -dms(2, 21, 8)),
    ),
    ("40°25′ N 3°42′ O", "https://es.wikipedia.org/wiki/Madrid", (dms(40, 25), -dms(3, 42))),
    ("41°54′ N 12°29′ E", "https://it.wikipedia.org/wiki/Roma", (dms(41, 54), dms(12, 29))),
    ("41°54′ N 12°29′ O", "https://it.wikipedia.org/wiki/Roma", (dms(41, 54), -dms(12, 29))),
    ("23°33′ S 46°38′ O", "https://pt.wikipedia.org/wiki/X", (-dms(23, 33), -dms(46, 38))),
    ("23°33′ S 46°38′ L", "https://pt.wikipedia.org/wiki/X", (-dms(23, 33), dms(46, 38))),
    ("52°22′ N 4°54′ O", "https://nl.wikipedia.org/wiki/Amsterdam", (dms(52, 22), dms(4, 54))),
    ("33°52′ Z 151°12′ O", "https://nl.wikipedia.org/wiki/Sydney", (-dms(33, 52), dms(151, 12))),
)


@pytest.mark.parametrize(("quote", "url", "point"), READ)
def test_a_quote_is_read_as_the_page_prints_it(
    quote: str, url: str, point: tuple[float, float]
) -> None:
    lat, lon = PT.quote_point(quote, url)
    assert lat == pytest.approx(point[0], abs=1e-9), quote
    assert lon == pytest.approx(point[1], abs=1e-9), quote


# (quote, url): refused, not guessed
REFUSED = (
    # a bare pair is latitude first, but with words around it and no axis label the order is not
    # the quote's to give
    ("K001 Said Qala Tepe 65.5795897 31.5520628 mound", ""),
    # one label does not say where the other axis is
    ("Long. 65.5795897 31.5520628", ""),
    ("Lat. 31.5520628 Said Qala Tepe 65.5795897", ""),
    # a third decimal is a third number
    ("Long. Lat. K001 65.5795897 31.5520628 elevation 1500.5 m", ""),
    ("Long. Lat. 65.5795897", ""),
    # an O whose language is unknown, and one a language does not decide
    ("48°51′24″ N 2°21′08″ O", ""),
    ("48°51′24″ N 2°21′08″ O", "https://www.example.ch/x"),
    ("48°51′24″ N 2°21′08″ O", "https://en.wikipedia.org/wiki/Paris"),
    # a Z or an L of no language that reads it
    ("33°52′ Z 151°12′ E", "https://en.wikipedia.org/wiki/Sydney"),
    ("23°33′ S 46°38′ L", "https://fr.wikipedia.org/wiki/X"),
    # both axes labelled, but a hemisphere letter on top of a bare number
    ("Long. 65.5795897 E Lat. 31.5520628", ""),
    # a grid reference is still not read, labelled axes or not
    ("Long. Lat. NT 123 456 65.5795897 31.5520628", ""),
    ("UTM 42S 12345678 3456789", ""),
    # off Earth
    ("Long. Lat. 95.5795897 131.5520628", ""),
    # a hemisphere word of no language the table knows
    ("55°45′21″ x. y. 37°37′02″ z. w.", ""),
    # the same axis twice
    ("lon 65.5795897, lon 31.5520628", ""),
)


@pytest.mark.parametrize(("quote", "url"), REFUSED)
def test_a_quote_whose_order_or_letters_are_not_decided_is_refused(quote: str, url: str) -> None:
    with pytest.raises(Rejected):
        PT.quote_point(quote, url)


def test_the_language_of_a_page_is_its_wikipedia_edition_or_its_country() -> None:
    assert PT.language_of("https://de.wikipedia.org/wiki/Paris") == "de"
    assert PT.language_of("https://de.m.wikipedia.org/wiki/Paris") == "de"
    assert PT.language_of("https://fr.wikivoyage.org/wiki/Paris") == "fr"
    assert PT.language_of("https://www.beispiel.at/a") == "de"
    assert PT.language_of("https://www.exemple.fr/a") == "fr"
    assert PT.language_of("https://www.example.com/a") is None
    assert PT.language_of("https://www.example.ch/a") is None
    assert PT.language_of("https://en.wikipedia.org/wiki/X") == "en"
    assert PT.language_of("") is None


def test_what_the_old_reader_read_it_reads_the_same_way() -> None:
    from bcases.web_witness import parse_coordinates

    for quote in (
        "17.5744,-89.9958",
        "Lat/Long 51.754, -0.3579",
        "51.754 (lat), -0.3579 (long)",
        "51°10′44″N 1°49′34″W",
        "N17 13 22.0 W89 37 25.0",
        "Coordinates: 51.1789°N 1.8262°W",
    ):
        assert PT.quote_point(quote) == parse_coordinates(quote), quote


# ------------------------------------------------------------------------------ in an answer
def checked(answer: dict[str, Any], rule: R.Rule = R.RECHECK, **stored: Any) -> Any:
    return A.check_shape(TA.text(coordinates=answer), ["coordinates"], TA.line(**stored), rule)[
        "coordinates"
    ]


def test_the_said_qala_tepe_row_carries_a_replace_answer() -> None:
    """The pilot: the stored point lies about 17 km from the tell the table places at 31.552 N,
    65.580 E."""
    url = "https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0259228.s001"
    quote = "Long. Lat. K001 Said Qala Tepe 65.5795897 31.5520628 mound"
    answer = checked(
        TA.block("replace", "31.5520628, 65.5795897", [(url, quote)]),
        coordinates="31.631140957845208, 65.73780762488191",
    )
    assert answer.decision == "replace"


def test_the_value_must_be_the_point_the_quote_holds_not_its_mirror() -> None:
    url = "https://journals.plos.org/plosone/article/file?id=x"
    quote = "Long. Lat. K001 Said Qala Tepe 65.5795897 31.5520628 mound"
    # the latitude and longitude swapped: 65.58 N, 31.55 E is not the point of the row
    refused = checked(
        TA.block("replace", "65.5795897, 31.5520628", [(url, quote)]),
        coordinates="31.631140957845208, 65.73780762488191",
    )
    assert "km from the value" in refused


def test_the_russian_wikipedia_point_carries_a_replace_answer() -> None:
    quote = "16°15′30″ ю. ш. 46°44′27″ з. д."
    answer = checked(
        TA.block("replace", "-16.258333, -46.740833", [(RU, quote)]),
        coordinates="-16.283473944159716, -46.742282241834836",
    )
    assert answer.decision == "replace"
    # east instead of west is 93 degrees away
    refused = checked(
        TA.block("replace", "-16.258333, 46.740833", [(RU, quote)]),
        coordinates="-16.283473944159716, 46.742282241834836",
    )
    assert "km from the value" in refused


def test_an_o_is_read_by_the_url_of_the_quote_in_an_answer() -> None:
    quote = "48°51′24″ N 2°21′08″ O"
    german = checked(
        TA.block(
            "replace", "48.856667, 2.352222", [("https://de.wikipedia.org/wiki/Paris", quote)]
        ),
        coordinates="48.0, 2.0",
    )
    assert german.decision == "replace"
    french = checked(
        TA.block(
            "replace", "48.856667, 2.352222", [("https://fr.wikipedia.org/wiki/Paris", quote)]
        ),
        coordinates="48.0, 2.0",
    )
    assert "km from the value" in french
    unknown = checked(
        TA.block("replace", "48.856667, 2.352222", [("https://www.example.ch/paris", quote)]),
        coordinates="48.0, 2.0",
    )
    assert "holds no point" in unknown and "does not say" in unknown
