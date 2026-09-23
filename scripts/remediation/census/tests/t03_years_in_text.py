"""T03 - the years a card text states, against the site's own period bucket.

Plan Phase 1 item 3: "Years mentioned in the description text versus `period_start` -
catches contradictions Wikidata cannot see." §9.5 measured *why* this is the deterministic
route: Wikidata's P571 covers 10.3 % of the sites and P580/P582 exactly 0 %, so the
description is the only dating evidence available without an LLM. It is also evidence the
project already trusts - the detail page shows it verbatim as the Google snippet and the
JSON-LD `Place.description` (§15.4).

WHAT COUNTS AS A CLAIM
The checked-in texts carry 7,877 dated claims across 3,971 of the 5,004 sites; the other
1,033 state no year this check can read (many of them date themselves in era words such
as "Neolithic" - see below).
A *dated claim* is a span of years in the text that carries its own era marker:
`BC`/`BCE`/`AD`/`CE`, a century or millennium phrase (`3rd millennium BC`), or a
relative age (`1.2 million years ago`, `10,400 BP`). Both endpoints of a range inherit
the marker that follows it, so `2500-2000 BC` is [-2500, -2000] and `1204-1222 AD` is
[1204, 1222]; a range written across the era boundary (`500 BC - 550 AD`) is read as one
span. Endpoints are converted with `pipeline/normalizers/dates.py::parse_year` - the
project's own BC/AD parser - rather than with a second implementation.

WHAT IS NOT A CLAIM (the false-positive traps, each one seen in production)
* **Bare modern years.** `1998` without an era marker is an excavation, publication or
  designation date, never a period: Kit Hill's description gives the hill away "in 1985",
  Hatunmarka was "declared a Cultural Heritage of the Nation ... in November 2000".
  A bare number is therefore never a claim on its own. It is only *read* at all as the
  second endpoint of a span whose first endpoint carries the marker ("102 BC to AD 350"
  is already one claim; "4300-3900 BC" needs the bare 4300). It inherits the era of the
  marked endpoint, so "4300-3900 BC" cannot become 4300 AD. The same rule disposes of
  "500", which is ambiguous between AD and BC.
* **Anything dated to the modern era.** Every claim whose whole span lies at or after
  1500 AD is dropped: that is the project's own ancient/modern boundary
  (`pipeline/normalizers/dates.py::DATE_CUTOFF_AMERICAS`, the coarsest bucket
  `1500+ AD`) and it is why "first excavated in the 19th century" cannot be mistaken for
  a period statement. Of the 56 sites *in* the `1500+ AD` bucket 6 are flagged anyway -
  their text states an ancient date - and the other 50 pass, because everything they
  say about themselves is modern.
* **Era words without a number.** "used from the Neolithic to the Roman era" is a real
  dating statement, and Eileithyia Cave - a period_start error confirmed in §4.2 - reads
  exactly like that. It is still not a claim here: mapping "Neolithic" to years is
  region-dependent (Britain and the Near East disagree by 5,000 years), the plan's
  §4.3 forbids asserting a bucket from that, and a wrong flag costs more than a missed
  one. This check is deliberately numeric.

WHAT MAKES IT A FINDING
The site declares its period twice - `period_start` and `period_name` - so the declared
window is the union of both buckets (the bucket table is `PERIOD_BUCKETS` from
`pipeline/utils/text.py`, read from the module, not copied). A claim counts as *outside*
when its interval does not meet the declared window. Outside alone is not an error: a
description legitimately reports a later phase, a nearby site, or the publication of a
survey. So a site is flagged only when

    every dated claim in the text is outside the declared window    ("all-outside"), or
    a claim attached to the site's own dating verb is outside
    ("primary-outside"; the verb check is "dates to", "built", "occupied", ... in the
    claim's own clause - a comma, colon or full stop ends the clause - or a date in the
    first 40 characters, which effectively opens the text).

A text that states several periods, one of which is the declared one, is a pass: it
describes a phase, not a contradiction. That is §4.3 pattern 1 in practice - a bucket
value disagrees only when the text puts the site in a *different* bucket.

THE DECLARED EDGE IS NOT A CONTRADICTION
`period_start` sits exactly on a bucket boundary on 75 % of the sites (§3.1), so a text
year that lands on the window's edge is the boundary of a sort key, not a disagreement:
"around 3000 BC" against the bucket `4500 - 3000 BC` reads as the same date to a human
and differs by one year arithmetically. The comparison is therefore inclusive at both
edges. The measured cost of that choice: 254 further sites would flag if the edges were
exclusive, and a sample of them is exactly this boundary class (Wéris Megaliths, Quoyness
Chambered Cairn, Uley Long Barrow, The King's Grave, Bury Ditches). Neos Panteleimonas
then passes too: its §4.2 error is "does not belong in an archaeology database" (a scope
question, not this one), and the only span that could have caught it starts on the declared
edge ("5th century BC to the 5th century AD"). That is the price of a flag list without
one-bucket edge cases in it.

WHICH SIDE IS WRONG IS NOT DECIDED HERE
period_start is a sort key on 75 % of sites (§3.1), so a text that names a precise year
is not automatically the correct one, and a precise year is not automatically a valid
replacement for a bucket boundary. Every finding is therefore Proposal.REVIEW with
Confidence.UNVERIFIABLE and no value: this check finds the contradiction and hands the
question - bucket or text - to Phase 3. Nothing here is ever auto-applicable.

SEVERITY follows §15.4's blast radius. A contradiction in `description` is MODERATE (it
is the indexed snippet, read by whoever searches), SEVERE once the card text carries one
too: `card_stats.card_description` is spoken in every short and captioned in every video,
so a listener hears that contradiction whether or not they open the page. The card gets
its own finding when it is wrong on its own, and lifts the description's to SEVERE when
both are.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from census.model import Confidence, Evidence, Finding, Proposal, Severity

if TYPE_CHECKING:
    from census.run import Context

TEST_ID = "T03"
NAME = "text years vs period bucket"
DIMENSION = "period / description text"

REPO = Path(__file__).resolve().parents[4]

#: The project's ancient/modern boundary: the Americas cut at 1500 AD
#: (`pipeline/normalizers/dates.py`) and the coarsest period bucket starts there.
MODERN_FROM = 1500

#: The two text fields that date a site. `card_stats.card_description` is included
#: because §15.4 lists it as the spoken narration - a contradiction there is heard,
#: not read.
TEXT_FIELDS = ("description", "card_description")
TEXT_SOURCE = {
    "description": "snapshot:unified_sites.description",
    "card_description": "snapshot:card_stats.card_description",
}

#: Words that make a nearby year a statement about the site's own age rather than about
#: one event in its history. `abandoned`/`destroyed` are deliberately absent: they date
#: the end of use, not the site, and "the fort was abandoned in the 5th century BC" must
#: not turn a phase into the site's dating.
_DATING = re.compile(
    r"\b(?:date[sd]?|dating|constructed|erected|built|founded|established|settl\w*|"
    r"occupied|inhabited|in\s+use|flourish\w*|thriv\w*|commissioned|carved|raised|begun)\b",
    re.IGNORECASE,
)

#: A clause boundary: the dating verb must be in the claim's own clause, otherwise
#: "...dates to the 7th-6th century BC. In 900-1250 AD the site was reoccupied" would
#: borrow the verb from the previous sentence and call a later phase a dating claim.
_CLAUSE_BREAK = re.compile(r"[.!?;:,]\s*")

_BC = r"B\.?\s?C\.?(?:\s?E\.?)?"
_AD = r"A\.?\s?D\.?|C\.?\s?E\.?"
_ERA = rf"(?:{_BC}|{_AD})(?![A-Za-z])"
#: 4 and 3 digit groups only - "10,000 BC" is a year, "10.5 BC" is not a thing.
_NUM = r"(?:\d{1,3}(?:[.,]\d{3})+|\d{1,7})"
#: Ages may be fractional where years may not: "1.2 million years ago".
_AGE_NUM = r"(?:\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"

#: What may stand between two mentions of one span: "2500-2000 BC", "500 BC to 550 AD",
#: "9th century BC-10th century AD", "1st century BC to the 7th century AD". Deliberately
#: narrow - words are allowed only if they mean a span, and brackets are excluded so a
#: citation marker ("800 BC to AD 900 [1]") cannot become a span endpoint.
#:
#: A mention written without its own era is held to the connectors only - no filler
#: words, no full stop, no brackets: "between 9100 and 8600 BCE" and "occupied 3600 to
#: 2500 BC" are spans, while "excavated 1963-1989 and c. 800 BC" states two unrelated
#: things and would have invented a 2,000-year phase if fused.
_GAP_BARE = re.compile(r"^(?:[\s\-–—,/]|\b(?:to|until|through|and|or)\b)*$", re.IGNORECASE)

_GAP = re.compile(
    r"^(?:[\s\-–—]|"
    r"\b(?:to|until|through|and|or|the|a|an|between|from|by|in|c|ca|circa|cal|around|"
    r"about|approximately|approx|some|early|mid|middle|late|first|second|half|of|"
    r"B\.?C\.?E?|A\.?D\.?|C\.?E\.?)\b)*$",
    re.IGNORECASE,
)

#: "AD 500" / "CE 500" - the marker in front.
_PRE_ERA = re.compile(rf"(?<![A-Za-z])({_ERA})\s*({_NUM})", re.IGNORECASE)
#: "3000 BC", "10,000 cal. BC" - the ordinary case.
_SINGLE_ERA = re.compile(rf"(?<![0-9])({_NUM})\s*(?:cal\.?\s*)?({_ERA})", re.IGNORECASE)
#: "1.2 million years ago", "10,400 BP", "14,800 and 10,500 years ago", "1,000-2,000
#: years old" - the age expression governs the whole span, so a leading endpoint is
#: captured with it rather than merged in afterwards.
_AGE = re.compile(
    rf"(?<![0-9.,])(?:({_AGE_NUM})\s*(?:[-–—]|to|until|through|and)\s*)?({_AGE_NUM})\s*"
    r"(million|billion|thousand|k)?\s*(?:years?\s*)?"
    r"(?:ago|before\s+present|\bBP\b|\bold\b)",
    re.IGNORECASE,
)
#: "3rd millennium BC", "19th century" (the marker is optional - see below).
_ORDINAL_PERIOD = re.compile(
    r"(?<![A-Za-z0-9])(\d{1,2})(?:st|nd|rd|th)?[-\s]*(centur(?:y|ies)|millenni(?:um|a))"
    rf"(?![A-Za-z])\s*({_ERA})?",
    re.IGNORECASE,
)

#: "5th to 3rd millennium BC" - the first ordinal carries no unit of its own, so the
#: span would otherwise collapse to its later half and read as a contradiction.
_ORDINAL_RANGE = re.compile(
    r"(?<![A-Za-z0-9])(\d{1,2})(?:st|nd|rd|th)?\s*(?:[-–—]|to|until|through|and)"
    r"\s*(\d{1,2})(?:st|nd|rd|th)?[-\s]*(centur(?:y|ies)|millenni(?:um|a))"
    rf"(?![A-Za-z])\s*({_ERA})?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Mention:
    """One dated claim: an inclusive year interval plus what it was read from."""

    lo: int
    hi: int
    raw: str
    marked: bool  #: carried BC/BCE/AD/CE/BP/"years ago" - i.e. decidable on its own
    primary: bool  #: attached to the site's own dating verb, or opens the text
    back: bool = False  #: written in BC reckoning, so a bare neighbour counts backwards too

    @property
    def modern(self) -> bool:
        """Wholly at or after the project's ancient/modern boundary."""
        return self.lo >= MODERN_FROM


