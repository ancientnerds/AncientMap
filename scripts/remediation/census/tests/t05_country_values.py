"""T05 - every `country` is a country, under a spelling the project itself uses.

`unified_sites.country` is not free text. It is

* the last path segment of an indexed hub page per value - `/sites/{country}` is built
  from `country_path()` (`api/routes/sites_html.py:39-144`; live today:
  "Archaeological Sites in Georgia (country) (27)"),
* a filter entry on the globe, taken from the raw value by `extractCountry()`
  (`App.tsx:1132-1135`, `ancient-nerds-map/src/utils/searchUtils.ts:26-31`),
* the closing line the narrator speaks - `spoken_name()` appends the *last* comma part of
  the value and reads a parenthetical verbatim (`pipeline/video/shorts_tts.py:21-34`),
* an answer in the card game's "What country is X in?" quiz (`api/cardgame/quiz.py:60-91`)
  and the grouping key of its synergy rules (`api/cardgame/synergies.py:169-179`).

Every one of those consumers compares the string literally, so two spellings of one
country are two countries to the app. The whole vocabulary was therefore enumerated from
the snapshot first - 98 distinct values, 0 NULL, no leading or trailing whitespace, no
value that is not NFC, exactly one parenthetical and one comma - and every value
classified against the two vocabularies the project itself ships:

* `pipeline/utils/country_lookup.py::NAME_TO_ISO` (line 296) with `normalize_country()`
  (line 542) - the mapping the API uses (`api/cardgame/routes.py:104`,
  `api/routes/news.py:245`);
* `ancient-nerds-map/src/utils/countryFlags.ts::COUNTRY_CODES` (line 52) with
  `getCountryCode()` (line 338) - flags and continents in the UI, mirrored a second time
  by `pipeline/video/shorts_export.py::country_code_for` (line 48).

Both are read from source at run time, never copied. A value counts as recognised when at
least one vocabulary knows it; a value in neither is unusable in both surfaces (no flag
and no ISO code), and that is what this check reports.

The plan's Phase 1 item 5 names three defects, and the enumeration reproduces its counts
exactly: `Georgia (country)` 27, `Chile, Easter Island` 8, `Baltic Sea` 1. Three further
classes are not in the plan: `USA` 28 (the same country as `United States` 1, in two hub
pages and two filter entries), `Northern Ireland` 4 (in neither vocabulary, which the
plan's own S6 criterion counts as a failure) and `Republic of The Gambia` 2 (the long
official form, where both vocabularies also carry `Gambia`/`The Gambia`).

What this check refuses to do:

* It never guesses a country. `Baltic Sea` is a place, not a country; which coastal
  state's waters the site sits in is a point-in-polygon question (T02) or a human's, so
  the finding carries no value. CLEAR would be a guess too: it would drop the row out of
  every `/sites/{country}` hub and out of the globe's country filter
  (`api/routes/sites_html.py:39`) and lose the only location label the row carries.
* It never flattens deliberate design. `England`, `Wales` and `Scotland` are project
  design, not a bug (plan §4.3.2): both vocabularies map them to GB and they pass.
* It never modernises a historical entity. A site inside the Ottoman Empire may properly
  be labelled that way, so an unknown value - the fallback for anything this module
  cannot place - goes to REVIEW, never to a present-day replacement. No such value exists
  in this snapshot; that branch is the guard, not the result.

Provenance of the proposal guard. T04 can prove durability because
`pipeline/lyra/orchestrator.py` rewrites `site_type` on every container boot. `country`
has no such rewriter: the boot-time patch `pipeline/lyra/data_patches.py:46-62` (called
from `orchestrator.py:1061-1064`) sets `country` only where it `IS NULL` and
`source_id = 'lyra'`, so it can never revert a value this check repairs. The guard here is
therefore the weaker but still real one: a proposed value must (a) be a key of
`COUNTRY_CODES`, (b) resolve to an ISO-3166 alpha-2 code through `normalize_country()`,
(c) resolve to the SAME code as the value it replaces, and (d) be a fixed point of this
module's own classifier. A replacement the project reads as a different country - or one
this check would flag again on the next run - raises instead of being emitted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from census.model import Confidence, Evidence, Finding, Proposal, Severity

if TYPE_CHECKING:
    from census.run import Context

TEST_ID = "T05"
NAME = "country is a country, spelled the way the project spells it"
DIMENSION = "classification / country"

REPO = Path(__file__).resolve().parents[4]
FLAGS_TS = REPO / "ancient-nerds-map" / "src" / "utils" / "countryFlags.ts"
LOOKUP = "pipeline/utils/country_lookup.py"
FLAGS = "ancient-nerds-map/src/utils/countryFlags.ts:COUNTRY_CODES"
PLAN = "docs/procedures/SITES_DB_REMEDIATION_2026-09.md"

_KEY_RE = re.compile(r"""^\s*(?:'([^']+)'|"([^"]+)")\s*:\s*'([A-Za-z0-9]+)'""", re.M)

