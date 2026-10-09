"""The point a coordinate quote holds, in the form the page prints it (lane WD5, 2026-10-09).

`bcases.web_witness.parse_coordinates` reads the two forms an English page prints - signed decimals,
latitude first, and degrees with `N`/`S`/`E`/`W` - and nothing else around them but labels. The WD5
pilot (Opus spot check, 2026-10-09) found two `unresolved` coordinates where a source printed the
point and only that reader failed:

* **Said Qala Tepe** - a PLOS ONE appendix table whose header says `Long. Lat.`, the row
  `K001 Said Qala Tepe 65.5795897 31.5520628 mound`: the longitude comes first, and the row holds the
  site's name and type beside the numbers;
* **Gruta do Gentio** - the Russian Wikipedia's `16°15′30″ ю. ш. 46°44′27″ з. д.`: the hemispheres
  are Russian letters.

`quote_point` reads what `parse_coordinates` reads, unchanged, and then:

* **localised hemispheres**: Cyrillic `с. ш.`/`ю. ш.`/`в. д.`/`з. д.` (also Ukrainian `пн. ш.`,
  `пд. ш.`, `сх. д.`, `зх. д.`, Bulgarian `и. д.`, Serbian `с. г. ш.`...), Czech and Slovak `s. š.`,
  `j. š.`, `v. d.`, `z. d.`, Hungarian `é. sz.`, `d. sz.`, `k. h.`, `ny. h.`, and the one-letter
  forms that differ from English: German `O` (Ost, east), French, Spanish, Italian, Catalan and
  Galician `O` (ouest/oeste/ovest, west), Portuguese `L` (leste, east) and `O` (west), Dutch `Z`
  (zuid, south) and `O` (oost, east). A letter that means east in one language and west in another
  is read by the page's language (`language_of`: a Wikipedia language edition or a country domain);
  where that is unknown the quote is refused, not guessed. A decimal comma before the degree sign
  (`16,2583° ю. ш.`) is a decimal point;
* **an axis order the quote labels**: two bare decimals with an axis label for each. `Long. Lat.`
  before the numbers, or `lon 65.58, lat 31.55`, or `65.58 (lon), 31.55 (lat)` is longitude first;
  the other order is latitude first. Words around the numbers (a table row's id, name and type) are
  allowed here, because the labels, not the words, say what the numbers are; the quote must still
  hold exactly two bare decimals, and a grid reference is refused as before. A bare pair with no
  labels stays latitude first, and a pair whose order the quote does not label while words surround
  it is refused.
"""

from __future__ import annotations

import re

from bcases.web_witness import Rejected, normalise, parse_coordinates

#: A hemisphere written as the letters of a language other than English, after a number: pattern ->
#: the English letter. Only forms that can be nothing else beside a degree value.
_LOCAL_HEMISPHERES = (
    (r"с\.?\s?г\.?\s?ш\.?|пн\.?\s?ш\.?|с\.?\s?ш\.?|s\.\s?š\.|é\.\s?sz\.", "N"),
    (r"ј\.?\s?г\.?\s?ш\.?|пд\.?\s?ш\.?|ю\.?\s?ш\.?|j\.\s?š\.|d\.\s?sz\.", "S"),
    (r"и\.?\s?г\.?\s?д\.?|сх\.?\s?д\.?|в\.?\s?д\.?|и\.?\s?д\.?|v\.\s?d\.|k\.\s?h\.", "E"),
    (r"з\.?\s?г\.?\s?д\.?|зх\.?\s?д\.?|з\.?\s?д\.?|z\.\s?d\.|ny\.\s?h\.", "W"),
)
#: What a hemisphere letter stands after: a digit, a degree, minute or second sign.
_AFTER_NUMBER = r"(?<=[\d°'\"])\s*"
_ONE_LETTER = re.compile(_AFTER_NUMBER + r"(?P<letter>[OZL])(?![^\W\d_])")
#: The letters that differ from English, by the page's language: letter -> language -> hemisphere.
#: `O` is east in German ("Ost") and Dutch ("oost"), west in French, Spanish, Italian, Catalan,
#: Galician and Portuguese ("ouest", "oeste", "ovest", "oest"); `L` is Portuguese "leste" (east);
#: `Z` is Dutch "zuid" (south).
_LETTERS = {
    "O": {"de": "E", "nl": "E", "fr": "W", "es": "W", "it": "W", "ca": "W", "gl": "W", "pt": "W"},
    "L": {"pt": "E"},
    "Z": {"nl": "S"},
}
_LANGUAGE_HOST = re.compile(r"^([a-z]{2,3})(?:\.m)?\.(?:wikipedia|wikivoyage)\.org$")
_LANGUAGE_TLD = {
    "de": "de", "at": "de", "nl": "nl", "fr": "fr", "es": "es", "it": "it", "pt": "pt", "br": "pt",
}  # fmt: skip
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d+\s*°)")