def _buckets() -> list[tuple[str, int, int]]:
    """The project's period buckets, imported from the module that defines them."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from pipeline.utils.text import PERIOD_BUCKETS

    return list(PERIOD_BUCKETS)


def _parse_year(value: Any) -> int | None:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from pipeline.normalizers.dates import parse_year

    return parse_year(value)


def _bucket_of(year: int, buckets: list[tuple[str, int, int]]) -> str:
    """Bucket label for a year, by iterating the table rather than calling the helper.

    `pipeline/utils/text.py::categorize_period()` fell through to `"1500+ AD"` for any
    year below the table's floor (-999999) until 2026-09-22, which mislabelled the three
    sites at -1,400,000 (Atapuerca Mountains, Archaeological Site of Atapuerca, Barranco
    León - all three carry `period_name = '< 4500 BC'` in the snapshot); it now compares
    upper bounds only, as the frontend does. This walk stays because it is parameterised by
    the table the census reports on. A year below the first bucket belongs to the first
    bucket: it is the table's catch-all for the deep past.
    """
    for label, lo, hi in buckets:
        if lo <= year < hi:
            return label
    return buckets[0][0] if year < buckets[0][1] else buckets[-1][0]


def _year(token: str) -> int:
    """Digits with the thousand separators stripped, via the project's own parser."""
    cleaned = token.replace(",", "")
    year = _parse_year(cleaned)
    if year is None:
        # The extractor only emits digit groups, so this is a bug in this module, not
        # data. Crash loudly: a silently dropped claim would understate the flag list.
        raise AssertionError(f"parse_year({cleaned!r}) returned None for a digit token")
    return year