#: A source that knows both the country and a same-named US state writes the country as
#: `Georgia (country)`. Stripping the parenthetical is allowed only when the bare name is
#: a country both vocabularies know under the same ISO code - that is what makes it a
#: repair rather than a guess, so the rule is checked, not assumed.
_DISAMBIGUATED = re.compile(
    r"^(?P<plain>.+?)\s+\((?P<hint>country|state|nation|republic)\)$", re.IGNORECASE
)

#: Hand-decided replacements, each verified by `_verify()` before it is emitted. Kept
#: explicit rather than derived: which part of a compound label is the country is a
#: judgement, and the plan's Phase 1 item 5 has made it (the part before the comma).
REWRITES: dict[str, str] = {
    "Chile, Easter Island": "Chile",
}

#: Values with no replacement a snapshot can prove: value -> (class, reason). Each
#: reason is a fact verified against the code, not a preference. REVIEW carries no value
#: (the model raises on that), so nothing here can be written automatically.
BY_HAND: dict[str, tuple[str, str]] = {
    "Baltic Sea": (
        "not-a-country",
        (
            "the value is a sea, not a country - the row is an underwater structure "
            "(61.377 / 18.448) and which coastal state's waters those are is T02's "
            "point-in-polygon answer or a human's, not something this check may guess; "
            "CLEAR would also drop the site out of every /sites/{country} hub"
        ),
    ),
    "Northern Ireland": (
        "vocabulary-gap",
        (
            "in neither vocabulary, although the other three constituent countries of the UK "
            "are: no COUNTRY_CODES key, so no flag, and normalize_country() returns "
            "'northern ireland', not an ISO code - the plan's S6 counts exactly these 4 rows "
            "as failures. The value itself matches the deliberate local-name design "
            "(plan §4.3.2), so the gap is in the two vocabularies and no data change is safe"
        ),
    ),
    "USA": (
        "spelling-split",
        (
            "abbreviation of a country the snapshot also spells 'United States' (1 site, "
            "which this check leaves alone): one country in two hub pages (/sites/usa and "
            "/sites/united-states) and two entries in the globe's country filter. Both "
            "spellings are keys of COUNTRY_CODES and both map to US, so nothing is broken - "
            "which spelling wins is a display decision no module in the repo declares"
        ),
    ),
    "Republic of The Gambia": (
        "official-long-form",
        (
            "the long official form; both vocabularies carry it (COUNTRY_CODES by its "
            "case-insensitive pass, NAME_TO_ISO as 'republic of the gambia') and also carry "
            "the short display forms 'Gambia' and 'The Gambia', so the indexed hub title "
            "reads 'Archaeological Sites in Republic of The Gambia'. Which short form is "
            "wanted is a display decision; the row is not wrong"
        ),
    ),
}