_LAT_LABELS = ("latitude", "latitud", "latitudine", "lat", "breitengrad", "широта")
_LON_LABELS = (
    "longitude",
    "longitud",
    "longitudine",
    "long",
    "lon",
    "lng",
    "laengengrad",
    "долгота",
)
_LABEL = re.compile(
    r"(?<![^\W\d_])(?P<word>"
    + "|".join(sorted(_LAT_LABELS + _LON_LABELS, key=len, reverse=True))
    + r")\.?(?![^\W\d_])",
    re.IGNORECASE,
)
_BARE_DECIMAL = re.compile(r"(?<![\w.])(?P<value>[+-]?\d+\.\d+)(?![\w.])")
_LONE_HEMISPHERE = re.compile(r"(?<![^\W\d_])[NSEW](?![^\W\d_])")
#: What may stand between a label and its number: separators only.
_BEFORE_NUMBER = re.compile(r"^[\s:=,;(\[/]*$")
_AFTER_NUMBER_LABEL = re.compile(r"^\s*[(\[]\s*$")


def language_of(url: str) -> str | None:
    """The language of the page a quote is from, when its address says it: a Wikipedia or Wikivoyage
    language edition (`de.wikipedia.org`), or a domain of one country (`.de`, `.fr`...). None
    otherwise - a `.ch` or `.be` page may be in either of two languages."""
    host = re.sub(r"^https?://", "", url.strip().lower()).split("/")[0].split(":")[0]
    found = _LANGUAGE_HOST.match(host)
    if found:
        return found.group(1)
    return _LANGUAGE_TLD.get(host.rsplit(".", 1)[-1])


def localise(text: str, url: str = "") -> str:
    """`text` with a hemisphere written in another language's letters rewritten as `N`, `S`, `E` or
    `W`. `Rejected` for a one-letter hemisphere that the page's language does not decide."""
    text = _DECIMAL_COMMA.sub(".", text)
    for pattern, letter in _LOCAL_HEMISPHERES:
        text = re.sub(
            _AFTER_NUMBER + f"(?:{pattern})(?![^\\W\\d_])", f" {letter}", text, flags=re.I
        )

    language = language_of(url)

    def one_letter(match: re.Match[str]) -> str:
        letter = match["letter"]
        hemisphere = _LETTERS[letter].get(language or "")
        if hemisphere is None:
            if letter == "O":
                raise Rejected(
                    "unparsed",
                    "a hemisphere written O is east in German and Dutch and west in French, "
                    f"Spanish, Italian and Portuguese: the page's language ({url!r}) does not say",
                )
            return match.group(0)  # a Z or an L of no known language stays a stray letter
        return f" {hemisphere}"

    return _ONE_LETTER.sub(one_letter, text)


def _labelled(text: str) -> tuple[float, float] | None:
    """The point of two bare decimals whose axes the quote labels, or None when it does not."""
    if _LONE_HEMISPHERE.search(text):
        return None
    numbers = list(_BARE_DECIMAL.finditer(text))
    labels = list(_LABEL.finditer(text))
    if len(numbers) != 2 or len(labels) < 2:
        return None

    def axis(label: re.Match[str]) -> str:
        return "lat" if label["word"].casefold() in _LAT_LABELS else "lon"

    # each number has a label of its own right before it ("lon 65.58, lat 31.55") or right after it
    # ("65.58 (lon), 31.55 (lat)")
    found: list[str] = []
    for number in numbers:
        before = [label for label in labels if label.end() <= number.start()]
        after = [label for label in labels if label.start() >= number.end()]
        if before and _BEFORE_NUMBER.match(text[before[-1].end() : number.start()]):
            found.append(axis(before[-1]))
        elif after and _AFTER_NUMBER_LABEL.match(text[number.end() : after[0].start()]):
            found.append(axis(after[0]))
        else:
            break
    else:
        if set(found) == {"lat", "lon"}:
            return _point(found, numbers)
    # or the labels head the numbers, in the order the numbers follow: "Long. Lat. K001 Said Qala
    # Tepe 65.5795897 31.5520628 mound"
    if len(labels) == 2 and labels[1].end() <= numbers[0].start():
        order = [axis(labels[0]), axis(labels[1])]
        if set(order) == {"lat", "lon"}:
            return _point(order, numbers)
    return None


def _point(axes: list[str], numbers: list[re.Match[str]]) -> tuple[float, float]:
    by_axis = {a: float(n["value"]) for a, n in zip(axes, numbers, strict=True)}
    lat, lon = by_axis["lat"], by_axis["lon"]
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise Rejected("unparsed", f"{lat}, {lon} is not a point on Earth")
    return lat, lon


def quote_point(quote: str, url: str = "") -> tuple[float, float]:
    """`(lat, lon)` the quote holds, or `Rejected`: what `parse_coordinates` reads, with the
    hemisphere letters of other languages rewritten first (`localise`) and a longitude-first pair
    read when the quote labels its axes (`_labelled`). A grid reference is refused as it always
    was, and so is a pair whose order the quote does not label while words surround it."""
    text = localise(normalise(quote), url)
    try:
        return parse_coordinates(text)
    except Rejected as refused:
        if refused.code == "grid-reference":
            raise
        point = _labelled(text)
        if point is None:
            raise
        return point