def _mentions(text: str) -> list[_Mention]:
    """Every dated claim in `text`, longest match winning where patterns overlap."""
    found: list[tuple[int, int, _Mention]] = []

    def add(
        start: int, end: int, lo: int, hi: int, raw: str, marked: bool = True, back: bool = False
    ) -> None:
        # The era patterns accept the dotted abbreviations, so they swallow a
        # sentence-final full stop too ("occupied in the 3rd century AD. By the 12th
        # century ..."). The span must not keep it, or the merge below would read
        # across the sentence boundary.
        while end > start and text[end - 1] == ".":
            end -= 1
        # The claim's own clause only; see _CLAUSE_BREAK.
        head = text[:start]
        opens = [m.end() for m in _CLAUSE_BREAK.finditer(head)]
        clause = head[opens[-1] :] if opens else head
        primary = start < 40 or bool(_DATING.search(clause))
        found.append(
            (start, end, _Mention(min(lo, hi), max(lo, hi), raw.strip(". "), marked, primary, back))
        )

    for m in _PRE_ERA.finditer(text):
        year = _era_year(m.group(2), m.group(1))
        add(m.start(), m.end(), year, year, m.group(0), back=_is_bc(m.group(1)))

    for m in _SINGLE_ERA.finditer(text):
        year = _era_year(m.group(1), m.group(2))
        add(m.start(), m.end(), year, year, m.group(0), back=_is_bc(m.group(2)))

    for m in _AGE.finditer(text):
        mult = _multiplier(m.group(3))
        year = _age_years(m.group(2), mult)
        # A leading endpoint inherits the age expression: "14,800 and 10,500 years ago".
        lo = _age_years(m.group(1), mult) if m.group(1) else year
        add(m.start(), m.end(), lo, year, m.group(0))

    for m in _ORDINAL_RANGE.finditer(text):
        later = _ordinal_years(m.group(2), m.group(3), m.group(4))
        earlier = _ordinal_years(m.group(1), m.group(3), m.group(4))
        add(
            m.start(),
            m.end(),
            min(later[0], earlier[0]),
            max(later[1], earlier[1]),
            m.group(0),
            marked=bool(m.group(4)),
            back=_is_bc(m.group(4)),
        )

    for m in _ORDINAL_PERIOD.finditer(text):
        lo, hi = _ordinal_years(m.group(1), m.group(2), m.group(3))
        # An unmarked "3rd century" is ambiguous between AD and BC, so it is kept
        # unmarked and dropped by run(); "19th century" is unambiguous only because the
        # modern-era rule removes it.
        add(
            m.start(), m.end(), lo, hi, m.group(0), marked=bool(m.group(3)), back=_is_bc(m.group(3))
        )

    # Bare numbers are collected last and only as endpoints of a span: on their own they
    # are measurements, dates of excavation or prices (the modern trap), never a period.
    covered = [(start, end) for start, end, _ in found]
    for m in re.finditer(rf"(?<![0-9])({_NUM})(?![0-9])(?!(?:st|nd|rd|th)\b)", text):
        if any(m.start() < e and s < m.end() for s, e in covered):
            continue
        add(m.start(), m.end(), _year(m.group(1)), _year(m.group(1)), m.group(0), marked=False)

    # Greedy longest-first: a range must beat the single year inside it.
    kept: list[tuple[int, int, _Mention]] = []
    for item in sorted(found, key=lambda t: (t[0], -(t[1] - t[0]))):
        start, end, _ = item
        if any(start < e and s < end for s, e, _ in kept):
            continue
        kept.append(item)
    kept.sort(key=lambda t: t[0])

    # Merge neighbours that are separated by span words only, so that "800 BC to AD 900",
    # "2500-2000 BC" and "9th century BC-10th century AD" are read as the single spans
    # their authors wrote.
    out: list[_Mention] = []
    start_of = 0
    end_of = 0
    for start, end, mention in kept:
        if out and 0 <= start - end_of <= 30 and _joinable(out[-1], mention, text[end_of:start]):
            out[-1] = _merge(out[-1], mention, text[start_of:end])
            end_of = end
            continue
        out.append(mention)
        start_of, end_of = start, end
    return out