class _Verdict(NamedTuple):
    """One classification per distinct value; `proposed_value` is None for every REVIEW."""

    proposal: Proposal
    proposed_value: str | None
    severity: Severity
    slug: str
    note: str
    evidence: tuple[Evidence, ...]


def _vocabulary() -> tuple[dict[str, str], Any]:
    """`COUNTRY_CODES` and `normalize_country`, taken from the real sources."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from pipeline.utils.country_lookup import normalize_country

    text = FLAGS_TS.read_text(encoding="utf-8")
    block = re.search(r"COUNTRY_CODES[^=]*=\s*\{(.*?)\n\}", text, re.S)
    if not block:
        raise RuntimeError(f"cannot locate COUNTRY_CODES in {FLAGS_TS}")
    codes = {a or b: c for a, b, c in _KEY_RE.findall(block.group(1))}
    if len(codes) < 200:  # the map holds 254 entries; a partial parse must not pass silently
        raise RuntimeError(f"parsed only {len(codes)} country codes from {FLAGS_TS}")
    return codes, normalize_country


def _iso(value: str, normalize: Any) -> str | None:
    """The project's own answer, or None when it has none.

    `normalize_country()` returns the lowercased name for anything it does not know
    (`country_lookup.py:560`); treating that passthrough as an answer is how "4,999 of
    5,004 sites yield an ISO code" would write itself into a report as a false pass.
    """
    code = normalize(value)
    return code if len(code) == 2 and code.isalpha() and code.isupper() else None


def _flag_code(value: str, codes: dict[str, str]) -> str | None:
    """Mirror of `getCountryCode()` (countryFlags.ts:338-377): exact, case-insensitive,
    then the last comma part.

    Mirrored rather than assumed, because the case-insensitive pass is not cosmetic:
    the frontend carries `Georgia (country)` as `'Georgia (Country)'`, so its flag DOES
    render and the defect there is the display form, not a missing flag. Assuming the
    opposite would have turned 27 rows into a wrong claim.
    """
    if value in codes:
        return codes[value]
    lower = value.lower()
    for name, code in codes.items():
        if name.lower() == lower:
            return code
    if "," in value:
        part = value.split(",")[-1].strip()
        if part in codes:
            return codes[part]
        for name, code in codes.items():
            if name.lower() == part.lower():
                return code
    return None


def _display_name(plain: str, codes: dict[str, str]) -> str | None:
    """The project's own spelling of a bare country name, or None if it has none.

    The proposal must be that spelling, not the substring that happened to be in the
    row: `Georgia (country)` stripped of its hint is still `Georgia`, but a row that
    reads `georgia (country)` must not be repaired to lowercase `georgia` - a lowercase
    country is a different string to every consumer listed in the module docstring.
    """
    if plain in codes:
        return plain
    lower = plain.lower()
    for name in codes:
        if name.lower() == lower:
            return name
    return None


def _is_canonical(value: str, codes: dict[str, str], normalize: Any) -> bool:
    """Would this value come out of the check clean?

    Yes when either vocabulary knows it. Also the fixed-point test for a proposal: a
    replacement this predicate rejects would be flagged again on the next run.
    """
    if value in BY_HAND or value in REWRITES or _DISAMBIGUATED.match(value):
        return False
    return _flag_code(value, codes) is not None or _iso(value, normalize) is not None


def _verify(codes: dict[str, str], normalize: Any) -> None:
    """Prove every hand-written claim before a single finding leaves the module.

    Raising is the point: if a replacement is no longer safe, the module's advice is
    wrong, and that has to surface as a crash rather than as 8 confident findings.
    """
    for old, new in REWRITES.items():
        if new not in codes:
            raise AssertionError(f"{new!r} is not a key of COUNTRY_CODES; cannot propose it")
        old_iso, new_iso = _iso(old, normalize), _iso(new, normalize)
        if new_iso is None:
            raise AssertionError(
                f"{new!r} does not resolve to an ISO-3166 alpha-2 code via "
                f"normalize_country(); refusing to propose it for {old!r}"
            )
        if old_iso != new_iso:
            raise AssertionError(
                f"{old!r} is {old_iso} but {new!r} is {new_iso}: the project's own "
                "normalizer reads them as different countries"
            )
        if not _is_canonical(new, codes, normalize):
            raise AssertionError(f"{new!r} is not a fixed point of this check")

    for value, (_slug, reason) in BY_HAND.items():
        if not reason:
            raise AssertionError(f"{value!r} has no reason; a REVIEW without one is a hunch")


def _classify(value: str, codes: dict[str, str], normalize: Any) -> _Verdict | None:
    """Classify one distinct country value. None means it needs no finding. Pure."""
    if value in BY_HAND:
        slug, reason = BY_HAND[value]
        return _Verdict(
            Proposal.REVIEW,
            None,
            Severity.MODERATE,
            slug,
            reason,
            (
                Evidence(
                    source=LOOKUP,
                    quote=f"normalize_country({value!r}) -> {normalize(value)!r} "
                    f"(ISO code: {_iso(value, normalize) or 'none'})",
                ),
                Evidence(
                    source=FLAGS, quote=f"getCountryCode({value!r}) -> {_flag_code(value, codes)!r}"
                ),
            ),
        )

    m = _DISAMBIGUATED.match(value)
    if m:
        plain = m.group("plain").strip()
        # The spoken line drops everything before the last comma, so a parenthetical that
        # survives that cut is read aloud verbatim - the model's own SEVERE clause.
        spoken = (
            f"the narrator reads {value.split(',')[-1].strip()!r} aloud with no comma to shorten it"
        )
        name = _display_name(plain, codes)
        if (
            name is not None
            and _iso(name, normalize) is not None
            and _iso(name, normalize) == _iso(value, normalize)
            and _is_canonical(name, codes, normalize)
        ):
            return _Verdict(
                Proposal.SET,
                name,
                Severity.SEVERE,
                "disambiguated",
                f"the parenthetical is a disambiguation hint, and {spoken} - "
                "shorts_tts.py:21-34 appends the last comma part of the country",
                (
                    Evidence(
                        source=LOOKUP,
                        quote=f"NAME_TO_ISO maps both {name!r} and {value!r} to "
                        f"{_iso(value, normalize)}",
                    ),
                    Evidence(
                        source=FLAGS,
                        quote=f"getCountryCode({name!r}) -> {_flag_code(name, codes)}; "
                        f"getCountryCode({value!r}) -> {_flag_code(value, codes)} "
                        "(so the flag already renders; the defect is the label)",
                    ),
                    Evidence(
                        source=f"{PLAN}:395",
                        quote="S7: all 27 are `Georgia (country)` - the narrator reads "
                        "the parenthetical aloud, verbatim",
                    ),
                ),
            )
        # A parenthetical this module cannot resolve is not a licence to strip it.
        return _Verdict(
            Proposal.REVIEW,
            None,
            Severity.MODERATE,
            "unresolved-parenthetical",
            f"{value!r} reads as a disambiguated name, but the bare name {plain!r} is "
            f"either unknown to the vocabularies or resolves to a different country",
            (
                Evidence(
                    source=LOOKUP,
                    quote=f"normalize_country({value!r}) -> {normalize(value)!r}; "
                    f"normalize_country({plain!r}) -> {normalize(plain)!r}",
                ),
                Evidence(
                    source=FLAGS, quote=f"getCountryCode({plain!r}) -> {_flag_code(plain, codes)!r}"
                ),
            ),
        )

    if value in REWRITES:
        new = REWRITES[value]
        return _Verdict(
            Proposal.SET,
            new,
            Severity.MODERATE,
            "compound",
            f"compound country/region label; the country is {new!r}. The region is not "
            "lost - it is in the site's own name and description - and the spoken line "
            "already drops it (shorts_tts.py:21-23)",
            (
                Evidence(
                    source=LOOKUP,
                    quote=f"normalize_country({value!r}) -> {_iso(value, normalize)} "
                    "because the mapper reads the part before the comma",
                ),
                Evidence(
                    source=FLAGS,
                    quote=f"getCountryCode({value!r}) -> {_flag_code(value, codes)} via "
                    f"the last comma part; COUNTRY_CODES carries {new!r} -> "
                    f"{_flag_code(new, codes)}",
                ),
                Evidence(
                    source=f"{PLAN}:680",
                    quote="5. Country values: `Georgia (country)` 27, "
                    "`Chile, Easter Island` 8, `Baltic Sea` 1.",
                ),
            ),
        )

    if _is_canonical(value, codes, normalize):
        return None

    return _Verdict(
        Proposal.REVIEW,
        None,
        Severity.MODERATE,
        "unknown-value",
        f"{value!r} is unknown to both country vocabularies: no COUNTRY_CODES key, so no "
        "flag, and no ISO-3166 alpha-2 code from normalize_country(). A historical entity "
        "(USSR, Yugoslavia, Ottoman Empire, Persia) is not automatically wrong - a site "
        "inside such a polity may properly carry its name - so no present-day replacement "
        "is proposed here",
        (
            Evidence(
                source=LOOKUP,
                quote=f"NAME_TO_ISO has no key {value.lower()!r}; normalize_country() "
                f"returns {normalize(value)!r}",
            ),
            Evidence(source=FLAGS, quote=f"COUNTRY_CODES has no key {value!r}"),
        ),
    )


#: the "excluded from every hub" guard; no site in this snapshot carries it
_EMPTY_NOTE = (
    "no country at all: the row is excluded from every /sites/{country} hub and from the "
    "globe's country filter, and a country cannot be decided from the snapshot - that is "
    "T02's job"
)
_EMPTY_EVIDENCE = (
    Evidence(
        source="api/routes/sites_html.py:39",
        quote="_CURATED_WHERE = \"source_id = 'ancient_nerds' AND country IS NOT NULL "
        "AND country != ''\"",
    ),
)


def run(ctx: Context) -> list[Finding]:
    codes, normalize = _vocabulary()
    _verify(codes, normalize)

    verdicts: dict[str, _Verdict | None] = {}
    findings: list[Finding] = []

    for site in ctx.sites:
        sid = str(site["id"])
        raw = site.get("country")
        value = (raw or "").strip()

        if not value:
            # No instance in this snapshot (98 distinct values, 0 NULL), so this branch is
            # the guard that keeps a later export from turning a hole into a silent pass.
            findings.append(
                Finding(
                    site_id=sid,
                    test_id=f"{TEST_ID}/empty",
                    field="country",
                    severity=Severity.MODERATE,
                    dimension=DIMENSION,
                    current_value=raw,
                    proposal=Proposal.REVIEW,
                    confidence=Confidence.UNVERIFIABLE,
                    note=_EMPTY_NOTE,
                    evidence=list(_EMPTY_EVIDENCE),
                )
            )
            continue

        if value not in verdicts:  # one classification per distinct value
            verdicts[value] = _classify(value, codes, normalize)
        verdict = verdicts[value]
        if verdict is None:
            continue

        findings.append(
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/{verdict.slug}",
                field="country",
                severity=verdict.severity,
                dimension=DIMENSION,
                current_value=value,
                proposal=verdict.proposal,
                proposed_value=verdict.proposed_value,
                confidence=(
                    Confidence.AUTHORITATIVE
                    if verdict.proposal is Proposal.SET
                    else Confidence.UNVERIFIABLE
                ),
                note=verdict.note,
                evidence=list(verdict.evidence),
            )
        )

    return findings