def _joinable(prev: _Mention, nxt: _Mention, gap: str) -> bool:
    """May two mentions this far apart be one span? See _GAP and _GAP_BARE."""
    pattern = _GAP if prev.marked and nxt.marked else _GAP_BARE
    return bool(pattern.match(gap))


def _is_bc(era: str | None) -> bool:
    if not era:
        return False
    return bool(re.match(rf"^{_BC}$", era, re.IGNORECASE))


def _merge(prev: _Mention, nxt: _Mention, raw: str) -> _Mention:
    """Two mentions joined by span words only: "2500-2000 BC", "800 BC to AD 900".

    An endpoint written without its era inherits the era of the marked endpoint, so
    "4300-3900 BC" cannot turn 4300 into 4300 AD.
    """
    back = any(m.back for m in (prev, nxt) if m.marked)
    years: list[int] = []
    for m in (prev, nxt):
        lo, hi = m.lo, m.hi
        if back and not m.marked:
            lo, hi = -abs(lo), -abs(hi)
        years += [min(lo, hi), max(lo, hi)]
    return _Mention(
        min(years), max(years), raw, prev.marked or nxt.marked, prev.primary or nxt.primary, back
    )


def _era_year(token: str, era: str) -> int:
    """`("500", "BC")` -> -500, using parse_year's own BC/AD handling."""
    return _year(f"{token} {'BC' if _is_bc(era) else 'AD'}")


def _multiplier(word: str | None) -> int:
    return {"million": 10**6, "billion": 10**9}.get((word or "").lower(), 10**3 if word else 1)


def _age_years(token: str, mult: int) -> int:
    """Relative age in years -> year AD, taking 1950 as the reference epoch (BP)."""
    amount = float(token.replace(",", "")) * mult
    return int(round(1950 - amount))


def _ordinal_years(ordinal: str, unit: str, era: str | None) -> tuple[int, int]:
    """Century/millennium ordinal -> inclusive interval. 5th century BC = -500..-401."""
    n = int(ordinal)
    width = 100 if unit.lower().startswith("centur") else 1000
    if _is_bc(era):
        return -width * n, -width * (n - 1) - 1
    return width * (n - 1), width * n - 1


def _claims(text: str) -> list[_Mention]:
    """Dated claims that a bucket comparison may use: era-marked and not modern."""
    return [m for m in _mentions(text) if m.marked and not m.modern]


def _bounds(label: str, buckets: list[tuple[str, int, int]]) -> tuple[int, int]:
    for name, lo, hi in buckets:
        if name == label:
            return lo, hi
    # Unreachable: every label reaching this comes from _bucket_of or PERIOD_BUCKETS.
    raise AssertionError(f"unknown period bucket {label!r}")


def _window(
    site: dict[str, Any], buckets: list[tuple[str, int, int]]
) -> list[tuple[str, int, int]]:
    """The periods the site declares, as `(label, lo, hi)` spans.

    Both period fields are read because they disagree on 4 of 5,004 sites (§3.1). The
    span starts at `period_start` itself when that lies below the table's floor, so the
    three sites at -1,400,000 keep their own start instead of the first bucket's
    -999999.
    """
    out: list[tuple[str, int, int]] = []
    start = _parse_year(site.get("period_start"))
    if start is not None:
        label = _bucket_of(start, buckets)
        lo, hi = _bounds(label, buckets)
        out.append((label, min(start, lo), hi))
    name = (site.get("period_name") or "").strip()
    # 1 site carries the non-canonical "> 1500 AD" (§3.1); it is not a bucket and
    # period_start alone decides that one.
    if name in {b[0] for b in buckets} and all(name != o[0] for o in out):
        lo, hi = _bounds(name, buckets)
        out.append((name, lo, hi))
    return out


def _touches(mention: _Mention, window: list[tuple[str, int, int]]) -> bool:
    """Does the claim meet any declared span?

    The comparison is inclusive at both ends: on 75% of the sites `period_start` sits
    exactly on a bucket boundary (§3.1), so a text year landing on that boundary is a
    sort key, not a contradiction (§4.3 pattern 1).
    """
    return any(lo <= mention.hi and mention.lo <= hi for _, lo, hi in window)


def applies_to(site: dict[str, Any], ctx: Context) -> bool:
    """A site with no usable period cannot contradict one."""
    return bool(_window(site, _buckets()))


def run(ctx: Context) -> list[Finding]:
    buckets = _buckets()
    cards = ctx.snap.by("card_stats")

    findings: list[Finding] = []
    for site in ctx.sites:
        sid = str(site["id"])
        window = _window(site, buckets)
        if not window:
            continue  # applies_to() reports these as not_applicable
        declared = ", ".join(sorted({w[0] for w in window}))

        card = (cards.get(sid) or [{}])[0]
        texts = {
            "description": site.get("description") or "",
            "card_description": card.get("card_description") or "",
        }

        verdicts: dict[str, list[_Mention]] = {}
        all_claims: dict[str, list[_Mention]] = {}
        for field in TEXT_FIELDS:
            claims = _claims(texts[field])
            all_claims[field] = claims
            if not claims:
                continue
            outside = [c for c in claims if not _touches(c, window)]
            if not outside:
                continue
            if len(outside) < len(claims) and not any(c.primary for c in outside):
                # The text tells a longer story and its own dating agrees with the
                # site's bucket: an isolated later claim is a later phase, not a
                # contradiction (§4.3 pattern 1).
                continue
            verdicts[field] = outside

        if not verdicts:
            continue

        in_card = "card_description" in verdicts
        field = "card_description" if (in_card and "description" not in verdicts) else "description"
        # §15.4: the card text is spoken in every short, the description is only the
        # indexed snippet. A contradiction the card repeats reaches a listener.
        severity = Severity.SEVERE if in_card else Severity.MODERATE
        outside = verdicts[field]
        kind = "all-outside" if len(outside) == len(all_claims[field]) else "primary-outside"
        reported = outside if len(outside) < len(all_claims[field]) else all_claims[field]
        site_period = (
            f"period_start={site.get('period_start')!r}, period_name={site.get('period_name')!r}"
        )
        quoted = "; ".join(m.raw for m in reported[:3])
        seen = sorted({b for m in reported for b in _buckets_of(m, buckets)})

        findings.append(
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/{kind}",
                field=field,
                severity=severity,
                dimension=DIMENSION,
                current_value=site_period,
                proposal=Proposal.REVIEW,
                confidence=Confidence.UNVERIFIABLE,
                note=f"{field} dates the site to {quoted} ({', '.join(seen)}), but the "
                f"declared period is {declared} - a reviewer must decide whether the "
                "bucket or the text is wrong",
                evidence=[
                    Evidence(source=TEXT_SOURCE[field], quote=quoted),
                    Evidence(source="snapshot:unified_sites", quote=site_period),
                    Evidence(
                        source="pipeline/utils/text.py:PERIOD_BUCKETS",
                        quote=f"{quoted} -> {', '.join(seen)}; declared {declared}",
                    ),
                ],
            )
        )

    return findings


def _buckets_of(mention: _Mention, buckets: list[tuple[str, int, int]]) -> set[str]:
    """Every bucket the claim's interval touches - all of them, not just the endpoints'.

    A span as wide as "8th century BC to the 17th century AD" covers the bucket between
    its endpoints; testing the endpoints alone would call it outside a window it crosses.
    """
    out = {label for label, lo, hi in buckets if lo <= mention.hi and mention.lo < hi}
    out.add(_bucket_of(mention.lo, buckets))
    out.add(_bucket_of(mention.hi, buckets))
    return out
